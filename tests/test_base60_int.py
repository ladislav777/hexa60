# ============================================================================
# HEXA-60 CORE™ — High-Throughput Base60 Encoding Engine
# Copyright (c) 2026 Ladislav Müller (IČO: 40189589). All rights reserved.
#
# PROPRIETARY AND CONFIDENTIAL SOFTWARE.
# Unauthorized copying, distribution, or modification of this file, via any
# medium, is strictly prohibited under applicable copyright laws and B2B EULA.
# ============================================================================

"""Testy pre base60_int -- Base60Int a low-level funkcie."""
import random
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import hexa60 as H
from base60_int import (
    Base60Int, add_b60, sub_b60, mul_b60, divmod_b60, to_digits, from_digits,
)

RNG = random.Random(20240110)


def rand_b60(max_digits=12):
    """Nahodny kanonicky Base60 retazec s `max_digits` ciframi."""
    n = RNG.randrange(0, max_digits)
    return from_digits([RNG.randrange(0, 60) for _ in range(n)])


# ==================================================================== abeceda
def test_uses_hexa60_alphabet():
    from base60_int import ALPHABET
    assert ALPHABET == H.ALPHABET


def test_digits_roundtrip():
    """Cifry musi prejst roundtrip, ale high-order nuly sa normalizuju pryc."""
    for _ in range(500):
        d = [RNG.randrange(0, 60) for _ in range(RNG.randrange(1, 10))]
        # canonicalizujeme vystup tak, ako to robi from_digits
        expected = d
        while len(expected) > 1 and expected[-1] == 0:
            expected = expected[:-1]
        assert to_digits(from_digits(d)) == expected


def test_from_digits_drops_high_order_zeros():
    """to_digits je canonical -- high-order nuly nie su vratene spat."""
    assert from_digits([1, 0, 0]) == from_digits([1])
    assert to_digits(from_digits([1, 0, 0])) == [1]
    assert from_digits([0, 0]) == "0"
    assert to_digits(from_digits([0, 0])) == [0]


# ============================================================ low-level vs int
def test_add_b60_matches_int():
    for _ in range(5000):
        a, b = rand_b60(), rand_b60()
        assert Base60Int(add_b60(a, b)).to_int() == (
            Base60Int(a).to_int() + Base60Int(b).to_int()
        )


def test_mul_b60_matches_int():
    for _ in range(2000):
        a, b = rand_b60(), rand_b60()
        assert Base60Int(mul_b60(a, b)).to_int() == (
            Base60Int(a).to_int() * Base60Int(b).to_int()
        )


def test_sub_b60_matches_int():
    for _ in range(5000):
        a, b = rand_b60(), rand_b60()
        x, y = Base60Int(a).to_int(), Base60Int(b).to_int()
        if x >= y:
            assert Base60Int(sub_b60(a, b)).to_int() == x - y
        else:
            with pytest.raises(ValueError):
                sub_b60(a, b)


def test_sub_negative_raises():
    with pytest.raises(ValueError):
        sub_b60("0", "1")


def test_divmod_b60_matches_int():
    for _ in range(2000):
        a, b = rand_b60(), rand_b60()
        if b == H.ALPHABET[0]:
            continue
        q, r = divmod_b60(a, b)
        x, y = Base60Int(a).to_int(), Base60Int(b).to_int()
        assert Base60Int(q).to_int() == x // y
        assert Base60Int(r).to_int() == x % y
        # a == q*b + r
        assert Base60Int(mul_b60(q, b)).to_int() + Base60Int(r).to_int() == x


def test_divmod_by_zero():
    with pytest.raises(ZeroDivisionError):
        divmod_b60("5", "0")


def test_canonical_strips_leading_zeros():
    assert add_b60("000", "000") == "0"
    assert mul_b60("000001", "000001") == "1"
    # "000" su tri cifry nuly, takze hodnota je rovnaka ako pri prazdnom
    assert Base60Int("000123").to_b60() == "123"
    assert Base60Int("000123").to_int() == 1 * 60 ** 2 + 2 * 60 + 3


# ==================================================================== konverzie
def test_construct_from_all_types():
    assert Base60Int(60).to_b60() == "10"
    assert Base60Int("10").to_int() == 60
    assert Base60Int(b"\x01\x00").to_int() == 256
    assert Base60Int(Base60Int(60)).to_int() == 60
    assert Base60Int(0).to_b60() == "0"


def test_construct_rejects_negative():
    with pytest.raises(ValueError):
        Base60Int(-1)


def test_construct_rejects_bool():
    """bool je podclass int; ticho by sa spraval ako 0/1."""
    with pytest.raises(TypeError):
        Base60Int(True)


def test_construct_rejects_invalid_char():
    with pytest.raises(H.InvalidCharacterError):
        Base60Int("AB!")


def test_construct_rejects_empty():
    with pytest.raises(ValueError):
        Base60Int("")


def test_construct_rejects_unsupported_type():
    with pytest.raises(TypeError):
        Base60Int(1.5)


# ==================================================================== bytes
def test_to_bytes_roundtrip():
    for _ in range(500):
        v = RNG.randrange(0, 2 ** 64)
        assert int.from_bytes(Base60Int(v).to_bytes(), "big") == v


