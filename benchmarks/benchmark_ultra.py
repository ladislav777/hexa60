# ============================================================================
# HEXA-60 CORE™ — High-Throughput Base60 Encoding Engine
# Copyright (c) 2026 Ladislav Müller (IČO: 40189589). All rights reserved.
#
# PROPRIETARY AND CONFIDENTIAL SOFTWARE.
# Unauthorized copying, distribution, or modification of this file, via any
# medium, is strictly prohibited under applicable copyright laws and B2B EULA.
# ============================================================================

import time
import os
import sys
import random

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import hexa60
from hexa60 import _encode_chunked_pure as py_encode

def py_decode(text: str) -> bytes:
    return hexa60._decode_chunked_pure(text, strict=True)

try:
    import _hexa60c
    HAS_NATIVE = True
except ImportError:
    HAS_NATIVE = False


def benchmark_mode(name, enc_fn, dec_fn, sizes, seconds=0.6):
    print(f"\n--- {name} ---")
    print(f"{'Payload':<10} | {'Enc MB/s':<14} | {'Dec MB/s':<14} | {'Enc ns/8B':<14} | {'Dec ns/8B':<14}")
    print("-" * 76)

    results = {}
    for sz in sizes:
        rng = random.Random(42)
        payload = bytes(rng.getrandbits(8) for _ in range(sz))
        
        # ── Benchmark Encode ──
        t0 = time.perf_counter()
        iters_enc = 0
        limit = seconds if sz <= 16384 else seconds * 1.2
        while time.perf_counter() - t0 < limit:
            wire = enc_fn(payload)
            iters_enc += 1
        dt_enc = time.perf_counter() - t0
        
        mbs_enc = (sz * iters_enc / dt_enc) / 1_000_000
        ns_block_enc = (dt_enc / iters_enc) * 1e9 / (sz / 8) if sz >= 8 else 0

        # ── Benchmark Decode ──
        wire_sample = enc_fn(payload)
        t0 = time.perf_counter()
        iters_dec = 0
        while time.perf_counter() - t0 < limit:
            _ = dec_fn(wire_sample)
            iters_dec += 1
        dt_dec = time.perf_counter() - t0
        
        mbs_dec = (sz * iters_dec / dt_dec) / 1_000_000
        ns_block_dec = (dt_dec / iters_dec) * 1e9 / (sz / 8) if sz >= 8 else 0

        results[sz] = (mbs_enc, mbs_dec)
        label = f"{sz} B" if sz < 1024 else f"{sz // 1024} KiB" if sz < 1024*1024 else f"{sz // (1024*1024)} MiB"
        print(f"{label:<10} | {mbs_enc:>12.4f}   | {mbs_dec:>12.4f}   | {ns_block_enc:>12.2f}   | {ns_block_dec:>12.2f}")

    return results


def main():
    print("================================================================================")
    print("         HEXA-60 CORE™: Ultra C++20 vs Pure-Python Precision Bench             ")
    print("================================================================================")
    
    sizes = [16, 256, 1024, 4096, 16384, 65536, 1024 * 1024]

    # 1. Pure Python Reference Implementation (max 64 KiB for fast execution)
    py_sizes = [16, 256, 1024, 4096, 16384, 65536]
    py_res = benchmark_mode("Pure Python Reference", py_encode, py_decode, py_sizes, seconds=0.25)

    # 2. Native C++20 Ultra Accelerator
    if HAS_NATIVE:
        cpp_res = benchmark_mode("Native C++20 Ultra (_hexa60c)", _hexa60c.encode_chunked, _hexa60c.decode_chunked, sizes, seconds=0.4)

        print("\n--- 3. Direct Precise Speedup Comparison (C++20 Ultra vs Pure Python) ---")
        print(f"{'Payload':<10} | {'Nat Enc (MB/s)':<16} | {'Py Enc (MB/s)':<16} | {'Exact Speedup':<14}")
        print("-" * 64)
        for sz in py_sizes:
            nat_enc = cpp_res[sz][0]
            py_enc = py_res[sz][0]
            speedup = nat_enc / py_enc if py_enc > 0 else 0
            label = f"{sz} B" if sz < 1024 else f"{sz // 1024} KiB" if sz < 1024*1024 else f"{sz // (1024*1024)} MiB"
            print(f"{label:<10} | {nat_enc:>14.4f}   | {py_enc:>14.4f}   | {speedup:>12.2f}x")
    else:
        print("\n[!] Native C++20 modul (_hexa60c) nie je k dispozicii.")


if __name__ == "__main__":
    main()
