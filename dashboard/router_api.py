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


async def _cdp_eval(expr, navigate_first=False, await_promise=False):
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
                       {"expression": e, "returnByValue": True,
                        "awaitPromise": await_promise})
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


def cdp_eval(expr, navigate_first=False, await_promise=False):
    with _lock:  # one CDP conversation at a time
        return asyncio.run(_cdp_eval(expr, navigate_first, await_promise))


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


def do_set_wifi(key=None, ssid=None, bcast=None, enable=None):
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
    if bcast is not None:
        expr += f"b.bBcastSsid={json.dumps('1' if str(bcast) == '1' else '0')};"
    if enable is not None:
        expr += f"b.bEnable={json.dumps('1' if str(enable) == '1' else '0')};"
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


ALLOWED_INSTR = ("systool ", "forward ", "advanced ", "main ",
                   "wan ", "wlan ", "arpMap")


def do_instr(cmd):
    """TDDP INSTRUCT passthrough (whitelisted prefixes only)."""
    if not _ensure_auth():
        return {"ok": False, "error": "not-authenticated"}
    if not isinstance(cmd, str) or not cmd.startswith(ALLOWED_INSTR):
        return {"ok": False, "error": "blocked-prefix"}
    # CVE-2023-52162: stack overflow in `advanced bm` (behavior mgmt) parsing.
    # The panel never uses it (only `advanced pc`), so hard-block it here.
    if cmd.startswith("advanced bm"):
        return {"ok": False, "error": "blocked-cve-2023-52162"}
    if len(cmd) > 300:
        return {"ok": False, "error": "too-long"}
    r = cdp_eval("JSON.stringify($.instr(" + json.dumps(cmd) + "))")
    try:
        o = json.loads(r)
    except Exception:
        return {"ok": False, "error": "bad-response"}
    return {"ok": o.get("errorno") == 0, "errorno": o.get("errorno"),
            "data": o.get("data")}


def do_traffic():
    """Sample WAN counters twice -> live up/down rates."""
    if not _ensure_auth():
        return {"ok": False, "error": "not-authenticated"}
    import time as _t
    a = cdp_eval("JSON.stringify($.readEx(23))")
    _t.sleep(2)
    b = cdp_eval("JSON.stringify($.readEx(23))")
    try:
        A, B = json.loads(a), json.loads(b)
        dt = 2.0
        up = (int(B.get("outOctets", 0)) - int(A.get("outOctets", 0))) * 8 / dt
        down = (int(B.get("inOctets", 0)) - int(A.get("inOctets", 0))) * 8 / dt
        return {"ok": True, "up_bps": max(0, int(up)),
                "down_bps": max(0, int(down)),
                "wanIp": B.get("ip", ""), "uptime": B.get("upTime", ""),
                "totUpMB": round(int(B.get("outOctets", 0)) / 1e6, 1),
                "totDownMB": round(int(B.get("inOctets", 0)) / 1e6, 1)}
    except Exception as e:
        return {"ok": False, "error": f"parse: {e}"}


def do_speedtest(mb=10):
    """PC-side download speed test (honest label: measures THIS pc's net)."""
    import time as _t
    mb = max(1, min(int(mb), 50))
    url = f"https://cachefly.cachefly.net/{mb}mb.test"
    try:
        t0 = _t.time()
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        n = 0
        with urllib.request.urlopen(req, timeout=60) as r:
            while True:
                chunk = r.read(65536)
                if not chunk:
                    break
                n += len(chunk)
        dt = max(_t.time() - t0, 0.01)
        return {"ok": True, "mbps": round(n * 8 / dt / 1e6, 1),
                "mb": round(n / 1e6, 1), "sec": round(dt, 1)}
    except Exception as e:
        return {"ok": False, "error": str(e)[:120]}


def do_dns(dns1, dns2="", auto=False):
    if not _ensure_auth():
        return {"ok": False, "error": "not-authenticated"}
    import re as _re
    ipre = r"^\d{1,3}(\.\d{1,3}){3}$"
    if auto:
        fields = {"manualDns": "0"}
    else:
        if not _re.match(ipre, dns1 or ""):
            return {"ok": False, "error": "bad-dns1"}
        if dns2 and not _re.match(ipre, dns2):
            return {"ok": False, "error": "bad-dns2"}
        fields = {"manualDns": "1", "dns.0": dns1,
                  "dns.1": dns2 or "0.0.0.0"}
    return do_write_fields(25, fields)


