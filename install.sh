#!/usr/bin/env bash
# omarchy-airdrop installer: bin + plugin + user systemd service
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BIN_DIR="${HOME}/.local/bin"
PLUGIN_DIR="${HOME}/.config/omarchy/plugins/${USER:-$(id -un)}.airdrop"

info() { printf '\033[1;32m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m==>\033[0m %s\n' "$*"; }

[[ -f "$REPO_DIR/airdropd/cli.py" ]] || { echo "Run from a checkout of omarchy-airdrop" >&2; exit 1; }

## dependencies (optional, for native AirDrop mode)
if ! command -v openssl >/dev/null; then
  warn "openssl not found — required for the default https mode"
fi

## CLI
info "installing airdrop to $BIN_DIR"
mkdir -p "$BIN_DIR"
ln -sfn "$REPO_DIR/bin/airdrop" "$BIN_DIR/airdrop"

## Omarchy shell plugin (bar widget)
if [[ -d "$HOME/.config/omarchy" ]]; then
  info "installing Omarchy shell plugin to $PLUGIN_DIR"
  rm -rf "$PLUGIN_DIR"
  mkdir -p "$(dirname "$PLUGIN_DIR")"
  cp -r "$REPO_DIR/ui/omarchy-plugin/omarchy-airdrop" "$PLUGIN_DIR"
  info "enable the widget with: omarchy bar put ${USER:-$(id -un)}.airdrop"
else
  warn "no ~/.config/omarchy — skipping shell plugin"
fi

## share menu helper
info "installing airdrop-share to $BIN_DIR"
ln -sfn "$REPO_DIR/ui/airdrop-share" "$BIN_DIR/airdrop-share"

## systemd user service
info "installing systemd user service airdropd"
mkdir -p "$HOME/.config/systemd/user"
service_file="$HOME/.config/systemd/user/airdropd.service"
template="$(cat "$REPO_DIR/systemd/airdropd.service")"
printf '%s\n' "${template//__REPO_DIR__/$REPO_DIR}" > "$service_file"
chmod 644 "$service_file"

## default config
mkdir -p "$HOME/.config/omarchy-airdrop"
if [[ ! -f "$HOME/.config/omarchy-airdrop/config.json" ]]; then
  cat > "$HOME/.config/omarchy-airdrop/config.json" <<EOF
{
  "alias": "$(uname -n)",
  "download_dir": "$HOME/Drop/AirDrop",
  "port": 53317,
  "protocol": "https",
  "accept_policy": "ask"
}
EOF
fi
mkdir -p "$HOME/Drop/AirDrop"

info "enabling airdrop.service (autostart + start now)"
if systemctl --user daemon-reload 2>/dev/null && \
    systemctl --user enable --now airdropd.service 2>/dev/null; then
  :
else
  warn "could not talk to the systemd user manager; enable manually with:"
  warn "  systemctl --user daemon-reload && systemctl --user enable --now airdropd.service"
fi

cat <<EOF

omarchy-airdrop installed.

  status:   airdrop status
  peers:    airdrop peers
  send:     airdrop-share FILE   (or: airdrop send FILE)
  receive:  airdrop receive --prompt

Optional Hyprland keybinds: see $REPO_DIR/ui/keybinds-reference.lua
Native AirDrop (needs supported Wi-Fi hardware + owl + opendrop): see README.md
EOF
