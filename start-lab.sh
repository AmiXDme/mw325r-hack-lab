#!/bin/bash
# MW325R Hack Lab - one-click starter (localhost only)
# Usage: ./start-lab.sh
set -u
D="$(cd "$(dirname "$0")" && pwd)"
echo "[1/3] dashboard  -> http://localhost:8099/"
(nohup python3 -m http.server 8099 --directory "$D/dashboard" > "$D/dashboard/server.log" 2>&1 &)
echo "[2/3] backend    -> http://127.0.0.1:8100 (needs headless chrome --remote-debugging-port=9222)"
(nohup python3 "$D/dashboard/router_api.py" > "$D/dashboard/api.log" 2>&1 &)
sleep 2
echo "[3/3] check:"
curl -s -o /dev/null -w "  dashboard: %{http_code}\n" http://localhost:8099/
curl -s -o /dev/null -w "  backend:   %{http_code}\n" http://127.0.0.1:8100/api/health
echo "Open http://localhost:8099/ (status) and http://localhost:8099/control.html (panel)"