def do_scan():
    """WiFi site survey: run wlan scan, poll scanStatus, read block 36."""
    if not _ensure_auth():
        return {"ok": False, "error": "not-authenticated"}
    s = cdp_eval("JSON.stringify($.instr('wlan scan'))")
    try:
        if json.loads(s).get("errorno") != 0:
            return {"ok": False, "error": "scan-start-failed"}
    except Exception:
        return {"ok": False, "error": "bad-response"}
    for _ in range(20):
        time.sleep(1)
        r = cdp_eval("JSON.stringify($.instr('wlan scanStatus'))")
        try:
            st = str(json.loads(r).get("data", "")).strip()
        except Exception:
            st = ""
        if st == "1":
            break
    raw = cdp_eval("JSON.stringify($.readEx(36))")
    try:
        b = json.loads(raw)
    except Exception:
        return {"ok": False, "error": "parse-error"}
    aps = []
    for e in b.get("apEntry", []):
        if not e.get("cBssid") or e.get("cBssid", "").startswith("00-00-00"):
            continue
        aps.append({"bssid": e.get("cBssid"), "ssid": (e.get("cSsid") or "").strip(),
                    "rssi": e.get("uRssi"), "channel": e.get("uChannel"),
                    "auth": e.get("uAuthMode"), "width": e.get("uChanWidth")})
    aps.sort(key=lambda a: -int(a["rssi"] or 0))
    return {"ok": True, "count": len(aps), "aps": aps}


def do_wds(op, ssid="", key="", bssid=""):
    """Travel-router WDS bridge on block 32 apc + wlan wdsstatus."""
    if not _ensure_auth():
        return {"ok": False, "error": "not-authenticated"}
    if op == "get":
        raw = cdp_eval("JSON.stringify($.readEx(32))")
        try:
            b = json.loads(raw)
        except Exception:
            return {"ok": False, "error": "parse-error"}
        st = instr_raw = cdp_eval("JSON.stringify($.instr('wlan wdsstatus'))")
        try:
            wds = json.loads(st).get("data", "")
        except Exception:
            wds = ""
        apc = b.get("apc", {})
        return {"ok": True,
                "bridgeEnabled": apc.get("bBridgeEnabled"),
                "ssid": apc.get("cBridgedSsid", ""),
                "bssid": apc.get("cBridgedBssid", ""),
                "security": apc.get("uSecurityType"),
                "wdsStatus": {"0": "disconnected", "1": "init", "2": "scan",
                              "3": "auth", "4": "assoc", "5": "connected"}.get(
                                  str(wds).strip(), str(wds))}
    if op == "connect":
        ssid = ssid.strip()
        if not ssid:
            return {"ok": False, "error": "empty-ssid"}
        if key and not (8 <= len(key) <= 63):
            return {"ok": False, "error": "key must be 8-63 for WPA"}
        uSec = "4" if key else "1"
        bssid = (bssid or "").strip().upper()
        import re as _re
        if not _re.match(r"^([0-9A-F]{2}-){5}[0-9A-F]{2}$", bssid):
            bssid = "00-00-00-00-00-00"  # zeroed = router resolves BSSID by SSID
        return do_write_fields(32, {"apc.bBridgeEnabled": "1",
                                    "apc.cBridgedSsid": ssid,
                                    "apc.cBridgedBssid": bssid,
                                    "apc.uSecurityType": uSec,
                                    "apc.cPassWD": key})
    if op == "disconnect":
        return do_write_fields(32, {"apc.bBridgeEnabled": "0"})
    return {"ok": False, "error": "bad-op"}


