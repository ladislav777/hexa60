# ============================================================================
# HEXA-60 CORE™ — High-Throughput Base60 Encoding Engine
# Copyright (c) 2026 Ladislav Müller (IČO: 40189589). All rights reserved.
#
# PROPRIETARY AND CONFIDENTIAL SOFTWARE.
# Unauthorized copying, distribution, or modification of this file, via any
# medium, is strictly prohibited under applicable copyright laws and B2B EULA.
# ============================================================================

# ============================================
# hexa60.py – HEXA60 reference implementation
# ============================================
# Deterministic, identifier-safe binary-to-text encoding.
#
# Alphabet: 60 unique chars, no '+', '/', '='  -> no URL/header/QR escaping.
# Chunks:    CHUNK_BYTES (8) -> CHUNK_CHARS (11), ratio 1.375
# Tail:      TAIL_CHARS[r] chars for r leftover bytes (r < CHUNK_BYTES)
#
# NOTE: encode_chunked output is a dedicated wire format and is NOT
#       compatible with the bulk decode().

import importlib
import math
import os

__all__ = [
    "ALPHABET",
    "BASE",
    "LOOKUP",
    "CHUNK_BYTES",
    "CHUNK_CHARS",
    "TAIL_CHARS",
    "Base60Error",
    "InvalidCharacterError",
    "LengthError",
    "is_valid",
    "encode",
    "decode",
    "encode_chunked",
    "decode_chunked",
    "decode_chunked_auto",
    "bytes_to_base60",
    "base60_to_bytes",
    "base60_to_bytes_lenient",
    "HAS_NATIVE",
]

# 60 unique characters. Excluded for visual ambiguity: I, O (upper), l, o (lower).
ALPHABET = "0123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnpqrstuvwxyz_-"
BASE = 60
LOOKUP = {ch: i for i, ch in enumerate(ALPHABET)}

# --- hot-path lookup tables (Phase 1 optimisation) ---------------------------
# _ENC/_DEC are the SAME alphabet as LOOKUP, only in a branch-light form:
# _DEC[ord(c)] is an int list lookup instead of a dict probe. LOOKUP stays
# the canonical public mapping; keep both in sync (asserted in tests).
_ENC = ALPHABET.encode("ascii")
_DEC = [-1] * 256
for _i, _c in enumerate(_ENC):
    _DEC[_c] = _i
assert len(_ENC) == BASE and all(_DEC[c] == i for i, c in enumerate(_ENC))

CHUNK_BYTES = 8
CHUNK_CHARS = 11

# TAIL_CHARS[r] = digits needed to encode a tail of r trailing bytes.
#
# A tail of R bytes holds any value in 0 .. 2**(8R), and one Base-60 digit
# carries log2(60) bits, so the minimum width is:
#
#     C(R) = ceil(8R / log2(60)),   1 <= R <= 7   (and C(0) = 0)
#
# CHUNK_BYTES * r below is exactly 8R; it is a byte count, not a bit count.
# Do not multiply by CHUNK_BYTES a second time -- that gives the bit width
# of a whole chunk and produces far too many digits.
TAIL_CHARS = {
    r: math.ceil(CHUNK_BYTES * r / math.log2(BASE)) for r in range(CHUNK_BYTES)
}
_REM_FROM_TAIL_CHARS = {c: r for r, c in TAIL_CHARS.items()}


# --- optional native accelerator (Phase 3) -----------------------------------
# _hexa60c is a nanobind extension wrapping the L1-pair-LUT C++ core. Loading
# it is OPTIONAL and never breaks the pure-Python import:
#   * HEXA60_PURE=1 (or any value other than "", "0", "false") forces pure,
#   * ImportError (not built) or any load failure -> pure fallback,
#   * ABI mismatch -> pure fallback (the wrapper changes with the header).
_NATIVE_ABI = 1
_NATIVE_CANDIDATES = ("_hexa60c", "_hexa60_native")


def _load_native():
    """Return the compiled codec module, or None for pure-Python mode."""
    if os.environ.get("HEXA60_PURE", "") not in ("", "0", "false", "False"):
        return None
    for name in _NATIVE_CANDIDATES:
        try:
            mod = importlib.import_module(name)
        except ImportError:
            continue
        except Exception:
            # Corrupt / ABI-mismatched binary: never break the pure import.
            continue
        if getattr(mod, "ABI_VERSION", None) == _NATIVE_ABI:
            return mod
    return None


