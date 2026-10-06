# ============================================================================
# HEXA-60 CORE™ — High-Throughput Base60 Encoding Engine
# Copyright (c) 2026 Ladislav Müller (IČO: 40189589). All rights reserved.
#
# PROPRIETARY AND CONFIDENTIAL SOFTWARE.
# Unauthorized copying, distribution, or modification of this file, via any
# medium, is strictly prohibited under applicable copyright laws and B2B EULA.
# ============================================================================

# ============================================
# demo.py – Ukážkový skript pre BASE60 projekt
# ============================================
# Použitie:
#   python demo.py "nejaký text"           # zakóduje a dekóduje text
#   python demo.py --file obrazok.png      # zakóduje súbor a spätne overí
#   python demo.py --benchmark             # rýchlostný test

import sys
import time
import argparse
from pathlib import Path
# Windows konzola používa cp1250/cp1252 a neprepíše emoji ani šípky.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except (ValueError, OSError):
            pass


from hexa60 import encode_chunked, decode_chunked_auto


def demo_text(text: str) -> None:
    print(f"Vstupný text:   {text!r}")
    raw = text.encode("utf-8")
    enc = encode_chunked(raw)
    dec = decode_chunked_auto(enc, strict=True).decode("utf-8")
    print(f"HEXA60 kód:     {enc}")
    print(f"Dekódovaný:     {dec!r}")
    print(f"Bajtov:         {len(raw)}  ->  Znakov: {len(enc)}  "
          f"(Base64 by dal ~{4 * (len(raw) + 2) // 3} z.)")
    print(f"OK:             {dec == text}")


def demo_file(path: str) -> None:
    p = Path(path)
    raw = p.read_bytes()
    print(f"Súbor:          {p.name}  ({len(raw):,} bajtov)")
    enc = encode_chunked(raw)
    print(f"Veľkosť kódu:   {len(enc):,} znakov HEXA60")
    dec = decode_chunked_auto(enc, strict=True)
    print(f"Round-trip OK:  {dec == raw}")
    if dec != raw:
        sys.exit("Dáta sa nezhodujú!")


def benchmark() -> None:
    sizes = [1024, 100_000, 1_000_000, 10_000_000]
    print(f"{ 'Veľkosť (B)':>12}  {'Kódovanie (s)':>14}  {'Dekódovanie (s)':>16}  "
          f"{'Bajty/s':>14}")
    for n in sizes:
        data = bytes((i * 7 + 13) & 0xFF for i in range(n))
        t0 = time.perf_counter(); enc = encode_chunked(data);      t1 = time.perf_counter()
        t2 = time.perf_counter(); dec = decode_chunked_auto(enc);   t3 = time.perf_counter()
        assert dec == data, f"Round-trip zlyhal pre {n} bajtov"
        print(f"{n:>12,}  {t1 - t0:>14.3f}  {t3 - t2:>16.3f}  "
              f"{n / (t1 - t0 + t3 - t2):>14,.0f}")


def main() -> None:
    ap = argparse.ArgumentParser(description="BASE60 demo – kóduje text/bajty na Base-60.")
    ap.add_argument("text", nargs="?", help="Text na zakódovanie/dekódovanie")
    ap.add_argument("--file", help="Cesta k súboru, ktorý sa zakóduje")
    ap.add_argument("--benchmark", action="store_true", help="Spustí rýchlostný test")
    args = ap.parse_args()

    if args.benchmark:
        benchmark()
    elif args.file:
        demo_file(args.file)
    elif args.text:
        demo_text(args.text)
    else:
        # default: rýchla ukážka
        demo_text("Ahoj Slovensko 🦅 — Vortex Base-60 funguje!")


if __name__ == "__main__":
    main()
