# Test Matrix — omarchy-airdrop

Manual interop validation checklist. Automated coverage: `uv run pytest -q`.

## Automated (CI-runnable)

| Area | Status |
|---|---|
| Filename sanitization (traversal, control chars, length, collisions) | 12 tests |
| LocalSend v2 payload shapes + announce roundtrip | 4 tests |
| Receiver end-to-end flow (prepare/upload/cancel/errors/keep-alive) | 20 tests |
| Sender pinning + argv construction | 4 tests |
| AWDL wrapper (discovery report, SIGINT lifecycle, staleness) | 12 tests |
| Desktop backends (omarchy/notify-send/rofi menus, prompts) | 12 tests |
| Security regressions (pinning fail-closed, same-name, label injection, negative size) | 6 tests |

## Manual — LAN mode (LocalSend compatible)

- [ ] iPhone (LocalSend app): discover → send → receive
- [ ] iPhone: receiver running on Omarchy, accept menu popup, file lands in `~/Drop/AirDrop`
- [ ] Android (LocalSend): both directions
- [ ] macOS (LocalSend): both directions
- [ ] Large file (~1 GB) transfer completes with progress
- [ ] Two Linux boxes (omarchy-airdrop ↔ omarchy-airdrop): announce, send, TLS pinning holds
- [ ] Receiver service survives network changes (Wi-Fi ↔ ethernet)
- [ ] `accept_policy: ask` denies when no menu backend (headless)

## Manual — native AirDrop mode (hardware-gated)

Prereq: supported adapter (Atheros AR9280 per owl), `owl` running, `opendrop` installed.

- [ ] `airdrop status` shows awdl iface + owl running
- [ ] iPhone appears in `airdrop peers --airdrop`
- [ ] iPhone → Omarchy: `airdrop receive --airdrop`, accept on phone
- [ ] Omarchy → iPhone: `airdrop send FILE --airdrop --to <id>`
- [ ] Intel CNVi (wlp0s20f3) documented as unsupported (passive monitor only)
- [ ] Verify transfers degrade to LAN mode when owl is stopped

## Regression gates before release

- [ ] `uv run pytest -q` green
- [ ] `bash -n` on all shell scripts
- [ ] install.sh → status → uninstall.sh round-trip in sandboxed HOME
- [ ] `makepkg --printsrcinfo` clean
