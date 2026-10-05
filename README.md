# HEXA60: Identifier-Safe Binary-to-Text Encoding Specification & Reference Implementation

[![License: AGPL v3](https://img.shields.io/badge/License-AGPL_v3-blue.svg)](LICENSE-v2.md)
[![Python Version](https://img.shields.io/badge/python-3.9%2B-blue)](https://www.python.org/)
[![C++ Standard](https://img.shields.io/badge/c%2B%2B-20-blue.svg)](cpp/)
[![Code Style](https://img.shields.io/badge/code%20style-pep8-green.svg)](https://www.python.org/dev/peps/pep-0008/)

**HEXA60** is a deterministic, high-performance binary-to-text encoding scheme engineered specifically for transport safety across modern network protocols, web APIs, biometrics, and database storage.

Unlike traditional Base64 (which requires characters like `+`, `/`, and `=`) or Base58, HEXA60 uses an **identifier-safe 60-character alphabet**. It eliminates all characters requiring URL percent-encoding, regex escaping, or special handling in HTTP headers, QR codes, and SQL queries.

---

## Key Features

- 🛡️ **Identifier-Safe Alphabet:** Devoid of `+`, `/`, `=`, and punctuation that triggers URL encoding or header parsing errors.
- ⚡ **$\mathcal{O}(N)$ Chunked Encoding:** High-throughput `encode_chunked()` processes 8-byte blocks into 11-character chunks in linear time ($\mathcal{O}(N)$), making it ideal for large payloads and biometrics.
- 0️⃣ **Deterministic Zero-Byte Preservation:** Preserves leading zero bytes (`b'\x00'`) by mapping them directly to `'0'` characters (the first character of `ALPHABET`).
- 🔍 **Strict Error Handling:** Immediate detection of corrupted input via `InvalidCharacterError` (with exact character and index position) and `LengthError`.
- 🔄 **Automatic Tail Length Detection:** `decode_chunked_auto()` recovers exact original byte length without requiring length metadata.
- ✅ **Pre-flight Validation:** Fast `is_valid()` utility to check reformatting and sanitization before decoding.

---

## Table of Contents

- [Alphabet Specification](#alphabet-specification)
- [Installation](#installation)
- [Quick Start](#quick-start)
  - [1. Bulk Encoding & Decoding](#1-bulk-encoding--decoding)
  - [2. High-Performance Chunked Encoding](#2-high-performance-chunked-encoding)
  - [3. Input Validation & Error Handling](#3-input-validation--error-handling)
  - [Chunk capacity](#chunk-capacity)
- [Encoding Modes](#encoding-modes)
- [Arithmetic](#arithmetic)
  - [Base60Int (object-oriented)](#base60int-object-oriented)
  - [Functional API](#functional-api)
  - [Periodic fractions](#periodic-fractions)
  - [Tail handling](#tail-handling)
- [Legacy API](#legacy-api)
- [Licensing](#licensing)

---

## Alphabet Specification

HEXA60 uses a fixed 60-character alphabet (`ALPHABET`):

```text
0123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnpqrstuvwxyz_-
```

- **Index 0:** `'0'` (used for zero-padding and leading zero bytes)
- **Safe Characters:** Numbers (`0-9`), Uppercase (`A-Z` except `I` and `O`), Lowercase (`a-z` except `l` and `o`), Underscore (`_`), Hyphen (`-`).
- **Excluded Ambiguous Characters:** `I`, `O`, `l`, `o` — each collides visually with `1`, `0`, `1` and `0` respectively. They are absent from the alphabet, so `decode(..., strict=True)` rejects them.
- **Index 59:** `'-'` is the digit 59, **not** a sign. Signed parsing is opt-in via `from_string_signed()` and is explicitly not wire-compatible.
- **Counts:** 10 digits + 24 uppercase + 24 lowercase + 2 = 60 characters.

The same string is defined once in `hexa60.ALPHABET` and once in `cpp/include/hexa60/codec.hpp`; the two must stay bit-identical. `tests/test_codec_boundaries.py` keeps a third independent copy and asserts all three agree.

---

## Installation

Install via `pip` (or include `hexa60.py` directly in your project):

```bash
pip install hexa60
```

---

## Quick Start

### 1. Bulk Encoding & Decoding

Suitable for short tokens, hashes, UUIDs, and API keys:

```python
from hexa60 import encode, decode

# Encoding arbitrary bytes (including leading zeros)
data = b"\x00\x00\x01\x02\x03\xff\xfe"
encoded_str = encode(data)
print(f"Encoded: {encoded_str}")

# Decoding back to bytes
decoded_bytes = decode(encoded_str)
assert decoded_bytes == data
```

### 2. High-Performance Chunked Encoding

Recommended for biometrics, payload streams, and large files ($\mathcal{O}(N)$ linear time complexity):

```python
from hexa60 import encode_chunked, decode_chunked_auto

payload = b"BiometricTemplateData_2026_Sample_Payload"

# Chunked Encoding (8-byte chunks -> 11 characters)
wire_format = encode_chunked(payload)
print(f"Wire Format: {wire_format}")

# Automatic Decoding (infers exact byte length automatically)
restored_payload = decode_chunked_auto(wire_format)
assert restored_payload == payload
```

### 3. Input Validation & Error Handling

```python
from hexa60 import is_valid, decode, decode_chunked_auto
from hexa60 import Base60Error, InvalidCharacterError, LengthError

user_input = "41SmmMHgyT7SbqrV1EEW_-"

if not is_valid(user_input):          # requires a str, raises TypeError otherwise
    print("Invalid HEXA60 string detected!")

try:
    decoded = decode(user_input, strict=True)     # strict=True is the default
except InvalidCharacterError as err:
    print(f"Invalid character {err.char!r} at position {err.position}")
except LengthError as err:
    print(f"Length mismatch: {err}")
except Base60Error as err:
    print(f"Other HEXA60 error: {err}")
```

Bulk `decode()` also accepts `length=` to left-pad with zero bytes or truncate
to exactly that size; a negative `length` raises `LengthError`.

### Chunk capacity

The example strings in the protocol illustration (`A1XA608EF`, `BK0WK27GK`, the
`HEXA60...` token) are 9 or 27 characters long, i.e. they are **bulk**
(`encode`) output, not `encode_chunked` output. Chunked output is always a
multiple of 11 characters plus a valid tail, so those strings must be decoded
with `decode()`.

`60**11 = 36279705600000000000` is larger than `2**64 = 18446744073709551616`, so
the 11-character space is slightly wider than the 8-byte space it encodes. An
`encode_chunked` value is always below `2**64` and therefore always decodable,
but roughly half of all theoretical 11-character strings cannot be represented
as 8 bytes. Such an over-capacity chunk raises `LengthError` — it is never
silently truncated to a shorter buffer.

```python
from hexa60 import decode_chunked_auto, encode_chunked, LengthError

encode_chunked(b"\xff" * 8)          # always round-trips
decode_chunked_auto("z" * 11)        # raises LengthError (over capacity)
```

The same rule applies to tails: a tail whose value needs more bytes than its
tail width implies is rejected rather than truncated.

---

## Encoding Modes

| Function | Format | Complexity | Use |
| :--- | :--- | :--- | :--- |
| `encode` / `decode` | Bulk (single big integer) | $\mathcal{O}(N^2)$ | Short tokens, salts, nonces |
| `encode_chunked` / `decode_chunked` | 8 bytes $\rightarrow$ 11 chars | $\mathcal{O}(N)$ | Large payloads, biometrics |

**Bulk and chunked output are different formats and are not interchangeable.**
Do not pass `encode_chunked` output to `decode`.

---

## Arithmetic

Beyond binary-to-text encoding, the package provides **Base-60 integer
arithmetic**. Both modules use the same `ALPHABET` as the codec, so a value
encoded by `hexa60` is directly usable as a number.

### Base60Int (object-oriented)

`Base60Int` is an immutable value type. It stores a Python `int` internally
(arbitrary precision) and renders itself as Base-60 text on demand.

```python
from base60_int import Base60Int

n = Base60Int(60)
n.to_b60()              # '10'  -- because 60 == '10' in Base-60
n + n                  # Base60Int('20')
n * n                  # Base60Int('100')

Base60Int(2) ** 10     # Base60Int('H4')  -- 1024 in decimal
int(Base60Int("10"))   # 60
```

It accepts `int`, `str` (Base-60 text), `bytes` (big-endian) or another
`Base60Int`. Comparison, `hash` and the usual arithmetic operators all work:

```python
a, b = Base60Int(60), Base60Int(61)
a < b                  # True
{a, Base60Int("10")}   # set works -- equal values hash equal

# mixed with plain int and Base-60 strings
n = Base60Int(10)
n + 5                  # 15
n + "5"                # 15
```

**No sign.** Base-60 has no room for a sign position, so a negative result is
rejected rather than silently mis-encoded:

```python
Base60Int(1) - Base60Int(5)   # raises ValueError
```

Pass `modulus=` for circular arithmetic — every result is normalised into
`[0, modulus)` and the modulus propagates through the whole chain:

```python
x = Base60Int(50, modulus=60)
(x + 30).to_int()             # 20
```

### Functional API

If you only need a one-off operation on strings, `base60_int` also exposes
digit-level helpers that avoid object overhead:

```python
from base60_int import add_b60, mul_b60, divmod_b60

add_b60("10", "10")       # '20'
mul_b60("10", "10")       # '100'
divmod_b60("10", "3")     # ('L', '0')  -- 60 // 3, 60 % 3
```

The older `base60_arithmetic` module offers the same style of operations under
its original names (`base60_add`, `base60_multiply`, ...). Both modules produce
identical results; `base60_int` is the recommended entry point because its
multiplication is $\mathcal{O}(n \cdot m)$ without the `insert(0, ...)`
reallocation cost of the original implementation.

```python
import base60_arithmetic as arith

arith.base60_add("10", "10")        # '20'
arith.base60_multiply("10", "10")   # '100'
```

### Periodic fractions

`base60_arithmetic.base60_fraction` performs long division directly in Base-60
and returns a fractional string, detecting repeating cycles automatically:

```python
from base60_arithmetic import base60_fraction

base60_fraction("1", "3")     # '0.L'      -- 20 + 20 + 20 ... = 0.333...
base60_fraction("1", "2")     # '0.W'      -- 30/60
base60_fraction("1", "4")     # '0.F'      -- 15/60
base60_fraction("1", "5")     # '0.C'      -- 12/60
base60_fraction("1", "6")     # '0.A'      -- 10/60
base60_fraction("1", "60")    # '0.0A'     -- 10/60^2, "60" == 60
base60_fraction("2", "3")     # '0.g'      -- 40 + 20 + 20 ... = 0.666...
base60_fraction("1", "7")     # '0.8aH'    -- cycle 8,a,H (60 == 4 mod 7)
```

Note the denominator is itself Base-60: `base60_fraction("1", "10")` divides 1
by **60** (since `"10"` is `1*60 + 0`), not by decimal 10.

### Tail handling

Leftover bytes use `TAIL_CHARS`, derived as `C = ceil(CHUNK_BYTES * r / log2(60))`:

| Remaining bytes (R) | 1 | 2 | 3 | 4 | 5 | 6 | 7 |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| Chars (C) | 2 | 3 | 5 | 6 | 7 | 9 | 10 |

The resulting residues modulo `CHUNK_CHARS` (11) are `0, 2, 3, 5, 6, 7, 9, 10` —
all unique, so `decode_chunked_auto` recovers the tail length from
`len(text) % 11` without extra metadata. Residues **1, 4 and 8 are invalid** and
raise `LengthError` instead of being decoded.

### Legacy API

| Name | Alias of | Notes |
| :--- | :--- | :--- |
| `bytes_to_base60(data)` | `encode` | Bulk encoder |
| `base60_to_bytes(text, length=)` | `decode` | Strict by default |
| `base60_to_bytes_lenient(s, length)` | — | Skips bad chars, truncates instead of raising (lossy) |

`BASE60_DIGITS.py`, `BASE60_CORE.py`, `BASE60_BINAR.py` and `base60.py` are
retained for backwards compatibility and now delegate to `hexa60`. The chunked
output is **no longer** the historical `3 bytes -> 5 chars` layout, so legacy
aliases cannot decode records stored under the old format.

---

## Input validation

`encode()` and `encode_chunked()` accept any bytes-like object — `bytes`,
`bytearray` or `memoryview` — and raise `TypeError` for anything else. An empty
input encodes to `""`, which is the encoding of `b""`.

> **Note (1.0.1):** these encoders previously began with `if not data: return ""`,
> which is also true for `None`. `encode(None)` returned an empty string instead
> of reporting the type error, so a caller that lost its buffer received a silent
> empty result that round-trips to `b""` and looks like valid data. It now raises.

`decode()` is strict by default and raises `InvalidCharacterError`.

`decode_chunked()` is **lenient** by default: with `strict=False` it silently
strips characters outside the alphabet. In a chunked payload this shifts every
subsequent block boundary, so corrupted input can decode to entirely different
bytes without any error. Pass `strict=True` when the input is not already
trusted, and see the 1.0.1 entry in `CHANGELOG.md`.

---

## Licensing

HEXA60 is published under a **Dual-Licensing Model**:

1. **Open-Source (GNU AGPLv3):** Free for open-source applications, personal projects, and academic research under the terms of the [GNU Affero General Public License v3.0](LICENSE-v2.md).
2. **Commercial OEM License:** Required for commercial entities, closed-source proprietary applications, and SaaS integrations that do not wish to be bound by AGPLv3 copyleft terms.

For commercial licensing enquiries, custom integration support, or OEM agreement details, please contact: `mullerladislav20@gmail.com`.
