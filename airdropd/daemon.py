from __future__ import annotations

import logging
import sys
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


def _default_on_file_received(name: str, sender_alias: str, path) -> None:
    try:
        from airdropd import desktop

        desktop.notify("File received", f"{name} from {sender_alias}")
    except Exception:
        log.debug("notify failed", exc_info=True)


def make_announce(cfg: Config, fingerprint: str, download: bool = False) -> Announce:
    return Announce(
        alias=cfg.alias,
        fingerprint=fingerprint,
        port=cfg.port,
        protocol=cfg.protocol,
        download=download,
    )


def resolve_prompt(prompt: bool | None, prompt_ui: str, isatty: bool):
    """Decide the accept-prompt callback. Returns None (deny-all) or callable."""
    from airdropd import desktop

    want_prompt = bool(prompt) or prompt_ui == "stdin"
    if not want_prompt:
        return None
    backend = desktop.make_prompt(prompt_ui)
    if backend is not None:
        return backend
    if isatty:
        if prompt_ui != "stdin":
            log.warning("no menu backend available; falling back to stdin prompts")
        return _stdin_prompt
    log.warning("no prompt backend available in this environment; "
                "incoming transfers will be denied")
    return None


def run_receiver(cfg: Config, cert_dir=None, prompt: bool | None = None,
                 prompt_ui: str = "auto", notifications: bool = True):
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
    prompt_fn = resolve_prompt(prompt, prompt_ui, sys.stdin.isatty())
    on_file = _default_on_file_received if notifications else None
    httpd = make_server(cfg, info_json, cert_dir=cert_dir, prompt=prompt_fn,
                        on_file_received=on_file)
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