_NATIVE = _load_native()
HAS_NATIVE = _NATIVE is not None



class Base60Error(Exception):
    """Base class for all HEXA60 errors."""


class InvalidCharacterError(Base60Error):
    """Raised on a character outside ALPHABET during strict decoding."""

    def __init__(self, char, position):
        self.char = char
        self.position = position
        super().__init__(
            f"Invalid HEXA60 character {char!r} at position {position}"
        )


class LengthError(Base60Error):
    """Raised when a chunk layout or value does not fit the HEXA60 format.

    Covers both a total encoded length that does not match a valid chunk
    layout and an individual chunk whose value is too large for its byte
    width.
    """

    def __init__(self, length, expected):
        self.length = length
        self.expected = expected
        shown = sorted(str(e) for e in expected)
        super().__init__(
            f"Invalid HEXA60 length {length}; expected one of {shown}"
        )


def is_valid(text) -> bool:
    """True if `text` is a str containing only ALPHABET characters.

    The empty string is valid: it is the encoding of b"".
    Raises TypeError for non-str input (bytes must be decoded first).
    """
    if not isinstance(text, str):
        raise TypeError(f"is_valid() expects str, got {type(text).__name__}")
    dec = _DEC
    for ch in text:
        o = ord(ch)
        if o > 255 or dec[o] < 0:
            return False
    return True


def _prepare(text, strict):
    """Validate type, optionally raise on bad chars, else strip them."""
    if not isinstance(text, str):
        raise TypeError(f"Expected str, got {type(text).__name__}")
    if strict:
        dec = _DEC
        for i, ch in enumerate(text):
            o = ord(ch)
            if o > 255 or dec[o] < 0:
                raise InvalidCharacterError(ch, i)
        return text
    return "".join(ch for ch in text if ch in LOOKUP)


def _encode_fixed(num, width):
    """Encode `num` as exactly `width` Base-60 digits (big-endian).

    Hot path: writes into a preallocated bytearray at the caller's offset
    instead of building and joining small strings.
    """
    enc = _ENC
    buf = bytearray(width)
    for i in range(width - 1, -1, -1):
        num, r = divmod(num, BASE)
        buf[i] = enc[r]
    return bytes(buf).decode("ascii")


def _write_fixed(buf: bytearray, off: int, num: int, width: int) -> None:
    """Encode `num` as `width` digits directly into `buf` at `off`."""
    enc = _ENC
    for i in range(width - 1, -1, -1):
        num, r = divmod(num, BASE)
        buf[off + i] = enc[r]


def _encode_chunked_pure(raw: bytes) -> str:
    """Pure-Python chunked encoder (Phase 1 bytearray hot path).

    Single preallocated bytearray: each chunk is written at its own offset,
    so no per-chunk strings are built or joined. `raw` must be bytes-like
    (type validation happens in encode_chunked).
    """
    if not raw:
        return ""
    full, rem = divmod(len(raw), CHUNK_BYTES)
    buf = bytearray(full * CHUNK_CHARS + (TAIL_CHARS[rem] if rem else 0))
    off_b = 0
    off_c = 0
    m = memoryview(raw)
    for _ in range(full):
        _write_fixed(buf, off_c, int.from_bytes(m[off_b:off_b + CHUNK_BYTES], "big"),
                     CHUNK_CHARS)
        off_b += CHUNK_BYTES
        off_c += CHUNK_CHARS
    if rem:
        _write_fixed(buf, off_c, int.from_bytes(m[off_b:], "big"), TAIL_CHARS[rem])
    return buf.decode("ascii")


def encode_chunked(data: bytes) -> str:
    """bytes -> HEXA60 text, 8 bytes -> 11 chars, O(N). Wire format.

    Dispatches to the compiled _hexa60c module when available (see
    HAS_NATIVE), otherwise uses the pure-Python bytearray path. Both paths
    produce byte-identical output.
    """
    if not isinstance(data, (bytes, bytearray, memoryview)):
        raise TypeError(
            f"encode_chunked() expects a bytes-like object, got "
            f"{type(data).__name__}"
        )
    if isinstance(data, memoryview):
        # memoryview has no lstrip-free slicing guarantees across versions,
        # so normalise to bytes once; bytes/bytearray are used without copying.
        raw = data.tobytes()
    elif isinstance(data, bytes):
        raw = data
    else:
        raw = bytes(data)
    if not raw:
        return ""
    if _NATIVE is not None:
        return _NATIVE.encode_chunked(raw)
    return _encode_chunked_pure(raw)


