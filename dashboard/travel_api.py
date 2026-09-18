#!/usr/bin/env python3
"""travel_api.py — PORTABLE MW325R panel backend (no Chrome, no third-party).

Same HTTP API as router_api.py (the SAME control.html works with either),
but talks to the router over DIRECT TDDP (tddp.py, stdlib only) instead of
CDP + headless Chrome.

Why: the Chrome stack only runs on a PC. This file runs anywhere Python 3
runs — PC, Raspberry Pi, or an Android phone under Termux — so the router
can be controlled while traveling with NO laptop.

Usage:
  python3 travel_api.py                 # localhost:8101 only
  python3 travel_api.py 8101            # custom port
  python3 travel_api.py 8101 --lan      # also reachable from home LAN
                                       # (e.g. phone browser). LAN-only!
Point control.html at it with:  control.html?api=http://<host>:<port>
Password lives in RAM only (the TDDP session id), never on disk/log.
"""
import json
import re
import sys
import threading
import time
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer

import tddp

_state = {"t": tddp.TDDP()}
_lock = threading.Lock()
EUNAUTH = 7
ALLOWED_INSTR = ("systool ", "forward ", "advanced ", "main ",
                 "wan ", "wlan ", "arpMap")
IPRE = r"^\d{1,3}(\.\d{1,3}){3}$"
MACRE = r"^([0-9A-F]{2}-){5}[0-9A-F]{2}$"


def _ensure_auth():
    t = _state["t"]
    if not t.session:
        return False
    try:
        r = t.read(29)  # tiny clock block doubles as session probe
    except Exception:
        return True  # transport blip: keep session, let the op decide
    if not r.get("ok") and r.get("errorno") == EUNAUTH:
        t.session = ""
        return False
    return True


def _auth(fn):
    def w(*a, **k):
        with _lock:
            if not _ensure_auth():
                return {"ok": False, "error": "not-authenticated"}
            try:
                return fn(*a, **k)
            except Exception as e:
                return {"ok": False, "error": "backend-error: %s" % e}
    return w


def do_login(password):
    with _lock:
        if not password:
            return {"ok": False, "error": "empty-password"}
        return _state["t"].login(password)


def _read(bid):
    r = _state["t"].read(bid)
    if not r.get("ok"):
        return r
    return {"ok": True, "block": r["block"]}


@_auth
def overview():
    out = {}
    for bid in (0, 1, 9, 33):
        r = _read(bid)
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


@_auth
def read_block(bid):
    try:
        return _read(int(bid))
    except Exception:
        return {"ok": False, "error": "bad-id"}


@_auth
def do_reboot():
    r = _state["t"].reboot()
    return {"ok": r.get("errorno") == 0, "errorno": r.get("errorno")}


@_auth
def do_set_wps(enabled):
    val = "1" if str(enabled) in ("1", "true", "on") else "0"
    r = _state["t"].write_block(33, {"wps.bEnabled": val})
    if not r.get("ok"):
        return {"ok": False, "errorno": r.get("errorno")}
    cur = _state["t"].read(33)["block"]["wps"]["bEnabled"]
    return {"ok": cur == val, "wpsEnabled": cur, "errorno": 0}


@_auth
def do_set_upnp(enabled):
    val = "1" if str(enabled) in ("1", "true", "on") else "0"
    r = _state["t"].write_block(19, {"igdEnable": val})
    if not r.get("ok"):
        return {"ok": False, "errorno": r.get("errorno")}
    cur = _state["t"].read(19)["block"].get("igdEnable")
    return {"ok": str(cur) == str(val), "igdEnable": cur, "errorno": 0}


@_auth
def do_set_wifi(key=None, ssid=None):
    if key is not None and not (8 <= len(key) <= 63):
        return {"ok": False, "error": "key must be 8-63 chars"}
    if ssid is not None and not (1 <= len(ssid) <= 32):
        return {"ok": False, "error": "ssid must be 1-32 chars"}
    f = {}
    if key is not None:
        f["cPskSecret"] = key
    if ssid is not None:
        f["cSsid"] = ssid
    r = _state["t"].write_block(33, f)
    return {"ok": r.get("errorno") == 0, "errorno": r.get("errorno")}


