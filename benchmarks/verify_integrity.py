#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""verify_integrity.py — HEXA60 integrity + wire/storage footprint verifier."""
from __future__ import annotations
import csv
import hashlib
import io
import json
import os
import random
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import hexa60
from hexa60 import CHUNK_BYTES, CHUNK_CHARS, TAIL_CHARS, decode_chunked_auto, encode_chunked

TOTAL = 10_000
SEED = 20261005
RATIO = CHUNK_CHARS / CHUNK_BYTES  # 1.375

UTF8_POOL = [
    "The quick brown fox jumps over the lazy dog. 0123456789",
    "Lorem ipsum dolor sit amet, consectetur adipiscing elit. " * 4,
    "Special chars: !@#$%^&*()_+-=[]{}|;':\",./<>?`~\\ \t\n",
    "0123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnpqrstuvwxyz_-",
    "Příliš žluťoučký kůň úpěl ďábelské ódy. Hlášení o stavu sítě.",
    "Nechť motory burácí! Případně žluté koníčky přeskočily sníh.",
    "Slovensky: Ľupčianska džungľa, Ftákovce, Štrba, Ďumbier, Chopok, Hrnčiarovce.",
    "Česky: nezábudka, křižovatka, městský úřad, bezpečnost, elektronický podpis.",
    "Emoji+symboly: 🚀🔥☃€∑αβγ 中文 Русский العربية žščřďťňôľĺŕáíéýúů",
    "Opakovaný vzor: " + "ABCD_1234-xyz žšř " * 64,
]
CSV_CITIES = ["Praha", "Brno", "Bratislava", "Košice", "Ostrava", "Žilina"]

def sha256(d: bytes) -> str:
    return hashlib.sha256(d).hexdigest()

def expected_wire_len(n: int) -> int:
    full, rem = divmod(n, CHUNK_BYTES)
    return full * CHUNK_CHARS + TAIL_CHARS[rem]

def gen_random_binary(rng, i: int) -> bytes:
    # Pocitadlo binarnych iteracii: kazda 400-ta je velka (256 KB..1 MB),
    # kazda 40-ta je stredna (16..64 KB), zvysok maly (16 B..4 KB).
    gen_random_binary.counter = getattr(gen_random_binary, "counter", 0) + 1
    c = gen_random_binary.counter
    if c % 400 == 0:
        return rng.randbytes(rng.randint(256 * 1024, 1024 * 1024))
    if c % 40 == 0:
        return rng.randbytes(rng.randint(16 * 1024, 64 * 1024))
    size = rng.randint(16, 4096)
    if rng.random() < 0.10:
        size = rng.randint(16, 64)
    return rng.randbytes(size)

def gen_utf8_text(rng) -> bytes:
    base = rng.choice(UTF8_POOL)
    reps = rng.randint(1, 20)
    extra = rng.choice(["", " " + str(rng.randint(0, 999999))])
    text = (base + extra + " ") * reps
    cut = rng.randint(16, len(text))
    return text[:cut].encode("utf-8")

def gen_json(rng) -> bytes:
    obj = {"id": rng.randint(0, 10**9),
           "name": rng.choice(["Alice", "Bob", "Cyril", "Dasa", "Ester"]) + f"-{rng.randint(0,999)}",
           "active": rng.choice([True, False]),
           "score": rng.uniform(-1e6, 1e6),
           "tags": [rng.choice(["a", "b", "c", "z", "s", "_-"]) for _ in range(rng.randint(0, 8))],
           "note": rng.choice(UTF8_POOL)[:rng.randint(0, 120)]}
    style = rng.choice([{"ensure_ascii": False}, {"ensure_ascii": True}])
    return json.dumps(obj, **style).encode("utf-8")

def gen_csv(rng) -> bytes:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(["id", "meno", "mesto", "hodnota", "poznámka"])
    for _ in range(rng.randint(1, 50)):
        w.writerow([rng.randint(0, 99999),
                    rng.choice(["Novák", "Svoboda", "Horváth", "Kováč", "Žiška-Řehák"]),
                    rng.choice(CSV_CITIES), f"{rng.uniform(0, 9999):.2f}",
                    rng.choice(["ok", "čaká", "storno; reklamácia", "a,b,c", ""])])
    return buf.getvalue().encode("utf-8")

