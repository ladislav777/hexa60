import math

import pytest

import hexa60 as h


def _sample(n):
    return bytes((i * 37 + 11) & 0xFF for i in range(n))


# --- alphabet / constants ---------------------------------------------------

def test_alphabet_has_60_unique_chars():
    assert len(h.ALPHABET) == 60
    assert len(set(h.ALPHABET)) == 60


def test_alphabet_is_identifier_safe():
    for ch in "+/=":
        assert ch not in h.ALPHABET
    assert all(ord(ch) < 128 for ch in h.ALPHABET)


def test_visually_ambiguous_chars_excluded():
    for ch in "IOlo":
        assert ch not in h.ALPHABET


def test_lookup_is_inverse_of_alphabet():
    assert all(h.LOOKUP[ch] == i for i, ch in enumerate(h.ALPHABET))


# --- math from the spec -----------------------------------------------------

def test_chunk_constants():
    assert (h.CHUNK_BYTES, h.CHUNK_CHARS) == (8, 11)
    assert h.CHUNK_CHARS / h.CHUNK_BYTES == pytest.approx(1.375)


def test_chunk_entropy_covers_64_bits():
    assert h.BASE ** h.CHUNK_CHARS > 2 ** 64
    assert 11 * math.log2(h.BASE) == pytest.approx(64.976, abs=0.001)


def test_tail_chars_match_formula():
    for r in range(h.CHUNK_BYTES):
        expected = math.ceil(h.CHUNK_BYTES * r / math.log2(h.BASE))
        assert h.TAIL_CHARS[r] == expected


def test_tail_chars_table():
    assert [h.TAIL_CHARS[r] for r in range(1, 8)] == [2, 3, 5, 6, 7, 9, 10]


def test_tail_chars_have_unique_mod_11_residues():
    residues = [c % h.CHUNK_CHARS for c in h.TAIL_CHARS.values()]
    assert len(set(residues)) == len(residues)
    assert sorted(residues) == [0, 2, 3, 5, 6, 7, 9, 10]


@pytest.mark.parametrize("r", range(1, 8))
def test_tail_chars_have_enough_entropy(r):
    """60**TAIL_CHARS[r] must cover the full byte range for r bytes."""
    assert h.BASE ** h.TAIL_CHARS[r] >= 256 ** r
# --- chunked round-trip -----------------------------------------------------

@pytest.mark.parametrize("n", range(0, 201))
def test_chunked_roundtrip(n):
    data = _sample(n)
    assert h.decode_chunked_auto(h.encode_chunked(data)) == data


@pytest.mark.parametrize("n", range(0, 50))
def test_chunked_roundtrip_all_byte_values(n):
    data = bytes(range(256))[:n]
    assert h.decode_chunked_auto(h.encode_chunked(data)) == data


def test_chunked_empty():
    assert h.encode_chunked(b"") == ""
    assert h.decode_chunked_auto("") == b""


def test_chunked_full_block_is_11_chars():
    assert len(h.encode_chunked(b"\x00" * 8)) == h.CHUNK_CHARS
    assert len(h.encode_chunked(b"\x00" * 16)) == 2 * h.CHUNK_CHARS


@pytest.mark.parametrize("r", range(1, 8))
def test_chunked_tail_length(r):
    data = b"\x00" * h.CHUNK_BYTES + _sample(r)
    enc = h.encode_chunked(data)
    assert len(enc) == h.CHUNK_CHARS + h.TAIL_CHARS[r]


def test_chunked_preserves_leading_zero_bytes():
    data = b"\x00\x00\x00\x01\x02"
    assert h.decode_chunked_auto(h.encode_chunked(data)) == data


def test_chunked_is_deterministic():
    assert h.encode_chunked(b"abc") == h.encode_chunked(b"abc")


def test_decode_chunked_enforces_length():
    data = _sample(20)
    enc = h.encode_chunked(data)
    assert h.decode_chunked(enc, length=20) == data
    with pytest.raises(h.LengthError):
        h.decode_chunked(enc, length=99)


# --- length validation (the silent-corruption fix) --------------------------

def test_invalid_residues_are_exactly_1_4_8():
    valid = {c % h.CHUNK_CHARS for c in h.TAIL_CHARS.values()}
    assert [r for r in range(h.CHUNK_CHARS) if r not in valid] == [1, 4, 8]