def do_macclone(op, mac=""):
    """MAC clone (block 1 mac[1] + wanMacType), peer MAC via TDDP8."""
    if not _ensure_auth():
        return {"ok": False, "error": "not-authenticated"}
    if op == "get":
        raw = cdp_eval("JSON.stringify($.readEx(1))")
        try:
            b = json.loads(raw)
        except Exception:
            return {"ok": False, "error": "parse-error"}
        peer = cdp_eval("JSON.stringify($.getPeerMac())")
        pc = ""
        try:
            pc = str(json.loads(peer).get("data", "")).strip().splitlines() and \
                 str(json.loads(peer).get("data", "")).split("\r\n")[0]
        except Exception:
            pass
        return {"ok": True,
                "lanMac": (b.get("mac") or ["?", "?"])[0],
                "wanMac": (b.get("mac") or ["?", "?"])[1],
                "wanMacType": b.get("wanMacType"),
                "pcMac": pc}
    if op == "set":
        import re as _re
        mac = (mac or "").strip().upper()
        if not _re.match(r"^([0-9A-F]{2}-){5}[0-9A-F]{2}$", mac):
            return {"ok": False, "error": "bad-mac-format"}
        if mac in ("00-00-00-00-00-00", "FF-FF-FF-FF-FF-FF"):
            return {"ok": False, "error": "invalid-mac"}
        cur = json.loads(cdp_eval("JSON.stringify($.readEx(1))"))
        lan = (cur.get("mac") or ["?"])[0].upper()
        if mac == lan:
            return {"ok": False, "error": "wan-mac-equals-lan-mac"}
        return do_write_fields(1, {"mac.1": mac, "wanMacType": "2"})
    return {"ok": False, "error": "bad-op"}


TZ_OPTIONS = [
    ("0", "UTC-12 (Eniwetok)"), ("60", "UTC-11 (Midway)"),
    ("120", "UTC-10 (Hawaii)"), ("180", "UTC-9 (Alaska)"),
    ("240", "UTC-8 (Pacific)"), ("300", "UTC-7 (Mountain)"),
    ("360", "UTC-6 (Central)"), ("420", "UTC-5 (Eastern)"),
    ("510", "UTC-4:30 (Newfoundland)"), ("540", "UTC-3 (Brasilia)"),
    ("600", "UTC-3:30 (Mid-Atlantic)"), ("660", "UTC-2 (Cape Verde)"),
    ("720", "UTC (GMT)"), ("780", "UTC+1 (Amsterdam)"),
    ("840", "UTC+2 (Cairo)"), ("900", "UTC+3 (Baghdad)"),
    ("930", "UTC+3:30 (Tehran)"), ("960", "UTC+4 (Abu Dhabi)"),
    ("990", "UTC+4:30 (Kabul)"), ("1020", "UTC+5 (Yekaterinburg)"),
    ("1050", "UTC+5:30 (Madras)"), ("1065", "UTC+5:45 (Kathmandu)"),
    ("1080", "UTC+6 (Alma-Ata)"), ("1110", "UTC+6:30 (Rangoon)"),
    ("1140", "UTC+7 (Bangkok)"), ("1200", "UTC+8 (Beijing)"),
    ("1260", "UTC+9 (Tokyo)"), ("1290", "UTC+9:30 (Adelaide)"),
    ("1320", "UTC+10 (Brisbane)"), ("1380", "UTC+11 (Magadan)"),
    ("1440", "UTC+12 (Fiji)"), ("1500", "UTC+13 (Nuku'alofa)"),
]


def do_time(op, tz="1080"):
    """Date/time view (blocks 28/29) + timezone set (stored = tz - 720)."""
    if not _ensure_auth():
        return {"ok": False, "error": "not-authenticated"}
    try:
        cfg = json.loads(cdp_eval("JSON.stringify($.readEx(28))"))
        now = json.loads(cdp_eval("JSON.stringify($.readEx(29))"))
    except Exception:
        return {"ok": False, "error": "parse-error"}
    stored = str(cfg.get("timeZone", "360"))
    if op == "get":
        gmt = cdp_eval("JSON.stringify($.instr('systool sntpc -getGmtStatus'))")
        try:
            gmt = str(json.loads(gmt).get("data", "")).strip()
        except Exception:
            gmt = ""
        return {"ok": True, "timeZone": stored,
                "tzSel": str(int(stored) + 720), "gmt": gmt,
                "clock": {"year": now.get("year"), "month": now.get("month"),
                          "day": now.get("day"), "hour": now.get("hour"),
                          "minute": now.get("minute"), "second": now.get("second"),
                          "sntpOk": now.get("sntpcSuccess")}}
    if op == "set":
        try:
            sel = int(tz)
        except Exception:
            return {"ok": False, "error": "bad-tz"}
        return do_write_fields(28, {"timeZone": str(sel - 720)})
    return {"ok": False, "error": "bad-op"}


