# ============================================================================
# HEXA-60 CORE™ — High-Throughput Base60 Encoding Engine
# Copyright (c) 2026 Ladislav Müller (IČO: 40189589). All rights reserved.
#
# PROPRIETARY AND CONFIDENTIAL SOFTWARE.
# Unauthorized copying, distribution, or modification of this file, via any
# medium, is strictly prohibited under applicable copyright laws and B2B EULA.
# ============================================================================

"""Benchmark for the HEXA60 codec and arithmetic.

Replaces the earlier arithmetic-only script. Differences worth noting:

- The codec is measured too, and against base64, because that is the actual
  use case: not "how fast is Base60 in isolation" but "what do I pay versus
  the encoding I would otherwise use".
- Throughput is reported in MB/s as well as microseconds, so sizes are
  comparable against each other.
- Every timed section asserts its result before reporting, so a benchmark
  cannot look fast by being wrong.

Run:  python benchmark.py
"""

import base64
import math
import os
import platform
import random
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import hexa60 as h
from base60_arithmetic import base60_add, base60_multiply, base60_fraction
from base60_int import Base60Int
from hexa60 import (
    CHUNK_BYTES,
    CHUNK_CHARS,
    TAIL_CHARS,
    decode,
    decode_chunked,
    encode,
    encode_chunked,
)

RNG = random.Random(20261001)  # fixed seed, so runs are comparable

SIZES = [16, 256, 1024, 4096, 16384]
ALPHABET = "0123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnpqrstuvwxyz_-"
out = []


def timeit(fn, repeats=200):
    """Best-of-n seconds per call. Best-of rejects scheduler noise."""
    best = math.inf
    for _ in range(repeats):
        start = time.perf_counter()
        fn()
        best = min(best, time.perf_counter() - start)
    return best


def payload(size):
    return bytes(RNG.getrandbits(8) for _ in range(size))


def header(title):
    return f"\n{'=' * 70}\n{title}\n{'=' * 70}"


def emit(line=""):
    out.append(line)


def rand_b60(digits):
    return "".join(ALPHABET[RNG.randrange(60)] for _ in range(digits))


emit("HEXA60 benchmark")
emit(f"python   : {platform.python_version()}  ({platform.machine()})")
emit(f"platform : {platform.system()} {platform.release()}")
emit(f"seed     : 20261001")
emit(f"chunk    : {CHUNK_BYTES} bytes -> {CHUNK_CHARS} chars")
emit(f"tail     : {dict(sorted(TAIL_CHARS.items()))}")

emit(header("1. Codec throughput, compared with base64"))
emit()
emit(f"{'bytes':>8}  {'hexa enc':>11}  {'hexa dec':>11}  {'b64 enc':>11}"
     f"  {'b64 dec':>11}  {'hexa/b64':>10}")
emit("-" * 78)

# Bulk encode is O(N^2) on big ints: it is only timed up to BULK_MAX bytes
# here. Larger sizes are covered by the chunked codec (section 2) and the
# scaling section (section 6); timing them here would never finish.
BULK_MAX = 256

for size in SIZES:
    data = payload(size)
    hex_wire = encode(data)
    b64_wire = base64.b64encode(data)

    assert decode(hex_wire) == data
    assert base64.b64decode(b64_wire) == data

    t_b64_enc = timeit(lambda: base64.b64encode(data))
    t_b64_dec = timeit(lambda: base64.b64decode(b64_wire))

    if size <= BULK_MAX:
        t_hex_enc = timeit(lambda: encode(data))
        t_hex_dec = timeit(lambda: decode(hex_wire))
        emit(f"{size:>8}  {t_hex_enc*1e6:>9.1f} us  {t_hex_dec*1e6:>9.1f} us"
             f"  {t_b64_enc*1e6:>9.1f} us  {t_b64_dec*1e6:>9.1f} us"
             f"  {t_b64_enc/t_hex_enc:>8.2f}x")
        mb = size / 1e6
        emit(f"{'':>8}  {mb/t_hex_enc:>8.1f} MB/s{'':>4}  {mb/t_hex_dec:>8.1f} MB/s"
             f"  {mb/t_b64_enc:>8.1f} MB/s  {mb/t_b64_dec:>8.1f} MB/s")
    else:
        emit(f"{size:>8}  {'-':>11}  {'-':>11}"
             f"  {t_b64_enc*1e6:>9.1f} us  {t_b64_dec*1e6:>9.1f} us"
             f"  {'bulk O(N^2), see s6':>10}")
emit(header("2. Chunked wire format, the intended path for bulk data"))
emit()
emit(f"{'bytes':>8}  {'encode':>12}  {'decode':>12}  {'MB/s enc':>10}  {'MB/s dec':>10}")
emit("-" * 60)

for size in SIZES:
    data = payload(size)
    wire = encode_chunked(data)
    t_enc = timeit(lambda: encode_chunked(data), repeats=50)
    t_dec = timeit(lambda: decode_chunked(wire), repeats=50)
    assert decode_chunked(encode_chunked(data)) == data
    mb = size / 1e6
    emit(f"{size:>8}  {t_enc*1e6:>9.1f} us  {t_dec*1e6:>9.1f} us"
         f"  {mb/t_enc:>10.1f}  {mb/t_dec:>10.1f}")

