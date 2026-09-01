from __future__ import annotations

import hashlib
import logging
import ssl
import subprocess
from pathlib import Path

log = logging.getLogger(__name__)

CERT_DAYS = 825


def ensure_cert(config_dir: str | Path, alias: str) -> tuple[Path, Path] | None:
    d = Path(config_dir)
    d.mkdir(parents=True, exist_ok=True)
    cert = d / "cert.pem"
    key = d / "key.pem"
    if cert.is_file() and key.is_file():
        return cert, key
    cmd = [
        "openssl", "req", "-x509", "-newkey", "rsa:2048",
        "-keyout", str(key), "-out", str(cert),
        "-days", str(CERT_DAYS), "-nodes",
        "-subj", f"/CN={alias}",
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True, timeout=30)
    except (subprocess.SubprocessError, OSError) as exc:
        log.warning("certificate generation failed, falling back to http: %s", exc)
        return None
    return cert, key


def fingerprint(cert_path: str | Path) -> str:
    pem = Path(cert_path).read_bytes()
    der = ssl.PEM_cert_to_DER_cert(pem.decode("utf-8"))
    return hashlib.sha256(der).hexdigest()


def load_ssl_context(cert_path: str | Path, key_path: str | Path) -> ssl.SSLContext:
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(str(cert_path), str(key_path))
    return ctx


def client_ssl_context() -> ssl.SSLContext:
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx
