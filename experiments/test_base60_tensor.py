# ============================================================================
# HEXA-60 CORE™ — High-Throughput Base60 Encoding Engine
# Copyright (c) 2026 Ladislav Müller (IČO: 40189589). All rights reserved.
#
# PROPRIETARY AND CONFIDENTIAL SOFTWARE.
# Unauthorized copying, distribution, or modification of this file, via any
# medium, is strictly prohibited under applicable copyright laws and B2B EULA.
# ============================================================================

"""Testy pre base60_tensor -- batch aritmetika v base-60 cez PyTorch.

Kazda operacia sa overuje PROTI Base60Int, nie proti sebe. Toto je
referenčna implementacia pre test, nie zdroj pravdy.
"""
import random
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from base60_int import ALPHABET, Base60Int, add_b60 as BA_add, mul_b60 as BI_mul
from base60_tensor import Base60Tensor as T, Base60ValueError

W = 8  # max_digits pouzivane vo vsetkych testoch
RNG = random.Random(4242)


def rand_b60(max_digits=5):
    n = RNG.randrange(1, max_digits)
    return "".join(ALPHABET[RNG.randrange(60)] for _ in range(n))


def b60(v):
    return Base60Int(v).to_b60()


def norm(s):
    """Tenzorove cisla su MSB first a plnou sirkou, takze veduce nuly
    treba striasnut na ZACIATKU. rstrip() by nestacil -- ten ma vymazat
    koncove nuly, a tie su vzadu."""
    return s.lstrip("0") or "0"


# ================================================================ roundtrip
@pytest.mark.parametrize("s", ["1", "12", "123", "zzz", "0", "_", "-", "9Rh"])
def test_encode_decode_roundtrip(s):
    got = T.decode(T.encode([s], W))[0]
    assert norm(got) == norm(s)


def test_decode_returns_full_width():
    """decode normalizuje vysledok -- veduce nuly su odstranene."""
    out = T.decode(T.encode(["1"], W))
    assert out == ["1"]
    # ale dlzka cisla je v tenzore vzdy W, co vidno na encode
    assert T.encode(["1"], W).shape[1] == W


def test_decode_strips_leading_zeros():
    """Regresia: _rows_to_strings hladalo PRVU NULU namiesto prvej
    nenulovej cifry, takze vracalo '0' alebo nespratny zvysok."""
    assert T.decode(T.encode(["00000001"], W)) == ["1"]
    assert T.decode(T.encode(["0000000z"], W)) == ["z"]
    assert T.decode(T.encode(["0Eq45SQz"], W)) == ["Eq45SQz"]


def test_decode_zero_is_not_empty():
    """Nula musi dekodovat na "0", nie na prazdny retazec."""
    assert T.decode(T.encode(["0"], W)) == ["0"]


# ================================================================ add
def test_add_matches_base60int():
    for _ in range(400):
        a, b = rand_b60(), rand_b60()
        x, y = Base60Int(a), Base60Int(b)
        if len((x + y).to_b60()) <= W:
            assert [norm(s) for s in T.add([a], [b], W)] == [(x + y).to_b60()]


def test_add_batch_matches_base60int():
    a = [rand_b60() for _ in range(50)]
    b = [rand_b60() for _ in range(50)]
    pairs = [
        (x, y) for x, y in zip(a, b)
        if len((Base60Int(x) + Base60Int(y)).to_b60()) <= W
    ]
    want = [(Base60Int(x) + Base60Int(y)).to_b60() for x, y in pairs]
    got = T.add([p[0] for p in pairs], [p[1] for p in pairs], W)
    assert [norm(s) for s in got] == want


def test_add_overflow_raises():
    # zzzzzzzz (8 cislic) + zzzzzzzz (8 cislic) >> 8 cislic
    z8 = "zzzzzzzz"
    assert len(BA_add(z8, z8)) > W
    with pytest.raises(Base60ValueError):
        T.add([z8], [z8], W)


# ================================================================ subtract
def test_subtract_matches_base60int():
    for _ in range(400):
        a, b = rand_b60(), rand_b60()
        x, y = Base60Int(a), Base60Int(b)
        if x >= y:
            got = T.subtract([a], [b], W)
            assert [norm(s) for s in got] == [(x - y).to_b60()]


