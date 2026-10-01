# Changelog

All notable changes to this project will be documented in this file.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2026-10-01

First release of the unified core. The Python package and the C++20 library now
share a single alphabet and a single definition of the wire format.

### Added

- **Core Base60 Codec (`hexa60`)**
  - 8-byte chunking to an 11-character Base60 representation, using the
    canonical identifier-safe alphabet
    `0123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnpqrstuvwxyz_-`.
  - Strict tail handling, `TAIL_CHARS = {0, 2, 3, 5, 6, 7, 9, 10}` for
    `r = 0..7` remaining bytes.
  - `InvalidCharacterError` (with character and absolute position) and
    `LengthError` (invalid layout, or a chunk over its byte width).
  - `decode_chunked_auto()` recovers the exact byte length from
    `len(text) % 11`; residues 1, 4 and 8 are rejected.

- **Base60 Integer Arithmetic (`base60_int`, `base60_arithmetic`)**
  - `Base60Int`: immutable value type, arbitrary-precision magnitude, full
    operator overloading (`+`, `-`, `*`, `/`, `%`, comparisons, `pow`).
  - Optional `modulus=` for circular arithmetic, propagated through operations.
  - Functional string API (`add_b60`, `sub_b60`, `mul_b60`, `divmod_b60`)
    with no object construction. `base60_arithmetic` keeps its original
    function names for backwards compatibility.
  - `base60_fraction`: periodic sexagesimal expansion with cycle detection.
  - 429 Python tests (355 codec + 43 integer + 31 functional), each operation
    checked against native Python integers.

- **C++20 header-only implementation (`cpp/`)**
  - Zero dependencies beyond the standard library, namespace `hexa60`.
  - `codec.hpp`, `int.hpp`, `fraction.hpp`, `tensor.hpp`, plus the umbrella
    header `hexa60.hpp`.
  - `constexpr` lookup table with compile-time proofs that the alphabet has 60
    distinct characters and that the tail tables are mutually inverse.
  - Test suite passes 70/70 under MSVC 19.50 with `/W4 /permissive-`, runnable
    with GoogleTest or with the bundled dependency-free harness
    (`-DHEXA60_NO_GTEST`).

### Tensor support

Two distinct implementations, with different roles:

- **Production: `cpp/include/hexa60/tensor.hpp`.** Fixed-width digit rows,
  zero dependencies, MSB-first convolution aligned at `2w - 2 - i - j` with
  carry propagating from LSB to MSB. The convolution accumulator is `uint64_t`
  and is proven at compile time to overflow only above
  `W ≈ 5.2 × 10^15`, which is unreachable in practice (the `std::array` alone
  would need ~80 PB first). Verified at widths up to 256.
- **Reference: `experiments/base60_tensor.py`.** A PyTorch batch-arithmetic
  experiment for advanced matrix work and research. It is **not** packaged
  for PyPI and is not imported by the core; its MSB-first convolution layout
  was used to validate the C++ version.

### Fixed

- 5-byte tails encode to **7** characters, not 8:
  `60^6 = 2.18e10 < 2^40 <= 60^7 = 2.80e12`. The larger value wastes a
  character and breaks length recovery from `len(text) % 11`.
- Tensor convolution alignment and carry direction (see above).
- Sign handling is no longer ambiguous: `-` is `ALPHABET[59]`, the digit 59,
  so a leading `-` cannot also be a sign. The wire-compatible
  `from_string()` / `to_b60()` never treat it as a sign; the signed form is
  opt-in via `from_string_signed()` / `to_signed_string()` and is explicitly
  **not** wire-compatible.
- Every module now reads the alphabet from `hexa60.ALPHABET`, so a codec value
  is directly usable as a number.

### Changed

- `base60_arithmetic` promoted from `experiments/` to a packaged module.
- `requires-python` raised from 3.8 to 3.9.

### Known limitations

- `Base60Int` is deliberately bounded to 64 bits of magnitude. Longer values
  raise `OverflowError` rather than silently wrapping. The tensor API is the
  path for wider arithmetic.
- Over-capacity chunks are rejected, never truncated. Roughly half of all
  11-character strings exceed `2^64` and will raise `LengthError`.
- `hexa60` is not a compression scheme. It is a transcription format; 8 bytes
  become 11 characters.
