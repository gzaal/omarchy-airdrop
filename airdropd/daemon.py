from __future__ import annotations

import logging
import threading

from airdropd import identity
from airdropd.config import Config, ensure_download_dir
from airdropd.discovery import Announce, start_responder
from airdropd.receiver import build_info_json, make_server

log = logging.getLogger(__name__)


def _stdin_prompt(sender_alias: str, summary: str) -> bool:
    print(f"Incoming transfer from {sender_alias}: {summary}", flush=True)
    answer = input("Accept? [y/N] ").strip().lower()
    return answer in ("y", "yes")


def make_announce(cfg: Config, fingerprint: str, download: bool = False) -> Announce:
    return Announce(
        alias=cfg.alias,
        fingerprint=fingerprint,
        port=cfg.port,
        protocol=cfg.protocol,
        download=download,
    )


def run_receiver(cfg: Config, cert_dir=None, prompt: bool = False):
    download_dir = ensure_download_dir(cfg)
    if cfg.protocol == "https":
        paths = identity.ensure_cert(cert_dir or _default_cert_dir(), cfg.alias)
        if paths is None:
            cfg.protocol = "http"
        else:
            fingerprint = identity.fingerprint(paths[0])
    else:
        fingerprint = "http-no-tls"
    info_json = build_info_json(cfg, fingerprint)
    prompt_fn = _stdin_prompt if prompt else None
    httpd = make_server(cfg, info_json, cert_dir=cert_dir, prompt=prompt_fn)
    announce = make_announce(cfg, fingerprint)
    stop = threading.Event()
    start_responder(announce, port=cfg.port, stop_event=stop)
    log.info(
        "receiving on %s:%s (%s), saving to %s, policy=%s",
        "0.0.0.0", cfg.port, cfg.protocol, download_dir, cfg.accept_policy,
    )
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        log.info("shutting down")
    finally:
        stop.set()
        httpd.server_close()


def _default_cert_dir():
    from airdropd.config import CONFIG_DIRNAME

    return CONFIG_DIRNAME