@_auth
def do_write_fields(bid, fields):
    if not isinstance(fields, dict) or not fields:
        return {"ok": False, "error": "empty-fields"}
    try:
        bid = int(bid)
    except Exception:
        return {"ok": False, "error": "bad-id"}
    for k in fields:
        if not isinstance(k, str) or not k.replace(".", "").replace(
                "_", "").isalnum():
            return {"ok": False, "error": f"bad-key: {k}"}
    r = _state["t"].write_block(bid, fields)
    return {"ok": r.get("errorno") == 0, "errorno": r.get("errorno")}


@_auth
def do_change_admin(old_pw, new_pw):
    if not old_pw or not new_pw:
        return {"ok": False, "error": "empty-password"}
    if len(new_pw) < 1 or len(new_pw) > 63:
        return {"ok": False, "error": "bad-length"}
    r = _state["t"].change_password(old_pw, new_pw)
    out = {"ok": r.get("errorno") == 0, "errorno": r.get("errorno")}
    if out["ok"]:
        _state["t"].session = ""  # password changed: force re-login
    return out


@_auth
def do_factory_reset():
    r = _state["t"].reset()
    return {"ok": r.get("errorno") == 0, "errorno": r.get("errorno")}


@_auth
def do_backup():
    return _state["t"].backup()


@_auth
def do_instr(cmd):
    if not isinstance(cmd, str) or not cmd.startswith(ALLOWED_INSTR):
        return {"ok": False, "error": "blocked-prefix"}
    if len(cmd) > 300:
        return {"ok": False, "error": "too-long"}
    r = _state["t"].instr(cmd)
    return {"ok": r.get("errorno") == 0, "errorno": r.get("errorno"),
            "data": r.get("data")}


def _valid_ip(ip):
    if not re.match(IPRE, ip or ""):
        return False
    return all(0 <= int(p) <= 255 for p in ip.split("."))


@_auth
def do_fwd(op, idx=None, ip="", lport="", start="", end="", ptc="0"):
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
    r = _state["t"].instr(cmd)
    return {"ok": r.get("errorno") == 0, "errorno": r.get("errorno")}


@_auth
def do_traffic():
    A = _state["t"].read(23)["block"]
    time.sleep(2)
    B = _state["t"].read(23)["block"]
    try:
        up = (int(B.get("outOctets", 0)) - int(A.get("outOctets", 0))) * 8 / 2
        down = (int(B.get("inOctets", 0)) - int(A.get("inOctets", 0))) * 8 / 2
        return {"ok": True, "up_bps": max(0, int(up)),
                "down_bps": max(0, int(down)),
                "wanIp": B.get("ip", ""), "uptime": B.get("upTime", ""),
                "totUpMB": round(int(B.get("outOctets", 0)) / 1e6, 1),
                "totDownMB": round(int(B.get("inOctets", 0)) / 1e6, 1)}
    except Exception as e:
        return {"ok": False, "error": f"parse: {e}"}


def do_speedtest(mb=10):
    mb = max(1, min(int(mb), 50))
    url = f"https://cachefly.cachefly.net/{mb}mb.test"
    try:
        t0 = time.time()
        req = urllib.request.Request(url,
                                     headers={"User-Agent": "Mozilla/5.0"})
        n = 0
        with urllib.request.urlopen(req, timeout=60) as r:
            while True:
                chunk = r.read(65536)
                if not chunk:
                    break
                n += len(chunk)
        dt = max(time.time() - t0, 0.01)
        return {"ok": True, "mbps": round(n * 8 / dt / 1e6, 1),
                "mb": round(n / 1e6, 1), "sec": round(dt, 1)}
    except Exception as e:
        return {"ok": False, "error": str(e)[:120]}


@_auth
def do_dns(dns1, dns2="", auto=False):
    if auto:
        fields = {"manualDns": "0"}
    else:
        if not re.match(IPRE, dns1 or ""):
            return {"ok": False, "error": "bad-dns1"}
        if dns2 and not re.match(IPRE, dns2):
            return {"ok": False, "error": "bad-dns2"}
        fields = {"manualDns": "1", "dns.0": dns1,
                  "dns.1": dns2 or "0.0.0.0"}
    r = _state["t"].write_block(25, fields)
    return {"ok": r.get("errorno") == 0, "errorno": r.get("errorno")}