@pytest.mark.parametrize("size", [1, 4, 8, 12, 15, 19, 23])
def test_invalid_tail_residues_raise_length_error(size):
    """Residues 1, 4 and 8 (mod 11) are not a valid tail length."""
    with pytest.raises(h.LengthError):
        h.decode_chunked_auto("0" * size)


@pytest.mark.parametrize("r", range(1, 8))
def test_all_valid_residues_decode(r):
    data = _sample(r)
    enc = h.encode_chunked(data)
    assert len(enc) == h.TAIL_CHARS[r]
    assert h.decode_chunked_auto(enc) == data


# --- over-capacity chunks must not leak OverflowError ------------------------

def test_full_chunk_capacity_ratio():
    """60**11 exceeds 2**64, so not every 11-char value fits in 8 bytes.

    This is intentional: encode_chunked can only ever emit values < 2**64,
    and the decoder rejects the remainder instead of silently truncating.
    """
    assert h.BASE ** h.CHUNK_CHARS > 2 ** 64
    ratio = h.BASE ** h.CHUNK_CHARS / 2 ** 64
    assert 1.0 < ratio < 2.0


def test_largest_encodable_chunk_roundtrips():
    """The largest chunk encode_chunked can produce is 2**64 - 1."""
    data = b"\xff" * 8
    enc = h.encode_chunked(data)
    assert len(enc) == h.CHUNK_CHARS
    assert h.decode_chunked_auto(enc) == data


def test_max_alphabet_chunk_is_over_capacity():
    """'z' * 11 == 60**11 - 1 > 2**64 - 1, so it cannot fit 8 bytes."""
    assert int.from_bytes(h.decode_chunked_auto(h.encode_chunked(b"\xff" * 8)), "big") \
        == 2 ** 64 - 1
    with pytest.raises(h.LengthError):
        h.decode_chunked_auto(h.ALPHABET[-1] * 11)


@pytest.mark.parametrize("extra", range(1, 12))
def test_full_chunk_over_capacity_raises_length_error(extra):
    """A full chunk wider than 11 chars is a layout error, not a decode."""
    text = h.ALPHABET[-1] * (11 + extra)
    with pytest.raises(h.LengthError):
        h.decode_chunked_auto(text)


@pytest.mark.parametrize("rem", [2, 3, 5, 6, 7, 9, 10])
def test_tail_capacity_boundary(rem):
    """Each tail width must decode values up to its byte capacity."""
    r_bytes = {v: k for k, v in h.TAIL_CHARS.items()}[rem]
    limit = min(60 ** rem, 2 ** (8 * r_bytes))

    # The largest in-capacity tail value decodes to exactly r_bytes bytes.
    top = h._encode_fixed(limit - 1, rem)
    assert len(h.decode_chunked_auto(top)) == r_bytes

    # One step above the byte capacity (if reachable) must be rejected.
    if limit < 60 ** rem:
        over = h._encode_fixed(limit, rem)
        with pytest.raises(h.LengthError):
            h.decode_chunked_auto(over)


def test_tail_over_capacity_raises_length_error():
    """An over-capacity full chunk followed by a valid tail -> LengthError."""
    text = h.ALPHABET[-1] * 11 + h.ALPHABET[-1] * 10
    with pytest.raises(h.LengthError):
        h.decode_chunked_auto(text)


def test_over_capacity_never_raises_overflow_error():
    """Regression: raw OverflowError must not escape any public decoder."""
    cases = [
        h.ALPHABET[-1] * 11,
        h.ALPHABET[-1] * 12,
        h.ALPHABET[-1] * 23,
        h.ALPHABET[-1] * 34,
        h.ALPHABET[-1] * 11 + h.ALPHABET[-1] * 10,
        h.ALPHABET[-1] * 22 + h.ALPHABET[-1] * 3,
    ]
    for text in cases:
        with pytest.raises(h.LengthError):
            h.decode_chunked_auto(text)


def test_over_capacity_is_not_silently_truncated():
    """A rejected chunk must raise, never return a shortened buffer."""
    text = h.ALPHABET[-1] * 11
    try:
        h.decode_chunked_auto(text)
    except h.LengthError:
        pass
    else:  # pragma: no cover
        pytest.fail("over-capacity chunk decoded without LengthError")


# --- strict mode / characters ----------------------------------------------

def test_strict_rejects_bad_character_with_position():
    with pytest.raises(h.InvalidCharacterError) as exc:
        h.decode_chunked_auto("0P!5", strict=True)
    assert exc.value.char == "!"
    assert exc.value.position == 2


