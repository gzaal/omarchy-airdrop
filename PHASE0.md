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
- **BUILD OK** (2026-09-01). Worked around missing system deps without root:
  - Extracted cached `cmake` and `libev` pacman packages to `/tmp/opencode/awdl-root` and built against that prefix (`CPATH`/`LIBRARY_PATH`).
  - CMake 4.x needs `-DCMAKE_POLICY_VERSION_MINIMUM=3.5 -DBUILD_TESTING=OFF`; googletest submodule is too old for GCC 15/CMake 4, so local patch guards it behind `BUILD_TESTING`.
  - Binary: `spike/owl/build/daemon/owl`.

### Live test — BLOCKED on root
`owl` needs root to enable monitor mode; no NOPASSWD rule covers it. Command for user:
```
sudo spike/owl/build/daemon/owl -i wlp0s20f3 -c 6 -v
```
(with an Apple device nearby; check `ip n` for discovered peers, Ctrl-C after ~60s)

## Next steps
1. User runs live owl test (above).
2. If Intel card fails as expected: order Atheros AR9280 adapter (USB/PCIe), retest.
3. Run opendrop end-to-end transfer test (both directions) — closes Phase 0.
