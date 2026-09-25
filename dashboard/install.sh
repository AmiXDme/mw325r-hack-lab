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
Comment=Modern control panel for the MW325R router + Hack Lab (local only)
Exec="$SRC/launch-panel.sh"
Icon=mw325r-panel
Categories=Network;
Terminal=false
StartupWMClass=MW325R-Panel
EOF

if [ -d "$DESK_DIR" ]; then
    cp "$APP_DIR/mw325r-panel.desktop" "$DESK_DIR/"
    chmod +x "$DESK_DIR/mw325r-panel.desktop"
    # Cinnamon/GNOME: mark trusted so double-click just works
    gio set "$DESK_DIR/mw325r-panel.desktop" metadata::trusted true 2>/dev/null || true
fi
update-desktop-database "$APP_DIR" 2>/dev/null || true
gtk-update-icon-cache -f "$HOME/.local/share/icons" 2>/dev/null || true
echo "Installed. Launch 'MW325R Panel' from your app menu or desktop icon."
