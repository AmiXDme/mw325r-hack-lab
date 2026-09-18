#!/bin/bash
# MW325R Panel launcher: starts the backend if needed, opens the panel
# as a standalone app window (no browser bars).
PANEL_DIR="/home/mint/mw325r-hack-lab/dashboard"
API="http://127.0.0.1:8100/api/health"

if ! curl -s -m 3 "$API" | grep -q '"ok": true'; then
    setsid nohup python3 "$PANEL_DIR/router_api.py" \
        > /tmp/mw325r-backend.log 2>&1 < /dev/null &
    sleep 2
fi
exec setsid google-chrome \
    --app="file://$PANEL_DIR/control.html" \
    --user-data-dir="$HOME/.config/mw325r-panel" \
    --class=MW325R-Panel "$@" < /dev/null > /dev/null 2>&1