def do_arp():
    """Live ARP table: name\r\rmac\r\rip\r\rbindFlag per line."""
    if not _ensure_auth():
        return {"ok": False, "error": "not-authenticated"}
    r = cdp_eval("JSON.stringify($.instr('main staMgt -get arp'))")
    try:
        data = str(json.loads(r).get("data", ""))
    except Exception:
        return {"ok": False, "error": "bad-response"}
    out = []
    for line in (data.split("\r\n") if data else []):
        parts = line.split("\r\r")
        if len(parts) >= 3:
            out.append({"name": parts[0] or "(anonymous)",
                        "mac": parts[1] or "", "ip": parts[2] or "",
                        "bind": parts[3] if len(parts) > 3 else ""})
    return {"ok": True, "arp": out}


def do_ipmac(op, ip="", mac="", name=""):
    """IP-MAC binding via main staMgt bind verbs (block 12 bindEntry)."""
    if not _ensure_auth():
        return {"ok": False, "error": "not-authenticated"}
    import urllib.parse as _up
    import re as _re
    if op == "list":
        raw = cdp_eval("JSON.stringify($.readEx(12))")
        try:
            b = json.loads(raw)
        except Exception:
            return {"ok": False, "error": "parse-error"}
        binds = [x for x in b.get("list", []) if x.get("bindEntry") == "1"]
        return {"ok": True, "binds": binds}
    if op in ("add", "delete", "clear"):
        ip = ip.strip()
        mac = (mac or "").strip().upper()
        if not _re.match(r"^\d{1,3}(\.\d{1,3}){3}$", ip) or \
           not _re.match(r"^([0-9A-F]{2}-){5}[0-9A-F]{2}$", mac):
            return {"ok": False, "error": "bad-ip-or-mac"}
        cmd = f"main staMgt -{op} bind ip:{ip} mac:{mac} name:{_up.quote(name or '')}"
        r = cdp_eval("JSON.stringify($.instr(" + json.dumps(cmd) + "))")
        try:
            o = json.loads(r)
        except Exception:
            return {"ok": False, "error": "bad-response"}
        return {"ok": o.get("errorno") == 0, "errorno": o.get("errorno")}
    return {"ok": False, "error": "bad-op"}


PW_MASK_KEYS = ("paswd", "passwd")


def _scrub_passwords(b):
    for k in list(b.keys()):
        if k.lower() in PW_MASK_KEYS and b[k]:
            b[k] = "***set***"
    return b


def _valid_ip(ip):
    import re as _re
    if not _re.match(r"^\d{1,3}(\.\d{1,3}){3}$", ip or ""):
        return False
    return all(0 <= int(p) <= 255 for p in ip.split("."))


