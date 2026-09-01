from __future__ import annotations

import json
import logging
import socket
import struct
import time
from dataclasses import dataclass

from airdropd.localsend import Announce, BROADCAST_ADDR, MULTICAST_GROUP

log = logging.getLogger(__name__)
DISCOVERY_PORT = 53317
DISCOVERY_TIMEOUT = 2.0


@dataclass(frozen=True)
class Peer:
    ip: str
    alias: str
    fingerprint: str
    port: int
    protocol: str
    device_model: str = ""

    @property
    def base_url(self) -> str:
        return f"{self.protocol}://{self.ip}:{self.port}"


def _announce_bytes(announce: Announce) -> bytes:
    return json.dumps(announce.to_json()).encode("utf-8")


def _open_listener(port: int) -> socket.socket:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(("", port))
    mreq = struct.pack("4s4s", socket.inet_aton(MULTICAST_GROUP), socket.inet_aton("0.0.0.0"))
    s.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
    s.settimeout(0.5)
    return s


def start_responder(announce: Announce, port: int = DISCOVERY_PORT, stop_event=None):
    import threading

    payload = _announce_bytes(announce)
    own_fp = announce.fingerprint
    stop_event = stop_event or threading.Event()

    def loop():
        try:
            s = _open_listener(port)
        except OSError as exc:
            log.warning("discovery responder unavailable (port %s): %s", port, exc)
            return
        log.info("discovery responder listening on udp/%s", port)
        while not stop_event.is_set():
            try:
                data, addr = s.recvfrom(65535)
            except socket.timeout:
                continue
            except OSError:
                break
            msg = Announce.from_json(_safe_json(data))
            if msg is None or msg.fingerprint == own_fp:
                continue
            try:
                s.sendto(payload, addr)
            except OSError as exc:
                log.debug("announce reply to %s failed: %s", addr, exc)
        s.close()

    t = threading.Thread(target=loop, name="airdropd-discovery", daemon=True)
    t.start()
    return t, stop_event


def discover(announce: Announce, timeout: float = DISCOVERY_TIMEOUT,
             port: int = DISCOVERY_PORT) -> list[Peer]:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    try:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(("", 0))
        payload = _announce_bytes(announce)
        for target in (BROADCAST_ADDR, MULTICAST_GROUP):
            try:
                s.sendto(payload, (target, port))
            except OSError as exc:
                log.debug("announce to %s failed: %s", target, exc)
        peers: dict[str, Peer] = {}
        deadline = time.monotonic() + timeout
        s.settimeout(0.25)
        while time.monotonic() < deadline:
            try:
                data, addr = s.recvfrom(65535)
            except socket.timeout:
                continue
            except OSError:
                break
            msg = Announce.from_json(_safe_json(data))
            if msg is None or msg.fingerprint == announce.fingerprint:
                continue
            peers.setdefault(msg.fingerprint, Peer(
                ip=addr[0], alias=msg.alias, fingerprint=msg.fingerprint,
                port=msg.port, protocol=msg.protocol, device_model=msg.device_model,
            ))
        return list(peers.values())
    finally:
        s.close()


def _safe_json(data: bytes) -> dict | None:
    try:
        obj = json.loads(data.decode("utf-8"))
        return obj if isinstance(obj, dict) else None
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
