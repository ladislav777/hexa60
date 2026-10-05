# ============================================================================
# HEXA-60 CORE™ — High-Throughput Base60 Encoding Engine
# Copyright (c) 2026 Ladislav Müller (IČO: 40189589). All rights reserved.
#
# PROPRIETARY AND CONFIDENTIAL SOFTWARE.
# Unauthorized copying, distribution, or modification of this file, via any
# medium, is strictly prohibited under applicable copyright laws and B2B EULA.
# ============================================================================

import time
import sys
import random

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import hexa60
from hexa60 import _encode_chunked_pure, _decode_chunked_pure

try:
    import _hexa60c
    HAS_NATIVE = True
except ImportError:
    HAS_NATIVE = False


def py_decode_strict(text: str) -> bytes:
    return _decode_chunked_pure(text, strict=True)


def measure_throughput(enc_fn, dec_fn, sz: int, seconds: float = 0.5):
    rng = random.Random(42)
    payload = bytes(rng.getrandbits(8) for _ in range(sz))
    
    # ── Benchmark Encode ──
    t0 = time.perf_counter()
    iters_enc = 0
    while time.perf_counter() - t0 < seconds:
        wire = enc_fn(payload)
        iters_enc += 1
    dt_enc = time.perf_counter() - t0
    mbs_enc = (sz * iters_enc / dt_enc) / 1_000_000
    ns_block_enc = (dt_enc / iters_enc) * 1e9 / (sz / 8) if sz >= 8 else 0

    # ── Benchmark Decode ──
    wire_sample = enc_fn(payload)
    t0 = time.perf_counter()
    iters_dec = 0
    while time.perf_counter() - t0 < seconds:
        _ = dec_fn(wire_sample)
        iters_dec += 1
    dt_dec = time.perf_counter() - t0
    mbs_dec = (sz * iters_dec / dt_dec) / 1_000_000
    ns_block_dec = (dt_dec / iters_dec) * 1e9 / (sz / 8) if sz >= 8 else 0

    return mbs_enc, mbs_dec, ns_block_enc, ns_block_dec


def main():
    print("=========================================================================================")
    print("                  HEXA-60 CORE™: Ultra C++20 vs Pure-Python Benchmark                    ")
    print("=========================================================================================")
    
    sizes = [16, 256, 1024, 4096, 16384, 65536, 1024 * 1024]

    print("\n--- 1. Pure Python Reference Implementation ---")
    print(f"{'Payload':<10} | {'Enc MB/s':<12} | {'Dec MB/s':<12} | {'Enc ns/block':<14} | {'Dec ns/block':<14}")
    print("-" * 74)
    py_results = {}
    for sz in [16, 256, 1024, 4096, 16384]:
        label = f"{sz} B" if sz < 1024 else f"{sz // 1024} KiB"
        mbs_enc, mbs_dec, ns_enc, ns_dec = measure_throughput(_encode_chunked_pure, py_decode_strict, sz, seconds=0.3)
        py_results[sz] = (mbs_enc, mbs_dec)
        print(f"{label:<10} | {mbs_enc:>10.2f}   | {mbs_dec:>10.2f}   | {ns_enc:>12.1f}   | {ns_dec:>12.1f}")

    if HAS_NATIVE:
        print("\n--- 2. Native C++20 Ultra Accelerator (_hexa60c nanobind) ---")
        print(f"{'Payload':<10} | {'Enc MB/s':<12} | {'Dec MB/s':<12} | {'Enc ns/block':<14} | {'Dec ns/block':<14}")
        print("-" * 74)
        nat_results = {}
        for sz in sizes:
            label = f"{sz} B" if sz < 1024 else f"{sz // 1024} KiB" if sz < 1024*1024 else f"{sz // (1024*1024)} MiB"
            mbs_enc, mbs_dec, ns_enc, ns_dec = measure_throughput(_hexa60c.encode_chunked, _hexa60c.decode_chunked, sz, seconds=0.5)
            nat_results[sz] = (mbs_enc, mbs_dec)
            print(f"{label:<10} | {mbs_enc:>10.2f}   | {mbs_dec:>10.2f}   | {ns_enc:>12.1f}   | {ns_dec:>12.1f}")

        print("\n--- 3. Direct Speedup Comparison (C++20 Ultra vs Pure Python) ---")
        print(f"{'Payload':<10} | {'Nat Enc (MB/s)':<16} | {'Py Enc (MB/s)':<16} | {'Speedup':<12}")
        print("-" * 62)
        for sz in [16, 256, 1024, 4096, 16384]:
            nat_enc, _ = nat_results[sz]
            py_enc, _ = py_results[sz]
            speedup = nat_enc / py_enc
            label = f"{sz} B" if sz < 1024 else f"{sz // 1024} KiB"
            print(f"{label:<10} | {nat_enc:>14.2f}   | {py_enc:>14.2f}   | {speedup:>10.1f}x")
    else:
        print("\n[!] Native C++20 modul (_hexa60c) nie je k dispozicii.")


if __name__ == "__main__":
    main()
