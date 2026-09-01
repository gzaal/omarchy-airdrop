from __future__ import annotations

import http.client
import json
import logging
from pathlib import Path

from airdropd import identity
from airdropd.discovery import Peer
from airdropd.localsend import (
    API_PREFIX,
    DeviceInfo,
    FileRequest,
    UPLOAD_CHUNK,
    build_prepare_upload_request,
)

log = logging.getLogger(__name__)


class SendError(Exception):
    pass


def _connection(peer: Peer, timeout: float = 10.0) -> http.client.HTTPConnection:
    if peer.protocol == "https":
        return http.client.HTTPSConnection(
            peer.ip, peer.port, context=identity.client_ssl_context(), timeout=timeout
        )
    return http.client.HTTPConnection(peer.ip, peer.port, timeout=timeout)


def _post_json(conn: http.client.HTTPConnection, path: str, payload: dict) -> dict:
    body = json.dumps(payload).encode("utf-8")
    conn.request("POST", path, body=body, headers={"Content-Type": "application/json"})
    resp = conn.getresponse()
    data = resp.read()
    if resp.status != 200:
        raise SendError(f"{path} -> HTTP {resp.status}: {_error_text(data)}")
    try:
        return json.loads(data.decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as exc:
        raise SendError(f"{path}: invalid response: {exc}") from exc


def _error_text(data: bytes) -> str:
    try:
        parsed = json.loads(data.decode("utf-8"))
        return str(parsed.get("error") or parsed)
    except (ValueError, UnicodeDecodeError):
        return data.decode("utf-8", "replace")[:200]


def _noop_log(name: str, pct: int) -> None:
    pass


def prepare_upload(peer: Peer, sender: DeviceInfo,
                   files: list[FileRequest]) -> tuple[str, dict[str, str]]:
    conn = _connection(peer)
    try:
        resp = _post_json(conn, f"{API_PREFIX}/prepare-upload",
                          build_prepare_upload_request(sender, files))
    finally:
        conn.close()
    session_id = str(resp.get("sessionId") or "")
    tokens = resp.get("files")
    if not session_id or not isinstance(tokens, dict):
        raise SendError("prepare-upload: malformed response")
    return session_id, tokens


def upload_file(peer: Peer, session_id: str, file_id: str, token: str,
                path: Path, size: int, progress_log=_noop_log) -> None:
    conn = _connection(peer, timeout=30.0)
    try:
        url = f"{API_PREFIX}/upload?sessionId={session_id}&fileId={file_id}&token={token}"
        sent = 0
        last_pct = -10

        def body_iter():
            nonlocal sent, last_pct
            with path.open("rb") as f:
                while True:
                    chunk = f.read(UPLOAD_CHUNK)
                    if not chunk:
                        break
                    sent += len(chunk)
                    pct = int(sent * 100 / size) if size else 100
                    if pct >= last_pct + 10 or sent == size:
                        last_pct = pct
                        progress_log(path.name, pct)
                    yield chunk

        conn.request(
            "POST", url, body=body_iter(),
            headers={"Content-Type": "application/octet-stream", "Content-Length": str(size)},
        )
        resp = conn.getresponse()
        data = resp.read()
        if resp.status != 200:
            raise SendError(f"upload {path.name} -> HTTP {resp.status}: {_error_text(data)}")
    finally:
        conn.close()


def send_files(peer: Peer, sender: DeviceInfo, paths: list[Path],
               progress_log=None) -> list[Path]:
    files = []
    for i, p in enumerate(paths):
        files.append(FileRequest(
            file_id=str(i), file_name=p.name, size=p.stat().st_size
        ))
    session_id, tokens = prepare_upload(peer, sender, files)
    delivered: list[Path] = []
    for f, p in zip(files, paths):
        token = tokens.get(f.file_id)
        if token is None:
            raise SendError(f"receiver did not provide a token for {p.name}")
        upload_file(peer, session_id, f.file_id, token, p, f.size,
                    progress_log=progress_log or _noop_log)
        delivered.append(p)
    return delivered
