import http.client
import json
import threading

import pytest

from airdropd import identity, sender
from airdropd.config import Config
from airdropd.discovery import Peer
from airdropd.localsend import (
    API_PREFIX,
    Announce,
    DeviceInfo,
    FileRequest,
    build_prepare_upload_request,
    sanitize_filename,
)
from airdropd.receiver import build_info_json, make_server
from tests.test_receiver_flow import free_port, request


def test_fingerprint_pinning_fails_closed(tmp_path):
    cert_dir = tmp_path / "cfg"
    paths = identity.ensure_cert(cert_dir, "box")
    assert paths is not None
    real_fp = identity.fingerprint(paths[0])
    cfg = Config(alias="box", download_dir=tmp_path / "dl",
                 accept_policy="auto-accept", protocol="https")
    httpd = make_server(cfg, build_info_json(cfg, real_fp),
                        cert_dir=cert_dir, port=free_port(), protocol="https")
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    port = httpd.server_address[1]
    src = tmp_path / "f.txt"
    src.write_bytes(b"data")
    info = DeviceInfo(alias="tx", fingerprint="txfp")

    def peer(fp):
        return Peer(ip="127.0.0.1", alias="box", fingerprint=fp, port=port,
                    protocol="https")

    try:
        with pytest.raises(sender.SendError, match="fingerprint"):
            sender.send_files(peer("x"), info, [src])
        with pytest.raises(sender.SendError, match="fingerprint"):
            sender.send_files(peer("f" * 64), info, [src])
        sender.send_files(peer(real_fp), info, [src])
    finally:
        httpd.shutdown()
        httpd.server_close()


def _start_http(tmp_path, cfg, **kw):
    httpd = make_server(cfg, build_info_json(cfg, "fp"),
                        port=free_port(), protocol="http", **kw)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, f"127.0.0.1:{httpd.server_address[1]}"


def _prepare(base, files):
    payload = build_prepare_upload_request(
        DeviceInfo(alias="s", fingerprint="x"), files)
    status, data = request(base, "POST", f"{API_PREFIX}/prepare-upload",
                           json.dumps(payload).encode(),
                           {"Content-Type": "application/json"})
    return status, data


def test_same_name_files_do_not_collide(tmp_path):
    cfg = Config(alias="box", download_dir=tmp_path, accept_policy="auto-accept",
                 protocol="http", max_file_size=1024 * 1024)
    httpd, base = _start_http(tmp_path, cfg)
    files = [FileRequest(file_id="0", file_name="photo.jpg", size=2),
             FileRequest(file_id="1", file_name="photo.jpg", size=3)]
    status, data = _prepare(base, files)
    assert status == 200
    resp = json.loads(data)
    session_id = resp["sessionId"]
    for file_id, token in resp["files"].items():
        s, _ = request(base, "POST",
                       f"{API_PREFIX}/upload?sessionId={session_id}&fileId={file_id}&token={token}",
                       b"ab" if file_id == "0" else b"abc")
        assert s == 200
    httpd.shutdown()
    httpd.server_close()
    names = sorted(p.name for p in (cfg.download_dir / session_id).iterdir())
    assert names == ["photo (1).jpg", "photo.jpg"]
    contents = {p.name: p.read_bytes()
                for p in (cfg.download_dir / session_id).iterdir()}
    assert contents["photo.jpg"] == b"ab"
    assert contents["photo (1).jpg"] == b"abc"


def test_alias_sanitized_in_announce():
    a = Announce.from_json({"alias": "evil\npeer\x00name", "fingerprint": "fp",
                            "port": 53317, "protocol": "http"})
    assert a is not None
    assert "\n" not in a.alias
    assert "\x00" not in a.alias
    assert len(a.alias) <= 64


def test_prompt_summary_is_sanitized(tmp_path):
    captured = {}

    def prompt(alias, summary):
        captured["alias"] = alias
        captured["summary"] = summary
        return True

    cfg = Config(alias="box", download_dir=tmp_path, accept_policy="ask",
                 protocol="http", max_file_size=1024 * 1024)
    evil = "innocent.pdf\nAccept: holiday.jpg"
    httpd, base = _start_http(tmp_path, cfg, prompt=prompt)
    try:
        status, data = _prepare(base, [
            FileRequest(file_id="0", file_name=evil, size=1)])
        assert status == 200
    finally:
        httpd.shutdown()
        httpd.server_close()
    assert "\n" not in captured["summary"]
    assert captured["summary"] == sanitize_filename(evil)


def test_negative_size_rejected(tmp_path):
    cfg = Config(alias="box", download_dir=tmp_path, accept_policy="auto-accept",
                 protocol="http", max_file_size=1024 * 1024)
    httpd, base = _start_http(tmp_path, cfg)
    try:
        status, _ = _prepare(base, [FileRequest(file_id="0", file_name="neg.txt",
                                                size=-5)])
        assert status == 400
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_too_many_files_rejected(tmp_path):
    cfg = Config(alias="box", download_dir=tmp_path, accept_policy="auto-accept",
                 protocol="http", max_file_size=1024 * 1024)
    httpd, base = _start_http(tmp_path, cfg)
    from airdropd.receiver import MAX_FILES_PER_SESSION

    files = [FileRequest(file_id=str(i), file_name=f"f{i}.txt", size=1)
             for i in range(MAX_FILES_PER_SESSION + 1)]
    try:
        status, _ = _prepare(base, files)
        assert status == 400
    finally:
        httpd.shutdown()
        httpd.server_close()
