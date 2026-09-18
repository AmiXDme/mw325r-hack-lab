#!/usr/bin/env python3
"""tddp.py — pure-stdlib TDDP client for the MW325R (VxWorks + MINIFS web UI).

Reverses the stock page's own protocol (lib/Quary.js + lib/DM.js + lib/ajax.js):
  session auth  : POST ?code=7&asyn=0 -> challenge lines ->
                  session=securityEncode(authInfo[3], orgAuthPwd(pw), authInfo[4])
  every request : POST http://192.168.1.1/?code=N&asyn=0&id=<session>
  codes         : 0=INSTRUCT 1=WRITE 2=READ 5=RESET 6=REBOOT 7=AUTH 8=GETPEERMAC
                  9=CONFIG(restore) 10=CHGPWD 4=DOWNLOAD(backup)
  reply format  : "<errno>\\r\\n<data>"  (errno 0 = ok)
  block text    : "key value\\r\\n" / "key index value\\r\\n" for list fields,
                  values are encodeURIComponent-escaped.

No browser, no third-party packages: runs on a PC, a Raspberry Pi, or an
Android phone under Termux. Password lives in RAM only, never logged.
"""
import json
import urllib.parse
import urllib.request

ROUTER = "http://192.168.1.1"

# TDDP operation codes (lib/DM.js)
INSTRUCT, WRITE, READ = 0, 1, 2
DOWNLOAD, RESET, REBOOT, AUTH = 4, 5, 6, 7
GETPEERMAC, CONFIG, CHGPWD = 8, 9, 10

# Login crypto constants (lib/Quary.js :: orgAuthPwd)
_AUTH_B = "RDpbLfCPsJZ7fiv"
_AUTH_A = ("yLwVl0zKqws7LgKPRQ84Mdt708T1qQ3Ha7xv3H7NyU84p21BriUWBU43odz3iP4rBL3cD0"
           "2KZciXTysVXiV8ngg6vL48rPJyAUw0HurW20xqxv9aYb4M9wK1Ae0wlro510qXeU07kV57"
           "fQMc8L6aLgMLwygtc0F10a0Dg70TOoouyFhdysuRMO51yY5ZlOZZLEal1h0t9YQW0Ko7o"
           "BwmCAHoic4HYbUyVeU3sfQ1xtXcPcf1aT303wAQhv66qzW")


def security_encode(f, d, b):
    """Port of Quary.js securityEncode: k.charAt((l^i)%j) per char."""
    k = b
    a = []
    e, c, j = len(f), len(d), len(k)
    h = e if e > c else c
    for g in range(h):
        l, i = 187, 187
        if g >= e:
            i = ord(d[g])
        elif g >= c:
            l = ord(f[g])
        else:
            l, i = ord(f[g]), ord(d[g])
        a.append(k[(l ^ i) % j])
    return "".join(a)


def org_auth_pwd(password):
    return security_encode(password, _AUTH_B, _AUTH_A)


def js_quote(s):
    """encodeURIComponent equivalent."""
    return urllib.parse.quote(str(s), safe="-_.!~*'()")