@_auth
def do_diag(action, dtype="ping", target="", size="64", count="4",
            timeout="800", hops="20", icmpId=None):
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
        r = _state["t"].instr(cmd)
        if r.get("errorno") != 0:
            return {"ok": False, "errorno": r.get("errorno")}
        try:
            return {"ok": True, "icmpId": int(str(r.get("data", "")).strip())}
        except Exception:
            return {"ok": False, "error": "no-icmpid", "data": r.get("data")}
    if icmpId is None:
        return {"ok": False, "error": "empty-icmpid"}
    code = "2" if action == "poll" else "1" if action == "stop" else None
    if code is None:
        return {"ok": False, "error": "bad-action"}
    r = _state["t"].instr(
        f"systool {dtype} code:{code} icmpId:{int(icmpId)}")
    if action == "poll" and r.get("errorno") == 0:
        data = str(r.get("data", ""))
        pos = data.find("\r\n")
        if pos >= 0:
            return {"ok": True, "finished": data[:pos].strip(),
                    "text": data[pos + 2:]}
    return {"ok": r.get("errorno") == 0, "errorno": r.get("errorno"),
            "data": r.get("data")}


@_auth
def do_scan():
    r = _state["t"].instr("wlan scan")
    if r.get("errorno") != 0:
        return {"ok": False, "error": "scan-start-failed"}
    for _ in range(20):
        time.sleep(1)
        st = _state["t"].instr("wlan scanStatus")
        if str(st.get("data", "")).strip() == "1":
            break
    b = _state["t"].read(36)["block"]
    aps = []
    for e in b.get("apEntry", []):
        if not isinstance(e, dict) or not e.get("cBssid") or \
                e.get("cBssid", "").startswith("00-00-00-00"):
            continue
        aps.append({"bssid": e.get("cBssid"),
                    "ssid": (e.get("cSsid") or "").strip(),
                    "rssi": e.get("uRssi"), "channel": e.get("uChannel"),
                    "auth": e.get("uAuthMode"), "width": e.get("uChanWidth")})
    aps.sort(key=lambda a: -int(a["rssi"] or 0))
    return {"ok": True, "count": len(aps), "aps": aps}


_WDS_STATES = {"0": "disconnected", "1": "init", "2": "scan",
               "3": "auth", "4": "assoc", "5": "connected"}


@_auth
def do_wds(op, ssid="", key="", bssid=""):
    if op == "get":
        b = _state["t"].read(32)["block"]
        st = _state["t"].instr("wlan wdsstatus")
        wds = str(st.get("data", "")).strip()
        apc = b.get("apc", {})
        return {"ok": True,
                "bridgeEnabled": apc.get("bBridgeEnabled"),
                "ssid": apc.get("cBridgedSsid", ""),
                "bssid": apc.get("cBridgedBssid", ""),
                "security": apc.get("uSecurityType"),
                "wdsStatus": _WDS_STATES.get(wds, wds)}
    if op == "connect":
        ssid = ssid.strip()
        if not ssid:
            return {"ok": False, "error": "empty-ssid"}
        if key and not (8 <= len(key) <= 63):
            return {"ok": False, "error": "key must be 8-63 for WPA"}
        bssid = (bssid or "").strip().upper()
        if not re.match(MACRE, bssid):
            bssid = "00-00-00-00-00-00"
        r = _state["t"].write_block(32, {
            "apc.bBridgeEnabled": "1", "apc.cBridgedSsid": ssid,
            "apc.cBridgedBssid": bssid,
            "apc.uSecurityType": "4" if key else "1",
            "apc.cPassWD": key})
        return {"ok": r.get("errorno") == 0, "errorno": r.get("errorno")}
    if op == "disconnect":
        r = _state["t"].write_block(32, {"apc.bBridgeEnabled": "0"})
        return {"ok": r.get("errorno") == 0, "errorno": r.get("errorno")}
    return {"ok": False, "error": "bad-op"}