def _unpack(num, n_bytes, n_chars):
    """Convert a chunk/tail value to `n_bytes` bytes.

    A chunk value can exceed the capacity of its byte width; that is an
    over-capacity chunk, which is reported as LengthError rather than the
    raw OverflowError from int.to_bytes().
    """
    try:
        return num.to_bytes(n_bytes, "big")
    except OverflowError:
        raise LengthError(
            n_chars,
            {f"<= {BASE ** n_chars} for {n_bytes} bytes"},
        ) from None


def _block_value(text: str, start: int, n: int) -> int:
    """Value of an n-digit block via the _DEC table (hot path)."""
    dec = _DEC
    acc = 0
    for i in range(start, start + n):
        o = ord(text[i])
        acc = acc * BASE + dec[o]  # caller guarantees validity via _prepare
    return acc


def _decode_chunked_pure(text: str, length=None, strict: bool = False) -> bytes:
    """Pure-Python chunked decoder (the reference implementation)."""
    clean = _prepare(text, strict)
    if not clean:
        return b""

    n_full, rem = divmod(len(clean), CHUNK_CHARS)
    if rem not in _REM_FROM_TAIL_CHARS:
        raise LengthError(rem, set(_REM_FROM_TAIL_CHARS))

    if strict:
        # Validated already by _prepare; decode via the fast table path.
        dec = _DEC
        out = bytearray(n_full * CHUNK_BYTES + (_REM_FROM_TAIL_CHARS[rem] if rem else 0))
        pos = 0
        o = 0
        for _ in range(n_full):
            num = 0
            for i in range(pos, pos + CHUNK_CHARS):
                num = num * BASE + dec[ord(clean[i])]
            out[o:o + CHUNK_BYTES] = num.to_bytes(CHUNK_BYTES, "big")
            pos += CHUNK_CHARS
            o += CHUNK_BYTES
        if rem:
            r = _REM_FROM_TAIL_CHARS[rem]
            num = 0
            for i in range(pos, pos + rem):
                num = num * BASE + dec[ord(clean[i])]
            out[o:o + r] = _unpack(num, r, rem)
    else:
        out = bytearray()
        for i in range(n_full):
            block = clean[i * CHUNK_CHARS:(i + 1) * CHUNK_CHARS]
            num = 0
            for ch in block:
                num = num * BASE + LOOKUP[ch]
            out.extend(_unpack(num, CHUNK_BYTES, CHUNK_CHARS))

        if rem:
            num = 0
            for ch in clean[n_full * CHUNK_CHARS:]:
                num = num * BASE + LOOKUP[ch]
            out.extend(_unpack(num, _REM_FROM_TAIL_CHARS[rem], rem))

    if length is not None and len(out) != length:
        raise LengthError(len(out), {length})
    return bytes(out)


def _raise_native_decode_error(exc: ValueError) -> None:
    """Translate a structured native ValueError into the real Python error.

    The codes mirror cpp/nanobind/bindings.cpp exactly; the arguments are
    rebuilt so the raised exception is indistinguishable from the pure path.
    """
    parts = str(exc).split("|")
    kind = parts[0]
    if kind == "invalid_char" and len(parts) == 3:
        raise InvalidCharacterError(chr(int(parts[2])), int(parts[1])) from None
    if kind == "invalid_layout" and len(parts) == 2:
        raise LengthError(int(parts[1]), set(_REM_FROM_TAIL_CHARS)) from None
    if kind == "overflow" and len(parts) == 3:
        n_chars, n_bytes = int(parts[1]), int(parts[2])
        raise LengthError(
            n_chars, {f"<= {BASE ** n_chars} for {n_bytes} bytes"}
        ) from None
    raise Base60Error(f"native decode_chunked failed: {exc}") from None


