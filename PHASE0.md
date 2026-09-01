# Phase 0 — Feasibility Spike Log

## Findings (2026-09-01)

### Upstream projects
- `seemoo-lab/owl` — cloned to `spike/owl` (AWDL userspace implementation, C).
- `seemoo-lab/opendrop` — cloned to `spike/opendrop` (AirDrop protocol, Python).
- `owlinux170` (fork with extra Intel card support) **no longer exists on GitHub** — only upstream `owl` is available. PLAN.md has been corrected.

### Hardware requirements (from owl README)
- Wi-Fi card with **active monitor mode** (monitor + frame injection + ACK of received frames).
- Recommended chip: **Atheros AR9280** (802.11n). See owl issue #9 for other tested cards.
- No VMs/WSL; direct card access required.

### This machine
- Wi-Fi: Intel 700-series CNVi (iwlwifi), `wlp0s20f3` — AX-class, **not recommended**.
- `iw list` shows monitor mode support, but Intel cards generally only do *passive*
  monitor (no injection / no ACK). Expected result: OWL may see peers but transfers
  will degrade heavily or fail. Needs live test once OWL builds.
- Verdict: a **supported USB adapter (Atheros AR9280-based)** is very likely required.

### Build status
- Blocker: missing build deps on this machine — `cmake`, `libev`
  (libpcap, libnl, openssl already installed).
- Pending command (requires sudo):
  ```
  sudo pacman -S --needed cmake libev
  cd spike/owl && git submodule update --init && mkdir build && cd build && cmake .. && make
  ```

## Next steps
1. Install deps, build owl.
2. Test `sudo owl -i wlp0s20f3 -c 6` with an Apple device nearby — check `ip n` for peers.
3. If Intel card fails as expected: order Atheros AR9280 adapter (USB/PCIe), retest.
4. Run opendrop end-to-end transfer test (both directions) — closes Phase 0.
