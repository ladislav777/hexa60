"""
base60_int.py -- Base60Int, nepremenlivy typ cisla v sústave 60.

Navrh vychadza z hexa60.ALPHABET, takze kody su zhodne s wire formatom
v hexa60.py. Rovnaku abecedu pouziva aj base60_arithmetic.py, takze vsetky
tri moduly hovoria o TIEZ CISLACH a su navzajom zamenitelne.

Dve vrstvy:
  1. Low-level funkcie na retazcoch (add_b60, mul_b60, ...) -- rucne
     implementovana aritmetika na cislach, bez int() medzikroku.
  2. Base60Int -- nepremenlive ohnisko, interne drzi python int.

Low-level funkcie su referenciou pre spravnost; testy to overuju na
desiatkach tisicok nahodnych vstupov proti python int.

Ziadny z tychto typov nema znamienko. Zaporne hodnoty nie su
representovatelne v 60-symbolickej sustave bez znamienkovej pozicie, takze
odcitanie, ktore dava zaporny vysledok, hodi ValueError. Ak potrebujes
znamienka, pridaj ich az na tejto urovni explicitne -- nevyskytuju sa
potichu.
"""
from __future__ import annotations

import math
from typing import List, Optional, Tuple, Union

from hexa60 import ALPHABET, BASE, LOOKUP, InvalidCharacterError, LengthError

__all__ = [
    "BASE",
    "ALPHABET",
    "Base60Int",
    "add_b60",
    "sub_b60",
    "mul_b60",
    "divmod_b60",
    "to_digits",
    "from_digits",
]

BITS_PER_BYTE = 8


# --------------------------------------------------------------------------
# Validacia a pomocne prevody
# --------------------------------------------------------------------------
def _check_str(s, name: str) -> str:
    if not isinstance(s, str):
        raise TypeError(f"{name}: expected str, got {type(s).__name__}")
    if not s:
        raise ValueError(f"{name}: empty string is not a number")
    for i, ch in enumerate(s):
        if ch not in LOOKUP:
            raise InvalidCharacterError(ch, i)
    return s


def _strip_zeros(s: str) -> str:
    """Odstrani high-order nuly. '000' -> '0'."""
    stripped = s.lstrip(ALPHABET[0])
    return stripped if stripped else ALPHABET[0]


def to_digits(s: str) -> List[int]:
    """Base60 retazec -> zoznam cisl [LSB ... MSB]."""
    _check_str(s, "to_digits")
    return [LOOKUP[ch] for ch in reversed(s)]


def from_digits(digits: List[int]) -> str:
    """Zoznam cisl [LSB ... MSB] -> kanonicky Base60 retazec."""
    out = []
    for d in digits:
        if not isinstance(d, int) or isinstance(d, bool):
            raise TypeError(f"from_digits: digit must be int, got {type(d).__name__}")
        if not 0 <= d < BASE:
            raise ValueError(f"from_digits: digit {d} out of range [0, {BASE})")
        out.append(ALPHABET[d])
    return _strip_zeros("".join(reversed(out)))


# --------------------------------------------------------------------------
# Low-level aritmetika na cislach (LSB first)
# --------------------------------------------------------------------------
def _add_digits(a: List[int], b: List[int]) -> List[int]:
    n = max(len(a), len(b))
    out = []
    carry = 0
    for i in range(n):
        total = (a[i] if i < len(a) else 0) + (b[i] if i < len(b) else 0) + carry
        out.append(total % BASE)
        carry = total // BASE
    if carry:
        out.append(carry)
    return out


def _cmp_digits(a: List[int], b: List[int]) -> int:
    n = max(len(a), len(b))
    for i in range(n - 1, -1, -1):
        x = a[i] if i < len(a) else 0
        y = b[i] if i < len(b) else 0
        if x != y:
            return 1 if x > y else -1
    return 0


