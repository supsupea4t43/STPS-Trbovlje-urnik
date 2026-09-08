# -*- coding: utf-8 -*-
"""
Izdela ikono aplikacije (assets/urnik.ico + web/icon.svg) brez zunanjih knjiznic.

Ikona je koledarcek na modrem zaobljenem kvadratu. Risemo s 4x nadvzorcenjem,
da so robovi gladki tudi pri 16 px.
"""

import os
import struct
import zlib

OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")
WEB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")
SIZES = (16, 20, 24, 32, 40, 48, 64, 128, 256)

BG_A = (37, 99, 235)     # #2563eb
BG_B = (14, 165, 233)    # #0ea5e9
PAPER = (255, 255, 255)
INK = (29, 78, 216)      # #1d4ed8

# Postavitev v normaliziranih koordinatah (0..1).
CARD = (0.17, 0.24, 0.83, 0.80)   # telo koledarja
CARD_R = 0.07
STRIP_H = 0.13                    # visina glave koledarja
DOTS_COLS = ((0.27, 0.41), (0.44, 0.58), (0.61, 0.75))
DOTS_ROWS = ((0.53, 0.62), (0.66, 0.75))


def _in_rrect(x, y, x0, y0, x1, y1, r):
    if x < x0 or x > x1 or y < y0 or y > y1:
        return False
    cx = min(max(x, x0 + r), x1 - r)
    cy = min(max(y, y0 + r), y1 - r)
    dx, dy = x - cx, y - cy
    return dx * dx + dy * dy <= r * r


def _sample(x, y):
    """Barva v tocki (x, y) ali None, ce je tam prosojno."""
    if not _in_rrect(x, y, 0.02, 0.02, 0.98, 0.98, 0.22):
        return None

    x0, y0, x1, y1 = CARD
    if _in_rrect(x, y, x0, y0, x1, y1, CARD_R):
        if y < y0 + STRIP_H:
            return INK
        for cx0, cx1 in DOTS_COLS:
            for ry0, ry1 in DOTS_ROWS:
                if cx0 <= x <= cx1 and ry0 <= y <= ry1:
                    return INK
        return PAPER

    t = (x + y) / 2.0
    return tuple(round(a + (b - a) * t) for a, b in zip(BG_A, BG_B))


def render(size, ss=4):
    """RGBA vrstice za dano velikost."""
    rows, step, n = [], 1.0 / (size * ss), float(ss * ss)
    for py in range(size):
        row = bytearray()
        for px in range(size):
            r = g = b = a = 0
            for sy in range(ss):
                y = (py * ss + sy + 0.5) * step
                for sx in range(ss):
                    x = (px * ss + sx + 0.5) * step
                    c = _sample(x, y)
                    if c is not None:
                        r += c[0]; g += c[1]; b += c[2]; a += 255
            if a:
                hits = a / 255.0
                row += bytes((round(r / hits), round(g / hits), round(b / hits),
                              round(a / n)))
            else:
                row += b"\0\0\0\0"
        rows.append(bytes(row))
    return rows


def png_bytes(size, rows):
    def chunk(tag, data):
        body = tag + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body))

    ihdr = struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)
    raw = b"".join(b"\x00" + row for row in rows)
    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", ihdr)
            + chunk(b"IDAT", zlib.compress(raw, 9))
            + chunk(b"IEND", b""))


def build_ico(path):
    images = [png_bytes(s, render(s)) for s in SIZES]
    offset = 6 + 16 * len(images)
    header = struct.pack("<HHH", 0, 1, len(images))
    entries, blobs = b"", b""
    for size, blob in zip(SIZES, images):
        dim = 0 if size >= 256 else size
        entries += struct.pack("<BBBBHHII", dim, dim, 0, 0, 1, 32, len(blob), offset)
        offset += len(blob)
        blobs += blob
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as fh:
        fh.write(header + entries + blobs)
    return path


SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">
  <defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1">
    <stop offset="0" stop-color="#2563eb"/><stop offset="1" stop-color="#0ea5e9"/>
  </linearGradient></defs>
  <rect x="2" y="2" width="96" height="96" rx="22" fill="url(#g)"/>
  <rect x="17" y="24" width="66" height="56" rx="7" fill="#fff"/>
  <path d="M17 31a7 7 0 0 1 7-7h52a7 7 0 0 1 7 7v6H17z" fill="#1d4ed8"/>
  <g fill="#1d4ed8">
    <rect x="27" y="53" width="14" height="9" rx="2"/>
    <rect x="44" y="53" width="14" height="9" rx="2"/>
    <rect x="61" y="53" width="14" height="9" rx="2"/>
    <rect x="27" y="66" width="14" height="9" rx="2"/>
    <rect x="44" y="66" width="14" height="9" rx="2"/>
    <rect x="61" y="66" width="14" height="9" rx="2"/>
  </g>
</svg>
"""

if __name__ == "__main__":
    ico = build_ico(os.path.join(OUT_DIR, "urnik.ico"))
    os.makedirs(WEB_DIR, exist_ok=True)
    with open(os.path.join(WEB_DIR, "icon.svg"), "w", encoding="utf-8") as fh:
        fh.write(SVG)
    print("Ustvarjeno:", ico)
    print("Ustvarjeno:", os.path.join(WEB_DIR, "icon.svg"))
