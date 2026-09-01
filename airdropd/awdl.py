from __future__ import annotations

import json
import logging
import re
import shutil
import signal
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)

DEFAULT_AWDL_IFACE = "awdl0"
OPENDROP_REPORT = Path.home() / ".opendrop" / "discover.last.json"


class AwdlError(Exception):
    pass


def opendrop_available() -> bool:
    return shutil.which("opendrop") is not None


def find_awdl_iface(preferred: str = DEFAULT_AWDL_IFACE, base: str = "/sys/class/net") -> str | None:
    net = Path(base)
    if not net.is_dir():
        return None
    ifaces = sorted(p.name for p in net.iterdir())
    if preferred in ifaces:
        return preferred
    for name in ifaces:
        if name.startswith("awdl"):
            return name
    return None


def iface_ipv6(iface: str) -> str | None:
    try:
        out = subprocess.run(
            ["ip", "-6", "-brief", "addr", "show", "dev", iface],
            capture_output=True, text=True, timeout=5, check=True,
        ).stdout
    except (subprocess.SubprocessError, OSError):
        return None
    m = re.search(r"inet6\s+(fe80[0-9a-f:]*)", out)
    return m.group(1) if m else None


def owl_running(iface: str = DEFAULT_AWDL_IFACE) -> bool:
    try:
        out = subprocess.run(
            ["pgrep", "-x", "owl"],
            capture_output=True, text=True, timeout=5,
        ).stdout
    except (subprocess.SubprocessError, OSError):
        return False
    for pid in out.split():
        try:
            cmdline = Path(f"/proc/{pid}/cmdline").read_bytes().decode("utf-8").split("\0")
        except OSError:
            continue
        if iface in cmdline:
            return True
    return False


@dataclass(frozen=True)
class NativePeer:
    name: str | None
    address: str
    peer_id: str
    discoverable: bool = True


def discover_peers(iface: str = DEFAULT_AWDL_IFACE, timeout: float = 5.0,
                   report: Path = OPENDROP_REPORT) -> list[NativePeer]:
    if not opendrop_available():
        raise AwdlError("opendrop is not installed")
    start = time.time()
    try:
        report.unlink()
    except FileNotFoundError:
        pass
    except OSError as exc:
        raise AwdlError(f"cannot reset discovery report: {exc}") from exc
    try:
        proc = subprocess.Popen(
            ["opendrop", "find", "-i", iface],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
    except OSError as exc:
        raise AwdlError(f"failed to run opendrop: {exc}") from exc
    try:
        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        # upstream opendrop only writes its report in a finally block reached
        # via KeyboardInterrupt, so SIGINT (not SIGTERM/SIGKILL) is required
        proc.send_signal(signal.SIGINT)
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
    if not report.is_file() or report.stat().st_mtime < start - 1:
        return []
    try:
        data = json.loads(report.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise AwdlError(f"invalid discovery report: {exc}") from exc
    peers: list[NativePeer] = []
    if not isinstance(data, list):
        return []
    for entry in data:
        if not isinstance(entry, dict) or "address" not in entry:
            continue
        if not entry.get("discoverable"):
            continue
        peers.append(NativePeer(
            name=entry.get("name"),
            address=str(entry["address"]),
            peer_id=str(entry.get("id") or ""),
        ))
    return peers


def send_native(file: Path, receiver: str, iface: str = DEFAULT_AWDL_IFACE,
                name: str | None = None, timeout: float | None = None) -> None:
    if not opendrop_available():
        raise AwdlError("opendrop is not installed")
    cmd = ["opendrop", "send", "-f", str(file), "-r", receiver, "-i", iface]
    if name:
        cmd += ["-n", name]
    try:
        proc = subprocess.run(cmd, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        raise AwdlError("airdrop send timed out") from exc
    except OSError as exc:
        raise AwdlError(f"failed to run opendrop: {exc}") from exc
    if proc.returncode != 0:
        raise AwdlError(f"opendrop send failed with exit code {proc.returncode}")


def receive_native(iface: str = DEFAULT_AWDL_IFACE, name: str | None = None) -> None:
    if not opendrop_available():
        raise AwdlError("opendrop is not installed")
    cmd = ["opendrop", "receive", "-i", iface]
    if name:
        cmd += ["-n", name]
    try:
        proc = subprocess.run(cmd)
    except OSError as exc:
        raise AwdlError(f"failed to run opendrop: {exc}") from exc
    if proc.returncode != 0:
        raise AwdlError(f"opendrop receive failed with exit code {proc.returncode}")


def native_status(iface: str | None = None) -> dict:
    iface = iface or find_awdl_iface()
    return {
        "interface": iface,
        "ipv6": iface_ipv6(iface) if iface else None,
        "owl_running": owl_running(iface) if iface else False,
        "opendrop": opendrop_available(),
    }