@_auth
def do_macclone(op, mac=""):
    if op == "get":
        b = _state["t"].read(1)["block"]
        pc = _state["t"].peer_mac().get("data", "")
        pc = str(pc).strip().split("\r\n")[0] if pc else ""
        return {"ok": True,
                "lanMac": (b.get("mac") or ["?", "?"])[0],
                "wanMac": (b.get("mac") or ["?", "?"])[1],
                "wanMacType": b.get("wanMacType"),
                "pcMac": pc}
    if op == "set":
        mac = (mac or "").strip().upper()
        if not re.match(MACRE, mac):
            return {"ok": False, "error": "bad-mac-format"}
        if mac in ("00-00-00-00-00-00", "FF-FF-FF-FF-FF-FF"):
            return {"ok": False, "error": "invalid-mac"}
        lan = (_state["t"].read(1)["block"].get("mac") or ["?"])[0].upper()
        if mac == lan:
            return {"ok": False, "error": "wan-mac-equals-lan-mac"}
        r = _state["t"].write_block(1, {"mac.1": mac, "wanMacType": "2"})
        return {"ok": r.get("errorno") == 0, "errorno": r.get("errorno")}
    return {"ok": False, "error": "bad-op"}


TZ_OPTIONS = [(str(v), l) for v, l in [
    (0, "UTC-12"), (60, "UTC-11"), (120, "UTC-10"), (180, "UTC-9"),
    (240, "UTC-8"), (300, "UTC-7"), (360, "UTC-6"), (420, "UTC-5"),
    (510, "UTC-4:30"), (540, "UTC-3"), (600, "UTC-3:30"), (660, "UTC-2"),
    (720, "UTC (GMT)"), (780, "UTC+1"), (840, "UTC+2"), (900, "UTC+3"),
    (930, "UTC+3:30"), (960, "UTC+4"), (990, "UTC+4:30"),
    (1020, "UTC+5"), (1050, "UTC+5:30"), (1065, "UTC+5:45"),
    (1080, "UTC+6"), (1110, "UTC+6:30"), (1140, "UTC+7"), (1200, "UTC+8"),
    (1260, "UTC+9"), (1290, "UTC+9:30"), (1320, "UTC+10"),
    (1380, "UTC+11"), (1440, "UTC+12"), (1500, "UTC+13")]]


@_auth
def do_time(op, tz="1080"):
    cfg = _state["t"].read(28)["block"]
    now = _state["t"].read(29)["block"]
    stored = str(cfg.get("timeZone", "360"))
    if op == "get":
        gmt = str(_state["t"].instr(
            "systool sntpc -getGmtStatus").get("data", "")).strip()
        return {"ok": True, "timeZone": stored,
                "tzSel": str(int(stored) + 720), "gmt": gmt,
                "clock": {"year": now.get("year"), "month": now.get("month"),
                          "day": now.get("day"), "hour": now.get("hour"),
                          "minute": now.get("minute"),
                          "second": now.get("second"),
                          "sntpOk": now.get("sntpcSuccess")}}
    if op == "set":
        try:
            sel = int(tz)
        except Exception:
            return {"ok": False, "error": "bad-tz"}
        r = _state["t"].write_block(28, {"timeZone": str(sel - 720)})
        return {"ok": r.get("errorno") == 0, "errorno": r.get("errorno")}
    return {"ok": False, "error": "bad-op"}


@_auth
def do_arp():
    data = str(_state["t"].instr("main staMgt -get arp").get("data", ""))
    out = []
    for line in (data.split("\r\n") if data else []):
        parts = line.split("\r\r")
        if len(parts) >= 3:
            out.append({"name": parts[0] or "(anonymous)",
                        "mac": parts[1] or "", "ip": parts[2] or "",
                        "bind": parts[3] if len(parts) > 3 else ""})
    return {"ok": True, "arp": out}


@_auth
def do_ipmac(op, ip="", mac="", name=""):
    if op == "list":
        b = _state["t"].read(12)["block"]
        binds = [x for x in b.get("list", [])
                 if isinstance(x, dict) and x.get("bindEntry") == "1"]
        return {"ok": True, "binds": binds}
    if op in ("add", "delete", "clear"):
        ip = ip.strip()
        mac = (mac or "").strip().upper()
        if not re.match(IPRE, ip) or not re.match(MACRE, mac):
            # clear needs no ip/mac; validate only for add/delete
            if op != "clear":
                return {"ok": False, "error": "bad-ip-or-mac"}
        qn = urllib.parse.quote(name or "")
        if op == "clear":
            cmd = "main staMgt -clr bind"
        else:
            cmd = (f"main staMgt -{op} bind ip:{ip} mac:{mac} "
                   f"name:{qn}")
        r = _state["t"].instr(cmd)
        return {"ok": r.get("errorno") == 0, "errorno": r.get("errorno")}
    return {"ok": False, "error": "bad-op"}


