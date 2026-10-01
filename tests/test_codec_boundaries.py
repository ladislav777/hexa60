"""
Boundary and validation tests for the Hexa60 codec.

Three corrections relative to the earlier draft of this file, all found by
running that draft against the real implementation:

1. The alphabet. HEXA60 excludes I, O, l and o for visual ambiguity, so the
   real alphabet has 60 characters, not 64. The draft's alphabet also contained
   those four letters, which shifted every digit index from 18 onwards:
   encode_chunked(b"\\xff\\xff") is "JCF", not "ICF".

2. The wrong functions. Chunk boundaries, tail layouts and capacity limits are
   properties of the CHUNKED wire format, i.e. encode_chunked /
   decode_chunked. The bulk encode / decode have no chunking at all: every
   well-formed string decodes and no length is invalid.

3. The wrong exception types. InvalidCharacterError and LengthError both
   derive from Base60Error, which derives from Exception -- not from
   ValueError -- so pytest.raises(ValueError) would not have caught them.

Note also that decode_chunked defaults to strict=False, which silently drops
characters outside the alphabet. Character validation tests therefore pass
strict=True explicitly; without it the expected exception is never raised.

The reference encoder below is independent of the production code: it
re-derives digits from the positional definition value = sum(d_i * 60**i)
using a literal copy of the alphabet, so that a change to hexa60.ALPHABET is
caught here instead of being silently mirrored.
"""

import pytest

from hexa60 import (
    ALPHABET,
    BASE,
    CHUNK_BYTES,
    CHUNK_CHARS,
    TAIL_CHARS,
    InvalidCharacterError,
    LengthError,
    decode_chunked,
    encode_chunked,
)

# Independent literal copy, deliberately duplicated. Any divergence from
# hexa60.ALPHABET is a finding, not something to reconcile silently.
REFERENCE_ALPHABET = "0123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnpqrstuvwxyz_-"


