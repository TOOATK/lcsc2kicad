#!/usr/bin/env python3
"""Draw the plugin icons (no dependencies): an IC with an arrow dropping into it.
Writes plugins/icons/icon-{light,dark}-{24,48}.png and resources/icon.png (64px)."""
from __future__ import annotations

import struct
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SS = 4  # supersampling


def png(path: Path, w: int, h: int, px: list[tuple[int, int, int, int]]) -> None:
    raw = b"".join(b"\0" + bytes(c for p in px[y * w:(y + 1) * w] for c in p) for y in range(h))

    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d))

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0))
                     + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


def shape(u: float, v: float) -> str | None:
    """What covers point (u, v) in a 0..1 square, top-most first."""
    # arrow (accent): shaft + head, top centre
    if 0.44 <= u <= 0.56 and 0.04 <= v <= 0.30:
        return "accent"
    if 0.26 <= v <= 0.44 and abs(u - 0.5) <= (0.44 - v) * 1.0:
        return "accent"
    # IC body with pin-1 notch
    if 0.24 <= u <= 0.76 and 0.48 <= v <= 0.96:
        if (u - 0.5) ** 2 + (v - 0.48) ** 2 <= 0.07 ** 2:
            return None
        return "body"
    # pins, 3 per side
    for pv in (0.56, 0.72, 0.88):
        if abs(v - pv) <= 0.04 and (0.08 <= u < 0.24 or 0.76 < u <= 0.92):
            return "pin"
    return None


def render(size: int, colors: dict[str, tuple[int, int, int]]) -> list[tuple[int, int, int, int]]:
    out = []
    n = size * SS
    for y in range(size):
        for x in range(size):
            acc = [0, 0, 0]
            hits = 0
            for sy in range(SS):
                for sx in range(SS):
                    s = shape((x * SS + sx + 0.5) / n, (y * SS + sy + 0.5) / n)
                    if s:
                        c = colors[s]
                        acc = [a + b for a, b in zip(acc, c)]
                        hits += 1
            if hits:
                out.append((*(a // hits for a in acc), 255 * hits // (SS * SS)))
            else:
                out.append((0, 0, 0, 0))
    return out


LIGHT = {"body": (40, 44, 52), "pin": (120, 124, 132), "accent": (0, 122, 204)}
DARK = {"body": (220, 222, 226), "pin": (150, 154, 160), "accent": (64, 170, 255)}

if __name__ == "__main__":
    for name, col in (("light", LIGHT), ("dark", DARK)):
        for s in (24, 48):
            png(ROOT / "plugins" / "icons" / f"icon-{name}-{s}.png", s, s, render(s, col))
    png(ROOT / "resources" / "icon.png", 64, 64, render(64, LIGHT))
    print("icons written")
