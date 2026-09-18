# MW325R Modern Panel — install & run (any Linux)

A modern replacement for the MERCUSYS MW325R's stock settings page, plus
travel-router (WDS + survey + MAC clone), ghost mode, ISP tools and a
pure-Python direct-TDDP backend that also runs on Raspberry Pi / Android.

## Quick start (this PC)

```bash
./launch-panel.sh
```

It starts the backend if needed and opens the panel as an app window.
Then log in with your router admin password.

Manual way:

```bash
python3 router_api.py            # backend on http://127.0.0.1:8100
# open control.html in Chrome/Chromium, log in
```

## Install as a Linux app (menu + desktop icon)

```bash
./install.sh
```

Then launch **MW325R Panel** from your app menu. No sudo needed.

## Travel mode (no laptop)

```bash
python3 travel_api.py 8101 --lan     # stdlib only: Pi / Termux / any PC
# open control.html?api=http://<this-host>:8101 in any browser
```

See `TRAVEL.md` for the Android/Termux walkthrough.

## Files

| File | What |
|---|---|
| `control.html` | the panel UI (all tabs) |
| `router_api.py` | backend, needs Python + Chrome (PC) |
| `travel_api.py` | backend, stdlib only (PC/Pi/phone) |
| `tddp.py` | pure-Python TDDP client library |
| `launch-panel.sh` | one-click starter (repo paths) |
| `install.sh` | installs menu/desktop icon (generic paths) |
| `TRAVEL.md` | travel/ghost-mode guide |

## Requirements

- Linux, Python 3.8+, Google Chrome or Chromium (PC backend only)
- A MERCUSYS MW325R (V2 EU tested) at `192.168.1.1`
- Your router admin password (typed into the panel, kept in RAM only)

## Safety

- Every write action asks first. Parental controls are intentionally absent.
- `advanced bm` verbs are hard-blocked (CVE-2023-52162).
- Nothing is ever uploaded anywhere; secrets never touch disk or git.
