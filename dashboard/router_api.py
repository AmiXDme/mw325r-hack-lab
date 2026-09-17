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


def do_reboot():
    if not _ensure_auth():
        return {"ok": False, "error": "not-authenticated"}
    err = cdp_eval("$.reboot().errorno")
    return {"ok": err == 0, "errorno": err}


def do_set_wps(enabled):
    if not _ensure_auth():
        return {"ok": False, "error": "not-authenticated"}
    val = "1" if str(enabled) in ("1", "true", "on") else "0"
    err = cdp_eval(
        "(function(){var b=$.readEx(33);b.wps.bEnabled="
        + json.dumps(val) + ";return $.write($.toText(b),0);})()")
    if err != 0:
        return {"ok": False, "errorno": err}
    cur = cdp_eval("$.readEx(33).wps.bEnabled")
    return {"ok": cur == val, "wpsEnabled": cur, "errorno": err}


def do_set_upnp(enabled):
    if not _ensure_auth():
        return {"ok": False, "error": "not-authenticated"}
    val = 1 if str(enabled) in ("1", "true", "on") else 0
    err = cdp_eval(
        "(function(){var b=$.readEx(19);b.igdEnable=" + str(val) +
        ";return $.write($.toText(b),0);})()")
    if err != 0:
        return {"ok": False, "errorno": err}
    cur = cdp_eval("$.readEx(19).igdEnable")
    ok = str(cur) == str(val)
    return {"ok": ok, "igdEnable": cur, "errorno": err}


def do_set_wifi(key=None, ssid=None):
    if not _ensure_auth():
        return {"ok": False, "error": "not-authenticated"}
    if key is not None and not (8 <= len(key) <= 63):
        return {"ok": False, "error": "key must be 8-63 chars"}
    if ssid is not None and not (1 <= len(ssid) <= 32):
        return {"ok": False, "error": "ssid must be 1-32 chars"}
    expr = "(function(){var b=$.readEx(33);"
    if key is not None:
        expr += f"b.cPskSecret={json.dumps(key)};"
    if ssid is not None:
        expr += f"b.cSsid={json.dumps(ssid)};"
    expr += "return $.write($.toText(b),0);})()"
    err = cdp_eval(expr)
    return {"ok": err == 0, "errorno": err}


def _set_path(obj_expr, dotted, value_json):
    parts = dotted.split(".")
    s = obj_expr
    for p in parts[:-1]:
        s += f"[{json.dumps(p)}]"
    return f"{s}[{json.dumps(parts[-1])}]={value_json};"


def do_write_fields(bid, fields):
    """Generic read-modify-write of one TDDP block. fields: {dotted.key: value}."""
    if not _ensure_auth():
        return {"ok": False, "error": "not-authenticated"}
    if not isinstance(fields, dict) or not fields:
        return {"ok": False, "error": "empty-fields"}
    try:
        bid = int(bid)
    except Exception:
        return {"ok": False, "error": "bad-id"}
    expr = f"(function(){{var b=$.readEx({bid});"
    for k, v in fields.items():
        if not isinstance(k, str) or not k.replace(".", "").replace("_", "").isalnum():
            return {"ok": False, "error": f"bad-key: {k}"}
        expr += _set_path("b", k, json.dumps(v))
    expr += "return $.write($.toText(b),0);})()"
    err = cdp_eval(expr)
    return {"ok": err == 0, "errorno": err}


def do_change_admin(old_pw, new_pw):
    if not _ensure_auth():
        return {"ok": False, "error": "not-authenticated"}
    if not old_pw or not new_pw:
        return {"ok": False, "error": "empty-password"}
    if len(new_pw) < 1 or len(new_pw) > 63:
        return {"ok": False, "error": "bad-length"}
    err = cdp_eval("$.changeSysPwd(" + json.dumps(old_pw) + "," +
                   json.dumps(new_pw) + ").errorno")
    return {"ok": err == 0, "errorno": err}


