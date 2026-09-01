import json
from pathlib import Path

import pytest

from airdropd import awdl
from airdropd.awdl import NativePeer, discover_peers, find_awdl_iface


def test_find_awdl_iface_prefers_awdl0(tmp_path):
    for name in ("wlp0s20f3", "awdl0", "eth0"):
        (tmp_path / name).mkdir()
    assert find_awdl_iface(base=str(tmp_path)) == "awdl0"


def test_find_awdl_iface_falls_back_to_prefix(tmp_path):
    (tmp_path / "wlan0").mkdir()
    (tmp_path / "awdl1234").mkdir()
    assert find_awdl_iface(base=str(tmp_path)) == "awdl1234"


def test_find_awdl_iface_none(tmp_path):
    (tmp_path / "wlan0").mkdir()
    assert find_awdl_iface(base=str(tmp_path)) is None


def test_discover_peers_parses_report(tmp_path, monkeypatch):
    monkeypatch.setattr(awdl, "opendrop_available", lambda: True)
    entries = [
        {"name": "iPhone", "address": "fe80::1", "port": 8770, "id": "abc",
         "flags": 8, "discoverable": True},
        {"name": None, "address": "fe80::2", "port": 8770, "id": "def",
         "flags": 8, "discoverable": False},
    ]
    report = tmp_path / "discover.last.json"

    def fake_popen(*a, **k):
        return _FakeProc(on_exit=lambda: report.write_text(json.dumps(entries)))

    monkeypatch.setattr(awdl.subprocess, "Popen", fake_popen)
    report.write_text(json.dumps([
        {"name": "iPhone", "address": "fe80::1", "port": 8770, "id": "abc",
         "flags": 8, "discoverable": True},
        {"name": None, "address": "fe80::2", "port": 8770, "id": "def",
         "flags": 8, "discoverable": False},
    ]))
    peers = discover_peers(report=report, timeout=0.01)
    assert len(peers) == 1
    assert isinstance(peers[0], NativePeer)
    assert peers[0].name == "iPhone"
    assert peers[0].address == "fe80::1"


def test_discover_peers_missing_report(tmp_path, monkeypatch):
    monkeypatch.setattr(awdl, "opendrop_available", lambda: True)
    monkeypatch.setattr(awdl.subprocess, "Popen", lambda *a, **k: _FakeProc())
    assert discover_peers(report=tmp_path / "nope.json", timeout=0.01) == []


def test_discover_peers_invalid_report(tmp_path, monkeypatch):
    monkeypatch.setattr(awdl, "opendrop_available", lambda: True)
    report = tmp_path / "discover.last.json"

    def fake_popen(*a, **k):
        return _FakeProc(on_exit=lambda: report.write_text("not json {"))

    monkeypatch.setattr(awdl.subprocess, "Popen", fake_popen)
    with pytest.raises(awdl.AwdlError):
        discover_peers(report=report, timeout=0.01)


def test_discover_requires_opendrop(tmp_path, monkeypatch):
    monkeypatch.setattr(awdl, "opendrop_available", lambda: False)
    with pytest.raises(awdl.AwdlError):
        discover_peers(report=tmp_path / "x.json", timeout=0.01)


class _FakeProc:
    def __init__(self, hang=False):
        self.hang = hang
        self.signals = []
        self.killed = False

    def wait(self, timeout=None):
        import time
        if self.hang:
            time.sleep(timeout or 0)
            raise __import__("subprocess").TimeoutExpired("opendrop", timeout)
        return 0

    def send_signal(self, sig):
        self.signals.append(sig)

    def kill(self):
        self.killed = True


class _FakeProc:
    def __init__(self, hang=False, on_exit=None):
        self.hang = hang
        self.on_exit = on_exit
        self.signals = []
        self.killed = False

    def wait(self, timeout=None):
        import subprocess as sp
        import time

        if self.hang and not (self.signals or self.killed):
            time.sleep(min(timeout or 0, 0.3))
            raise sp.TimeoutExpired("opendrop", timeout)
        if self.on_exit:
            self.on_exit()
        return 0

    def send_signal(self, sig):
        self.signals.append(sig)

    def kill(self):
        self.killed = True


def test_discover_sends_sigint_on_timeout(tmp_path, monkeypatch):
    import signal

    monkeypatch.setattr(awdl, "opendrop_available", lambda: True)
    procs = []

    def fake_popen(*a, **k):
        p = _FakeProc(hang=True)
        procs.append(p)
        return p

    monkeypatch.setattr(awdl.subprocess, "Popen", fake_popen)
    report = tmp_path / "discover.last.json"
    peers = discover_peers(iface="awdl0", timeout=0.05, report=report)
    assert peers == []
    assert procs[0].signals == [signal.SIGINT]
    assert not procs[0].killed


def test_discover_ignores_stale_report(tmp_path, monkeypatch):
    import os

    monkeypatch.setattr(awdl, "opendrop_available", lambda: True)
    monkeypatch.setattr(awdl.subprocess, "Popen", lambda *a, **k: _FakeProc())
    report = tmp_path / "discover.last.json"
    report.write_text(json.dumps([
        {"name": "ghost", "address": "fe80::9", "id": "old", "discoverable": True},
    ]))
    os.utime(report, (0, 0))
    assert discover_peers(report=report, timeout=0.01) == []


def test_send_native_argv(tmp_path, monkeypatch):
    captured = {}

    def fake_run(cmd, timeout=None):
        captured["cmd"] = cmd
        captured["timeout"] = timeout

        class R:
            returncode = 0

        return R()

    monkeypatch.setattr(awdl, "opendrop_available", lambda: True)
    monkeypatch.setattr(awdl.subprocess, "run", fake_run)
    awdl.send_native(tmp_path / "f.txt", "deadbeef", iface="awdl0", name="Box")
    assert captured["cmd"] == ["opendrop", "send", "-f", str(tmp_path / "f.txt"),
                               "-r", "deadbeef", "-i", "awdl0", "-n", "Box"]
    assert captured["timeout"] is None


def test_send_native_failure(tmp_path, monkeypatch):
    monkeypatch.setattr(awdl, "opendrop_available", lambda: True)

    def fake_run(cmd, timeout=None):
        class R:
            returncode = 1

        return R()

    monkeypatch.setattr(awdl.subprocess, "run", fake_run)
    with pytest.raises(awdl.AwdlError):
        awdl.send_native(tmp_path / "f.txt", "x")


def test_owl_running_no_process(monkeypatch):
    class R:
        stdout = ""

    monkeypatch.setattr(awdl.subprocess, "run", lambda *a, **k: R())
    assert awdl.owl_running() is False
