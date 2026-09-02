from __future__ import annotations

import json
import logging
import os
import secrets
import shutil
import tempfile
import threading
import time
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from airdropd import identity
from airdropd.config import Config
from airdropd.localsend import (
    API_PREFIX,
    MAX_JSON_BODY,
    PrepareUploadRequest,
    UPLOAD_CHUNK,
    build_prepare_upload_response,
    new_session_id,
    resolve_collision,
    sanitize_filename,
)

log = logging.getLogger(__name__)


class Reject(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


@dataclass
class PendingFile:
    token: str
    name: str
    size: int
    target: Path
    received: int = 0


@dataclass
class Session:
    sender_alias: str
    directory: Path
    created: float = field(default_factory=time.monotonic)
    files: dict[str, PendingFile] = field(default_factory=dict)


MAX_OPEN_SESSIONS = 16
SESSION_TTL = 30 * 60


class ReceiverState:
    def __init__(self, cfg: Config, info_json: dict, prompt=None,
                 on_file_received=None):
        self.cfg = cfg
        self.info_json = info_json
        self.prompt = prompt
        self.on_file_received = on_file_received
        self.sessions: dict[str, Session] = {}
        self.lock = threading.Lock()

    def _gc_locked(self, now: float) -> None:
        stale = [sid for sid, s in self.sessions.items() if now - s.created > SESSION_TTL]
        for sid in stale:
            session = self.sessions.pop(sid)
            shutil.rmtree(session.directory, ignore_errors=True)

    def open_session(self, req: PrepareUploadRequest) -> tuple[str, dict[str, str]]:
        if self.cfg.accept_policy == "auto-deny":
            raise Reject(403, "receiver is not accepting files")
        for f in req.files:
            if f.size > self.cfg.max_file_size:
                raise Reject(413, f"file {f.file_name} exceeds size limit")
        summary = ", ".join(f"{f.file_name} ({f.size} bytes)" for f in req.files)
        if self.cfg.accept_policy == "ask":
            if self.prompt is None or not self.prompt(req.sender.alias, summary):
                log.info("rejected transfer from %s", req.sender.alias)
                raise Reject(403, "transfer rejected by user")
        with self.lock:
            self._gc_locked(time.monotonic())
            if len(self.sessions) >= MAX_OPEN_SESSIONS:
                raise Reject(503, "too many pending transfers")
        session_dir = Path(self.cfg.download_dir).expanduser() / new_session_id()
        session_dir.mkdir(parents=True, exist_ok=True)
        tokens: dict[str, str] = {}
        session = Session(sender_alias=req.sender.alias, directory=session_dir)
        for f in req.files:
            safe = sanitize_filename(f.file_name)
            target = session_dir / resolve_collision(session_dir, safe)
            token = secrets.token_urlsafe(32)
            session.files[f.file_id] = PendingFile(
                token=token, name=safe, size=f.size, target=target
            )
            tokens[f.file_id] = token
        with self.lock:
            self.sessions[session_dir.name] = session
        return session_dir.name, tokens

    def upload(self, session_id: str, file_id: str, token: str, rfile, content_length: int):
        with self.lock:
            session = self.sessions.get(session_id)
            if session is None:
                raise Reject(404, "unknown session")
            entry = session.files.get(file_id)
            if entry is None:
                raise Reject(404, "unknown file")
        if token != entry.token:
            raise Reject(401, "invalid token")
        if content_length != entry.size or entry.size > self.cfg.max_file_size:
            raise Reject(413, "size mismatch")
        tmp = tempfile.NamedTemporaryFile(dir=session.directory, delete=False, suffix=".part")
        received = 0
        try:
            while received < entry.size:
                chunk = rfile.read(min(UPLOAD_CHUNK, entry.size - received))
                if not chunk:
                    raise Reject(413, "truncated upload")
                tmp.write(chunk)
                received += len(chunk)
            tmp.flush()
            os.replace(tmp.name, entry.target)
        except Reject:
            tmp.close()
            os.unlink(tmp.name)
            raise
        except (OSError, ValueError) as exc:
            tmp.close()
            os.unlink(tmp.name)
            raise Reject(500, f"write failed: {exc}") from exc
        finally:
            tmp.close()
        log.info("received %s from %s", entry.name, session.sender_alias)
        if self.on_file_received is not None:
            try:
                self.on_file_received(entry.name, session.sender_alias, entry.target)
            except Exception:
                log.debug("on_file_received hook failed", exc_info=True)

    def cancel(self, session_id: str) -> None:
        with self.lock:
            session = self.sessions.pop(session_id, None)
        if session is not None:
            shutil.rmtree(session.directory, ignore_errors=True)


def build_info_json(cfg: Config, fingerprint: str) -> dict:
    return {
        "alias": cfg.alias,
        "deviceModel": "linux",
        "deviceType": "desktop",
        "fingerprint": fingerprint,
        "download": False,
    }


class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    timeout = 30
    server_version = "airdropd"

    @property
    def state(self) -> ReceiverState:
        return self.server.state  # type: ignore[attr-defined]

    def log_message(self, fmt, *args):
        log.debug("%s %s", self.address_string(), fmt % args)

    def _send_json(self, status: int, payload: dict | None = None, close: bool = False):
        body = json.dumps(payload or {"ok": True}).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        if close:
            self.send_header("Connection", "close")
            self.close_connection = True
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> dict:
        raw = self.headers.get("Content-Length")
        if raw is None:
            raise Reject(411, "content-length required")
        try:
            length = int(raw)
        except ValueError as exc:
            raise Reject(400, "malformed content-length") from exc
        if length <= 0 or length > MAX_JSON_BODY:
            raise Reject(400, "invalid body size")
        try:
            data = json.loads(self.rfile.read(length).decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as exc:
            raise Reject(400, f"invalid json: {exc}") from exc
        if not isinstance(data, dict):
            raise Reject(400, "json object expected")
        return data

    def do_GET(self):
        path = urlparse(self.path).path
        if path == f"{API_PREFIX}/info":
            self._send_json(200, self.state.info_json)
        else:
            self._send_json(404, {"error": "not found"})

    def do_POST(self):
        url = urlparse(self.path)
        path = url.path
        try:
            if path == f"{API_PREFIX}/register":
                self._read_json()
                self._send_json(200, self.state.info_json)
            elif path == f"{API_PREFIX}/prepare-upload":
                req = PrepareUploadRequest.from_json(self._read_json())
                if req is None:
                    raise Reject(400, "malformed prepare-upload request")
                if not req.files:
                    raise Reject(400, "no files requested")
                session_id, tokens = self.state.open_session(req)
                self._send_json(200, build_prepare_upload_response(session_id, tokens))
            elif path == f"{API_PREFIX}/upload":
                qs = parse_qs(url.query)
                session_id = (qs.get("sessionId") or [""])[0]
                file_id = (qs.get("fileId") or [""])[0]
                token = (qs.get("token") or [""])[0]
                raw_len = self.headers.get("Content-Length")
                if raw_len is None:
                    raise Reject(411, "content-length required")
                try:
                    length = int(raw_len)
                except ValueError as exc:
                    raise Reject(400, "malformed content-length") from exc
                self.state.upload(session_id, file_id, token, self.rfile, length)
                self._send_json(200)
            elif path == f"{API_PREFIX}/cancel":
                data = self._read_json()
                self.state.cancel(str(data.get("sessionId") or ""))
                self._send_json(200)
            else:
                self._send_json(404, {"error": "not found"})
        except Reject as exc:
            self._send_json(exc.status, {"error": exc.message}, close=True)


def make_server(cfg: Config, info_json: dict, cert_dir: str | Path | None = None,
                port: int | None = None, prompt=None, protocol: str | None = None,
                on_file_received=None):
    proto = protocol or cfg.protocol
    bind_port = port if port is not None else cfg.port
    state = ReceiverState(cfg, info_json, prompt=prompt,
                          on_file_received=on_file_received)
    httpd = ThreadingHTTPServer(("0.0.0.0", bind_port), _Handler)
    httpd.state = state  # type: ignore[attr-defined]
    if proto == "https":
        if cert_dir is None:
            from airdropd.config import CONFIG_DIRNAME
            cert_dir = CONFIG_DIRNAME
        paths = identity.ensure_cert(cert_dir, cfg.alias)
        if paths is None:
            log.warning("starting in http mode")
        else:
            httpd.socket = identity.load_ssl_context(*paths).wrap_socket(httpd.socket, server_side=True)
    return httpd