def do_factory_reset():
    if not _ensure_auth():
        return {"ok": False, "error": "not-authenticated"}
    err = cdp_eval("$.reset().errorno")
    return {"ok": err == 0, "errorno": err}


def do_backup_url():
    if not _ensure_auth():
        return {"ok": False, "error": "not-authenticated"}
    return {"ok": True, "url": cdp_eval(
        "(function(){var d=$.readEx(0);var sv=d.softVer,hv=d.hardVer,i=0,c=0;"
        "for(i=0;i<hv.length;i++){if(hv[i]==' '){break}c++}"
        "var model=hv.substring(0,c),vc=c+1;"
        "for(i=c;i<hv.length;i++){if(hv[i]=='.'){break}c++}"
        "var ver=hv.substring(vc,c),bc=sv.indexOf('Build')+6,rc=sv.indexOf('Rel.')+4;"
        "c=bc;for(i=bc;i<sv.length;i++){if(sv[i]==' '){break}c++}"
        "var B=sv.substring(bc,c);c=rc;"
        "for(i=rc;i<sv.length;i++){if(sv[i]=='n'){break}c++}"
        "var R=sv.substring(rc,c);"
        "return $.orgURL($.domainUrl+model+\"V\"+ver+B+R+\"n.bin\""
        "+\"?code=\"+TDDP_INSTRUCT+\"&asyn=0\");})()")}


def do_diag(action, dtype="ping", target="", size="64", count="4",
             timeout="800", hops="20", icmp_id=None):
    """TDDP INSTRUCT systool ping/tracert. start->poll->stop lifecycle."""
    if not _ensure_auth():
        return {"ok": False, "error": "not-authenticated"}
    if dtype not in ("ping", "tracert"):
        return {"ok": False, "error": "bad-type"}
    if action == "start":
        if not target:
            return {"ok": False, "error": "empty-target"}
        tgt = "".join(c for c in target if c.isalnum() or c in ".-")
        if dtype == "ping":
            cmd = (f"systool ping code:0 target:{tgt} "
                   f"size:{int(size)} metric:{int(count)} "
                   f"timeout:{int(timeout)}")
        else:
            cmd = f"systool tracert code:0 target:{tgt} metric:{int(hops)}"
        r = cdp_eval(f"JSON.stringify($.instr({json.dumps(cmd)}))")
        try:
            o = json.loads(r)
        except Exception:
            return {"ok": False, "error": "bad-response"}
        if o.get("errorno") != 0:
            return {"ok": False, "errorno": o.get("errorno")}
        try:
            return {"ok": True, "icmpId": int(str(o.get("data", "")).strip())}
        except Exception:
            return {"ok": False, "error": "no-icmpid",
                    "data": o.get("data")}
    if icmp_id is None:
        return {"ok": False, "error": "empty-icmpid"}
    code = "2" if action == "poll" else "1" if action == "stop" else None
    if code is None:
        return {"ok": False, "error": "bad-action"}
    r = cdp_eval("JSON.stringify($.instr(" + json.dumps(
        f"systool {dtype} code:{code} icmpId:{int(icmp_id)}") + "))")
    try:
        o = json.loads(r)
    except Exception:
        return {"ok": False, "error": "bad-response"}
    if action == "poll" and o.get("errorno") == 0:
        data = str(o.get("data", ""))
        pos = data.find("\r\n")
        if pos >= 0:
            return {"ok": True, "finished": data[:pos].strip(),
                    "text": data[pos + 2:]}
    return {"ok": o.get("errorno") == 0, "errorno": o.get("errorno"),
            "data": o.get("data")}


