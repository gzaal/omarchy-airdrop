#!/usr/bin/env bash
# omarchy-airdrop uninstaller: removes everything install.sh created
set -euo pipefail

BIN_DIR="${HOME}/.local/bin"
PLUGIN_DIR="${HOME}/.config/omarchy/plugins/${USER:-$(id -un)}.airdrop"
SERVICE_DIR="${HOME}/.config/systemd/user"

systemctl --user disable --now airdropd.service 2>/dev/null || true
rm -f "$SERVICE_DIR/airdropd.service"
systemctl --user daemon-reload 2>/dev/null || true

rm -f "$BIN_DIR/airdrop" "$BIN_DIR/airdrop-share"
rm -rf "$PLUGIN_DIR"

echo "omarchy-airdrop uninstalled."
echo "Your config and received files were kept:"
echo "  ~/.config/omarchy-airdrop/  ~/Drop/AirDrop/"