def test_to_bytes_pads():
    assert Base60Int(1).to_bytes(4) == b"\x00\x00\x00\x01"
    assert Base60Int(0).to_bytes(3) == b"\x00\x00\x00"


def test_to_bytes_too_short_raises():
    with pytest.raises(H.LengthError):
        Base60Int(2 ** 64).to_bytes(1)


def test_to_bytes_rejects_negative_length():
    with pytest.raises(ValueError):
        Base60Int(1).to_bytes(-1)


# ==================================================================== immutability
def test_is_immutable():
    n = Base60Int(5)
    with pytest.raises(AttributeError):
        n._value = 10
    with pytest.raises(AttributeError):
        n.anything = 1
    assert n.to_int() == 5


def test_slots_prevent_dynamic_attrs():
    n = Base60Int(5)
    with pytest.raises(AttributeError):
        n.__dict__


# ==================================================================== arithmetic
def test_add_with_all_operand_types():
    a = Base60Int(10)
    assert (a + 5).to_int() == 15
    assert (a + "5").to_int() == 15
    assert (a + Base60Int(5)).to_int() == 15
    assert (5 + a).to_int() == 15


def test_sub_negative_raises():
    with pytest.raises(ValueError):
        Base60Int(1) - Base60Int(5)
    with pytest.raises(ValueError):
        1 - Base60Int(5)


def test_div_by_zero_raises():
    for op in (
        lambda: Base60Int(5) // 0,
        lambda: Base60Int(5) % 0,
        lambda: divmod(Base60Int(5), 0),
        lambda: 5 // Base60Int(0),
    ):
        with pytest.raises(ZeroDivisionError):
            op()


def test_pow():
    assert (Base60Int(2) ** 10).to_int() == 1024
    assert (Base60Int(2) ** Base60Int(10)).to_int() == 1024
    assert (Base60Int(2) ** 10 % 1000).to_int() == 24


def test_pow_negative_exponent_raises():
    with pytest.raises(ValueError):
        Base60Int(2) ** -1


def test_negation_raises():
    with pytest.raises(TypeError):
        -Base60Int(1)


def test_comparison():
    a, b = Base60Int(60), Base60Int(61)
    assert a < b and a <= b and b > a and b >= a
    assert Base60Int(60) == "10"
    assert Base60Int(60) == 60
    assert Base60Int(60) != "11"


def test_hash_usable_in_set():
    s = {Base60Int(60), Base60Int(60), Base60Int("10")}
    assert len(s) == 1


def test_int_roundtrip_and_bool():
    assert int(Base60Int(60)) == 60
    assert bool(Base60Int(0)) is False
    assert bool(Base60Int(1)) is True


def test_repr_and_str():
    assert str(Base60Int(60)) == "10"
    assert repr(Base60Int(60)) == "Base60Int('10')"
    assert "modulus=60" in repr(Base60Int(5, modulus=60))


# ==================================================================== modulus
def test_modulus_reduces():
    assert Base60Int(100, modulus=60).to_int() == 40


def test_modulus_propagates_through_ops():
    n = Base60Int(50, modulus=60)
    assert (n + 30).to_int() == 20
    assert (n * n).to_int() == (50 * 50) % 60


def test_modulus_rejects_bad():
    with pytest.raises(ValueError):
        Base60Int(1, modulus=0)
    with pytest.raises(ValueError):
        Base60Int(1, modulus=-5)


# ==================================================================== rotate
def test_rotate_digit_basic():
    """rotate_digit je PERMUTACIA cifier, nie aritmetika."""
    assert Base60Int(1).rotate_digit(1).digits() == [2]


def test_rotate_digit_wraps_at_60():
    assert Base60Int(59).rotate_digit(1).digits() == [0]


def test_rotate_digit_shift_60_is_identity():
    """rotate_digit(60) musi byt identita -- inak to nie je permutacia."""
    n = Base60Int(1234, modulus=60 ** 4)
    assert n.rotate_digit(60).to_int() == n.to_int()


def test_rotate_digit_with_explicit_width():
    """Kazda cifra sa posunie, aj high-order nuly. [5,0,0] -> [6,1,1]."""
    assert Base60Int(5).rotate_digit(1, width=3).to_b60() == from_digits([6, 1, 1])


def test_rotate_digit_rejects_bad():
    with pytest.raises(TypeError):
        Base60Int(1).rotate_digit("x")
    with pytest.raises(ValueError):
        Base60Int(1).rotate_digit(1, width=0)


# ==================================================================== ring_add
def test_ring_add_mod_60():
    """Scitanie na kruhu: prenos sa zahadzuje, nie prenasa."""
    assert Base60Int(59).ring_add(1).to_b60() == "0"


def test_ring_add_keeps_width_with_modulus():
    n = Base60Int(1, modulus=60 ** 3)
    assert n.ring_add(1).to_b60() == "2"
    assert n.ring_add(59).to_b60() == from_digits([0, 0, 0])


def test_ring_add_commutative():
    a, b = Base60Int(30), Base60Int(45)
    assert a.ring_add(b).to_int() == b.ring_add(a).to_int()


def test_ring_add_rejects_non_60_modulus():
    with pytest.raises(ValueError):
        Base60Int(1).ring_add(1, modulus=10)