@_auth
def do_device(op, mac="", name="", up="0", down="0", blocked=None):
    mac = (mac or "").upper()
    if not re.match(MACRE, mac):
        return {"ok": False, "error": "bad-mac"}
    if op in ("block", "unblock", "rename", "limit", "set"):
        cmd = (f"main staMgt -add mac:{mac} "
               f"name:{urllib.parse.quote(name or '')} "
               f"upload:{up} download:{down}")
        if op == "block" or (op == "set" and str(blocked) == "1"):
            cmd += " blocked"
    else:
        return {"ok": False, "error": "bad-op"}
    r = _state["t"].instr(cmd)
    return {"ok": r.get("errorno") == 0, "errorno": r.get("errorno")}


@_auth
def do_ddns(op, f=None):
    f = f or {}
    if op == "get":
        b = _state["t"].read(40)["block"]
        for s in b.get("serviceList", []):
            if isinstance(s, dict) and s.get("password"):
                s["password"] = "***set***"
        return {"ok": True, "ddns": b}
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
        r = _state["t"].write_block(40, pf)
        return {"ok": r.get("errorno") == 0, "errorno": r.get("errorno")}
    return {"ok": False, "error": "bad-op"}


@_auth
def do_rmt(op, f=None):
    f = f or {}
    if op == "get":
        out = {}
        for bid in (5, 6, 7):
            out[str(bid)] = _state["t"].read(bid)["block"]
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
        r = _state["t"].write_block(
            7, {"rule": rule, "port": port, "addr": addr})
        return {"ok": r.get("errorno") == 0, "errorno": r.get("errorno")}
    if op == "set_local":
        macs = list((f.get("macs") or []) + ["", "", "", ""])[:4]
        pf = {"enableAll": "1" if str(f.get("enableAll")) == "1" else "0"}
        for i, m in enumerate(macs):
            m = (m or "").strip().upper()
            if pf["enableAll"] == "0" and m and not re.match(MACRE, m):
                return {"ok": False, "error": f"bad-mac-{i}"}
            pf[f"mac.{i}"] = m or "00-00-00-00-00-00"
        r = _state["t"].write_block(6, pf)
        return {"ok": r.get("errorno") == 0, "errorno": r.get("errorno")}
    return {"ok": False, "error": "bad-op"}


@_auth
def do_route(op, net="", mask="", gateway="", idx=None):
    if op == "list":
        return {"ok": True, "routes": {
            "14": _state["t"].read(14)["block"],
            "16": _state["t"].read(16)["block"]}}
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
    r = _state["t"].instr(cmd)
    return {"ok": r.get("errorno") == 0, "errorno": r.get("errorno")}