def _post(url, body=b"", timeout=30):
    import urllib.error
    req = urllib.request.Request(
        url, data=body if isinstance(body, bytes) else body.encode(),
        headers={"User-Agent": "Mozilla/5.0",
                 "Content-Type": "text/plain;charset=UTF-8"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        # the router answers 401 with the challenge in the BODY (the stock
        # page reads responseText regardless of status) — same here.
        return e.read().decode("utf-8", "replace")


def _split_reply(text):
    """<errno>\\r\\n<data> -> (errno:int, data:str)."""
    pos = text.find("\r\n")
    if pos < 0:
        try:
            return int(text.strip() or -1), ""
        except ValueError:
            return -1, text
    head, data = text[:pos], text[pos + 2:]
    t = head.strip()
    if not t or any(not ch.isdigit() for ch in t):
        errno = 0
    else:
        s = t.lstrip("0")
        errno = int(s) if s else 0
    return errno, data


# List-valued fields per block, captured live from the owner's unit
# (scalar fields use "key value", these use "key index value").
LIST_FIELDS = {
    1: ["mac"], 2: ["list"], 3: ["list"], 6: ["mac"],
    8: ["dns"], 9: ["list"], 12: ["list"], 13: ["list"],
    14: ["list"], 15: ["list"], 16: ["list"], 20: ["list"],
    21: ["list"], 23: ["dns", "dualDns"], 24: ["dns"], 25: ["dns"],
    26: ["dns"], 30: ["list"],
    31: ["rList", "hList", "tList", "sList"],
    33: ["privacyRcd"], 34: ["privacyRcd"],
    35: ["privacyRcd", "uTimeTable"], 36: ["apEntry"],
    37: ["uService"], 38: ["dns"], 39: ["dns"], 40: ["serviceList"],
    41: ["status"], 45: ["dns"], 47: ["dns"],
    53: ["privacyRcd"], 54: ["privacyRcd", "uTimeTable"],
}


# Field order per object-list, captured live (key order of first item).
ROW_ORDER = {
    2: {"list": ["level", "days", "hours", "mins", "secs", "msecs", "msg"]},
    3: {"list": ["msg"]},
    9: {"list": ["hostName", "ip", "mac", "expires", "reserved", "state"]},
    12: {"list": ["ip", "mac", "reserved", "bindEntry", "staMgtEntry",
                  "name", "blocked", "upLimit", "downLimit"]},
    13: {"list": ["ip", "mac", "type", "online", "blocked", "up", "down",
                  "upLimit", "downLimit", "name", "bindEntry", "reserved",
                  "staMgtEntry", "posX", "posY"]},
    14: {"list": ["enable", "net", "mask", "gateway"]},
    15: {"list": ["net", "mask", "gateway"]},
    16: {"list": ["net", "mask", "gateway", "netif"]},
    20: {"list": ["extPort", "intPort", "ptc", "enabled", "leaseDuration",
                  "leaseTimer", "rmtHost", "client", "desc"]},
    21: {"list": ["vsEntryEnable", "vsLclIp", "vsLclPort", "vsRmtPort",
                  "vsPtc", "vsOpenPortE", "vsOpenPortS", "vsRmtIp"]},
    30: {"list": ["mac", "reserved"]},
    31: {"rList": ["rName", "rActive", "rHost", "rTarget", "rSchedule",
                   "rReserved"],
          "hList": ["hName", "hMac", "hReserved", "hIpEnd", "hIpStart",
                    "hIsIp"],
          "tList": ["tName", "tType", "tProto", "tIpStart", "tIpEnd",
                    "tPortStart", "tPortEnd", "tUrl0", "tUrl1", "tUrl2",
                    "tUrl3"],
          "sList": ["sName", "sActive", "sMon", "sTue", "sWed", "sThu",
                    "sFri", "sSat", "sSun"]},
    33: {"privacyRcd": ["uKeyLength", "cKeyVal"]},
    34: {"privacyRcd": ["uKeyLength", "cKeyVal"]},
    35: {"privacyRcd": ["uKeyLength", "cKeyVal"]},
    36: {"apEntry": ["cBssid", "cSsid", "uRssi", "uChannel", "uAuthMode",
                     "uBgnMode", "uChanWidth"]},
    37: {"uService": ["uVid", "uVlanPriority", "uMemberPorts", "bTagEnable",
                      "uServiceType"]},
    40: {"serviceList": ["enable", "username", "password", "domainName",
                         "ip", "status"]},
    53: {"privacyRcd": ["uKeyLength", "cKeyVal"]},
    54: {"privacyRcd": ["uKeyLength", "cKeyVal"]},
}

# Nested sub-objects per block (TDDP text flattens them; fold back here).
NESTED = {
    32: {"adv": ["uRTSThreshold", "uFragThreashold", "uBeaconInterval",
                 "uPower", "uDTIMInterval", "bWMEEnabled", "bIsolationEnabled",
                 "bShortPrmbleDisabled", "bShortGI"],
          "apc": ["bBridgeEnabled", "cBridgedSsid", "cBridgedBssid",
                  "uWepIndex", "uSecurityType", "cPassWD", "uDetect"]},
    33: {"wps": ["bEnabled", "cUsrPIN", "bConfigured", "bIsLocked"]},
    34: {"wps": ["bEnabled", "cUsrPIN", "bConfigured", "bIsLocked"]},
    35: {"wps": ["bEnabled", "cUsrPIN", "bConfigured", "bIsLocked"]},
    52: {"adv": ["uRTSThreshold", "uFragThreashold", "uBeaconInterval",
                 "uPower", "uDTIMInterval", "bWMEEnabled", "bIsolationEnabled",
                 "bShortPrmbleDisabled", "bShortGI"],
          "apc": ["bBridgeEnabled", "cBridgedSsid", "cBridgedBssid",
                  "uWepIndex", "uSecurityType", "cPassWD", "uDetect"]},
    53: {"wps": ["bEnabled", "cUsrPIN", "bConfigured", "bIsLocked"]},
    54: {"wps": ["bEnabled", "cUsrPIN", "bConfigured", "bIsLocked"]},
}


def parse_block_text(text, bid):
    """Parse TDDP block text. TDDP rows are grouped by their index token;
    object-lists are rebuilt with ROW_ORDER, nested dicts via NESTED."""
    bid = int(bid)
    lists = set(LIST_FIELDS.get(bid, []))
    order = ROW_ORDER.get(bid, {})
    nested = NESTED.get(bid, {})
    # object-list rows are keyed by SUB-field name ("uKeyLength 0 0"), so any
    # known sub-key with a numeric middle token is an indexed row.
    subkeys = {k for keys in order.values() for k in keys}
    blk = {"id": bid}
    # reverse map: sub-key -> parent dict
    parent_of = {}
    for parent, keys in nested.items():
        for k in keys:
            parent_of[k] = parent
    groups = {}   # idx -> [(name, value)] in arrival order
    group_seq = []  # idx order of first appearance
    for line in text.split("\r\n"):
        if not line.strip() or line.startswith("#"):
            continue
        parts = line.split(" ")
        name = parts[0]
        if name == "id":
            try:
                blk["id"] = int(parts[-1])
            except ValueError:
                pass
            continue
        if len(parts) >= 3 and parts[1].isdigit() and \
                (name in lists or name in subkeys):
            idx = int(parts[1])
            val = urllib.parse.unquote(" ".join(parts[2:]))
            if idx not in groups:
                groups[idx] = []
                group_seq.append(idx)
            groups[idx].append((name, val))
        else:
            blk[name] = urllib.parse.unquote(" ".join(parts[1:]))
    # Regroup: several lists share index space (block 31 r/h/t/sList, block
    # 35 privacyRcd/uTimeTable, block 23 dns/dualDns), so rows are bucketed
    # by list affinity — never by index alone.
    by_list = {}
    # (bid, row-name) -> order-list for singleton-dict rows (block 3 "msg")
    singletons = {}
    for lname, lkeys in order.items():
        if len(lkeys) == 1:
            singletons[lkeys[0]] = lname
    for idx in group_seq:
        rows = groups[idx]
        scalar, members, raw = {}, {}, []
        for n, v in rows:
            if n in lists:
                scalar.setdefault(n, []).append(v)
            else:
                hit = next((ln for ln, lk in order.items() if n in lk), None)
                if hit:
                    members.setdefault(hit, []).append((n, v))
                else:
                    raw.append((n, v))
        for n, vals in scalar.items():
            if n in singletons:
                k = singletons[n]
                by_list.setdefault(k, {})[idx] = [{n: x} for x in vals] \
                    if len(vals) > 1 else {n: vals[0]}
            else:
                by_list.setdefault(n, {})[idx] = (
                    vals[0] if len(vals) == 1 else vals)
        for lname, part in members.items():
            # chunk rows into items; emit ONLY keys the router sent (never
            # invent fields — the stock parser only sets what arrives, and
            # read-modify-write then preserves everything else).
            items, cur = [], {}
            for n, v in part:
                if n in cur:
                    items.append(cur)
                    cur = {}
                cur[n] = v
            if cur:
                items.append(cur)
            d = by_list.setdefault(lname, {})
            if idx in d:
                prev = d[idx]
                d[idx] = (prev if isinstance(prev, list) else [prev]) + items
            else:
                d[idx] = items[0] if len(items) == 1 else items
        if raw:
            # unknown shape: keep raw pairs (never silently drop data)
            by_list.setdefault("_raw", []).append({idx: raw})
    for lname, items in by_list.items():
        if lname == "_raw":
            blk["_raw"] = items
            continue
        blk[lname] = [items[i] if i in items else {}
                      for i in range(max(items) + 1)] if items else []
    # fold flattened sub-dict keys back into their parents
    for parent, keys in nested.items():
        sub = {}
        for k in keys:
            if k in blk:
                sub[k] = blk.pop(k)
        if sub:
            blk[parent] = sub
    return blk


def to_text(blk):
    """Port of DM.js toText: dict -> TDDP write body."""
    out = []

    def enc(v):
        return js_quote("" if v is None else v)

    for k, v in blk.items():
        if k == "id":
            out.append("id %s" % v)
        elif isinstance(v, dict):
            for sk, sv in v.items():
                out.append("%s %s" % (sk, enc(sv)))
        elif isinstance(v, list):
            if v and isinstance(v[0], dict):
                for i, item in enumerate(v):
                    for sk, sv in item.items():
                        out.append("%s %d %s" % (sk, i, enc(sv)))
            else:
                for i, item in enumerate(v):
                    out.append("%s %d %s" % (k, i, enc(item)))
        else:
            out.append("%s %s" % (k, enc(v)))
    return "\r\n".join(out) + "\r\n"


class TDDP:
    """One authenticated router session (session id in RAM only)."""

    def __init__(self, base=ROUTER, timeout=30):
        self.base = base.rstrip("/")
        self.timeout = timeout
        self.session = ""

    def _url(self, code, extra=""):
        u = "%s/?code=%d&asyn=0%s" % (self.base, code, extra)
        if self.session:
            u += "&id=" + urllib.parse.quote(self.session, safe="")
        return u

    def login(self, password):
        r = _post(self._url(AUTH), b"", self.timeout)
        errno, data = _split_reply(r)
        lines = [l for l in data.split("\r\n") if l != ""]
        if errno == 0 or len(lines) < 4:
            self.session = ""
            return {"ok": False, "errorno": errno or -1}
        enc = org_auth_pwd(password)
        sess = security_encode(lines[2], enc, lines[3])
        r2 = _post(self._url(AUTH, "&id=" + urllib.parse.quote(sess, safe="")),
                   b"", self.timeout)
        errno2, _ = _split_reply(r2)
        if errno2 == 0:
            self.session = sess
            return {"ok": True}
        self.session = ""
        return {"ok": False, "errorno": errno2}

    def _authed(self):
        return bool(self.session)

    def read(self, bid):
        if not self._authed():
            return {"ok": False, "error": "not-authenticated"}
        r = _post(self._url(READ), str(int(bid)), self.timeout)
        errno, data = _split_reply(r)
        if errno != 0:
            return {"ok": False, "errorno": errno}
        try:
            return {"ok": True, "block": parse_block_text(data, bid)}
        except Exception:
            return {"ok": False, "error": "parse-error"}

    def write_block(self, bid, fields):
        """Read-modify-write one block. fields: {dotted.key: value}."""
        if not self._authed():
            return {"ok": False, "error": "not-authenticated"}
        r = self.read(bid)
        if not r.get("ok"):
            return r
        b = r["block"]
        for dotted, val in (fields or {}).items():
            parts = dotted.split(".")
            node = b
            for p in parts[:-1]:
                if isinstance(node, list):
                    p = int(p)
                    while len(node) <= p:
                        node.append({})
                    node = node[p]
                else:
                    if p not in node or not isinstance(node[p], (dict, list)):
                        node[p] = {}
                    node = node[p]
            last = parts[-1]
            if isinstance(node, list):
                last = int(last)
                while len(node) <= last:
                    node.append("")
                node[last] = val
            else:
                node[last] = val
        r2 = _post(self._url(WRITE, "&asyn=0"), to_text(b), self.timeout)
        errno, _ = _split_reply(r2)
        return {"ok": errno == 0, "errorno": errno}

    def instr(self, cmd):
        if not self._authed():
            return {"ok": False, "error": "not-authenticated"}
        r = _post(self._url(INSTRUCT), cmd, self.timeout)
        errno, data = _split_reply(r)
        return {"ok": errno == 0, "errorno": errno, "data": data}

    def peer_mac(self):
        if not self._authed():
            return {"ok": False, "error": "not-authenticated"}
        r = _post(self._url(GETPEERMAC), b"", self.timeout)
        errno, data = _split_reply(r)
        return {"ok": errno == 0, "errorno": errno, "data": data}

    def reboot(self):
        if not self._authed():
            return {"ok": False, "error": "not-authenticated"}
        r = _post(self._url(REBOOT, "&asyn=1"), b"", self.timeout)
        errno, _ = _split_reply(r)
        return {"ok": errno == 0, "errorno": errno}

    def reset(self):
        """Factory reset (TDDP_RESET). WIPES everything — caller confirms."""
        if not self._authed():
            return {"ok": False, "error": "not-authenticated"}
        r = _post(self._url(RESET, "&asyn=1"), b"", self.timeout)
        errno, _ = _split_reply(r)
        return {"ok": errno == 0, "errorno": errno}

    def change_password(self, old_pw, new_pw):
        if not self._authed():
            return {"ok": False, "error": "not-authenticated"}
        url = self._url(CHGPWD, "&auth=" + urllib.parse.quote(
            org_auth_pwd(old_pw), safe=""))
        r = _post(url, org_auth_pwd(new_pw), self.timeout)
        errno, _ = _split_reply(r)
        return {"ok": errno == 0, "errorno": errno}

    def backup(self):
        """Download the official config backup bytes (ports the stock
        SysBakNRestore filename recipe + TDDP_INSTRUCT download)."""
        if not self._authed():
            return {"ok": False, "error": "not-authenticated"}
        b = self.read(0)
        if not b.get("ok"):
            return b
        d = b["block"]
        sv, hv = d.get("softVer", ""), d.get("hardVer", "")
        c = next((i for i, ch in enumerate(hv) if ch == " "), len(hv))
        model, vc = hv[:c], c + 1
        c = next((i for i in range(c, len(hv)) if hv[i] == "."), len(hv))
        ver = hv[vc:c]
        bc = sv.find("Build") + 6
        rc = sv.find("Rel.") + 4
        c = next((i for i in range(bc, len(sv)) if sv[i] == " "), len(sv))
        build = sv[bc:c]
        c = next((i for i in range(rc, len(sv)) if sv[i] == "n"), len(sv))
        rel = sv[rc:c]
        name = "%sV%s%s%sn.bin" % (model, ver, build, rel)
        url = "%s/%s?code=%d&asyn=0&id=%s" % (
            self.base, urllib.parse.quote(name, safe=""), INSTRUCT,
            urllib.parse.quote(self.session, safe=""))
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=30) as r:
            return {"ok": True, "filename": name, "bytes": r.read()}