def do_wan(op, wtype=None, f=None):
    """ISP-level WAN: link type + PPPoE/static/L2TP/PPTP creds + IPTV mode.

    Mirrors the stock pages: writes LINK(22) + the type block, then
    bounces WAN (linkDown/linkUp) so settings take effect without reboot.
    Passwords: blank means 'keep existing'; real values never leave here.
    """
    if not _ensure_auth():
        return {"ok": False, "error": "not-authenticated"}
    f = f or {}
    if op == "get":
        out = {}
        for bid in (22, 24, 26, 38, 39, 37):
            raw = cdp_eval(f"JSON.stringify($.readEx({bid}))")
            try:
                out[str(bid)] = _scrub_passwords(json.loads(raw))
            except Exception:
                return {"ok": False, "error": "parse-error"}
        return {"ok": True, "wan": out}
    if op in ("set_dynamic", "set_pppoe", "set_static",
              "set_l2tp", "set_pptp"):
        type_map = {"set_dynamic": "0", "set_static": "1",
                    "set_pppoe": "2", "set_l2tp": "3", "set_pptp": "4"}
        wt = type_map[op]
        writes = []  # (bid, {field: value})
        if op == "set_pppoe":
            name = (f.get("name") or "").strip()
            if not name:
                return {"ok": False, "error": "pppoe-user-required"}
            mtu = str(f.get("mtu") or "1480")
            if not mtu.isdigit() or not 576 <= int(mtu) <= 1492:
                return {"ok": False, "error": "mtu must be 576-1492"}
            pf = {"name": name, "lcpMru": mtu,
                  "fixipEnb": "1" if str(f.get("fixipEnb")) == "1" else "0",
                  "fixip": f.get("fixip") or "0.0.0.0",
                  "manualDns": "1" if str(f.get("manualDns")) == "1" else "0"}
            if pf["fixipEnb"] == "1" and not _valid_ip(pf["fixip"]):
                return {"ok": False, "error": "bad-fixed-ip"}
            dns = [f.get("dns1") or "0.0.0.0", f.get("dns2") or "0.0.0.0"]
            if pf["manualDns"] == "1" and not all(map(_valid_ip, dns)):
                return {"ok": False, "error": "bad-dns"}
            pf["dns.0"], pf["dns.1"] = dns
            if f.get("paswd"):  # blank = keep existing password
                pf["paswd"] = f["paswd"]
            writes.append((26, pf))
        elif op == "set_static":
            need = {k: (f.get(k) or "").strip()
                    for k in ("ip", "mask", "gateway", "mtu")}
            if not all(map(_valid_ip, (need["ip"], need["mask"],
                                       need["gateway"]))):
                return {"ok": False, "error": "bad-static-ip"}
            if not need["mtu"].isdigit() or not 576 <= int(need["mtu"]) <= 1500:
                return {"ok": False, "error": "mtu must be 576-1500"}
            dns = [f.get("dns1") or "0.0.0.0", f.get("dns2") or "0.0.0.0"]
            if not all(map(_valid_ip, dns)):
                return {"ok": False, "error": "bad-dns"}
            writes.append((24, {"ip": need["ip"], "mask": need["mask"],
                                "gateway": need["gateway"], "mtu": need["mtu"],
                                "dns.0": dns[0], "dns.1": dns[1]}))
        elif op in ("set_l2tp", "set_pptp"):
            bid = 39 if op == "set_l2tp" else 38
            user = (f.get("user") or "").strip()
            srv = (f.get("server") or "").strip()
            if not user or not srv:
                return {"ok": False, "error": "user-and-server-required"}
            mtu = str(f.get("mtu") or "1460")
            if not mtu.isdigit() or not 576 <= int(mtu) <= 1500:
                return {"ok": False, "error": "mtu must be 576-1500"}
            tf = {"userName": user, "domainIp": srv, "mtu": mtu,
                  "bDhcp": "0" if str(f.get("static")) == "1" else "1"}
            if tf["bDhcp"] == "0":
                for k in ("ip", "mask", "gateway"):
                    v = (f.get(k) or "").strip()
                    if not _valid_ip(v):
                        return {"ok": False, "error": "bad-tunnel-ip"}
                    tf[k] = v
            if f.get("paswd"):
                tf["passwd"] = f["paswd"]
            writes.append((bid, tf))
        writes.append((22, {"linkType": wt}))
        for bid, fields in writes:
            r = do_write_fields(bid, fields)
            if not r.get("ok"):
                return {"ok": False, "error": "write-failed",
                        "block": bid, "detail": r}
        for verb in ("wan -linkDown", "wan -linkUp"):
            r = cdp_eval("JSON.stringify($.instr(" +
                         json.dumps(verb) + "))")
            try:
                if json.loads(r).get("errorno") != 0:
                    return {"ok": False, "error": "reconnect-failed",
                            "verb": verb}
            except Exception:
                return {"ok": False, "error": "bad-response"}
            time.sleep(2)
        return {"ok": True, "linkType": wt}
    if op == "set_iptv":
        mode = str(f.get("uMode", "0"))
        if mode not in ("0", "1", "3", "13"):
            return {"ok": False, "error": "bad-iptv-mode"}
        fields = {"uMode": mode}
        if mode == "1" and "uBridgePorts" in f:
            fields["uBridgePorts"] = str(f["uBridgePorts"])
        if mode == "13":
            import re as _re2
            for k, v in f.items():
                if _re2.match(r"^uService\.[0-3]\.(uVid|uVlanPriority|"
                              r"bTagEnable)$", k):
                    fields[k] = str(v)
        return do_write_fields(37, fields)
    return {"ok": False, "error": "bad-op"}


