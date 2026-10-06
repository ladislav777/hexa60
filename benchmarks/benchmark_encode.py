#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""benchmark_encode.py — HEXA-60 vs Base64 vs Base85 vs Base91, rovnake datasety.

Metodika: 1 MB / 10 MB / 100 MB deterministicke data (seed), pre kazdy encoder:
output size, expanzia, encode MB/s, decode MB/s, SHA-256 round-trip PASS/FAIL.
Vstupne MB/s = input_bytes / cas (kodovanie aj dekodovanie vztiahnute na povodne data).
"""
from __future__ import annotations
import base64
import binascii
import gc
import hashlib
import os
import platform
import random
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import hexa60
from hexa60 import decode_chunked_auto, encode_chunked

SEED = 20261005
SIZES = [1_000_000, 10_000_000, 100_000_000]
REPEATS = {1_000_000: 5, 10_000_000: 3, 100_000_000: 1}
# Stdlib Base85 (int.from_bytes na celom bloku) pada s MemoryError uz na 10 MB
# a cisto-python Base91 by na 100 MB bral ~10 min. Oba preto meriame na 1 MB
# (expanzia aj radova rychlost su tam plne vypovedne), HEXA-60 a Base64 idu 1/10/100 MB.
BIG_ONLY = {"HEXA-60", "Base64"}

# --- Base91 (vendored basE91, J. Henke; public-domain algorithm, bez zavislosti)
B91_ALPHABET = ("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
                "0123456789!#$%&()*+,./:;<=>?@[]^_`{|}~\"")
_B91_DEC = [-1] * 256
for _i, _ch in enumerate(B91_ALPHABET):
    _B91_DEC[ord(_ch)] = _i

def b91encode(data: bytes) -> str:
    abc = B91_ALPHABET
    out: list[str] = []
    ap = out.append
    b = 0
    n = 0
    for d in data:
        b |= d << n
        n += 8
        if n > 13:
            v = b & 8191
            if v > 88:
                b >>= 13
                n -= 13
            else:
                v = b & 16383
                b >>= 14
                n -= 14
            ap(abc[v % 91])
            ap(abc[v // 91])
    if n:
        ap(abc[b % 91])
        if n > 7 or b > 90:
            ap(abc[b // 91])
    return "".join(out)

def b91decode(text) -> bytes:
    if isinstance(text, (bytes, bytearray)):
        text = text.decode("ascii")
    dec = _B91_DEC
    out = bytearray()
    app = out.append
    v = -1
    b = 0
    n = 0
    for c in text:
        o = ord(c)
        d = dec[o] if o < 256 else -1
        if d < 0:
            raise ValueError("base91: zly znak")
        if v < 0:
            v = d
        else:
            v += d * 91
            b |= v << n
            n += 13 if (v & 8191) > 88 else 14
            while n >= 8:
                app(b & 255)
                b >>= 8
                n -= 8
            v = -1
    if v >= 0:
        app((b | (v << n)) & 255)
    return bytes(out)

# Sanity check vendored base91 (padne hned, nie po 100 MB).
assert b91decode(b91encode(b"")) == b""
assert b91decode(b91encode(b"Hello, HEXA-60 vs base91!")) == b"Hello, HEXA-60 vs base91!"
assert b91decode(b91encode(bytes(range(256)) * 3)) == bytes(range(256)) * 3

def timeit(fn, repeats: int) -> float:
    best = float("inf")
    for _ in range(repeats):
        t0 = time.perf_counter()
        fn()
        dt = time.perf_counter() - t0
        if dt < best:
            best = dt
    return best

_MAKE_N = 0  # aktualna velkost datasetu pre make_data_at (nastavuje main)


def make_data(n: int) -> bytes:
    # Deterministicke data: kazdy 256 KB blok ma seed (SEED ^ n ^ block_index),
    # takze make_data_at(offset, size) vrati identicke bajty bez drzania vsetkeho v RAM.
    global _MAKE_N
    _MAKE_N = n
    buf = bytearray(n)
    step = 1 << 18  # 256 KiB
    nblocks = (n + step - 1) // step
    for block in range(nblocks):
        b0 = block * step
        size = step if b0 + step <= n else n - b0
        buf[b0:b0 + size] = random.Random(SEED ^ n ^ block).randbytes(size)
    return bytes(buf)

def make_data_at(offset: int, size: int) -> bytes:
    # Deterministicky chunk: rovnake data, ako keby sme vzali make_data(SEED^n)[offset:offset+size],
    # ale bez drzania celeho 100 MB v RAM. Kazdy 256 KB blok ma vlastny seed z (SEED, n, index).
    # POZOR: vyzaduje, aby make_data pouzivalo rovnaku schemu (vid nizsie).
    out = bytearray(size)
    step = 1 << 18
    end = offset + size
    first_block = offset // step
    last_block = (end - 1) // step
    for block in range(first_block, last_block + 1):
        b0 = block * step
        rnd = random.Random(SEED ^ _MAKE_N ^ block)
        full = rnd.randbytes(step if b0 + step <= _MAKE_N else _MAKE_N - b0)
        lo = max(offset, b0)
        hi = min(end, b0 + len(full))
        out[lo - offset:hi - offset] = full[lo - b0:hi - b0]
        del full
    return bytes(out)


def sha_of_make_data(n: int) -> str:
    h = hashlib.sha256()
    step = 1 << 18
    for block in range(0, (n + step - 1) // step):
        b0 = block * step
        size = step if b0 + step <= n else n - b0
        rnd = random.Random(SEED ^ n ^ block)
        h.update(rnd.randbytes(size))
    return h.hexdigest()


def fmt_mb(n: int) -> str:
    return f"{n / 1e6:.0f} MB"

def bench_one(name: str, data: bytes, enc, dec, repeats: int):
    # 1) round-trip + SHA-256 (bez duplicitnych 100 MB kopii)
    wire = enc(data)
    out_len = len(wire)  # str aj bytes: 1 ASCII znak = 1 B vystupu
    back = dec(wire)
    if not isinstance(back, (bytes, bytearray)):
        back = bytes(back)
    h_data = hashlib.sha256(data).hexdigest()
    h_back = hashlib.sha256(back).hexdigest()
    ok = (len(back) == len(data)) and (bytes(back) == data) and (h_back == h_data)
    sample = (wire[:32] if isinstance(wire, str) else bytes(wire[:32]))
    del back, wire
    gc.collect()
    # 2) casovanie (vysledky sa zahadzuju, ziadne drzanie 2x wire)
    t_enc = timeit(lambda: enc(data), repeats)
    gc.collect()
    wire2 = enc(data)
    t_dec = timeit(lambda: dec(wire2), repeats)
    enc_mbs = len(data) / t_enc / 1e6
    dec_mbs = len(data) / t_dec / 1e6
    del wire2
    gc.collect()
    return {"name": name, "out": out_len, "exp": out_len / len(data),
            "enc": enc_mbs, "dec": dec_mbs, "ok": ok, "sample": sample}


CHUNK_100M = 999_984  # ~1 MB, nasobok 24 = nasobok 8 (HEXA-60) aj 3 (Base64) -> exaktne sucty


def bench_streamed(name: str, seed_data_n: int, enc, dec, repeats: int):
    # Streamovana verzia pre 100 MB: rovnake data ako make_data(n), ale nikdy
    # nedrzi v RAM cely vstup + cely vystup naraz. Meria priepustnost + SHA-256.
    total_out = 0
    h_all = hashlib.sha256()
    # 1) round-trip (chunk koduj -> hned dekoduj -> hash, vystup sa nedrzi)
    t_enc_total = 0.0
    t_dec_total = 0.0
    for off in range(0, seed_data_n, CHUNK_100M):
        size = CHUNK_100M if off + CHUNK_100M <= seed_data_n else seed_data_n - off
        chunk = make_data_at(off, size)
        t0 = time.perf_counter()
        wire = enc(chunk)
        t_enc_total += time.perf_counter() - t0
        total_out += len(wire)
        t0 = time.perf_counter()
        back = dec(wire)
        t_dec_total += time.perf_counter() - t0
        if not isinstance(back, (bytes, bytearray)):
            back = bytes(back)
        if bytes(back) != chunk:
            raise AssertionError(f"round-trip FAIL (streamed): {name} @ off={off}")
        h_all.update(back)
        del chunk, wire, back
    gc.collect()
    h_stream = h_all.hexdigest()
    h_ref = sha_of_make_data(seed_data_n)
    ok = (h_stream == h_ref)
    enc_mbs = seed_data_n / t_enc_total / 1e6
    dec_mbs = seed_data_n / t_dec_total / 1e6
    return {"name": name, "out": total_out, "exp": total_out / seed_data_n,
            "enc": enc_mbs, "dec": dec_mbs, "ok": ok, "sample": ""}

def main() -> int:
    global _MAKE_N
    print("=" * 100)
    print("HEXA-60 vs Base64 vs Base85 vs Base91 — rovnake datasety, rovnaka metodika")
    print(f"python={platform.python_version()} arch={platform.machine()} HAS_NATIVE={hexa60.HAS_NATIVE}")
    print(f"seed={SEED}  MB/s = vstupne MB/s (orig bytes / cas)  best-of-N")
    print("=" * 100)
    all_rows = []
    for n in SIZES:
        reps = REPEATS[n]
        print(f"\n>>> Dataset {fmt_mb(n)} ({n} B vstup, repeats best-of-{reps}) ...", flush=True)
        enc_all = [
            ("HEXA-60", encode_chunked, lambda w: decode_chunked_auto(w, strict=True)),
            ("Base64 ", lambda d: base64.b64encode(d), lambda w: base64.b64decode(w)),
            ("Base85 ", lambda d: base64.b85encode(d), lambda w: base64.b85decode(w)),
            ("Base91 ", b91encode, b91decode),
        ]
        if n > 10_000_000:
            # 100 MB: streamovane po 1 MB chunkoch (rovnake data, zlomok RAM).
            _MAKE_N = n
            print(f"    sha256 vstup: {sha_of_make_data(n)[:32]}... (streamovane meranie)")
            encoders = [e for e in enc_all if e[0].strip() in BIG_ONLY]
            rows = []
            for name, enc, dec in encoders:
                r = bench_streamed(name, n, enc, dec, reps)
                rows.append(r)
                print(f"    {r['name']}: out={r['out']:>10d} B exp={r['exp']:.5f}x "
                      f"enc={r['enc']:8.2f} MB/s dec={r['dec']:8.2f} MB/s roundtrip={'PASS' if r['ok'] else 'FAIL'}")
                if not r["ok"]:
                    raise AssertionError(f"round-trip FAIL: {name} @ {n} B")
            all_rows.append((n, rows))
            gc.collect()
            continue
        data = make_data(n)
        print(f"    sha256 vstup: {hashlib.sha256(data).hexdigest()[:32]}...")
        encoders = list(enc_all)
        if n > 1_000_000:
            encoders = [e for e in encoders if e[0].strip() in BIG_ONLY]
        rows = []
        for name, enc, dec in encoders:
            r = bench_one(name, data, enc, dec, reps)
            rows.append(r)
            print(f"    {r['name']}: out={r['out']:>10d} B exp={r['exp']:.5f}x "
                  f"enc={r['enc']:8.2f} MB/s dec={r['dec']:8.2f} MB/s roundtrip={'PASS' if r['ok'] else 'FAIL'}")
            if not r["ok"]:
                raise AssertionError(f"round-trip FAIL: {name} @ {n} B")
        all_rows.append((n, rows))
        # Uvolni 100 MB dataset aj wire pred dalsou velkostou.
        del data
        gc.collect()
    print("\n" + "=" * 100)
    print("SUHRN — vystup / expanzia / priepustnost (vstupne MB/s)")
    print(f"{'velkost':>8} | {'encoder':<7} | {'output size':>11} | {'expanzia':>8} | {'encode MB/s':>11} | {'decode MB/s':>11} | roundtrip")
    print("-" * 100)
    for n, rows in all_rows:
        for r in rows:
            print(f"{fmt_mb(n):>8} | {r['name']:<7} | {r['out']:>11d} | {r['exp']:>7.4f}x | "
                  f"{r['enc']:>11.2f} | {r['dec']:>11.2f} | {'PASS' if r['ok'] else 'FAIL'}")
    print("-" * 100)
    print("Teoreticke expanzie: HEXA-60 11/8=1.37500x (meratelne presne), "
          "Base64 4/3=1.33333x, Base85 5/4=1.25x, Base91 ~1.23x (datovo-zavisle).")
    sufix = "NATIVE C++20" if hexa60.HAS_NATIVE else "pure Python"
    print(f"HEXA-60 engine v tomto behu: {sufix}.")
    print("USP signal: HEXA-60 kupuje +3.2 % miesta oproti Base64 (1.375 vs 1.333), "
          "ale predava bezpecnost abecedy: ziadne + / = \" \" ' \\, prezije URL/header/token bez escapovania.")
    print("=" * 100)
    return 0

if __name__ == "__main__":
    sys.exit(main())

