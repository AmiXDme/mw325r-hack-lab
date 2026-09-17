#!/usr/bin/env python3
"""MINIFS extractor for MERCUSYS MW325R (VxWorks) firmware.
Layout (all integers big-endian):
  MINIFS magic -> header(32B): files @+0x14, names_size @+0x1C
  Table of Names @ base+32 (NUL-delimited path/name strings)
  Table of Files @ base+32+names_size: 20B recs
      [path_off, name_off, chunk_no, offset_in_chunk, size]
  Table of Chunks after ToF: 12B recs [off, comp_size, ...]
  Chunk blobs: LZMA-alone streams (13B header incl. 0xFF size).
Verified against live router files (class.js byte-identical).
"""
import lzma
import os
import struct
import sys

BIN = "/tmp/opencode/fw/mw325rv2-eu-up-boot_2020-11-16_13.57.58.bin"
OUT = "/tmp/opencode/fw/minifs_out"


def W(d, o):
    return struct.unpack(">I", d[o:o + 4])[0]


def main():
    data = open(BIN, "rb").read()
    base = data.find(b"MINIFS")
    assert base != -1
    nfiles, namesz = W(data, base + 0x14), W(data, base + 0x1C)
    ton = base + 32
    tof = ton + namesz
    print(f"base={base:#x} files={nfiles} names_size={namesz} "
          f"ToN={ton:#x} ToF={tof:#x}")

    def S(off):
        e = data.find(b"\x00", ton + off)
        return data[ton + off:e].decode("ascii", "replace")

    files = []
    for i in range(nfiles):
        o = tof + i * 20
        p, n, c, off, sz = (W(data, o + j) for j in (0, 4, 8, 12, 16))
        files.append({"path": S(p), "name": S(n), "chunk": c,
                      "off": off, "size": sz})

    # chunk boundaries from LZMA config words; MINIFS uses chunks 0..max
    maxchunk = max(f["chunk"] for f in files)
    hdrs = []
    i = data.find(b"\x5d\x00\x00\x80")
    while i != -1:
        hdrs.append(i)
        i = data.find(b"\x5d\x00\x00\x80", i + 1)
    print(f"chunks used 0..{maxchunk}, LZMA headers: {[hex(h) for h in hdrs]}")

    decomp = {}
    for c in range(maxchunk + 1):
        start = hdrs[c]
        # NOTE: 0xF018A's 5D000080 is a false positive inside chunk6's
        # stream (chunk6 fails truncated if cut there); last chunk runs to EOF
        end = hdrs[c + 1] if c + 1 < maxchunk + 1 else len(data)
        raw = lzma.decompress(data[start:end], format=lzma.FORMAT_ALONE)
        decomp[c] = raw
        print(f"chunk{c}: comp={end-start} decomp={len(raw)}")

    n_ok = 0
    for f in files:
        blob = decomp[f["chunk"]][f["off"]:f["off"] + f["size"]]
        assert len(blob) == f["size"], (f["path"], f["name"])
        d = os.path.join(OUT, f["path"])
        os.makedirs(d, exist_ok=True)
        open(os.path.join(d, f["name"]), "wb").write(blob)
        n_ok += 1
    print(f"extracted {n_ok}/{len(files)} files -> {OUT}")


if __name__ == "__main__":
    main()
