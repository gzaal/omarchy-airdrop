from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field

DEFAULT_PORT = 53317
MULTICAST_GROUP = "224.0.0.167"
BROADCAST_ADDR = "255.255.255.255"
API_PREFIX = "/api/localsend/v2"
DEVICE_TYPE = "desktop"
DEVICE_MODEL = "linux"
DEFAULT_MAX_FILE_SIZE = 10 * 1024 * 1024 * 1024
MAX_JSON_BODY = 1024 * 1024
UPLOAD_CHUNK = 1024 * 1024


@dataclass(frozen=True)
class DeviceInfo:
    alias: str
    fingerprint: str
    device_model: str = DEVICE_MODEL
    device_type: str = DEVICE_TYPE

    def to_json(self) -> dict:
        return {
            "alias": self.alias,
            "deviceModel": self.device_model,
            "deviceType": self.device_type,
            "fingerprint": self.fingerprint,
        }


@dataclass(frozen=True)
class Announce(DeviceInfo):
    port: int = DEFAULT_PORT
    protocol: str = "https"
    download: bool = False

    def to_json(self) -> dict:
        return {
            **super().to_json(),
            "port": self.port,
            "protocol": self.protocol,
            "download": self.download,
        }

    @classmethod
    def from_json(cls, data: dict) -> Announce | None:
        try:
            port = int(data["port"])
            protocol = str(data["protocol"])
            if not 0 < port <= 65535 or protocol not in ("http", "https"):
                return None
            return cls(
                alias=sanitize_label(str(data["alias"])),
                fingerprint=sanitize_label(str(data["fingerprint"]), 128),
                device_model=sanitize_label(str(data.get("deviceModel") or ""), 32),
                device_type=sanitize_label(str(data.get("deviceType") or ""), 32),
                port=port,
                protocol=protocol,
                download=bool(data.get("download", False)),
            )
        except (KeyError, TypeError, ValueError):
            return None


@dataclass(frozen=True)
class FileRequest:
    file_id: str
    file_name: str
    size: int
    file_type: str = "application/octet-stream"

    def to_json(self) -> dict:
        return {
            "id": self.file_id,
            "fileName": self.file_name,
            "size": self.size,
            "fileType": self.file_type,
        }


@dataclass(frozen=True)
class PrepareUploadRequest:
    sender: DeviceInfo
    files: tuple[FileRequest, ...]

    @classmethod
    def from_json(cls, data: dict) -> PrepareUploadRequest | None:
        try:
            info = data["info"]
            sender = DeviceInfo(
                alias=sanitize_label(str(info["alias"])),
                fingerprint=sanitize_label(str(info.get("fingerprint", "")), 128),
                device_model=sanitize_label(str(info.get("deviceModel") or ""), 32),
                device_type=sanitize_label(str(info.get("deviceType") or ""), 32),
            )
            files = []
            for file_id, meta in data["files"].items():
                files.append(
                    FileRequest(
                        file_id=str(file_id),
                        file_name=str(meta["fileName"]),
                        size=int(meta["size"]),
                        file_type=str(meta.get("fileType") or "application/octet-stream"),
                    )
                )
            return cls(sender=sender, files=tuple(files))
        except (KeyError, TypeError, ValueError, AttributeError):
            return None


def build_prepare_upload_request(sender: DeviceInfo, files: list[FileRequest]) -> dict:
    return {
        "info": sender.to_json(),
        "files": {f.file_id: f.to_json() for f in files},
    }


def build_prepare_upload_response(session_id: str, tokens: dict[str, str]) -> dict:
    return {"sessionId": session_id, "files": dict(tokens)}


def new_session_id() -> str:
    return uuid.uuid4().hex


_WHITESPACE_RE = re.compile(r"\s+")


def sanitize_label(text: str, limit: int = 64) -> str:
    """Make untrusted display text (aliases, names) safe for menus/argv."""
    cleaned = re.sub(r"[\x00-\x1f\x7f]", "", text)
    cleaned = _WHITESPACE_RE.sub(" ", cleaned).strip()
    return cleaned[:limit]


def sanitize_filename(name: str) -> str:
    name = name.replace("\\", "/")
    parts = [p for p in name.split("/") if p not in ("", ".")]
    candidate = parts[-1] if parts else ""
    candidate = candidate.lstrip(".")
    candidate = re.sub(r"[\x00-\x1f\x7f]", "", candidate)
    candidate = _WHITESPACE_RE.sub(" ", candidate).strip()
    candidate = _truncate_with_extension(candidate)
    return candidate or "unnamed"


def _truncate_with_extension(candidate: str, limit: int = 200) -> str:
    if len(candidate.encode("utf-8", "ignore")) <= limit:
        return candidate
    stem, dot, ext = candidate.rpartition(".")
    if dot and ext and len(ext.encode()) < limit:
        while len((stem + dot + ext).encode("utf-8", "ignore")) > limit and stem:
            stem = stem[:-1]
        return (stem + dot + ext) if stem else _truncate_with_extension(ext, limit)
    out = candidate
    while len(out.encode("utf-8", "ignore")) > limit:
        out = out[:-1]
    return out


def resolve_collision(directory: str, name: str) -> str:
    import os

    candidate = name
    stem, ext = os.path.splitext(name)
    n = 1
    while os.path.lexists(os.path.join(directory, candidate)):
        candidate = f"{stem} ({n}){ext}"
        n += 1
    return candidate