def _valid_mac(mac):
    import re as _re
    return bool(_re.match(r"^([0-9A-F]{2}-){5}[0-9A-F]{2}$",
                          (mac or "").strip().upper()))


def do_ddns(op, f=None):
    """DDNS (block 40): 2 provider slots. Blank password = keep existing."""
    if not _ensure_auth():
        return {"ok": False, "error": "not-authenticated"}
    f = f or {}
    if op == "get":
        raw = cdp_eval("JSON.stringify($.readEx(40))")
        try:
            return {"ok": True, "ddns": _scrub_passwords(json.loads(raw))}
        except Exception:
            return {"ok": False, "error": "parse-error"}
    if op == "set":
        try:
            idx = int(f.get("idx", 0))
        except Exception:
            return {"ok": False, "error": "bad-slot"}
        if idx not in (0, 1):
            return {"ok": False, "error": "bad-slot"}
        pf = {f"serviceList.{idx}.enable":
              "1" if str(f.get("enable")) == "1" else "0",
              f"serviceList.{idx}.username": (f.get("username") or "")[:64],
              f"serviceList.{idx}.domainName": (f.get("domain") or "")[:64]}
        if f.get("password"):
            pf[f"serviceList.{idx}.password"] = f["password"]
        return do_write_fields(40, pf)
    return {"ok": False, "error": "bad-op"}


def do_rmt(op, f=None):
    """Remote/local web management (blocks 7/6). Stock semantics:
    rule 0=remote OFF, 1=all IPs, 2=single IP; port 1024-65535."""
    if not _ensure_auth():
        return {"ok": False, "error": "not-authenticated"}
    f = f or {}
    if op == "get":
        out = {}
        for bid in (5, 6, 7):
            raw = cdp_eval(f"JSON.stringify($.readEx({bid}))")
            try:
                out[str(bid)] = json.loads(raw)
            except Exception:
                return {"ok": False, "error": "parse-error"}
        return {"ok": True, "rmt": out}
    if op == "set_remote":
        rule = str(f.get("rule", "0"))
        if rule not in ("0", "1", "2"):
            return {"ok": False, "error": "bad-rule"}
        port = str(f.get("port") or "8888")
        if not port.isdigit() or not 1024 <= int(port) <= 65535:
            return {"ok": False, "error": "port must be 1024-65535"}
        addr = (f.get("addr") or "0.0.0.0").strip()
        if rule == "2" and not _valid_ip(addr):
            return {"ok": False, "error": "bad-addr"}
        return do_write_fields(7, {"rule": rule, "port": port,
                                   "addr": addr})
    if op == "set_local":
        macs = [ (f.get("macs") or []) + ["", "", "", ""] ] [0][:4]
        pf = {"enableAll": "1" if str(f.get("enableAll")) == "1" else "0"}
        for i, m in enumerate(macs):
            m = (m or "").strip().upper()
            if pf["enableAll"] == "0" and m and not _valid_mac(m):
                return {"ok": False, "error": f"bad-mac-{i}"}
            pf[f"mac.{i}"] = m or "00-00-00-00-00-00"
        return do_write_fields(6, pf)
    return {"ok": False, "error": "bad-op"}


