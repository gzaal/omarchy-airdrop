import http.client
import json
import socket
import threading

import pytest

from airdropd.config import Config
from airdropd.localsend import (
    DeviceInfo,
    FileRequest,
    build_prepare_upload_request,
    build_prepare_upload_response,
)
from airdropd.receiver import build_info_json, make_server

API = "/api/localsend/v2"


def free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


@pytest.fixture()
def server(tmp_path):
    cfg = Config(
        alias="testbox", download_dir=tmp_path, accept_policy="auto-accept",
        protocol="http", max_file_size=1024 * 1024,
    )
    info = build_info_json(cfg, "testfp")
    httpd = make_server(cfg, info, port=free_port(), protocol="http")
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}", cfg
    httpd.shutdown()
    httpd.server_close()


def request(base, method, path, body=None, headers=None):
    conn = http.client.HTTPConnection("127.0.0.1", int(base.rsplit(":", 1)[1]), timeout=5)
    try:
        conn.request(method, path, body=body, headers=headers or {})
        resp = conn.getresponse()
        data = resp.read()
        return resp.status, data
    finally:
        conn.close()


def prepare(base, sender="laptop", files=None, port_override=None):
    info = DeviceInfo(alias=sender, fingerprint="sfp")
    files = files or [FileRequest(file_id="0", file_name="hello.txt", size=5)]
    payload = build_prepare_upload_request(info, files)
    status, data = request(base, "POST", f"{API}/prepare-upload",
                           json.dumps(payload).encode(),
                           {"Content-Type": "application/json"})
    return status, json.loads(data) if data else {}


def test_info_and_register(server):
    base, cfg = server
    status, data = request(base, "GET", f"{API}/info")
    assert status == 200
    info = json.loads(data)
    assert info["alias"] == "testbox"
    assert info["fingerprint"] == "testfp"
    status, data = request(base, "POST", f"{API}/register", b"{}")
    assert status == 200
    assert json.loads(data)["alias"] == "testbox"


def test_full_upload_flow(server, tmp_path):
    base, cfg = server
    status, resp = prepare(base, files=[
        FileRequest(file_id="0", file_name="one.txt", size=5),
        FileRequest(file_id="1", file_name="two.txt", size=11),
    ])
    assert status == 200
    session_id = resp["sessionId"]
    assert set(resp["files"]) == {"0", "1"}

    status, _ = request(base, "POST",
                        f"{API}/upload?sessionId={session_id}&fileId=0&token={resp['files']['0']}",
                        b"hello")
    assert status == 200
    status, _ = request(base, "POST",
                        f"{API}/upload?sessionId={session_id}&fileId=1&token={resp['files']['1']}",
                        b"hello world")
    assert status == 200
    assert (cfg.download_dir / session_id / "one.txt").read_bytes() == b"hello"
    assert (cfg.download_dir / session_id / "two.txt").read_bytes() == b"hello world"


def test_wrong_token(server):
    base, cfg = server
    status, resp = prepare(base)
    session_id = resp["sessionId"]
    status, _ = request(base, "POST",
                        f"{API}/upload?sessionId={session_id}&fileId=0&token=wrong",
                        b"hello")
    assert status == 401


def test_unknown_session_and_file(server):
    base, cfg = server
    status, _ = request(base, "POST",
                        f"{API}/upload?sessionId=nope&fileId=0&token=x", b"hello")
    assert status == 404
    status, resp = prepare(base)
    session_id = resp["sessionId"]
    status, _ = request(base, "POST",
                        f"{API}/upload?sessionId={session_id}&fileId=99&token={resp['files']['0']}",
                        b"hello")
    assert status == 404


def test_oversize_rejected_at_prepare(server):
    base, cfg = server
    big = FileRequest(file_id="0", file_name="big.bin", size=10 * 1024 * 1024)
    status, _ = prepare(base, files=[big])
    assert status == 413


def test_oversize_rejected_at_upload(server):
    base, cfg = server
    status, resp = prepare(base, files=[FileRequest(file_id="0", file_name="m.txt", size=5)])
    session_id = resp["sessionId"]
    status, _ = request(base, "POST",
                        f"{API}/upload?sessionId={session_id}&fileId=0&token={resp['files']['0']}",
                        b"hello too long")
    assert status == 413
    status, _ = request(base, "POST",
                        f"{API}/upload?sessionId={session_id}&fileId=0&token={resp['files']['0']}",
                        b"hi")
    assert status == 413


