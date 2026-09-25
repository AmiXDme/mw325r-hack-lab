#!/bin/bash
# MW325R Panel launcher — starts every backend if needed, opens the panel
# as an app window. Self-locating: works from any path, any user.
SRC="$(cd "$(dirname "$0")" && pwd)"
LOG=/tmp/mw325r-launch.log
CHROME_BIN="$(command -v google-chrome || command -v chromium || command -v chromium-browser)"

{
  echo "=== $(date) launch ==="
  echo "SRC=$SRC"
  echo "CHROME=$CHROME_BIN"
} >> "$LOG"

if [ -z "$CHROME_BIN" ]; then
  echo "ERROR: no chrome/chromium found" >> "$LOG"
  notify-send "MW325R Panel" "Chrome not found — cannot open panel" 2>/dev/null
  exit 1
fi

# 1) headless Chrome w/ CDP (router_api talks to the router through it)
if ! curl -s -m 2 http://127.0.0.1:9222/json/version | grep -q Protocol-Version; then
  mkdir -p "$HOME/.config/mw325r-cdp"
  setsid nohup "$CHROME_BIN" --headless --disable-gpu --no-sandbox \
      --remote-debugging-port=9222 --user-data-dir="$HOME/.config/mw325r-cdp" \
      about:blank >> "$LOG" 2>&1 < /dev/null &
  sleep 3
fi

# 2) router TDDP backend
if ! curl -s -m 3 http://127.0.0.1:8100/api/health | grep -q '"ok": true'; then
  setsid nohup python3 "$SRC/router_api.py" >> "$LOG" 2>&1 < /dev/null &
  sleep 2
fi

# 3) Hack Lab engine (portal :8080, DNS :5354, WS :8765)
if ! curl -s -m 2 http://127.0.0.1:8101/api/health | grep -q '"ok": true'; then
  setsid nohup python3 "$SRC/hacklab_api.py" >> "$LOG" 2>&1 < /dev/null &
  sleep 2
fi

# 4) the panel itself
exec setsid "$CHROME_BIN" \
    --app="file://$SRC/control.html" \
    --user-data-dir="$HOME/.config/mw325r-panel" \
    --class=MW325R-Panel \
    --start-maximized "$@" >> "$LOG" 2>&1