def do_route(op, net="", mask="", gateway="", idx=None):
    """Static routes via `main route -stc ...` (block 14 = table)."""
    if not _ensure_auth():
        return {"ok": False, "error": "not-authenticated"}
    if op == "list":
        out = {}
        for bid in (14, 16):
            raw = cdp_eval(f"JSON.stringify($.readEx({bid}))")
            try:
                out[str(bid)] = json.loads(raw)
            except Exception:
                return {"ok": False, "error": "parse-error"}
        return {"ok": True, "routes": out}
    if op == "add":
        if not all(map(_valid_ip, (net, mask, gateway))):
            return {"ok": False, "error": "bad-route-ip"}
        cmd = (f"main route -stc -add index:0 net:{net.strip()} "
               f"mask:{mask.strip()} gateway:{gateway.strip()} valid")
    elif op == "delete":
        try:
            idx = int(idx)
        except Exception:
            return {"ok": False, "error": "bad-index"}
        cmd = f"main route -stc -delete index:{idx}"
    elif op == "clear":
        cmd = "main route -stc -clr"
    else:
        return {"ok": False, "error": "bad-op"}
    r = cdp_eval("JSON.stringify($.instr(" + json.dumps(cmd) + "))")
    try:
        o = json.loads(r)
    except Exception:
        return {"ok": False, "error": "bad-response"}
    return {"ok": o.get("errorno") == 0, "errorno": o.get("errorno")}


def do_syslog():
    """Download the full syslog text (stock logSave URL, page session)."""
    if not _ensure_auth():
        return {"ok": False, "error": "not-authenticated"}
    js = ("(async function(){var r=await fetch($.orgURL($.domainUrl+"
          "'syslog.txt?code='+TDDP_INSTRUCT+'&asyn=0&disposition=1'),"
          "{credentials:'include'});return await r.text();})()")
    try:
        txt = cdp_eval(js, await_promise=True)
    except Exception as e:
        return {"ok": False, "error": f"backend-error: {e}"}
    if not isinstance(txt, str):
        return {"ok": False, "error": "bad-response"}
    return {"ok": True, "log": txt}


def do_detect():
    """Network health self-checks from the WDS wizard: LAN-IP conflict +
    rogue-DHCP-server detection. Read-only diagnostics."""
    if not _ensure_auth():
        return {"ok": False, "error": "not-authenticated"}

    def run(cmd):
        r = cdp_eval("JSON.stringify($.instr(" + json.dumps(cmd) + "))")
        try:
            return str(json.loads(r).get("data", "")).strip()
        except Exception:
            return ""

    for _ in range(12):
        if run("wlan lanIpConflictStatus") == "2":
            break
        time.sleep(2)
    ip_conflict = run("wlan lanIpConflictResult")
    for _ in range(12):
        if run("wlan dhcpsDetectStatus") == "2":
            break
        time.sleep(2)
    dhcp = run("wlan dhcpsDetectResult")
    # result "0" = clean on a healthy net; anything else names the culprit
    # (conflicting IP / rogue DHCP server IP) — shown raw, never guessed.
    return {"ok": True, "lanIpConflict": ip_conflict or "?",
            "lanIpClear": ip_conflict == "0",
            "rogueDhcp": dhcp or "?",
            "dhcpClear": dhcp == "0"}


def do_restore(b64, filename="restore.bin"):
    """Config restore: upload a backup file through the logged-in router
    page (same URL + session the stock page uses). ~4KB files only."""
    if not _ensure_auth():
        return {"ok": False, "error": "not-authenticated"}
    import base64 as _b64
    try:
        blob = _b64.b64decode(b64 or "", validate=True)
    except Exception:
        return {"ok": False, "error": "bad-file"}
    if not blob or len(blob) > 65536:
        return {"ok": False, "error": "file must be 1B-64KB"}
    if not (filename or "").lower().endswith(".bin"):
        return {"ok": False, "error": "expecting a .bin backup"}
    js = ("(async function(){try{"
          "var raw=atob(" + json.dumps(b64) + ");"
          "var by=new Uint8Array(raw.length);"
          "for(var i=0;i<raw.length;i++)by[i]=raw.charCodeAt(i);"
          "var fd=new FormData();"
          "fd.append('fileName',new Blob([by],{type:'application/octet-stream'}),"
          + json.dumps(filename) + ");"
          "var url=$.orgURL($.domainUrl+'?code='+9+'&asyn=0');"
          "var r=await fetch(url,{method:'POST',body:fd,credentials:'include'});"
          "var t=await r.text();"
          "return JSON.stringify({status:r.status,len:t.length,"
          "head:t.slice(0,160)});}catch(e){return JSON.stringify({error:String(e)});}})()")
    try:
        r = cdp_eval(js, await_promise=True)
        o = json.loads(r or "{}")
    except Exception:
        return {"ok": False, "error": "bad-response"}
    if o.get("error"):
        return {"ok": False, "error": "upload-failed", "detail": o["error"][:120]}
    return {"ok": o.get("status") == 200, "status": o.get("status"),
            "note": "sent; if the file is valid the router reboots now"}