def decode_chunked(text: str, length=None, strict: bool = False) -> bytes:
    """HEXA60 chunked text -> bytes. Pass `length` to enforce an exact size.

    Chunks whose value exceeds the capacity of their byte width, as well as
    lengths that do not match a valid chunk layout, raise LengthError.

    Dispatches to the compiled _hexa60c module when available (see
    HAS_NATIVE), otherwise uses the pure-Python reference decoder. Both
    paths raise identical exception classes with identical arguments.
    """
    if not isinstance(text, str):
        raise TypeError(f"Expected str, got {type(text).__name__}")
    if _NATIVE is None:
        return _decode_chunked_pure(text, length, strict)
    try:
        out = _NATIVE.decode_chunked(text, strict)
    except ValueError as exc:
        _raise_native_decode_error(exc)
    # Empty result: same as the pure path, which returns b"" before the
    # length check when the cleaned input is empty.
    if out and length is not None and len(out) != length:
        raise LengthError(len(out), {length})
    return out


def decode_chunked_auto(text: str, strict: bool = False) -> bytes:
    """Chunked decode recovering the tail length from len(text) % CHUNK_CHARS."""
    return decode_chunked(text, strict=strict)


def encode(data: bytes) -> str:
    """Bulk bytes -> HEXA60 text as one big integer, O(N^2).

    Interprets the whole input as a single base-256 integer and converts it to
    base 60. Leading zero bytes are preserved by mapping each one to '0',
    following the base58/base62 convention.
    Empty input returns "". All-zero input returns a run of '0' characters.
    """
    if not isinstance(data, (bytes, bytearray, memoryview)):
        raise TypeError(
            f"encode() expects a bytes-like object, got {type(data).__name__}"
        )
    if not isinstance(data, bytes):
        # memoryview has no lstrip; normalise before the byte-level work below.
        data = bytes(data)
    if not data:
        return ""
    zeros = len(data) - len(data.lstrip(b"\x00"))
    num = int.from_bytes(data, "big")
    out = []
    while num > 0:
        num, idx = divmod(num, BASE)
        out.append(ALPHABET[idx])
    return "0" * zeros + "".join(reversed(out))


def _fit(data: bytes, length: int) -> bytes:
    """Pad with leading zeros or truncate to exactly `length` bytes."""
    if length < 0:
        raise LengthError(length, ">= 0")
    if length == 0:
        return b""
    if len(data) > length:
        return data[-length:]
    return b"\x00" * (length - len(data)) + data


def decode(text: str, *, length=None, strict: bool = True) -> bytes:
    """Bulk HEXA60 text -> bytes. Does NOT accept encode_chunked output.

    strict=True (default) raises InvalidCharacterError on any character
    outside ALPHABET. With strict=False such characters are silently skipped.

    If `length` is given, the result is left-padded with zero bytes or
    truncated to exactly that many bytes. A negative length raises LengthError.
    """
    if length is not None and length < 0:
        raise LengthError(length, ">= 0")
    clean = _prepare(text, strict)
    if not clean:
        result = b""
    else:
        dec = _DEC
        num = 0
        for i, ch in enumerate(clean):
            d = dec[ord(ch)] if ord(ch) < 256 else -1
            if d < 0:  # only reachable in non-strict mode; _prepare strips there
                continue
            num = num * BASE + d
        leading = len(clean) - len(clean.lstrip(ALPHABET[0]))
        result = b"\x00" * leading + num.to_bytes((num.bit_length() + 7) // 8, "big")
    return result if length is None else _fit(result, length)


# Legacy API.
# bytes_to_base60 is a direct alias of the bulk encode() per the specification.
# NOTE: the historical bytes_to_base60 was chunked (3 -> 5 chars), so callers
# relying on the old wire format must migrate; data encoded before this change
# cannot be decoded with base60_to_bytes.
bytes_to_base60 = encode
base60_to_bytes = decode


def base60_to_bytes_lenient(s, length=None):
    """Benevolent legacy decoder: never raises on overflow, truncates instead.

    Invalid characters are skipped and, when the decoded value exceeds
    `length`, the trailing `length` bytes are returned. This is lossy and
    unsafe for integrity-critical data - prefer hexa60.decode().
    """
    clean = "".join(c for c in s if c in LOOKUP) if isinstance(s, str) else ""
    if not clean:
        return b"" if length is None else b"\x00" * max(length, 0)
    dec = _DEC
    num = 0
    for ch in clean:
        num = num * BASE + dec[ord(ch)]
    leading = len(clean) - len(clean.lstrip(ALPHABET[0]))
    raw = b"\x00" * leading + num.to_bytes((num.bit_length() + 7) // 8, "big")
    if length is None:
        return raw
    if length < 0:
        return raw
    return _fit(raw, length)


