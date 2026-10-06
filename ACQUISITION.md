# HEXA-60 CORE — Technical Summary for IP Acquisition

> HEXA-60 is a deterministic binary-to-text encoding technology that combines
> a fixed 8-byte-to-11-character mapping, a constrained identifier-safe
> alphabet, predictable 1.375x wire expansion, and native C++ throughput in
> the hundreds of MB/s, with 10,000/10,000 verified round trips across
> binary, UTF-8, JSON, CSV and edge-case datasets.

## 1. What the buyer gets

| Asset | Location | Notes |
|---|---|---|
| Python reference implementation | `hexa60.py` | Zero-dependency, `encode`/`decode` + `encode_chunked`/`decode_chunked_auto`, strict errors |
| Header-only C++20 library | `cpp/include/hexa60/` | `codec.hpp` (wire format), `fast_codec.hpp` (L1-pair-LUT), `int.hpp`, `fraction.hpp`, `tensor.hpp` |
| Rust core | `core-rust/` (`hexa60-core` 1.0.1) | Bit-identical chunked codec (`encode_chunked`/`decode_chunked_auto`), `thiserror` 2, 16 unit + 1 Python-vector tests |
| Native accelerator | `build_native.py` + `cpp/nanobind/` | Builds `_hexa60c` (MSVC, no CMake); auto-detected via `HAS_NATIVE` |
| Test suite | `tests/` | Codec boundaries, arithmetic, int — run with `pytest tests/` |
| Audit evidence | `benchmarks/` | `verify_integrity.py` (10k SHA-256), `benchmark_encode.py` + logs, `benchmark_pure_cpp.py` + `benchmark_native.cpp` + logs |
| Packaging | `pyproject.toml` | `hexa60`, `base60_int`, `base60_arithmetic` modules |

## 2. Verified technical facts (measured, reproducible)

- **Wire format:** 8 bytes -> 11 chars (`CHUNK_BYTES`/`CHUNK_CHARS`), tail
  `TAIL_CHARS = {0:0, 1:2, 2:3, 3:5, 4:6, 5:7, 6:9, 7:10}`; residue of
  `len(text) % 11` recovers tail length; residues 1/4/8 raise `LengthError`.
- **Expansion:** exactly **1.375x** on every full block (1 MB -> 1,375,000 B;
  100 MB -> 137,500,000 B), verified byte-for-byte including on-disk size.
- **Integrity:** **10,000/10,000 SHA-256 round trips PASS** (4,000 binary up
  to ~1 MB, 2,000 UTF-8 incl. CJK/diacritics/emoji, 1,000 JSON, 1,000 CSV,
  2,000 edge cases: all-zero, all-0xFF, `00 FF`, `AA 55`, 0–255 sequences).
- **Throughput (pure C++ vs C++, MSVC /O2, same buffers):** HEXA-60
  ~331/269 MB/s (enc/dec, 1 MB), ~245/156 MB/s (10 MB). Base64 is ~2.4x
  faster on encode — HEXA-60 competes on transport safety, not raw speed.
- **Throughput (Python level, native engine vs stdlib, identical data):**
  HEXA-60 ~345/298 (1 MB), ~261/200 (10 MB), ~222/177 (100 MB) MB/s,
  SHA-256 PASS everywhere.

## 3. Target segments

- **Database ID systems** — identifier-safe keys with computable length
  (`(n // 8) * 11 + TAIL[n % 8]`), no `+ / =` to escape in keys/URLs.
- **API gateways** — header-token-safe payloads without percent-encoding;
  strict `InvalidCharacterError` (char + index) at trust boundaries.
- **IoT / Embedded** — header-only C++20, zero dependencies, O(N) chunked
  path, deterministic memory profile per 8-byte block.
- **Optical / QR systems** — constrained 60-char alphabet (no `I O l o`
  lookalikes, no quotes/slashes); note: lowercase falls back to QR byte mode.

## 4. Honest limitations (for the purchase decision)

- +3.2 % wire size vs Base64 (1.375x vs 1.333x).
- Slower than Base64 in pure C++ (division/modulo 60 vs bit shifts).
  Optimization path: wider LUT blocking / SWAR division (see `fast_codec.hpp`).
- `decode_chunked()` defaults to lenient `strict=False` (lossy on corruption);
  cross-boundary input must use `strict=True` (planned default change noted
  in `CHANGELOG.md` 1.0.1 entry).

## 5. Reproduction (one cycle each)

- Tests: `pytest tests/`
- Rust core: `cd core-rust && cargo test --release` (16 unit + 1 Python-vector tests)
- Integrity: `python benchmarks/verify_integrity.py`
- Python-level shootout: `python benchmarks/benchmark_encode.py`
- Pure C++ shootout: `python benchmarks/benchmark_pure_cpp.py`
- Native rebuild: `python build_native.py`

## 6. Commercial terms

Dual-licensed (AGPLv3 open source / commercial OEM); full IP assignment
available under negotiation. See `LICENSE` (acquisition notice) and
`LICENSE-v2.md` (AGPL terms). Contact: `mullerladislav20@gmail.com`.