def test_traversal_filename_sanitized(server):
    base, cfg = server
    evil = FileRequest(file_id="0", file_name="../../../../etc/cron.d/evil.sh", size=4)
    status, resp = prepare(base, files=[evil])
    assert status == 200
    session_id = resp["sessionId"]
    status, _ = request(base, "POST",
                        f"{API}/upload?sessionId={session_id}&fileId=0&token={resp['files']['0']}",
                        b"true")
    assert status == 200
    saved = list((cfg.download_dir / session_id).iterdir())
    assert len(saved) == 1
    assert saved[0].name == "evil.sh"
    assert saved[0].read_bytes() == b"true"
    top = list(cfg.download_dir.iterdir())
    assert all(d.name == session_id for d in top)


def test_cancel(server):
    base, cfg = server
    status, resp = prepare(base)
    session_id = resp["sessionId"]
    payload = json.dumps({"sessionId": session_id}).encode()
    status, _ = request(base, "POST", f"{API}/cancel", payload,
                        {"Content-Type": "application/json"})
    assert status == 200
    status, _ = request(base, "POST",
                        f"{API}/upload?sessionId={session_id}&fileId=0&token={resp['files']['0']}",
                        b"hello")
    assert status == 404


def test_auto_deny(server):
    base, cfg = server
    cfg.accept_policy = "auto-deny"
    status, _ = prepare(base)
    assert status == 403
    cfg.accept_policy = "auto-accept"


def test_missing_content_length(server):
    # http.client sends "Content-Length: 0" for body-less POST -> size mismatch
    base, cfg = server
    status, resp = prepare(base)
    session_id = resp["sessionId"]
    status, _ = request(base, "POST",
                        f"{API}/upload?sessionId={session_id}&fileId=0&token={resp['files']['0']}",
                        None)
    assert status == 413


def test_zero_byte_upload(server):
    base, cfg = server
    status, resp = prepare(base, files=[FileRequest(file_id="0", file_name="empty.txt", size=0)])
    assert status == 200
    session_id = resp["sessionId"]
    status, _ = request(base, "POST",
                        f"{API}/upload?sessionId={session_id}&fileId=0&token={resp['files']['0']}",
                        b"")
    assert status == 200
    assert (cfg.download_dir / session_id / "empty.txt").read_bytes() == b""


def test_error_response_closes_connection(server):
    base, cfg = server
    status, resp = prepare(base)
    session_id = resp["sessionId"]
    conn = http.client.HTTPConnection("127.0.0.1", int(base.rsplit(":", 1)[1]), timeout=5)
    try:
        conn.request("POST",
                     f"{API}/upload?sessionId={session_id}&fileId=0&token=wrong",
                     b"hello")
        r1 = conn.getresponse()
        assert r1.status == 401
        assert r1.getheader("Connection") == "close"
        r1.read()
    finally:
        conn.close()
    status, _ = request(base, "GET", f"{API}/info")
    assert status == 200


def test_nul_filename_sanitized(server):
    base, cfg = server
    evil = FileRequest(file_id="0", file_name="bad\x00name.txt", size=2)
    status, resp = prepare(base, files=[evil])
    assert status == 200
    session_id = resp["sessionId"]
    status, _ = request(base, "POST",
                        f"{API}/upload?sessionId={session_id}&fileId=0&token={resp['files']['0']}",
                        b"ok")
    assert status == 200
    names = [p.name for p in (cfg.download_dir / session_id).iterdir()]
    assert names == ["badname.txt"]
    assert not any(n.endswith(".part") for n in names)


def test_malformed_content_length(server):
    base, cfg = server
    status, resp = prepare(base)
    session_id = resp["sessionId"]
    conn = http.client.HTTPConnection("127.0.0.1", int(base.rsplit(":", 1)[1]), timeout=5)
    try:
        conn.putrequest("POST",
                        f"{API}/upload?sessionId={session_id}&fileId=0&token={resp['files']['0']}")
        conn.putheader("Content-Length", "abc")
        conn.endheaders()
        r = conn.getresponse()
        assert r.status == 400
        r.read()
    finally:
        conn.close()


def test_session_cap(server):
    base, cfg = server
    seen_503 = False
    for _ in range(20):
        status, resp = prepare(base)
        if status == 503:
            seen_503 = True
            break
        assert status == 200
    assert seen_503


def test_cancel_removes_dir(server):
    base, cfg = server
    status, resp = prepare(base)
    session_id = resp["sessionId"]
    payload = json.dumps({"sessionId": session_id}).encode()
    status, _ = request(base, "POST", f"{API}/cancel", payload,
                        {"Content-Type": "application/json"})
    assert status == 200
    assert not (cfg.download_dir / session_id).exists()
