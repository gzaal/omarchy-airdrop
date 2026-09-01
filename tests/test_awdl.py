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
    monkeypatch.setattr(awdl.subprocess, "run", lambda *a, **k: None)
    report = tmp_path / "discover.last.json"
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
    monkeypatch.setattr(awdl.subprocess, "run", lambda *a, **k: None)
    assert discover_peers(report=tmp_path / "nope.json", timeout=0.01) == []


def test_discover_peers_invalid_report(tmp_path, monkeypatch):
    monkeypatch.setattr(awdl, "opendrop_available", lambda: True)
    monkeypatch.setattr(awdl.subprocess, "run", lambda *a, **k: None)
    report = tmp_path / "discover.last.json"
    report.write_text("not json {")
    with pytest.raises(awdl.AwdlError):
        discover_peers(report=report, timeout=0.01)


def test_discover_requires_opendrop(tmp_path, monkeypatch):
    monkeypatch.setattr(awdl, "opendrop_available", lambda: False)
    with pytest.raises(awdl.AwdlError):
        discover_peers(report=tmp_path / "x.json", timeout=0.01)