def do_fwd(op, idx=None, ip="", lport="", start="", end="", ptc="0"):
    """Port-forwarding via TDDP INSTRUCT (block 21 is read-only)."""
    if not _ensure_auth():
        return {"ok": False, "error": "not-authenticated"}
    if op == "add":
        if not (ip and lport and start and end):
            return {"ok": False, "error": "missing-fields"}
        cmd = (f"forward vs -add lip:{ip} lport:{lport} "
               f"start:{start} end:{end} ptc:{ptc} valid")
    elif op == "delete":
        if idx is None:
            return {"ok": False, "error": "missing-index"}
        cmd = f"forward vs -delete index:{int(idx)}"
    elif op == "clear":
        cmd = "forward vs -clr"
    else:
        return {"ok": False, "error": "bad-op"}
    r = cdp_eval("JSON.stringify($.instr(" + json.dumps(cmd) + "))")
    try:
        o = json.loads(r)
    except Exception:
        return {"ok": False, "error": "bad-response"}
    return {"ok": o.get("errorno") == 0, "errorno": o.get("errorno")}


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
        from urllib.parse import urlparse
        u = urlparse(self.path)
        try:
            ln = int(self.headers.get("Content-Length", 0))
            data = json.loads(self.rfile.read(ln) or b"{}")
        except Exception:
            return self._json({"ok": False, "error": "bad-json"}, 400)
        if u.path == "/api/login":
            pw = data.get("password", "")
            if not pw:
                return self._json({"ok": False, "error": "empty-password"})
            try:
                return self._json(do_login(pw))
            except Exception as e:
                return self._json({"ok": False, "error": f"backend-error: {e}"},
                                  500)
        try:
            if u.path == "/api/reboot":
                return self._json(do_reboot())
            if u.path == "/api/set_wps":
                return self._json(do_set_wps(data.get("enabled")))
            if u.path == "/api/set_upnp":
                return self._json(do_set_upnp(data.get("enabled")))
            if u.path == "/api/set_wifi":
                return self._json(do_set_wifi(data.get("key"),
                                              data.get("ssid")))
            if u.path == "/api/write_fields":
                return self._json(do_write_fields(data.get("id"),
                                                  data.get("fields")))
            if u.path == "/api/change_admin":
                return self._json(do_change_admin(data.get("old"),
                                                  data.get("new")))
            if u.path == "/api/factory_reset":
                if data.get("confirm") != "YES-WIPE-MY-ROUTER":
                    return self._json({"ok": False,
                                       "error": "confirm-missing"})
                return self._json(do_factory_reset())
            if u.path == "/api/fwd":
                return self._json(do_fwd(
                    data.get("op"), data.get("idx"), data.get("ip", ""),
                    data.get("lport", ""), data.get("start", ""),
                    data.get("end", ""), data.get("ptc", "0")))
            if u.path == "/api/diag":
                return self._json(do_diag(
                    data.get("action"), data.get("type", "ping"),
                    data.get("target", ""), data.get("size", "64"),
                    data.get("count", "4"), data.get("timeout", "800"),
                    data.get("hops", "20"), data.get("icmpId")))
        except Exception as e:
            return self._json({"ok": False, "error": f"backend-error: {e}"},
                              500)
        return self._json({"ok": False, "error": "not-found"}, 404)

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
        elif u.path == "/api/backup":
            try:
                r = do_backup_url()
                if not r.get("ok"):
                    self._json(r, 401)
                else:
                    req = urllib.request.Request(
                        r["url"], headers={"User-Agent": "Mozilla/5.0"})
                    blob = urllib.request.urlopen(req, timeout=30).read()
                    self.send_response(200)
                    self._cors()
                    self.send_header("Content-Type",
                                     "application/octet-stream")
                    self.send_header("Content-Disposition",
                                     "attachment; filename=MW325R-backup.bin")
                    self.send_header("Content-Length", str(len(blob)))
                    self.end_headers()
                    self.wfile.write(blob)
            except Exception as e:
                self._json({"ok": False, "error": f"backend-error: {e}"}, 500)
        else:
            self._json({"ok": False, "error": "not-found"}, 404)

    def log_message(self, *a):
        pass  # quiet; never log passwords


if __name__ == "__main__":
    srv = HTTPServer(("127.0.0.1", 8100), Handler)
    print("MW325R panel backend on http://127.0.0.1:8100 (localhost only)",
          flush=True)
    srv.serve_forever()