def gen_edge(rng, i: int) -> bytes:
    kind = i % 6
    size = rng.choice([16, 17, 24, 31, 32, 64, 100, 1000, 4096, 8192])
    if kind == 0:
        return b"\x00" * size
    if kind == 1:
        return b"\xff" * size
    if kind == 2:
        return (b"\x00\xff" * ((size // 2) + 1))[:size]
    if kind == 3:
        return (b"\xaa\x55" * ((size // 2) + 1))[:size]
    if kind == 4:
        return bytes([rng.randint(0, 255)]) * size
    seq = bytes(range(256))
    return (seq * ((size // 256) + 1))[:size]

def roundtrip_once(original: bytes, idx: int, cat: str):
    h_orig = sha256(original)
    encoded = encode_chunked(original)
    wire_len = len(encoded.encode("ascii"))
    decoded = decode_chunked_auto(encoded, strict=True)
    h_dec = sha256(decoded)
    if h_orig != h_dec or original != decoded:
        raise AssertionError(f"INTEGRITY FAIL iter={idx} cat={cat} len={len(original)}/{len(decoded)} {h_orig}!={h_dec}")
    return encoded, wire_len

def main() -> int:
    rng = random.Random(SEED)
    print("=" * 78)
    print("HEXA60 verify_integrity.py — bitova integrita (SHA-256) + wire footprint")
    print(f"engine: HAS_NATIVE={hexa60.HAS_NATIVE} CHUNK {CHUNK_BYTES}B->{CHUNK_CHARS}ch ratio={RATIO:.6f}")
    print(f"TAIL_CHARS={dict(sorted(TAIL_CHARS.items()))} plan={TOTAL} iteracii seed={SEED}")
    print("=" * 78)
    counts = {"binary": 0, "utf8": 0, "json": 0, "csv": 0, "edge": 0}
    max_orig = ("", -1, "")
    max_wire = ("", -1, "")
    samples = []
    t0 = time.perf_counter()
    for i in range(TOTAL):
        slot = i % 10
        if slot <= 3:
            cat, original = "binary", gen_random_binary(rng, i)
        elif slot <= 5:
            cat, original = "utf8", gen_utf8_text(rng)
        elif slot == 6:
            cat, original = "json", gen_json(rng)
        elif slot == 7:
            cat, original = "csv", gen_csv(rng)
        else:
            cat, original = "edge", gen_edge(rng, i)
        encoded, wire_len = roundtrip_once(original, i, cat)
        counts[cat] += 1
        if len(original) > max_orig[1]:
            max_orig = (cat, len(original), sha256(original)[:16])
        if wire_len > max_wire[1]:
            max_wire = (cat, wire_len, sha256(original)[:16])
        if len(samples) < 12 or i % 1000 == 999:
            samples.append((i, cat, len(original), wire_len, sha256(original)[:16], encoded[:24]))
        if (i + 1) % 2000 == 0:
            print(f"  ... {i + 1}/{TOTAL} PASS (priebezne, 0 FAIL)")
    dt = time.perf_counter() - t0
    done = sum(counts.values())
    print("-" * 78)
    print(f"ROUND-TRIP: {done} / {TOTAL} PASS (FAIL=0) za {dt:.2f} s")
    print(f"  binary={counts['binary']} utf8={counts['utf8']} json={counts['json']} csv={counts['csv']} edge={counts['edge']}")
    print(f"  najvacsi original: cat={max_orig[0]} len={max_orig[1]} B sha16={max_orig[2]}")
    print(f"  najvacsi wire: cat={max_wire[0]} len={max_wire[1]} B sha16={max_wire[2]}")
    print("SUROVE DATA (iter, kat, orig_B, wire_B, sha16, enc_prefix):")
    for it, cat, lo, lw, sh, pf in samples[:16]:
        print(f"  #{it:05d} {cat:6s} orig={lo:7d} B wire={lw:7d} B sha16={sh} enc='{pf}...'")
    print("-" * 78)
    print("WIRE/STORAGE FOOTPRINT (ASCII bajty po zakodovani):")
    print(f"teoria: wire(n)=(n//8)*11+TAIL[n%8]; 11/8={RATIO}")
    print(f"{'n_orig_B':>9} {'exp':>9} {'real':>9} {'ratio':>8}  status")
    sizes = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 15, 16, 17, 24, 31, 32, 64, 100, 1000, 1024, 4096, 8192, 65536, 262144, 1048576]
    fails = 0
    for n in sizes:
        if n == 0:
            blob = b""
        elif n <= 8192:
            blob = rng.randbytes(n)
        else:
            blob = (bytes(range(256)) * ((n // 256) + 1))[:n]
        enc = encode_chunked(blob)
        real = len(enc.encode("ascii"))
        exp = expected_wire_len(n)
        ratio = (real / n) if n else 0.0
        ok = (real == exp)
        if n > 0 and n % 8 == 0:
            ok = ok and abs(ratio - 1.375) < 1e-12
        if not ok:
            fails += 1
        print(f"{n:9d} {exp:9d} {real:9d} {ratio:8.5f}  {'OK' if ok else 'FAIL'}")
    print("-" * 78)
    print("DISK CHECK (tempfile, os.path.getsize):")
    for n in (16, 1024, 65536):
        blob = rng.randbytes(n)
        enc = encode_chunked(blob)
        with tempfile.NamedTemporaryFile(delete=False, suffix=".hexa60") as f:
            f.write(enc.encode("ascii"))
            path = f.name
        try:
            on_disk = os.path.getsize(path)
        finally:
            os.unlink(path)
        exp = expected_wire_len(n)
        ok = on_disk == exp == len(enc)
        print(f"  n={n:6d} B on_disk={on_disk:6d} B len(enc)={len(enc):6d} exp={exp:6d} {'OK' if ok else 'FAIL'}")
        if not ok:
            fails += 1
    print("-" * 78)
    print(f"FOOTPRINT: {'ALL PASS' if fails == 0 else str(fails) + ' FAIL'} (plne 8B bloky = presne 1.375x)")
    if fails:
        raise AssertionError(f"Footprint FAIL: {fails}")
    if done != TOTAL:
        raise AssertionError(f"Round-trip FAIL: {done}/{TOTAL}")
    print(f"VYSLEDOK: {done} / {TOTAL} PASS — integrita SHA-256 drzi, footprint = 1.375x")
    print("=" * 78)
    return 0

if __name__ == "__main__":
    sys.exit(main())

