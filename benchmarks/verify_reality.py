# ============================================================================
# HEXA-60 CORE™ — High-Throughput Base60 Encoding Engine
# Copyright (c) 2026 Ladislav Müller (IČO: 40189589). All rights reserved.
#
# PROPRIETARY AND CONFIDENTIAL SOFTWARE.
# Unauthorized copying, distribution, or modification of this file, via any
# medium, is strictly prohibited under applicable copyright laws and B2B EULA.
# ============================================================================

import time
import random
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Ensure UTF-8 output on Windows consoles
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# 1. Kontrola dostupnosti modulov a overenie typov
print("=" * 78)
print("       HEXA-60 CORE™: REALITY CHECK & VERIFICATION SCRIPT          ")
print("=" * 78)

try:
    import _hexa60c
    native_available = True
    print("[INFO] Natívny C++ modul (_hexa60c) úspešne importovaný.")
    print(f"[DEBUG] _hexa60c encode funkcia: {type(_hexa60c.encode_chunked)}")
except ImportError as e:
    native_available = False
    print(f"[WARN] Natívny C++ modul NIE JE dostupný: {e}")

try:
    import hexa60
    # True Pure-Python reference kernels
    py_encode = hexa60._encode_chunked_pure
    py_decode = lambda t: hexa60._decode_chunked_pure(t, strict=True)
    python_available = True
    print("[INFO] Pure-Python modul (hexa60) úspešne importovaný.")
    print(f"[DEBUG] py_encode funkcia: {type(py_encode)}")
except ImportError as e:
    python_available = False
    print(f"[ERROR] Pure-Python modul nie je dostupný: {e}")
    sys.exit(1)

if native_available:
    cpp_encode = _hexa60c.encode_chunked
    cpp_decode = _hexa60c.decode_chunked
else:
    cpp_encode = None
    cpp_decode = None

sizes = [16, 256, 1024, 4096, 16384, 65536]
iterations_map = {
    16: 30000,
    256: 15000,
    1024: 8000,
    4096: 3000,
    16384: 1000,
    65536: 300
}


def benchmark_fn(fn, payload, iters):
    # Warmup
    for _ in range(min(50, iters)):
        _ = fn(payload)
    t0 = time.perf_counter()
    for _ in range(iters):
        _ = fn(payload)
    dt = time.perf_counter() - t0
    return dt


def run_benchmarks():
    print("\n" + "-" * 78)
    print(f"{'Payload':<10} | {'Mode':<15} | {'Enc (MB/s)':<12} | {'Dec (MB/s)':<12} | {'Speedup (Enc)':<14}")
    print("-" * 78)

    for sz in sizes:
        rng = random.Random(1337)
        payload = bytes(rng.getrandbits(8) for _ in range(sz))
        iters = iterations_map.get(sz, 1000)

        # ── Python Benchmark ──
        py_enc_dt = benchmark_fn(py_encode, payload, iters)
        py_wire = py_encode(payload)
        py_dec_dt = benchmark_fn(py_decode, py_wire, iters)

        py_enc_mbs = (sz * iters / py_enc_dt) / 1_000_000
        py_dec_mbs = (sz * iters / py_dec_dt) / 1_000_000

        label = f"{sz} B" if sz < 1024 else f"{sz // 1024} KiB"

        if native_available:
            # ── Native C++ Benchmark ──
            cpp_enc_dt = benchmark_fn(cpp_encode, payload, iters)
            cpp_wire = cpp_encode(payload)
            cpp_decode_dt = benchmark_fn(cpp_decode, cpp_wire, iters)

            cpp_enc_mbs = (sz * iters / cpp_enc_dt) / 1_000_000
            cpp_dec_mbs = (sz * iters / cpp_decode_dt) / 1_000_000
            
            speedup_enc = cpp_enc_mbs / py_enc_mbs if py_enc_mbs > 0 else 0

            print(f"{label:<10} | {'Python':<15} | {py_enc_mbs:>10.2f}   | {py_dec_mbs:>10.2f}   | {'1.00x':<14}")
            print(f"{'':<10} | {'C++20 Native':<15} | {cpp_enc_mbs:>10.2f}   | {cpp_dec_mbs:>10.2f}   | {speedup_enc:>12.2f}x")
            print("-" * 78)
        else:
            print(f"{label:<10} | {'Python':<15} | {py_enc_mbs:>10.2f}   | {py_dec_mbs:>10.2f}   | {'N/A':<14}")
            print("-" * 78)


if __name__ == "__main__":
    run_benchmarks()
