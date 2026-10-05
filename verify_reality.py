# ============================================================================
# HEXA-60 CORE™ — High-Throughput Base60 Encoding Engine
# Copyright (c) 2026 Ladislav Müller (IČO: 40189589). All rights reserved.
#
# PROPRIETARY AND CONFIDENTIAL SOFTWARE.
# Unauthorized copying, distribution, or modification of this file, via any
# medium, is strictly prohibited under applicable copyright laws and B2B EULA.
# ============================================================================

import sys
import os
import time
import random

# Ensure UTF-8 output on Windows consoles
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import hexa60

try:
    import _hexa60c
    HAS_NATIVE = True
except ImportError:
    HAS_NATIVE = False


def inspect_engine():
    print("=" * 80)
    print("           HEXA-60 CORE™: REALITY CHECK & DUAL-ENGINE VERIFICATION            ")
    print("=" * 80)
    print(f"Python Runtime : {sys.version.split()[0]} ({sys.platform})")
    print(f"Architecture   : {sys.maxsize > 2**32 and '64-bit' or '32-bit'}")
    print(f"Pure Python    : hexa60._encode_chunked_pure -> {type(hexa60._encode_chunked_pure)}")
    
    if HAS_NATIVE:
        print(f"Native Module  : _hexa60c -> {getattr(_hexa60c, '__file__', 'in-memory')}")
        print(f"Native Function: _hexa60c.encode_chunked -> {type(_hexa60c.encode_chunked)}")
        print(f"ABI Version    : {getattr(_hexa60c, 'ABI_VERSION', 'N/A')}")
        print(f"Native Active  : {hexa60.HAS_NATIVE}")
    else:
        print("Native Module  : NOT FOUND / DISABLED")
    print("=" * 80)


def benchmark_function(fn, data, min_seconds=0.4, warmup_iters=100):
    # Warmup phase (primes CPU caches & avoids JIT/allocation latency)
    for _ in range(warmup_iters):
        _ = fn(data)

    # Measurement phase
    t0 = time.perf_counter()
    iters = 0
    while True:
        _ = fn(data)
        iters += 1
        elapsed = time.perf_counter() - t0
        if elapsed >= min_seconds and iters >= 50:
            break

    total_bytes = len(data) * iters if isinstance(data, (bytes, bytearray)) else len(data.encode('ascii')) * iters
    mb_per_sec = (total_bytes / elapsed) / 1_000_000.0
    ns_per_block = (elapsed / iters) * 1e9 / (len(data) / 8.0) if len(data) >= 8 else 0.0
    return mb_per_sec, ns_per_block, iters, elapsed


def run_reality_verification():
    inspect_engine()

    if not HAS_NATIVE:
        print("\n[ERROR] Cannot perform comparison because C++ native module (_hexa60c) is not loaded.")
        return

    sizes = [
        ("16 B", 16),
        ("256 B", 256),
        ("1 KiB", 1024),
        ("4 KiB", 4096),
        ("16 KiB", 16384),
        ("64 KiB", 65536)
    ]

    print("\n[1] Bit-Identical Parity Verification (C++20 vs Pure Python):")
    rng = random.Random(20261005)
    for label, sz in sizes:
        sample = bytes(rng.getrandbits(8) for _ in range(sz))
        
        py_enc = hexa60._encode_chunked_pure(sample)
        nat_enc = _hexa60c.encode_chunked(sample)
        assert py_enc == nat_enc, f"Parity mismatch on encode for size {sz}!"

        py_dec = hexa60._decode_chunked_pure(nat_enc, strict=True)
        nat_dec = _hexa60c.decode_chunked(py_enc)
        assert py_dec == sample, f"Pure Python decode failed on size {sz}!"
        assert nat_dec == sample, f"Native C++ decode failed on size {sz}!"

    print("    [PASS] 100% Bit-Identical parity verified across all payload sizes.\n")

    print("[2] High-Precision Throughput Benchmark (time.perf_counter):")
    header = (
        f"{'Payload':<8} | "
        f"{'Py Enc':>9} | {'Nat Enc':>10} | {'Enc Boost':>9} | "
        f"{'Py Dec':>9} | {'Nat Dec':>10} | {'Dec Boost':>9} | "
        f"{'Nat Enc ns/8B':>13}"
    )
    print(header)
    print("-" * len(header))

    for label, sz in sizes:
        payload = bytes(rng.getrandbits(8) for _ in range(sz))
        wire = _hexa60c.encode_chunked(payload)

        # Pure Python timings
        py_enc_mb, _, _, _ = benchmark_function(hexa60._encode_chunked_pure, payload, min_seconds=0.3)
        py_dec_mb, _, _, _ = benchmark_function(lambda w: hexa60._decode_chunked_pure(w, strict=True), wire, min_seconds=0.3)

        # Native C++20 timings
        nat_enc_mb, nat_enc_ns, _, _ = benchmark_function(_hexa60c.encode_chunked, payload, min_seconds=0.4)
        nat_dec_mb, _, _, _ = benchmark_function(_hexa60c.decode_chunked, wire, min_seconds=0.4)

        enc_boost = nat_enc_mb / py_enc_mb if py_enc_mb > 0 else 0
        dec_boost = nat_dec_mb / py_dec_mb if py_dec_mb > 0 else 0

        print(
            f"{label:<8} | "
            f"{py_enc_mb:>7.2f} MB/s | {nat_enc_mb:>8.2f} MB/s | {enc_boost:>8.1f}x | "
            f"{py_dec_mb:>7.2f} MB/s | {nat_dec_mb:>8.2f} MB/s | {dec_boost:>8.1f}x | "
            f"{nat_enc_ns:>11.2f} ns"
        )

    print("-" * len(header))
    print("\n[VERDICT]: Native C++20 Ultra Acceleration is ACTIVE and verified in this environment.")


if __name__ == "__main__":
    run_reality_verification()
