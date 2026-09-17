#!/usr/bin/env python3
"""Modern MW325R control-panel backend (localhost only).
UI (control.html) -> http://127.0.0.1:8100/api/* -> CDP -> headless Chrome
(page at http://192.168.1.1/) -> router TDDP. Read-only in v1.
Password lives in RAM only, never on disk, never logged.
Stdlib only except `websockets` (already installed).
"""
import asyncio
import json
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer

import websockets

CDP_LIST = "http://localhost:9222/json/list"
ROUTER_URL = "http://192.168.1.1/"
_state = {"enc_pwd": None}   # orgAuthPwd(password), RAM only
_lock = threading.Lock()


def _router_ws():
    """Dedicated background tab for router comms (never touches user's tabs)."""
    global _ROUTER_WS
    try:
        return _ROUTER_WS
    except NameError:
        pass
    targets = json.loads(urllib.request.urlopen(CDP_LIST, timeout=3).read())
    for t in targets:
        if t.get("url") == ROUTER_URL and t.get("type") == "page":
            _ROUTER_WS = t["webSocketDebuggerUrl"]
            return _ROUTER_WS
    req = urllib.request.Request("http://localhost:9222/json/new?about:blank",
                                 method="PUT")
    t = json.loads(urllib.request.urlopen(req, timeout=5).read())
    _ROUTER_WS = t["webSocketDebuggerUrl"]
    return _ROUTER_WS


def _page_ws():
    targets = json.loads(urllib.request.urlopen(CDP_LIST, timeout=3).read())
    for t in targets:
        if t.get("type") == "page":
            return t["webSocketDebuggerUrl"]
    raise RuntimeError("no CDP page target")


async def _cdp_eval(expr, navigate_first=False):
    ws = await websockets.connect(_router_ws(), max_size=10_000_000)
    mid = [0]

    async def send(method, params=None):
        mid[0] += 1
        msg = {"id": mid[0], "method": method}
        if params:
            msg["params"] = params
        await ws.send(json.dumps(msg))
        while True:
            r = json.loads(await ws.recv())
            if r.get("id") == mid[0]:
                return r

    async def ev(e):
        r = await send("Runtime.evaluate",
                       {"expression": e, "returnByValue": True})
        return r.get("result", {}).get("result", {}).get("value")

    try:
        await send("Page.enable")
        await send("Runtime.enable")
        if navigate_first:
            await send("Page.navigate", {"url": ROUTER_URL})
            await asyncio.sleep(4)
        return await ev(expr)
    finally:
        await ws.close()


def cdp_eval(expr, navigate_first=False):
    with _lock:  # one CDP conversation at a time
        return asyncio.run(_cdp_eval(expr, navigate_first))


def do_login(password):
    enc = cdp_eval(f"$.orgAuthPwd({json.dumps(password)})",
                   navigate_first=True)
    err = cdp_eval(f"$.setLgPwd($.orgAuthPwd({json.dumps(password)}));"
                   f"$.auth($.pwd).errorno")
    if err == 0:
        _state["enc_pwd"] = enc
        return {"ok": True}
    _state["enc_pwd"] = None
    return {"ok": False, "errorno": err}


def _ensure_auth():
    if not _state["enc_pwd"]:
        return False
    err = cdp_eval(f"$.setLgPwd({json.dumps(_state['enc_pwd'])});"
                   f"$.auth($.pwd).errorno")
    return err == 0


def read_block(bid):
    if not _ensure_auth():
        return {"ok": False, "error": "not-authenticated"}
    raw = cdp_eval(f"JSON.stringify($.readEx({int(bid)}))")
    try:
        return {"ok": True, "block": json.loads(raw)}
    except Exception:
        return {"ok": False, "error": "parse-error"}


def overview():
    out = {}
    for bid in (0, 1, 9, 33):
        r = read_block(bid)
        if not r.get("ok"):
            return r
        out[str(bid)] = r["block"]
    dev, sys, dhcp, wifi = out["0"], out["1"], out["9"], out["33"]
    wps = wifi.get("wps", {}) if isinstance(wifi.get("wps"), dict) else {}
    clients = dhcp.get("list", []) if isinstance(dhcp, dict) else []
    return {"ok": True, "overview": {
        "model": f"{dev.get('facturer','')} {dev.get('modelName','')} "
                 f"{dev.get('modelVer','')}",
        "firmware": dev.get("softVer", ""),
        "mac": (sys.get("mac") or ["?"])[0],
        "ssid": wifi.get("cSsid", ""),
        "wifiKey": wifi.get("cPskSecret", ""),
        "wifiEnabled": wifi.get("bEnable", ""),
        "broadcast": wifi.get("bBcastSsid", ""),
        "security": wifi.get("uPSKSecOpt", ""),
        "wpsEnabled": wps.get("bEnabled", ""),
        "clients": [{"host": c.get("hostName") or "(unnamed)",
                     "ip": c.get("ip"), "mac": c.get("mac")}
                    for c in clients
                    if c.get("ip") and c.get("ip") != "0.0.0.0"],
    }}


class Handler(BaseHTTPRequestHandler):
    server_version = "MW325R-Panel/1.0"

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def _json(self, obj, code=200):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self._cors()
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_POST(self):
        if self.path != "/api/login":
            return self._json({"ok": False, "error": "not-found"}, 404)
        try:
            ln = int(self.headers.get("Content-Length", 0))
            data = json.loads(self.rfile.read(ln) or b"{}")
            pw = data.get("password", "")
            if not pw:
                return self._json({"ok": False, "error": "empty-password"})
            self._json(do_login(pw))
        except Exception as e:
            self._json({"ok": False, "error": f"backend-error: {e}"}, 500)

    def do_GET(self):
        from urllib.parse import urlparse, parse_qs
        u = urlparse(self.path)
        if u.path == "/api/overview":
            try:
                self._json(overview())
            except Exception as e:
                self._json({"ok": False, "error": f"backend-error: {e}"}, 500)
        elif u.path == "/api/block":
            try:
                bid = int(parse_qs(u.query).get("id", ["33"])[0])
                self._json(read_block(bid))
            except Exception as e:
                self._json({"ok": False, "error": f"backend-error: {e}"}, 500)
        elif u.path == "/api/health":
            self._json({"ok": True, "authed": bool(_state["enc_pwd"])})
        else:
            self._json({"ok": False, "error": "not-found"}, 404)

    def log_message(self, *a):
        pass  # quiet; never log passwords


if __name__ == "__main__":
    srv = HTTPServer(("127.0.0.1", 8100), Handler)
    print("MW325R panel backend on http://127.0.0.1:8100 (localhost only)",
          flush=True)
    srv.serve_forever()
