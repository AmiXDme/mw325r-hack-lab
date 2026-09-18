#!/bin/bash
# MW325R Panel installer — no sudo needed. Installs a menu + desktop icon
# that starts the backend (if needed) and opens the panel as an app window.
set -e
SRC="$(cd "$(dirname "$0")" && pwd)"
APP_DIR="$HOME/.local/share/applications"
ICON_DIR="$HOME/.local/share/icons"
DESK_DIR="$HOME/Desktop"

mkdir -p "$APP_DIR" "$ICON_DIR"
cp "$SRC/mw325r-panel.svg" "$ICON_DIR/"

cat > "$APP_DIR/mw325r-panel.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=MW325R Panel
Comment=Modern control panel for the MW325R router (local only)
Exec=bash -c 'curl -s -m 3 http://127.0.0.1:8100/api/health | grep -q "\"ok\": true" || (setsid nohup python3 "$SRC/router_api.py" > /tmp/mw325r-backend.log 2>&1 < /dev/null & sleep 2); exec setsid google-chrome --app="file://$SRC/control.html" --user-data-dir="\$HOME/.config/mw325r-panel" --class=MW325R-Panel < /dev/null > /dev/null 2>&1'
Icon=mw325r-panel
Categories=Network;
Terminal=false
StartupWMClass=MW325R-Panel
EOF

if [ -d "$DESK_DIR" ]; then
    cp "$APP_DIR/mw325r-panel.desktop" "$DESK_DIR/"
    chmod +x "$DESK_DIR/mw325r-panel.desktop"
fi
update-desktop-database "$APP_DIR" 2>/dev/null || true
echo "Installed. Launch 'MW325R Panel' from your app menu."