def reference_base60(value: int, width: int) -> str:
    """Encode `value` as exactly `width` Base-60 digits, without production code."""
    assert 0 <= value < (BASE**width)
    return "".join(
        REFERENCE_ALPHABET[(value // (BASE**position)) % BASE]
        for position in range(width - 1, -1, -1)
    )


# ---------------------------------------------------------------------------
# Alphabet and layout invariants
# ---------------------------------------------------------------------------


def test_alphabet_has_sixty_unique_characters():
    assert len(ALPHABET) == 60
    assert len(set(ALPHABET)) == 60
    assert ALPHABET == REFERENCE_ALPHABET


@pytest.mark.parametrize("ch", "IOlo")
def test_alphabet_excludes_visually_ambiguous_characters(ch):
    assert ch not in ALPHABET


@pytest.mark.parametrize("ch", "+/=")
def test_alphabet_excludes_url_unsafe_characters(ch):
    assert ch not in ALPHABET


def test_tail_chars_cover_every_short_length():
    assert sorted(TAIL_CHARS) == list(range(CHUNK_BYTES))
    assert TAIL_CHARS[0] == 0


def test_tail_chars_match_the_capacity_formula():
    """C = ceil(CHUNK_BYTES * r / log2(60)) is the smallest width that fits
    r bytes; one less must not be enough."""
    for r, chars in TAIL_CHARS.items():
        capacity = BASE**chars
        assert capacity >= 2 ** (8 * r)
        if r:
            assert BASE ** (chars - 1) < 2 ** (8 * r)


def test_chunk_layout_is_eight_bytes_to_eleven_chars():
    # 8 bytes = 2**64 and 60**11 > 2**64 >= 60**10, so 11 is the minimum.
    assert CHUNK_BYTES == 8
    assert CHUNK_CHARS == 11
    assert BASE**CHUNK_CHARS > 2 ** (8 * CHUNK_BYTES)
    assert BASE ** (CHUNK_CHARS - 1) < 2 ** (8 * CHUNK_BYTES)


def test_tail_residues_are_unique():
    """decode_chunked recovers the tail from len(text) % 11, so two remainders
    sharing a char count would make the tail ambiguous."""
    residues = [chars % CHUNK_CHARS for chars in TAIL_CHARS.values()]
    assert len(set(residues)) == len(residues)



# ---------------------------------------------------------------------------
# Tail boundaries: maximum value, first overflow, and the same tail after a
# complete block
# ---------------------------------------------------------------------------

TAIL_WIDTHS = sorted(TAIL_CHARS.items())  # [(r, chars), ...] for r = 0..7

# r = 0 has no tail: an empty chunk has zero capacity, so there is no
# "first value above capacity" to test.
OVERFLOW_TAIL_WIDTHS = [(r, c) for r, c in TAIL_WIDTHS if r >= 1]


@pytest.mark.parametrize("byte_count,char_count", OVERFLOW_TAIL_WIDTHS)
def test_maximum_value_for_tail_width(byte_count, char_count):
    """0xFF * n encodes to exactly TAIL_CHARS[n] digits and round-trips."""
    data = b"\xff" * byte_count
    text = encode_chunked(data)
    assert len(text) == char_count
    assert text == reference_base60(int.from_bytes(data, "big"), char_count)
    assert decode_chunked(text) == data


@pytest.mark.parametrize("byte_count,_char_count", OVERFLOW_TAIL_WIDTHS)
def test_first_value_above_capacity_is_rejected(byte_count, _char_count):
    """2**(8n) needs one digit more than 0xFF * n and must not decode."""
    overflow = reference_base60(1 << (8 * byte_count), TAIL_CHARS[byte_count])
    with pytest.raises(LengthError):
        decode_chunked(overflow)


@pytest.mark.parametrize("byte_count,_char_count", OVERFLOW_TAIL_WIDTHS)
def test_tail_after_complete_block(byte_count, _char_count):
    """A short tail following a full 11-char block behaves the same."""
    data = b"\x00" * CHUNK_BYTES + b"\xff" * byte_count
    text = encode_chunked(data)
    assert text[:CHUNK_CHARS] == REFERENCE_ALPHABET[0] * CHUNK_CHARS
    assert len(text) == CHUNK_CHARS + TAIL_CHARS[byte_count]
    assert decode_chunked(text) == data


def test_full_block_boundaries():
    """The 8-byte block is exact at maximum and rejects one past it."""
    data = b"\xff" * CHUNK_BYTES
    text = encode_chunked(data)
    assert len(text) == CHUNK_CHARS
    assert text == reference_base60(2**64 - 1, CHUNK_CHARS)
    assert decode_chunked(text) == data
    # 2**64 does not fit in 11 digits of Base-60.
    with pytest.raises(LengthError):
        decode_chunked(reference_base60(2**64, CHUNK_CHARS))


# ---------------------------------------------------------------------------
# Explicit vectors
# ---------------------------------------------------------------------------


def test_single_byte_maximum():
    # 255 = 4*60 + 15
    assert reference_base60(255, 2) == "4F"
    assert encode_chunked(b"\xff") == "4F"
    assert decode_chunked("4F") == b"\xff"


def test_two_byte_maximum():
    # 65535 = 18*60**2 + 12*60 + 15. Digit 18 is carried by 'J' because 'I' is
    # excluded from the alphabet; the arithmetic is unaffected.
    assert [65535 // (BASE**p) % BASE for p in (2, 1, 0)] == [18, 12, 15]
    assert reference_base60(65535, 3) == "JCF"
    assert encode_chunked(b"\xff\xff") == "JCF"
    assert decode_chunked("JCF") == b"\xff\xff"


def test_zero_bytes_are_preserved():
    # A tail of r zero bytes is r bytes wide, so it occupies TAIL_CHARS[r]
    # digits -- padding, not shortening. 3 bytes -> TAIL_CHARS[3] = 5.
    for r in range(1, CHUNK_BYTES):
        text = encode_chunked(b"\x00" * r)
        assert len(text) == TAIL_CHARS[r]
        assert text == REFERENCE_ALPHABET[0] * TAIL_CHARS[r]
        assert decode_chunked(text) == b"\x00" * r


# ---------------------------------------------------------------------------
# Character validation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("ch", "IOlo")
def test_ambiguous_characters_are_rejected(ch):
    with pytest.raises(InvalidCharacterError):
        decode_chunked("4" + ch, strict=True)


@pytest.mark.parametrize("ch", "+/=")
def test_url_unsafe_characters_are_rejected(ch):
    with pytest.raises(InvalidCharacterError):
        decode_chunked("4" + ch, strict=True)


def test_error_reports_character_and_position():
    with pytest.raises(InvalidCharacterError) as excinfo:
        decode_chunked("JCF+", strict=True)
    assert excinfo.value.char == "+"
    assert excinfo.value.position == 3


def test_non_strict_decode_drops_invalid_characters():
    """Documents the lenient default.

    strict=False strips characters outside the alphabet before chunking, so the
    *cleaned* string is what must form a valid layout. Dropping '+' from "4F+"
    leaves "4F", a well-formed 2-digit tail; dropping it from "4+" would leave
    an orphan of length 1, which raises LengthError instead. That is a property
    of the layout check, not of strictness.
    """
    assert decode_chunked("4F+") == b"\xff"
    with pytest.raises(InvalidCharacterError):
        decode_chunked("4F+", strict=True)


# ---------------------------------------------------------------------------
# Invalid chunk layouts
# ---------------------------------------------------------------------------

# Remainders that are not TAIL_CHARS values: 1, 4 and 8.
@pytest.mark.parametrize("text", ["0", "0000", "00000000"])
def test_orphan_lengths_are_rejected(text):
    assert len(text) % CHUNK_CHARS not in TAIL_CHARS.values()
    with pytest.raises(LengthError):
        decode_chunked(text)


def test_empty_text_decodes_to_empty_bytes():
    assert decode_chunked("") == b""
    assert encode_chunked(b"") == ""


def test_declared_length_mismatch_is_rejected():
    with pytest.raises(LengthError):
        decode_chunked("4F", length=2)


# ---------------------------------------------------------------------------
# Type checking
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("bad", [None, 0, 123, b"4F", ["4F"], {"a": "4F"}])
def test_decode_rejects_non_str(bad):
    with pytest.raises(TypeError):
        decode_chunked(bad)


@pytest.mark.parametrize("bad", [["4F"], 4.5])
def test_encode_rejects_non_bytes(bad):
    with pytest.raises((TypeError, AttributeError)):
        encode_chunked(bad)


@pytest.mark.xfail(
    reason="encode_chunked(b'') and encode_chunked(None) both return '' "
           "because 'if not data' is true for None as well as b''. bytes input "
           "is the intended type and works correctly; only the non-bytes "
           "falsy values slip through unvalidated.",
    strict=True,
)
def test_encode_chunked_does_not_silently_accept_none():
    """Known gap: None is accepted where bytes were required.

    Kept as xfail(strict=True) so it flips to a failure the moment the guard
    is tightened, rather than being quietly forgotten.
    """
    with pytest.raises(TypeError):
        encode_chunked(None)