def _sub_digits(a: List[int], b: List[int]) -> List[int]:
    """a - b, vyzaduje a >= b. Zvysny borrow je nedostatny, takze netreba
    ho prenasat -- to je rozdiel oproti base60_arithmetic, kde sa musel."""
    if _cmp_digits(a, b) < 0:
        raise ValueError("base60 subtract: a < b")
    n = max(len(a), len(b))
    out = list(a) + [0] * (n - len(a))
    borrow = 0
    for i in range(n):
        diff = out[i] - (b[i] if i < len(b) else 0) - borrow
        if diff < 0:
            diff += BASE
            borrow = 1
        else:
            borrow = 0
        out[i] = diff
    while out and out[-1] == 0:
        out.pop()
    return out or [0]


def _mul_digits(a: List[int], b: List[int]) -> List[int]:
    """Skolbook, O(n*m). Bez insert(0, ...) z base60_arithmetic, ktore je
    O(n) na kazdom kroku a tym padalo na O(n^2) s konstantou."""
    if a == [0] or b == [0]:
        return [0]
    out = [0] * (len(a) + len(b))
    for i, x in enumerate(a):
        if x == 0:
            continue
        carry = 0
        for j, y in enumerate(b):
            total = out[i + j] + x * y + carry
            out[i + j] = total % BASE
            carry = total // BASE
        k = i + len(b)
        while carry:
            total = out[k] + carry
            out[k] = total % BASE
            carry = total // BASE
            k += 1
    while out and out[-1] == 0:
        out.pop()
    return out or [0]


def _divmod_digits(a: List[int], b: List[int]) -> Tuple[List[int], List[int]]:
    """Long division na cislach, bez int() medzikroku.

    `a` je LSB first, takze delenie MUSI ist cez cifry od MSB -- inak
    zvysok vychadza vacsi nez dividend.
    """
    if b == [0]:
        raise ZeroDivisionError("division by zero in base-60")
    # Vysledne cifry podielu zbierame v poradi MSB first (lebo iterujeme
    # od MSB), no _strip_zeros a from_digits ocakavaju LSB first. Preto
    # na konci podiel otovime -- inak je podiel cislo s prehodenymi ciframi.
    quotient_msb: List[int] = []
    remainder: List[int] = [0]
    for digit in reversed(a):
        # remainder = remainder * 60 + digit
        remainder = [digit] + remainder
        while remainder and remainder[-1] == 0:
            remainder.pop()
        if not remainder:
            remainder = [0]
        q = 0
        while _cmp_digits(remainder, b) >= 0:
            remainder = _sub_digits(remainder, b)
            q += 1
        quotient_msb.append(q)
    quotient = list(reversed(quotient_msb))
    while quotient and quotient[-1] == 0:
        quotient.pop()
    return quotient or [0], remainder


# --------------------------------------------------------------------------
# Low-level API na retazcoch
# --------------------------------------------------------------------------
def add_b60(a: str, b: str) -> str:
    """Scita dva Base60 retazce, s prenosom."""
    return from_digits(_add_digits(to_digits(a), to_digits(b)))


def sub_b60(a: str, b: str) -> str:
    """Odcita b od a. ValueError, ak a < b (Base-60 nema znamienko)."""
    return from_digits(_sub_digits(to_digits(a), to_digits(b)))


def mul_b60(a: str, b: str) -> str:
    """Nasobi dva Base60 retazce."""
    return from_digits(_mul_digits(to_digits(a), to_digits(b)))


def divmod_b60(a: str, b: str) -> Tuple[str, str]:
    """Podiel a zvysok dvoch Base60 retazcov."""
    q, r = _divmod_digits(to_digits(a), to_digits(b))
    return from_digits(q), from_digits(r)


# --------------------------------------------------------------------------
# Base60Int
# --------------------------------------------------------------------------
Operand = Union["Base60Int", int, str]


