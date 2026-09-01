from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

from airdropd.localsend import DEFAULT_MAX_FILE_SIZE, DEFAULT_PORT

CONFIG_DIRNAME = Path.home() / ".config" / "omarchy-airdrop"
DEFAULT_DOWNLOAD_DIR = Path.home() / "Drop" / "AirDrop"

ACCEPT_POLICIES = ("ask", "auto-accept", "auto-deny")


@dataclass
class Config:
    alias: str = field(default_factory=lambda: os.uname().nodename)
    download_dir: Path = DEFAULT_DOWNLOAD_DIR
    port: int = DEFAULT_PORT
    protocol: str = "https"
    accept_policy: str = "ask"
    max_file_size: int = DEFAULT_MAX_FILE_SIZE

    def to_json(self) -> dict:
        data = asdict(self)
        data["download_dir"] = str(self.download_dir)
        return data

    @classmethod
    def from_json(cls, data: dict) -> Config:
        known = {f.name for f in fields(cls)}
        kwargs = {k: v for k, v in data.items() if k in known}
        if "download_dir" in kwargs:
            kwargs["download_dir"] = Path(kwargs["download_dir"]).expanduser()
        for int_key in ("port", "max_file_size"):
            if int_key in kwargs:
                try:
                    kwargs[int_key] = int(kwargs[int_key])
                except (TypeError, ValueError) as exc:
                    raise ValueError(f"invalid {int_key}: {kwargs[int_key]!r}") from exc
        cfg = cls(**kwargs)
        if cfg.accept_policy not in ACCEPT_POLICIES:
            raise ValueError(f"invalid accept_policy: {cfg.accept_policy}")
        if cfg.protocol not in ("http", "https"):
            raise ValueError(f"invalid protocol: {cfg.protocol}")
        if not 0 < cfg.port <= 65535:
            raise ValueError(f"invalid port: {cfg.port}")
        if cfg.max_file_size < 0:
            raise ValueError(f"invalid max_file_size: {cfg.max_file_size}")
        return cfg


def config_dir(override: str | Path | None = None) -> Path:
    d = Path(override).expanduser() if override else CONFIG_DIRNAME
    return d


def config_path(override: str | Path | None = None) -> Path:
    return config_dir(override) / "config.json"


def load(override: str | Path | None = None) -> Config:
    path = config_path(override)
    if not path.is_file():
        return Config()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return Config.from_json(data)
    except (json.JSONDecodeError, ValueError, TypeError) as exc:
        raise ValueError(f"invalid config {path}: {exc}") from exc


def save(cfg: Config, override: str | Path | None = None) -> Path:
    d = config_dir(override)
    d.mkdir(parents=True, exist_ok=True)
    path = config_path(override)
    path.write_text(json.dumps(cfg.to_json(), indent=2) + "\n", encoding="utf-8")
    return path


def ensure_download_dir(cfg: Config) -> Path:
    cfg.download_dir.expanduser().mkdir(parents=True, exist_ok=True)
    return cfg.download_dir.expanduser()
