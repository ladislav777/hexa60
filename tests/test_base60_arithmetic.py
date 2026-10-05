# ============================================================================
# HEXA-60 CORE™ — High-Throughput Base60 Encoding Engine
# Copyright (c) 2026 Ladislav Müller (IČO: 40189589). All rights reserved.
#
# PROPRIETARY AND CONFIDENTIAL SOFTWARE.
# Unauthorized copying, distribution, or modification of this file, via any
# medium, is strictly prohibited under applicable copyright laws and B2B EULA.
# ============================================================================

"""Testy pre base60_arithmetic -- digitova aritmetika na reťazcoch.

Toto je LEGACY modul (povodne bez vlastnych testov, pokryval ho len
neexistentny __main__). Kazda operacia sa overuje PROTI python int, takze
testy su nezavisle od base60_int -- inak by sme len porovnavali dve
implementacie, ktore mozu zdieľat rovnaku chybu.
"""
import random
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import base60_arithmetic as BA
import hexa60 as H

RNG = random.Random(31337)


def rand_b60(max_digits=10):
    n = RNG.randrange(1, max_digits)
    return "".join(H.ALPHABET[RNG.randrange(60)] for _ in range(n))


# ==================================================================== abeceda
def test_uses_hexa60_alphabet():
    """Abeceda musi byt TOTOZNA s hexa60, inak su moduly nekompatibilne."""
    assert BA.BASE60_ALPHABET == H.ALPHABET
    assert BA.BASE60_REVERSE == H.LOOKUP


def test_no_plus_in_alphabet():
    assert "+" not in BA.BASE60_ALPHABET


# ==================================================================== add
def test_add_basic():
    assert BA.base60_add("1", "1") == "2"
    assert BA.base60_add("0", "0") == "0"
    assert BA.base60_add("W", "W") == "10"      # 32+32 = 64 = 1*60+4


def test_add_carry_at_59():
    """59 je posledny znak ('-'). 59 + 1 musi dat carry."""
    assert BA.base60_add("-", "1") == "10"


def test_add_matches_int_random():
    for _ in range(3000):
        a, b = rand_b60(), rand_b60()
        got = BA.base60_add(a, b)
        assert BA.decode(got) == BA.decode(a) + BA.decode(b), f"{a} + {b}"


# ==================================================================== multiply
def test_multiply_basic():
    assert BA.base60_multiply("2", "3") == "6"
    assert BA.base60_multiply("0", "5") == "0"
    assert BA.base60_multiply("5", "0") == "0"


def test_multiply_by_one():
    for s in ["1", "5", "W", "zzz"]:
        assert BA.base60_multiply(s, "1") == s


def test_multiply_matches_int_random():
    for _ in range(500):
        a, b = rand_b60(), rand_b60()
        got = BA.base60_multiply(a, b)
        assert BA.decode(got) == BA.decode(a) * BA.decode(b), f"{a} * {b}"


# ==================================================================== compare
def test_compare_normalizes():
    """Regresia: compare musi NORMALIZOVAT obe strany, inak [0,0] > [2]."""
    assert BA.base60_compare([0, 0], [2]) < 0
    assert BA.base60_compare([0, 0], [0, 0]) == 0
    assert BA.base60_compare([3], [2, 0]) > 0


def test_compare_on_strings():
    assert BA.base60_compare("1", "2") < 0
    assert BA.base60_compare("2", "1") > 0
    assert BA.base60_compare("1", "1") == 0


# ==================================================================== subtract
def test_subtract_basic():
    assert BA.base60_from_digits(BA.base60_subtract([2], [1])) == "1"


def test_subtract_borrow_propagates():
    """Regresia: zvysny borrow musi prejst cez pozicie za b."""
    # 1000 - 1 = zzz  (60^3 - 1)
    digits_a = BA.base60_to_digits("1000")
    digits_b = BA.base60_to_digits("1")
    result = BA.base60_from_digits(BA.base60_subtract(digits_a, digits_b))
    assert BA.decode(result) == 60 ** 3 - 1


def test_subtract_raises_when_a_smaller():
    with pytest.raises(ValueError):
        BA.base60_subtract(BA.base60_to_digits("1"), BA.base60_to_digits("10"))


def test_subtract_does_not_mutate_input():
    """Subtract nesmie mutovat vstupny digit list."""
    a = BA.base60_to_digits("1000")
    b = BA.base60_to_digits("1")
    a_before, b_before = list(a), list(b)
    BA.base60_subtract(a, b)
    assert a == a_before
    assert b == b_before


# ==================================================================== fraction
@pytest.mark.parametrize("num,den,expect", [
    ("1", "3", "0.L"),
    ("1", "2", "0.W"),
    ("1", "4", "0.F"),
    ("1", "5", "0.C"),
    ("1", "6", "0.A"),
    ("2", "3", "0.g"),
    ("1", "7", "0.8aH"),
])
def test_fraction_known_values(num, den, expect):
    assert BA.base60_fraction(num, den) == expect


def test_fraction_terminates_exactly():
    """1/2 == 0.5 musi skoncit PRESNE, nie po 20 cifrach."""
    assert BA.base60_fraction("1", "2") == "0.W"
    assert BA.base60_fraction("1", "4") == "0.F"


def test_fraction_whole_number():
    assert BA.base60_fraction("2", "1") == "2"
    assert BA.base60_fraction("1", "1") == "1"


def test_fraction_by_zero_raises():
    with pytest.raises(ZeroDivisionError):
        BA.base60_fraction("1", "0")


def test_fraction_values_below_one_sixtieth():
    """Regresia: povodny guard `remainder[0] > 0` toto ukoncil po 1 cifre.
    Tieto zlomky su presne tie, ktore pokazovali na bug."""
    for den in ["H", "N", "V", "z"]:
        r = BA.base60_fraction("1", den)
        digits = r.split(".")[1]
        approx = sum(H.LOOKUP[c] / 60 ** (i + 1) for i, c in enumerate(digits))
        true = 1 / BA.decode(den)
        assert abs(approx - true) < 1e-9, f"1/{den}"


# ==================================================================== encode/decode
def test_encode_decode_roundtrip():
    for v in [0, 1, 59, 60, 3599, 3600, 12345, 10 ** 30]:
        assert BA.decode(BA.encode(v)) == v


def test_encode_59_is_last_char():
    assert BA.encode(59) == H.ALPHABET[59] == "-"


def test_encode_negative_raises():
    with pytest.raises(ValueError):
        BA.encode(-1)


def test_decode_empty_raises():
    with pytest.raises(ValueError):
        BA.decode("")


def test_decode_invalid_char_raises():
    with pytest.raises(ValueError):
        BA.decode("XY!")


# ==================================================================== zhoda s base60_int
def test_agrees_with_base60_int():
    """Oba moduly musia davat rovnake HODNOTY.

    Pozor: porovnavame cez decode(), nie na retezco. base60_arithmetic
    neodstranuje high-order nuly, takze rovnake cislo moze byt zapisane
    ako '000' (arithmetic) a '0' (base60_int).
    """
    from base60_int import add_b60, mul_b60

    for _ in range(1000):
        a, b = rand_b60(), rand_b60()
        for name, mine, theirs in [
            ("add", BA.base60_add(a, b), add_b60(a, b)),
            ("mul", BA.base60_multiply(a, b), mul_b60(a, b)),
        ]:
            assert BA.decode(mine) == BA.decode(theirs), f"{name} {a}, {b}"
