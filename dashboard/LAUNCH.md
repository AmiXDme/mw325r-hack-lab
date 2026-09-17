# Run the dashboard + modern panel (localhost only)

```bash
cd dashboard
python3 -m http.server 8099 &        # serves index.html + control.html + status.json
python3 router_api.py &              # TDDP backend on 127.0.0.1:8100 (needs: headless chrome --remote-debugging-port=9222)
```

- Open http://localhost:8099/ for the hack dashboard, http://localhost:8099/control.html for the modern panel.
- Log in with YOUR router admin password. It is kept in backend RAM only, never written to disk.
- `status.json` here is a sanitized demo snapshot — the live system rewrites it as events happen.