def do_device(op, mac="", name="", up="0", down="0", blocked=None):
    """Device block/rename/limit via staMgt instr (block 13 is read-only)."""
    if not _ensure_auth():
        return {"ok": False, "error": "not-authenticated"}
    import urllib.parse as _up
    mac = (mac or "").upper()
    import re as _re
    if not _re.match(r"^([0-9A-F]{2}-){5}[0-9A-F]{2}$", mac):
        return {"ok": False, "error": "bad-mac"}
    if op in ("block", "unblock", "rename", "limit", "set"):
        cmd = (f"main staMgt -add mac:{mac} name:{_up.quote(name or '')} "
               f"upload:{up} download:{down}")
        if op == "block" or (op == "set" and str(blocked) == "1"):
            cmd += " blocked"
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
                                              data.get("ssid"),
                                              data.get("bcast"),
                                              data.get("enable")))
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
            if u.path == "/api/instr":
                return self._json(do_instr(data.get("cmd", "")))

            if u.path == "/api/speedtest":
                return self._json(do_speedtest(data.get("mb", 10)))
            if u.path == "/api/dns":
                return self._json(do_dns(data.get("dns1", ""),
                                         data.get("dns2", ""),
                                         data.get("auto", False)))
            if u.path == "/api/device":
                return self._json(do_device(
                    data.get("op"), data.get("mac", ""),
                    data.get("name", ""), data.get("up", "0"),
                    data.get("down", "0"), data.get("blocked")))
            if u.path == "/api/diag":
                return self._json(do_diag(
                    data.get("action"), data.get("type", "ping"),
                    data.get("target", ""), data.get("size", "64"),
                    data.get("count", "4"), data.get("timeout", "800"),
                    data.get("hops", "20"), data.get("icmpId")))
            if u.path == "/api/scan":
                return self._json(do_scan())
            if u.path == "/api/wds":
                return self._json(do_wds(
                    data.get("op"), data.get("ssid", ""),
                    data.get("key", ""), data.get("bssid", "")))
            if u.path == "/api/macclone":
                return self._json(do_macclone(
                    data.get("op"), data.get("mac", "")))
            if u.path == "/api/time":
                return self._json(do_time(
                    data.get("op"), data.get("tz", "1080")))
            if u.path == "/api/arp":
                return self._json(do_arp())
            if u.path == "/api/ipmac":
                return self._json(do_ipmac(
                    data.get("op"), data.get("ip", ""),
                    data.get("mac", ""), data.get("name", "")))
            if u.path == "/api/wan":
                return self._json(do_wan(
                    data.get("op"), data.get("wtype"),
                    data.get("f") or {}))
            if u.path == "/api/ddns":
                return self._json(do_ddns(
                    data.get("op"), data.get("f") or {}))
            if u.path == "/api/rmt":
                return self._json(do_rmt(
                    data.get("op"), data.get("f") or {}))
            if u.path == "/api/route":
                return self._json(do_route(
                    data.get("op"), data.get("net", ""),
                    data.get("mask", ""), data.get("gateway", ""),
                    data.get("idx")))
            if u.path == "/api/restore":
                return self._json(do_restore(
                    data.get("b64", ""), data.get("filename", "restore.bin")))
            if u.path == "/api/detect":
                return self._json(do_detect())
            if u.path == "/api/syslog":
                return self._json(do_syslog())
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
        elif u.path == "/api/traffic":
            try:
                self._json(do_traffic())
            except Exception as e:
                self._json({"ok": False, "error": f"backend-error: {e}"}, 500)
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
