# omarchy-airdrop — Development Plan

Goal: send and receive files to/from native Apple AirDrop (macOS/iOS) from an Omarchy (Arch + Hyprland) machine, packaged as an Omarchy plugin.

## 1. Reality check (read first)

AirDrop is not a simple network protocol. It is three stacked proprietary pieces:

| Layer | What it is | Open implementation |
|---|---|---|
| AWDL | Apple Wireless Direct Link — proprietary frames over Wi-Fi, creates the `awdl0` interface (no router needed) | `owl` (Seemoo Lab, userspace C) |
| Discovery | BLE advertisements + mDNS (`_airdrop._tcp`, TLS) over awdl0 | OpenDrop (Python) |
| Transfer | HTTPS with Apple-signed TLS client certificates, signed identity records | OpenDrop (partially — see caveats) |

**Hardware constraint:** OWL needs a card with *active* monitor mode (frame injection + ACK); recommended chip is **Atheros AR9280** (see owl issue #9). Your current Intel CNVi (iwlwifi, AX-class) is passive-monitor only and expected to fail. Options:

1. Use a cheap supported USB Wi-Fi adapter dedicated to AWDL (Atheros AR9280-based — recommended, ethernet stays primary).
2. Skip AWDL entirely and use LAN-based LocalSend-protocol mode (works anywhere, but not *native* AirDrop).

**Protocol constraint:** recent macOS/iOS versions tightened AirDrop's certificate/identity handling. OpenDrop's interop with stock Apple devices is experimental and breaks with OS updates. Treat "works with my iPhone on iOS 18" as the acceptance test, not a guarantee.

This is why the plan is phased: **Phase 0 proves feasibility before any UI work.**

## 2. Architecture

```
omarchy-airdrop/
├── airdropd/               # Core daemon (Python)
│   ├── awdl.py             # AWDL link manager (wraps owl/owlinux170, needs root)
│   ├── discovery.py        # mDNS browsing/advertising (_airdrop._tcp / _localsend._tcp)
│   ├── receive.py          # HTTPS receiver, accept/reject policy, saves to ~/Drop/AirDrop
│   ├── send.py             # Sender: pick peer, upload
│   ├── localsend.py        # LocalSend-compatible fallback protocol (LAN mode)
│   └── identity.py         # Certificate generation / record signing
├── ui/
│   ├── waybar-module.sh    # Bar indicator: AWDL up? peers found?
│   ├── rofi-send           # "Send file → pick peer" picker
│   └── accept-dialog.py    # Hyprland notification/dialog for incoming files
├── systemd/
│   ├── airdropd.service    # User service
│   └── airdropd-awdl.service  # Root helper (CAP_NET_ADMIN) for monitor mode
├── install.sh              # Omarchy-style installer (deps + services + keybinds)
└── bin/airdrop             # Single CLI entrypoint: airdrop send|receive|status|peers
```

**Plugin shape for Omarchy:** install script + systemd user services + Hyprland keybind (e.g. `SUPER+Shift+A` → rofi-send) + waybar module + a `bin/airdrop` CLI. No fork of Omarchy needed; it lives in its own repo and is installed like other Omarchy extras.

## 3. Phases

### Phase 0 — Feasibility spike (do this before writing the plugin)
- [ ] Obtain a supported USB adapter (Atheros AR9280-based; check owl issue #9 for tested cards)
- [ ] Build `owl`/`owlinux170` on Arch, get `awdl0` up, see Apple devices appear in mDNS.
- [ ] Run upstream `opendrop` CLI end-to-end once: iPhone → Linux and Linux → iPhone.
- [ ] Decision gate: if interop works → continue. If not → keep Phase 1 (fallback mode) as the product and note the limitation.

### Phase 1 — Core daemon + fallback protocol (no AWDL needed)
- [ ] `airdropd` daemon: LocalSend-compatible discovery + send/receive over the normal LAN Wi-Fi (also usable with Android/Windows/Linux LocalSend apps — useful on its own).
- [ ] CLI: `airdrop send <file>`, `airdrop receive`, `airdrop peers`, `airdrop status`.
- [ ] Receive policy: auto-accept off / always ask / trusted-device list. Files land in `~/Drop/AirDrop`.
- [ ] Desktop notifications (`notify-send`) on incoming/failed transfers.
- [ ] Unit tests for protocol handling with recorded mDNS/HTTPS fixtures.

### Phase 2 — Native AirDrop via AWDL
- [ ] Vendor/wrap `owlinux170` as an optional dependency (AUR package or bundled build).
- [ ] Root helper service that brings up monitor mode + `awdl0`, handles channel hopping; daemon talks to it over a local socket.
- [ ] Apple-signed-cert handling, OOB/PSK handling, retries for flaky AWDL links.
- [ ] Graceful degradation: AWDL down → fall back to LAN mode automatically.

### Phase 3 — Desktop integration (the "plugin" polish)
- [ ] Rofi send flow: file picker → peer list → progress toast.
- [ ] Accept dialog on incoming transfer (thumbnail/filename/sender, accept once / always-from-this-device / deny).
- [ ] Waybar module: icon state (off / LAN / AWDL / N peers).
- [ ] Hyprland keybinds + file-manager "Send via AirDrop" context entry (Nautilus script).
- [ ] Idle/lock interplay: pause auto-accept when locked.

### Phase 4 — Packaging & install
- [ ] `install.sh` Omarchy-style: pacman/AUR deps, enable user services, install keybinds + waybar config.
- [ ] `uninstall.sh` that fully cleans up.
- [ ] PKGBUILD for AUR; docs with hardware compatibility table.

### Phase 5 — Hardening
- [ ] Security review of the HTTPS receiver (path traversal, size limits, timeouts — AirDrop's known CVEs are instructive).
- [ ] Transfer resumption for large files, sender-name spoofing protections.
- [ ] Test matrix: iPhone (2 recent iOS versions), MacBook, Android via LocalSend.

## 4. Key risks
- **Your Wi-Fi card can't do AWDL** — mitigation: supported USB adapter, or ship as LAN-only.
- **Apple changes the protocol** with OS updates — interop is best-effort; pin tested iOS/macOS versions in docs.
- **Root requirement for monitor mode** — isolate in a minimal root helper service, no broad sudo.
- **Scope creep** — Phase 1 (LocalSend fallback) is independently valuable; ship it first.