def test_subtract_negative_raises():
    with pytest.raises(Base60ValueError):
        T.subtract(["1"], ["10"], W)


def test_subtract_to_zero():
    assert [norm(s) for s in T.subtract(["zzz"], ["zzz"], W)] == ["0"]


# ================================================================ multiply
def test_multiply_trivial():
    """Regresia: 9Rh * 4 = dik. Puvodny kod tu vyhodil pretecenie,
    lebo premenil hi/lo naopak."""
    assert norm(T.multiply(["9Rh"], ["4"], W)[0]) == "dik"


def test_multiply_by_one():
    for s in ["1", "5", "12", "9Rh", "zzz"]:
        assert norm(T.multiply([s], ["1"], W)[0]) == norm(s)


def test_multiply_by_zero():
    for s in ["1", "5", "12", "9Rh", "zzz"]:
        assert norm(T.multiply([s], ["0"], W)[0]) == "0"


def test_multiply_small_exhaustive():
    """Vsetky dvojice cifer do 12x12 -- plne pokrytie nizkych hodnot."""
    for a in range(13):
        for b in range(13):
            got = norm(T.multiply([b60(a)], [b60(b)], W)[0])
            assert got == b60(a * b), f"{a} * {b}"


def test_multiply_matches_base60int():
    for _ in range(500):
        a, b = rand_b60(), rand_b60()
        x, y = Base60Int(a), Base60Int(b)
        want = (x * y).to_b60()
        if len(want) <= W:
            got = T.multiply([a], [b], W)[0]
            assert norm(got) == want, f"{a} * {b}: {got!r} != {want!r}"


def test_multiply_overflow_raises():
    # zzz*zzz = y02GC9 (len 6) -- zmesti sa. na pretecenie potrebujeme
    # nieco s 8 cislami: zzzz(8 cislic) * zzzz(8 cislic) >> 8 cislic.
    z8 = "zzzzzzzz"
    assert len((Base60Int(z8) * Base60Int(z8)).to_b60()) > W
    with pytest.raises(Base60ValueError):
        T.multiply([z8], [z8], W)


def test_multiply_max_fits():
    """60^W-1 * 1 = 60^W-1, este sa zmesti."""
    max_val = b60(60 ** W - 1)
    assert norm(T.multiply([max_val], ["1"], W)[0]) == norm(max_val)


# ================================================================ compare
def test_compare_matches_base60int():
    for _ in range(300):
        a, b = rand_b60(), rand_b60()
        x, y = Base60Int(a), Base60Int(b)
        want = 0 if x == y else (1 if x > y else -1)
        assert T.compare([a], [b], W) == [want]


def test_compare_batch():
    # 10 v base60 = 60, takze 10 > 2 a 2 < 10
    a = ["1", "10", "zzz", "2"]
    b = ["1", "2", "zzz", "10"]
    assert T.compare(a, b, W) == [0, 1, 0, -1]


# ================================================================ validacia
def test_encode_rejects_too_long():
    with pytest.raises(Base60ValueError):
        T.encode(["123456789"], 4)


def test_encode_rejects_empty_string():
    with pytest.raises(Base60ValueError):
        T.encode([""], 8)


def test_encode_rejects_invalid_char():
    with pytest.raises(Base60ValueError):
        T.encode(["ab!c"], 8)


def test_encode_rejects_non_ascii():
    with pytest.raises(Base60ValueError):
        T.encode(["\u00e9\u00e9"], 8)


def test_encode_rejects_non_str():
    with pytest.raises(Base60ValueError):
        T.encode([123], 8)


def test_rejects_mismatched_batch():
    with pytest.raises(Base60ValueError):
        T.add(["1", "2"], ["1"], W)


def test_decode_rejects_digit_60():
    with pytest.raises(Base60ValueError):
        T.decode(__import__("torch").tensor([[60] * W]))


def test_encode_rejects_digit_above_base():
    import torch
    with pytest.raises(Base60ValueError):
        T.decode(torch.tensor([[-1] + [0] * (W - 1)]))