def test_strict_rejects_excluded_letter():
    with pytest.raises(h.InvalidCharacterError):
        h.decode_chunked_auto("abcO", strict=True)


def test_non_strict_strips_bad_characters():
    data = b"Hello"
    enc = h.encode_chunked(data)
    dirty = enc[:2] + "!" + enc[2:]
    assert h.decode_chunked_auto(dirty) == data


def test_error_hierarchy():
    assert issubclass(h.InvalidCharacterError, h.Base60Error)
    assert issubclass(h.LengthError, h.Base60Error)
    with pytest.raises(h.Base60Error):
        h.decode_chunked_auto("0" * 12)


# --- is_valid ---------------------------------------------------------------

def test_is_valid_accepts_alphabet_only():
    assert h.is_valid("abc-DEF_012")
    assert h.is_valid("")


@pytest.mark.parametrize("bad", ["abc+", "abc/", "ab=c", "I", "O", "l", "o", "a b"])
def test_is_valid_rejects(bad):
    assert not h.is_valid(bad)


def test_is_valid_requires_str():
    with pytest.raises(TypeError):
        h.is_valid(b"abc")
    with pytest.raises(TypeError):
        h.is_valid(123)


def test_decode_rejects_bytes_input():
    with pytest.raises(TypeError):
        h.decode_chunked_auto(b"abc")


# --- bulk API ---------------------------------------------------------------

@pytest.mark.parametrize("n", [1, 2, 5, 10, 30, 300])
def test_bulk_roundtrip(n):
    data = _sample(n)
    assert h.decode(h.encode(data)) == data


def test_bulk_preserves_leading_zeros():
    data = b"\x00\x00\x01\x02"
    assert h.decode(h.encode(data)) == data
    assert h.encode(b"\x00\x00") == "00"


def test_bulk_empty():
    assert h.encode(b"") == ""
    assert h.decode("") == b""


def test_bulk_zero():
    assert h.encode(b"\x00") == "0"
    assert h.decode("0") == b"\x00"


# --- legacy aliases ---------------------------------------------------------

def test_legacy_aliases_bound_to_bulk():
    assert h.bytes_to_base60 is h.encode
    assert h.base60_to_bytes is h.decode


def test_legacy_alias_roundtrip():
    data = b"Vortex HEXA60"
    assert h.base60_to_bytes(h.bytes_to_base60(data)) == data


# --- decode(length=...) and strict default (spec section 5/6) ---------------

def test_decode_is_strict_by_default():
    with pytest.raises(h.InvalidCharacterError):
        h.decode("0P!5")
    assert h.decode("0P!5", strict=False) == h.decode("0P5")


def test_decode_length_is_keyword_only():
    with pytest.raises(TypeError):
        h.decode("0P5", 3)


def test_decode_length_pads_with_leading_zeros():
    data = b"\x01\x02"
    assert h.decode(h.encode(data), length=5) == b"\x00\x00\x00\x01\x02"


def test_decode_length_truncates_to_trailing_bytes():
    data = b"\xaa\xbb\xcc\xdd"
    assert h.decode(h.encode(data), length=2) == b"\xcc\xdd"


def test_decode_length_zero_returns_empty():
    assert h.decode(h.encode(b"\x01\x02"), length=0) == b""


def test_decode_length_exact_is_identity():
    data = _sample(6)
    assert h.decode(h.encode(data), length=6) == data


def test_decode_negative_length_raises():
    with pytest.raises(h.LengthError):
        h.decode("0P5", length=-1)


def test_lenient_decoder_skips_bad_chars():
    enc = h.encode(b"Hello")
    assert h.base60_to_bytes_lenient(enc[:2] + "!" + enc[2:]) == b"Hello"


def test_lenient_decoder_truncates_instead_of_raising():
    data = b"\xaa\xbb\xcc\xdd"
    assert h.base60_to_bytes_lenient(h.encode(data), length=2) == b"\xcc\xdd"


def test_lenient_decoder_pads():
    assert h.base60_to_bytes_lenient(h.encode(b"\x01"), length=3) == b"\x00\x00\x01"


def test_chunked_output_is_not_bulk_decodable_shape():
    """Chunked and bulk formats must stay separate."""
    data = b"\x00" * 16
    chunked = h.encode_chunked(data)
    bulk = h.encode(data)
    assert len(chunked) == 22
    assert len(bulk) == 16