class Base60Int:
    """
    Nepremenlive cislo v sústave Base60.

    Vnútorný stav je python int (neobmedzená presnost) + volitelný modulus
    pre kruhovú aritmetiku. Primárna reprezentácia je reťazec z
    hexa60.ALPHABET.

    Bez znamienka. Záporné hodnoty nie sú reprezentovateľné; odčítanie pod
    nulu hodí ValueError.
    """

    __slots__ = ("_value", "_modulus", "_text")

    def __init__(
        self,
        value: Union[int, str, bytes, "Base60Int"] = 0,
        *,
        modulus: Optional[int] = None,
    ):
        if isinstance(value, Base60Int):
            data = value._value
        elif isinstance(value, bool):
            raise TypeError("Base60Int: bool is not accepted; use int explicitly")
        elif isinstance(value, int):
            data = value
        elif isinstance(value, str):
            data = self._str_to_int(value)
        elif isinstance(value, (bytes, bytearray, memoryview)):
            data = self._bytes_to_int(bytes(value))
        else:
            raise TypeError(f"Base60Int: unsupported type {type(value).__name__}")

        if data < 0:
            raise ValueError(
                "Base60Int: negative values are not representable in Base-60"
            )

        if modulus is not None:
            if not isinstance(modulus, int) or isinstance(modulus, bool):
                raise TypeError("modulus must be int")
            if modulus <= 0:
                raise ValueError(f"modulus must be positive, got {modulus}")
            data %= modulus

        object.__setattr__(self, "_value", data)
        object.__setattr__(self, "_modulus", modulus)
        object.__setattr__(self, "_text", None)

    # -- internal ---------------------------------------------------------
    @staticmethod
    def _str_to_int(text: str) -> int:
        if not text:
            raise ValueError("Base60Int: empty string is not a number")
        for i, ch in enumerate(text):
            if ch not in LOOKUP:
                raise InvalidCharacterError(ch, i)
        value = 0
        for ch in text:
            value = value * BASE + LOOKUP[ch]
        return value

    @staticmethod
    def _bytes_to_int(data: bytes) -> int:
        return int.from_bytes(data, "big") if data else 0

    def _new(self, value: int) -> "Base60Int":
        return Base60Int(value, modulus=self._modulus)

    # -- immutability -----------------------------------------------------
    def __setattr__(self, name, value):
        raise AttributeError("Base60Int is immutable")

    def __delattr__(self, name):
        raise AttributeError("Base60Int is immutable")

    # -- properties -------------------------------------------------------
    @property
    def modulus(self) -> Optional[int]:
        return self._modulus

    @property
    def width(self) -> int:
        """Počet cifier v aktuálnej reprezentácii. Minimálne 1."""
        digits = self.digits()
        return len(digits)

    # -- conversions ------------------------------------------------------
    def to_b60(self) -> str:
        """Kanonický Base60 reťazec, bez high-order nul."""
        if self._text is None:
            object.__setattr__(self, "_text", self._encode(self._value))
        return self._text

    @staticmethod
    def _encode(value: int) -> str:
        if value == 0:
            return ALPHABET[0]
        chars = []
        while value:
            value, idx = divmod(value, BASE)
            chars.append(ALPHABET[idx])
        return "".join(reversed(chars))

    def to_int(self) -> int:
        return self._value

    def to_bytes(self, length: Optional[int] = None) -> bytes:
        """
        Bajtová reprezentácia, big-endian.

        length=None -> minimálny počet bajtov (0 pre hodnotu 0).
        length=n    -> presne n bajtov, doplnené nulami zľava. LengthError,
                       ak hodnota nezmestí.
        """
        if length is None:
            length = (self._value.bit_length() + BITS_PER_BYTE - 1) // BITS_PER_BYTE
        if not isinstance(length, int) or isinstance(length, bool):
            raise TypeError("length must be int or None")
        if length < 0:
            raise ValueError(f"length must be non-negative, got {length}")
        try:
            return self._value.to_bytes(length, "big")
        except OverflowError:
            needed = (self._value.bit_length() + BITS_PER_BYTE - 1) // BITS_PER_BYTE
            raise LengthError(
                length, {f">= {needed} bytes for value {self._value}"}
            ) from None

    def digits(self) -> List[int]:
        """Cifry [LSB ... MSB]."""
        if self._value == 0:
            return [0]
        out = []
        v = self._value
        while v:
            v, d = divmod(v, BASE)
            out.append(d)
        return out

    # -- arithmetic -------------------------------------------------------
    def __add__(self, other: Operand) -> "Base60Int":
        return self._new(self._value + self._coerce(other))

    __radd__ = __add__

    def __sub__(self, other: Operand) -> "Base60Int":
        result = self._value - self._coerce(other)
        if result < 0:
            raise ValueError(
                f"Base60Int: {self.to_b60()} - {self._describe(other)} is negative; "
                "Base-60 has no sign"
            )
        return self._new(result)

    def __rsub__(self, other: Operand) -> "Base60Int":
        result = self._coerce(other) - self._value
        if result < 0:
            raise ValueError("Base60Int: result is negative; Base-60 has no sign")
        return self._new(result)

    def __mul__(self, other: Operand) -> "Base60Int":
        return self._new(self._value * self._coerce(other))

    __rmul__ = __mul__

    def __floordiv__(self, other: Operand) -> "Base60Int":
        divisor = self._coerce(other)
        if divisor == 0:
            raise ZeroDivisionError("division by zero in Base60Int")
        return self._new(self._value // divisor)

    def __rfloordiv__(self, other: Operand) -> "Base60Int":
        if self._value == 0:
            raise ZeroDivisionError("division by zero in Base60Int")
        return self._new(self._coerce(other) // self._value)

    def __mod__(self, other: Operand) -> "Base60Int":
        divisor = self._coerce(other)
        if divisor == 0:
            raise ZeroDivisionError("modulo by zero in Base60Int")
        return self._new(self._value % divisor)

    def __rmod__(self, other: Operand) -> "Base60Int":
        if self._value == 0:
            raise ZeroDivisionError("modulo by zero in Base60Int")
        return self._new(self._coerce(other) % self._value)

    def __divmod__(self, other: Operand) -> Tuple["Base60Int", "Base60Int"]:
        divisor = self._coerce(other)
        if divisor == 0:
            raise ZeroDivisionError("division by zero in Base60Int")
        q, r = divmod(self._value, divisor)
        return self._new(q), self._new(r)

    def __rdivmod__(self, other: Operand) -> Tuple["Base60Int", "Base60Int"]:
        if self._value == 0:
            raise ZeroDivisionError("division by zero in Base60Int")
        q, r = divmod(self._coerce(other), self._value)
        return self._new(q), self._new(r)

    def __pow__(
        self,
        power: Union["Base60Int", int],
        modulo: Optional[Union["Base60Int", int]] = None,
    ) -> "Base60Int":
        if isinstance(power, bool) or not isinstance(power, (int, Base60Int)):
            raise TypeError("Base60Int power must be int")
        exp = power.to_int() if isinstance(power, Base60Int) else power
        if exp < 0:
            raise ValueError(
                "Base60Int: negative exponent needs modular inverse, not implemented"
            )
        if modulo is None:
            return self._new(pow(self._value, exp))
        mod = self._coerce(modulo)
        if mod == 0:
            raise ZeroDivisionError("modulo by zero in Base60Int")
        return self._new(pow(self._value, exp, mod))

    def __neg__(self) -> "Base60Int":
        raise TypeError("Base60Int: negation not supported; Base-60 has no sign")

    def __pos__(self) -> "Base60Int":
        return self

    def __abs__(self) -> "Base60Int":
        return self

    def __bool__(self) -> bool:
        return self._value != 0

    def __int__(self) -> int:
        return self._value

    def __index__(self) -> int:
        return self._value

    # -- comparison -------------------------------------------------------
    def __eq__(self, other: object) -> bool:
        if isinstance(other, (Base60Int, int, str)) and not isinstance(other, bool):
            try:
                return self._value == self._coerce(other)
            except (ValueError, InvalidCharacterError, TypeError):
                return NotImplemented
        return NotImplemented

    def __ne__(self, other: object) -> bool:
        result = self.__eq__(other)
        if result is NotImplemented:
            return result
        return not result

    def __lt__(self, other: Operand) -> bool:
        return self._value < self._coerce(other)

    def __le__(self, other: Operand) -> bool:
        return self._value <= self._coerce(other)

    def __gt__(self, other: Operand) -> bool:
        return self._value > self._coerce(other)

    def __ge__(self, other: Operand) -> bool:
        return self._value >= self._coerce(other)

    def __hash__(self) -> int:
        return hash(self._value)

    # -- ring / phase operations -----------------------------------------
    def _ring_width(self) -> int:
        """Sirka kruhu v cislach, odvodena z modulusu."""
        if self._modulus is None:
            raise ValueError("no modulus set on this Base60Int")
        if self._modulus == 1:
            return 1
        return math.ceil(math.log(self._modulus, BASE))

    def rotate_digit(self, shift: int, width: Optional[int] = None) -> "Base60Int":
        """
        Posunie každu cifru o shift pozícií mod 60.

        POZOR: to NIE JE aritmetická operácia. Je to permutácia cifier, ktorá
        nemení základ (neposunie číslo o rád čísel), takže výsledok nemá s
        pôvodnou hodnotou nič matematicky spoločné. Je to syntaktický alebo
        kryptografický nástroj, nie arithmetic. Ak potrebuješ číselný posun,
        použi `<<` na int alebo vynásobenie mocninou 60.

        width: pevná šírka. Ak je None a self má modulus, šírka sa odvodí
        z neho (60**k) a rotácia je stabilná. Inak sa použije aktuálna
        šírka hodnoty.
        """
        if isinstance(shift, bool) or not isinstance(shift, int):
            raise TypeError("shift must be int")
        if width is None:
            width = self._ring_width() if self._modulus is not None else self.width
        if isinstance(width, bool) or not isinstance(width, int):
            raise TypeError("width must be int")
        if width < 1:
            raise ValueError(f"width must be >= 1, got {width}")

        digits = self.digits()
        if len(digits) < width:
            digits += [0] * (width - len(digits))
        else:
            digits = digits[-width:]

        rotated = [(d + shift) % BASE for d in digits]
        return Base60Int(
            from_digits(rotated), modulus=self._modulus
        )

    def ring_add(
        self,
        other: Operand,
        modulus: int = 60,
    ) -> "Base60Int":
        """
        Sčítanie na kruhu cifier: každá cifra sa sčíta mod `modulus`,
        prenos sa zahazuje.

        Operandy sa zarovnajú na spoločnú šírku doplnením nulami zľava.
        Ak self má nastavený modulus, šírka je z neho odvodená, takže
        výsledok má rovnakú šírku. Bez modulusu sa použije max šírka oboch
        operandov.
        """
        if modulus != BASE:
            raise ValueError(
                f"ring_add: modulus must be {BASE} (a Base-60 digit ring), "
                f"got {modulus}"
            )
        rhs = self._coerce(other)
        a = self.digits()
        b = Base60Int(rhs).digits()
        width = self._ring_width() if self._modulus is not None else max(len(a), len(b))
        a = (a + [0] * width)[:width]
        b = (b + [0] * width)[:width]
        summed = [(x + y) % BASE for x, y in zip(a, b)]
        return Base60Int(from_digits(summed), modulus=self._modulus)

    # -- display ----------------------------------------------------------
    def __repr__(self) -> str:
        mod = f", modulus={self._modulus}" if self._modulus is not None else ""
        return f"Base60Int({self.to_b60()!r}{mod})"

    def __str__(self) -> str:
        return self.to_b60()

    # -- helpers ----------------------------------------------------------
    def _coerce(self, other: Operand) -> int:
        if isinstance(other, Base60Int):
            return other._value
        if isinstance(other, bool):
            raise TypeError("Base60Int: bool is not accepted; use int explicitly")
        if isinstance(other, int):
            return other
        if isinstance(other, str):
            return self._str_to_int(other)
        raise TypeError(f"Base60Int: cannot combine with {type(other).__name__}")

    @staticmethod
    def _describe(other: Operand) -> str:
        if isinstance(other, Base60Int):
            return other.to_b60()
        return repr(other)