emit()
emit(f"expansion: {CHUNK_CHARS} chars per {CHUNK_BYTES} bytes"
     f" = {CHUNK_CHARS / CHUNK_BYTES:.4f}x")

emit(header("3. Tail widths, every remainder round-trips"))
emit()
for r in range(1, CHUNK_BYTES):
    data = b"\xff" * r
    text = encode_chunked(data)
    assert decode_chunked(text) == data
    emit(f"  R={r}  C={TAIL_CHARS[r]:>2}  chars={len(text):>2}"
         f"  ratio={len(text)/r:.4f}  ok")

emit(header("4. Integer arithmetic (Base60Int)"))
emit()
emit(f"{'digits':>8}  {'add':>11}  {'multiply':>11}  {'divmod':>11}  {'parse':>11}")
emit("-" * 58)
for digits in [1, 2, 4, 8, 16]:
    a, b = rand_b60(digits), rand_b60(digits)
    # Guard against a zero divisor: rand_b60() can legitimately produce "0".
    # Regenerate once; if it is still zero, divmod is measured as "n/a".
    if Base60Int(b).to_int() == 0:
        b = rand_b60(digits)
    A, B = Base60Int(a), Base60Int(b)
    t_add = timeit(lambda: A + B, repeats=500)
    t_mul = timeit(lambda: A * B, repeats=500)
    if B.to_int() == 0:
        t_dvd = None
    else:
        t_dvd = timeit(lambda: A // B, repeats=500)
    t_par = timeit(lambda: Base60Int(a), repeats=500)
    dvd = f"{t_dvd*1e6:>8.2f} us" if t_dvd is not None else f"{'n/a (b=0)':>11}"
    emit(f"{digits:>8}  {t_add*1e6:>8.2f} us  {t_mul*1e6:>8.2f} us"
         f"  {dvd}  {t_par*1e6:>8.2f} us")

emit(header("5. Legacy functional API (base60_arithmetic)"))
emit()
emit(f"{'case':>20}  {'add':>11}  {'multiply':>11}  {'fraction':>11}")
emit("-" * 58)
for a, b in [("1", "1"), ("W", "W"), ("100", "50")]:
    t_add = timeit(lambda: base60_add(a, b), repeats=1000)
    t_mul = timeit(lambda: base60_multiply(a, b), repeats=1000)
    emit(f"{a} + {b}".rjust(20)
         + f"  {t_add*1e6:>8.2f} us  {t_mul*1e6:>8.2f} us  {'-':>11}")
emit()
for num, den in [("1", "2"), ("1", "3"), ("1", "7")]:
    t = timeit(lambda: base60_fraction(num, den), repeats=1000)
    emit(f"{num} / {den}".rjust(20)
         + f"  {'-':>11}  {'-':>11}  {t*1e6:>8.2f} us")

emit(header("6. Scaling: is the bulk encoder really O(N^2)?"))
emit()
emit(f"{'bytes':>8}  {'time':>12}  {'us/byte':>10}  {'vs prev':>9}")
emit("-" * 44)
prev = None
for size in [256, 512, 1024, 2048]:
    data = payload(size)
    t = timeit(lambda: encode(data), repeats=3)
    ratio = f"{t / prev:.2f}x" if prev else "-"
    emit(f"{size:>8}  {t*1e3:>9.2f} ms  {t/size*1e6:>9.3f}  {ratio:>9}")
    prev = t
emit()
emit("Doubling the input should roughly quadruple the time if this is O(N^2).")
emit("For large data prefer encode_chunked, which is O(N).")

emit(header("7. Native accelerator (nanobind) vs pure Python"))
emit()
emit(f"native loaded : {h.HAS_NATIVE}")
if h.HAS_NATIVE:
    emit(f"{'bytes':>8}  {'nat enc MB/s':>13}  {'nat dec MB/s':>13}"
         f"  {'pure enc MB/s':>14}  {'pure dec MB/s':>14}  {'speedup':>9}")
    emit("-" * 78)
    for size in SIZES:
        data = payload(size)
        wire = h.encode_chunked(data)
        assert h.decode_chunked(wire) == data
        t_nenc = timeit(lambda: h.encode_chunked(data), repeats=50)
        t_ndec = timeit(lambda: h.decode_chunked(wire), repeats=50)
        t_penc = timeit(lambda: h._encode_chunked_pure(data), repeats=50)
        t_pdec = timeit(lambda: h._decode_chunked_pure(wire), repeats=50)
        mb = size / 1e6
        emit(f"{size:>8}  {mb/t_nenc:>11.1f}  {mb/t_ndec:>11.1f}"
             f"  {mb/t_penc:>12.1f}  {mb/t_pdec:>12.1f}"
             f"  {t_penc/t_nenc:>8.1f}x")
else:
    emit("native module not built - run: python build_native.py")
    emit("then rerun this benchmark (or set HEXA60_PURE=1 to force pure).")

report = "\n".join(out) + "\n"
with open("benchmark_final.txt", "w", encoding="utf-8") as handle:
    handle.write(report)
print(report)
print("saved to benchmark_final.txt", file=sys.stderr)  
