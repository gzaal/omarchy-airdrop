# omarchy-airdrop

AirDrop-style local file transfer for [Omarchy](https://omarchy.org/), packaged as a plugin.

Two modes:

| Mode | Peers | Needs |
|---|---|---|
| **LAN (default)** | Any device running [LocalSend](https://localsend.org) (iOS, Android, macOS, Windows, Linux) or another omarchy-airdrop | Just Wi-Fi/LAN |
| **Native AirDrop** | Apple AirDrop on macOS/iOS directly | Supported Wi-Fi adapter (active monitor mode) + `owl` + `opendrop` |

## Install

```sh
git clone https://github.com/gzaal/omarchy-airdrop
cd omarchy-airdrop
./install.sh
```

This installs:

- `~/.local/bin/airdrop` — CLI (`peers`, `send`, `receive`, `status`)
- `~/.local/bin/airdrop-share` — share helper (peer menu → detached send)
- `~/.config/omarchy/plugins/<user>.airdrop` — bar widget for the Omarchy shell
- `airdropd.service` — systemd user service (receiver autostart)
- default config in `~/.config/omarchy-airdrop/config.json`

Files are received into `~/Drop/AirDrop/` (configurable).

## Usage

```sh
airdrop status              # config, fingerprint, AWDL state
airdrop peers               # LAN peers (LocalSend compatible)
airdrop peers --airdrop     # native AirDrop receivers (needs owl+opendrop)
airdrop send FILE [FILE...] [--to alias]
airdrop receive --prompt    # receiver with accept menu
airdrop-share FILE...       # Omarchy menu flow: pick peer, send
```

With the receiver service enabled, files sent from a phone (LocalSend app) pop up an
accept menu and land in `~/Drop/AirDrop/`, with a desktop notification.

### Configuration

`~/.config/omarchy-airdrop/config.json`:

| Key | Default | Meaning |
|---|---|---|
| `alias` | hostname | Name shown to peers |
| `download_dir` | `~/Drop/AirDrop` | Where received files go |
| `port` | `53317` | TCP+UDP port (LocalSend default) |
| `protocol` | `https` | TLS with a self-signed cert (auto-falls back to `http`) |
| `accept_policy` | `ask` | `ask` / `auto-accept` / `auto-deny` |
| `max_file_size` | 10 GiB | Upload size limit |

### Keybinds (Hyprland)

See `ui/keybinds-reference.lua`.

## Native AirDrop (Apple devices)

Requires the OWL AWDL implementation, which needs a Wi-Fi card with **active monitor
mode** (frame injection + ACK). Recommended: **Atheros AR9280** (see
[owl issue #9](https://github.com/seemoo-lab/owl/issues/9) for tested cards).
Most modern Intel cards (including CNVi/iwlwifi AX-class) do **not** work — a cheap
supported USB adapter is the practical path.

Setup once the adapter is present:

1. Build/install [owl](https://github.com/seemoo-lab/owl) and
   [opendrop](https://github.com/seemoo-lab/opendrop).
2. Enable the root AWDL daemon on your *physical* wifi interface (e.g. `wlp3s0`),
   using the unit from the repo (the PKGBUILD installs it to
   `/usr/lib/systemd/system/airdropd-owl@.service`):
   ```sh
   sudo cp systemd/airdropd-owl@.service /etc/systemd/system/
   sudo systemctl daemon-reload
   sudo systemctl enable --now airdropd-owl@wlp3s0.service
   ```
   owl creates the virtual `awdl0` interface.
3. Verify: `airdrop status` shows the awdl iface and `owl: running`.
4. Send: `airdrop send FILE --airdrop`, receive: `airdrop receive --airdrop`.

Interoperability with current iOS/macOS is best-effort — Apple changes the protocol
frequently. Tested configurations are documented in PHASE0.md as hardware becomes
available.

## Security notes

- Transfers are TLS (self-signed) in LAN mode; the sender pins the peer's
  certificate fingerprint from discovery.
- Filenames are sanitized (no path traversal, control chars stripped, length-capped)
  and written atomically inside per-session directories.
- Accept policy defaults to `ask`; there are caps on pending sessions and file sizes.

## Development

```sh
uv run pytest -q     # test suite
```

Phases, decisions, and hardware findings: see `PLAN.md` and `PHASE0.md`.

## Uninstall

```sh
./uninstall.sh
```
