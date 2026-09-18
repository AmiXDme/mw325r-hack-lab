# TRAVEL MODE — control the router with NO laptop

`router_api.py` needs a PC (Python + Chrome). `travel_api.py` + `tddp.py`
do the SAME job with **Python stdlib only** — they speak the router's TDDP
protocol directly (see `analysis/DIRECT_TDDP.md`). Same `control.html`
works with either backend:

```
control.html                          -> PC backend   (Chrome stack, :8100)
control.html?api=http://127.0.0.1:8101 -> travel backend (direct, :8101)
```

## Option A — Android phone (Termux, free, no root)

1. Install **Termux** from F-Droid/Play Store.
2. In Termux:
```
pkg install python git -y
git clone https://github.com/AmiXDme/mw325r-hack-lab.git
cd mw325r-hack-lab/dashboard
python3 travel_api.py 8101 --lan
```
3. Connect the phone to the router's WiFi (home OR hotel — wherever the
   MW325R is, e.g. WDS-bridged travel setup).
4. Open in the phone browser: `file:///sdcard/.../control.html?api=http://<phone-ip>:8101`
   (copy control.html to the phone, or serve it: `python3 -m http.server 8080`
   in Termux, then open `http://<phone-ip>:8080/control.html?api=http://<phone-ip>:8101`)
5. Log in with the router admin password. Done — full panel, no laptop.

`--lan` binds home-LAN only. Never forward this port to the internet.

## Option B — Raspberry Pi / any spare computer

```
python3 travel_api.py 8101 --lan
```
…then open `control.html?api=http://<pi-ip>:8101` from any home device.

## What was proven

- Direct login + all 60 blocks parse **byte-identical** to the Chrome stack
- 10 endpoint families diff-tested chrome-vs-direct: identical
- Writes verified: ALG + timezone no-ops (`errno 0`), live site survey