@_auth
def do_wan(op, wtype=None, f=None):
    f = f or {}
    if op == "get":
        out = {}
        for bid in (22, 24, 26, 38, 39, 37):
            b = _state["t"].read(bid)["block"]
            for k in list(b.keys()):
                if k.lower() in ("paswd", "passwd") and b[k]:
                    b[k] = "***set***"
            out[str(bid)] = b
        return {"ok": True, "wan": out}
    if op in ("set_dynamic", "set_pppoe", "set_static",
              "set_l2tp", "set_pptp"):
        type_map = {"set_dynamic": "0", "set_static": "1",
                    "set_pppoe": "2", "set_l2tp": "3", "set_pptp": "4"}
        wt = type_map[op]
        writes = []
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
                  "manualDns": "1" if str(f.get("manualDns")) == "1"
                  else "0"}
            if pf["fixipEnb"] == "1" and not _valid_ip(pf["fixip"]):
                return {"ok": False, "error": "bad-fixed-ip"}
            dns = [f.get("dns1") or "0.0.0.0", f.get("dns2") or "0.0.0.0"]
            if pf["manualDns"] == "1" and not all(map(_valid_ip, dns)):
                return {"ok": False, "error": "bad-dns"}
            pf["dns.0"], pf["dns.1"] = dns
            if f.get("paswd"):
                pf["paswd"] = f["paswd"]
            writes.append((26, pf))
        elif op == "set_static":
            need = {k: (f.get(k) or "").strip()
                    for k in ("ip", "mask", "gateway", "mtu")}
            if not all(map(_valid_ip, (need["ip"], need["mask"],
                                       need["gateway"]))):
                return {"ok": False, "error": "bad-static-ip"}
            if not need["mtu"].isdigit() or \
                    not 576 <= int(need["mtu"]) <= 1500:
                return {"ok": False, "error": "mtu must be 576-1500"}
            dns = [f.get("dns1") or "0.0.0.0", f.get("dns2") or "0.0.0.0"]
            if not all(map(_valid_ip, dns)):
                return {"ok": False, "error": "bad-dns"}
            writes.append((24, {"ip": need["ip"], "mask": need["mask"],
                                "gateway": need["gateway"],
                                "mtu": need["mtu"],
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
            r = _state["t"].write_block(bid, fields)
            if r.get("errorno") != 0:
                return {"ok": False, "error": "write-failed",
                        "block": bid, "detail": r}
        for verb in ("wan -linkDown", "wan -linkUp"):
            r = _state["t"].instr(verb)
            if r.get("errorno") != 0:
                return {"ok": False, "error": "reconnect-failed",
                        "verb": verb}
            time.sleep(2)
        return {"ok": True, "linkType": wt}
    if op == "set_iptv":
        mode = str(f.get("uMode", "0"))
        if mode not in ("0", "1", "2"):
            return {"ok": False, "error": "bad-iptv-mode"}
        r = _state["t"].write_block(37, {"uMode": mode})
        return {"ok": r.get("errorno") == 0, "errorno": r.get("errorno")}
    return {"ok": False, "error": "bad-op"}


@_auth
def do_detect():
    """Read-only network self-checks (LAN-IP conflict + rogue DHCP)."""
    def run(cmd):
        return str(_state["t"].instr(cmd).get("data", "")).strip()
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
    return {"ok": True, "lanIpConflict": ip_conflict or "?",
            "lanIpClear": ip_conflict == "0",
            "rogueDhcp": dhcp or "?",
            "dhcpClear": dhcp == "0"}


@_auth
def do_restore(b64, filename="restore.bin"):
    import base64 as _b64
    try:
        blob = _b64.b64decode(b64 or "", validate=True)
    except Exception:
        return {"ok": False, "error": "bad-file"}
    if not blob or len(blob) > 65536:
        return {"ok": False, "error": "file must be 1B-64KB"}
    if not (filename or "").lower().endswith(".bin"):
        return {"ok": False, "error": "expecting a .bin backup"}
    boundary = "----MW325RPanelRestore"
    body = (f"--{boundary}\r\nContent-Disposition: form-data; "
            f"name=\"fileName\"; filename=\"{filename}\"\r\n"
            f"Content-Type: application/octet-stream\r\n\r\n").encode() + \
        blob + f"\r\n--{boundary}--\r\n".encode()
    url = "%s/?code=%d&asyn=0&id=%s" % (
        _state["t"].base, tddp.CONFIG,
        urllib.parse.quote(_state["t"].session, safe=""))
    req = urllib.request.Request(
        url, data=body,
        headers={"User-Agent": "Mozilla/5.0",
                 "Content-Type": f"multipart/form-data; boundary={boundary}"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            st = r.status
    except Exception as e:
        return {"ok": False, "error": f"upload-failed: {e}"[:120]}
    return {"ok": st == 200, "status": st,
            "note": "sent; if the file is valid the router reboots now"}


class Handler(BaseHTTPRequestHandler):
    server_version = "MW325R-TravelPanel/1.0"

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
            P = {
                "/api/reboot": lambda: do_reboot(),
                "/api/set_wps": lambda: do_set_wps(data.get("enabled")),
                "/api/set_upnp": lambda: do_set_upnp(data.get("enabled")),
                "/api/set_wifi": lambda: do_set_wifi(data.get("key"),
                                                     data.get("ssid")),
                "/api/write_fields": lambda: do_write_fields(data.get("id"),
                                                             data.get("fields")),
                "/api/change_admin": lambda: do_change_admin(data.get("old"),
                                                             data.get("new")),
                "/api/fwd": lambda: do_fwd(
                    data.get("op"), data.get("idx"), data.get("ip", ""),
                    data.get("lport", ""), data.get("start", ""),
                    data.get("end", ""), data.get("ptc", "0")),
                "/api/instr": lambda: do_instr(data.get("cmd", "")),
                "/api/speedtest": lambda: do_speedtest(data.get("mb", 10)),
                "/api/dns": lambda: do_dns(data.get("dns1", ""),
                                           data.get("dns2", ""),
                                           data.get("auto", False)),
                "/api/device": lambda: do_device(
                    data.get("op"), data.get("mac", ""),
                    data.get("name", ""), data.get("up", "0"),
                    data.get("down", "0"), data.get("blocked")),
                "/api/diag": lambda: do_diag(
                    data.get("action"), data.get("type", "ping"),
                    data.get("target", ""), data.get("size", "64"),
                    data.get("count", "4"), data.get("timeout", "800"),
                    data.get("hops", "20"), data.get("icmpId")),
                "/api/scan": lambda: do_scan(),
                "/api/wds": lambda: do_wds(
                    data.get("op"), data.get("ssid", ""),
                    data.get("key", ""), data.get("bssid", "")),
                "/api/macclone": lambda: do_macclone(
                    data.get("op"), data.get("mac", "")),
                "/api/time": lambda: do_time(
                    data.get("op"), data.get("tz", "1080")),
                "/api/arp": lambda: do_arp(),
                "/api/ipmac": lambda: do_ipmac(
                    data.get("op"), data.get("ip", ""),
                    data.get("mac", ""), data.get("name", "")),
                "/api/ddns": lambda: do_ddns(
                    data.get("op"), data.get("f") or {}),
                "/api/rmt": lambda: do_rmt(
                    data.get("op"), data.get("f") or {}),
                "/api/route": lambda: do_route(
                    data.get("op"), data.get("net", ""),
                    data.get("mask", ""), data.get("gateway", ""),
                    data.get("idx")),
                "/api/wan": lambda: do_wan(
                    data.get("op"), data.get("wtype"),
                    data.get("f") or {}),
                "/api/restore": lambda: do_restore(
                    data.get("b64", ""), data.get("filename", "restore.bin")),
                "/api/detect": lambda: do_detect(),
            }
            if u.path == "/api/factory_reset":
                if data.get("confirm") != "YES-WIPE-MY-ROUTER":
                    return self._json({"ok": False,
                                       "error": "confirm-missing"})
                return self._json(do_factory_reset())
            if u.path in P:
                return self._json(P[u.path]())
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
            self._json({"ok": True,
                        "authed": bool(_state["t"].session)})
        elif u.path == "/api/traffic":
            try:
                self._json(do_traffic())
            except Exception as e:
                self._json({"ok": False, "error": f"backend-error: {e}"}, 500)
        elif u.path == "/api/backup":
            try:
                r = do_backup()
                if not r.get("ok"):
                    self._json(r, 401)
                else:
                    self.send_response(200)
                    self._cors()
                    self.send_header("Content-Type",
                                     "application/octet-stream")
                    self.send_header("Content-Disposition",
                                     "attachment; filename=" + r["filename"])
                    self.send_header("Content-Length",
                                     str(len(r["bytes"])))
                    self.end_headers()
                    self.wfile.write(r["bytes"])
            except Exception as e:
                self._json({"ok": False, "error": f"backend-error: {e}"}, 500)
        else:
            self._json({"ok": False, "error": "not-found"}, 404)

    def log_message(self, *a):
        pass  # quiet; never log passwords


if __name__ == "__main__":
    port = 8101
    host = "127.0.0.1"
    args = sys.argv[1:]
    if args and args[0].isdigit():
        port = int(args[0])
        args = args[1:]
    if "--lan" in args:
        host = "0.0.0.0"  # home LAN only — never expose to the internet
    srv = HTTPServer((host, port), Handler)
    print(f"MW325R TRAVEL backend on http://{host}:{port} "
          f"(direct TDDP, no Chrome)", flush=True)
    srv.serve_forever()
