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

import math

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
]

# 60 unique characters. Excluded for visual ambiguity: I, O (upper), l, o (lower).
ALPHABET = "0123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnpqrstuvwxyz_-"
BASE = 60
LOOKUP = {ch: i for i, ch in enumerate(ALPHABET)}

CHUNK_BYTES = 8
CHUNK_CHARS = 11

# TAIL_CHARS[r] = chars needed to encode r trailing bytes.
# Derived formula: C = ceil(CHUNK_BYTES * r / log2(BASE))
TAIL_CHARS = {
    r: math.ceil(CHUNK_BYTES * r / math.log2(BASE)) for r in range(CHUNK_BYTES)
}
_REM_FROM_TAIL_CHARS = {c: r for r, c in TAIL_CHARS.items()}


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
    return all(ch in LOOKUP for ch in text)


def _prepare(text, strict):
    """Validate type, optionally raise on bad chars, else strip them."""
    if not isinstance(text, str):
        raise TypeError(f"Expected str, got {type(text).__name__}")
    if strict:
        for i, ch in enumerate(text):
            if ch not in LOOKUP:
                raise InvalidCharacterError(ch, i)
        return text
    return "".join(ch for ch in text if ch in LOOKUP)


def _encode_fixed(num, width):
    chars = []
    for _ in range(width):
        num, idx = divmod(num, BASE)
        chars.append(ALPHABET[idx])
    return "".join(reversed(chars))


def encode_chunked(data: bytes) -> str:
    """bytes -> HEXA60 text, 8 bytes -> 11 chars, O(N). Wire format."""
    if not isinstance(data, (bytes, bytearray, memoryview)):
        raise TypeError(
            f"encode_chunked() expects a bytes-like object, got "
            f"{type(data).__name__}"
        )
    if not isinstance(data, bytes):
        # int.from_bytes accepts bytearray but not reliably memoryview across
        # versions, and the slicing below assumes a bytes-like result.
        data = bytes(data)
    if not data:
        return ""
    end = len(data) - len(data) % CHUNK_BYTES
    out = [
        _encode_fixed(int.from_bytes(data[i:i + CHUNK_BYTES], "big"), CHUNK_CHARS)
        for i in range(0, end, CHUNK_BYTES)
    ]
    tail = data[end:]
    if tail:
        out.append(_encode_fixed(int.from_bytes(tail, "big"), TAIL_CHARS[len(tail)]))
    return "".join(out)


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


def decode_chunked(text: str, length=None, strict: bool = False) -> bytes:
    """HEXA60 chunked text -> bytes. Pass `length` to enforce an exact size.

    Chunks whose value exceeds the capacity of their byte width, as well as
    lengths that do not match a valid chunk layout, raise LengthError.
    """
    clean = _prepare(text, strict)
    if not clean:
        return b""

    n_full, rem = divmod(len(clean), CHUNK_CHARS)
    if rem not in _REM_FROM_TAIL_CHARS:
        raise LengthError(rem, set(_REM_FROM_TAIL_CHARS))

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
        num = 0
        for ch in clean:
            num = num * BASE + LOOKUP[ch]
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
    num = 0
    for ch in clean:
        num = num * BASE + LOOKUP[ch]
    leading = len(clean) - len(clean.lstrip(ALPHABET[0]))
    raw = b"\x00" * leading + num.to_bytes((num.bit_length() + 7) // 8, "big")
    if length is None:
        return raw
    if length < 0:
        return raw
    return _fit(raw, length)


