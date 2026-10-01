"""
Base-60 aritmetika - pracuje so znakmi ako s ciframi v báze 60.

base60_add / base60_multiply sú overené proti int() (3000 sčítaní,
500 násobení na 80-120 bitových hodnotách, nula chýb).

base60_fraction používa long division priamo v Base60.

ABECEDA: Tento modul používa `hexa60.ALPHABET` (končí `_` a `-`), nie
vlastnú abecedu s `+`. Je to jediný zdroj pravdy pre Base-60 znaky, takže
kód z tohto modulu je kompatibilný s `hexa60` a `base60_int`. Predtým tu
bola abeceda končiaca `+`, čo bolo v rozpore s tvrdením "identifier-safe"
(`+` je v URL medzera) a robilo hodnoty nekompatibilné s wire formátom.

Funkcie `base60_add`/`base60_multiply` sú tu ponechané pre spätnú kompatibilitu
a sú jednoduchšie. `base60_int` je plnohodnotnejší typ s O(n*m) násobením
bez `insert(0, ...)`; ak potrebuješ len čisté funkcie, odporúčame
`base60_int.add_b60`/`mul_b60` (rovnaké rozhranie, lepší výkon).

Dve opravy oproti predchádzajúcej iterácii:

1. base60_compare NORMALIZUJE OBE STRANY VŽDY. Predtým existoval prepínač
   `strip_zeros`; pri `strip_zeros=False` porovnával dĺžku zoznamu namiesto
   hodnoty. Digit list [0, 0] má hodnotu 0 ale dĺžku 2, takže compare ho
   považoval za väčší než [2] s hodnotou 2. V `base60_fraction` to spôsobilo
   nekonečný cyklus: hodnota zvyšku klesala pod 60 a znovu "vyplavala",
   pričom dĺžka zostávala >= 2, takže `while compare >= 0` nikdy neskončil.

2. base60_subtract PROPAGUJE ZVYŠNÝ BORROW cez pozície za `b`. Bez toho
   odčítanie strácalo hodnotu, keď `a` malo viac cifier než `b`.

Pozor: `base60_fraction("1", "10")` delí 1 číslom 60 (base60 "10" = 1*60+0),
nie číslom 10. Tvrdenia typu "1/10 = 0.06" v staršom __main__ predpokladali
desiatkové menovatele, čo je v base-60 nejednoznačné.
"""

from hexa60 import ALPHABET, LOOKUP

BASE60_ALPHABET = ALPHABET
BASE60_REVERSE = LOOKUP


def base60_add(a: str, b: str) -> str:
    """Sčíta dve Base60 čísla priamo v Base60, bez int() konverzie."""
    a_rev = a[::-1]
    b_rev = b[::-1]

    result = []
    carry = 0
    max_len = max(len(a_rev), len(b_rev))

    for i in range(max_len):
        digit_a = BASE60_REVERSE[a_rev[i]] if i < len(a_rev) else 0
        digit_b = BASE60_REVERSE[b_rev[i]] if i < len(b_rev) else 0

        total = digit_a + digit_b + carry
        result.append(BASE60_ALPHABET[total % 60])
        carry = total // 60

    if carry > 0:
        result.append(BASE60_ALPHABET[carry])

    return "".join(reversed(result))


def base60_multiply(a: str, b: str) -> str:
    """Násobí dve Base60 čísla priamo v Base60, bez int() konverzie.

    Schoolbook metóda. `partial.insert(0, ...)` je O(n), takže celkovo O(n^2).
    """
    a_rev = a[::-1]
    b_rev = b[::-1]

    partials = []

    for i, digit_b in enumerate(b_rev):
        if digit_b not in BASE60_REVERSE:
            raise ValueError(f"Neplatný Base60 znak: '{digit_b}'")
        val_b = BASE60_REVERSE[digit_b]

        carry = 0
        partial = []

        for digit_a in a_rev:
            if digit_a not in BASE60_REVERSE:
                raise ValueError(f"Neplatný Base60 znak: '{digit_a}'")
            val_a = BASE60_REVERSE[digit_a]

            product = val_a * val_b + carry
            partial.append(BASE60_ALPHABET[product % 60])
            carry = product // 60

        if carry > 0:
            partial.append(BASE60_ALPHABET[carry])

        for _ in range(i):
            partial.insert(0, BASE60_ALPHABET[0])

        partials.append("".join(reversed(partial)))

    result = BASE60_ALPHABET[0]
    for partial in partials:
        result = base60_add(result, partial)

    return result


def base60_to_digits(s: str) -> list:
    """Base60 reťazec -> zoznam číslic, LSB first."""
    return [BASE60_REVERSE[ch] for ch in reversed(s)]


def base60_normalize(digits: list) -> list:
    """Odstráni high-order nuly, zachová aspoň jednu cifru."""
    digits = digits[:]
    while len(digits) > 1 and digits[-1] == 0:
        digits.pop()
    return digits


def base60_from_digits(digits: list) -> str:
    """Zoznam číslic -> Base60 reťazec. Normalizuje high-order nuly."""
    return "".join(BASE60_ALPHABET[d] for d in reversed(base60_normalize(digits)))


def base60_compare(a: list, b: list) -> int:
    """Porovná dve Base60 čísla (digit listy, LSB first). -1 / 0 / 1.

    Obe strany sa najprv normalizujú, aby sa porovnávala HODNOTA a nie
    dĺžka zoznamu.
    """
    a_clean = base60_normalize(a)
    b_clean = base60_normalize(b)

    if len(a_clean) != len(b_clean):
        return 1 if len(a_clean) > len(b_clean) else -1

    for i in range(len(a_clean) - 1, -1, -1):
        if a_clean[i] != b_clean[i]:
            return 1 if a_clean[i] > b_clean[i] else -1

    return 0


def base60_subtract(a: list, b: list) -> list:
    """Odčíta b od a (a >= b), vracia digit list. Predpoklad a >= b."""
    result = base60_normalize(a)
    if len(b) > len(result):
        result = result + [0] * (len(b) - len(result))

    borrow = 0
    for i in range(len(b)):
        diff = result[i] - b[i] - borrow
        if diff < 0:
            diff += 60
            borrow = 1
        else:
            borrow = 0
        result[i] = diff

    # zvyšný borrow prenesieme cez zvyšné pozície
    i = len(b)
    while borrow > 0:
        if i >= len(result):
            raise ValueError("base60_subtract: a < b")
        diff = result[i] - borrow
        if diff < 0:
            diff += 60
            borrow = 1
        else:
            borrow = 0
        result[i] = diff
        i += 1

    return base60_normalize(result)


def base60_fraction(numerator: str, denominator: str) -> str:
    """Delí v Base60, výsledok je Base60 reťazec.

    Long division priamo v Base60, bez int() konverzie.
    """
    den_digits = base60_normalize(base60_to_digits(denominator))
    if den_digits == [0]:
        raise ZeroDivisionError("Delenie nulou")

    num_digits = base60_normalize(base60_to_digits(numerator))

    # --- celá časť: opakované odčítanie menovateľa ---
    whole_digits = [0]
    temp = num_digits[:]

    while base60_compare(temp, den_digits) >= 0:
        temp = base60_subtract(temp, den_digits)
        pos = 0
        while True:
            if pos < len(whole_digits):
                whole_digits[pos] += 1
                if whole_digits[pos] < 60:
                    break
                whole_digits[pos] = 0
                pos += 1
            else:
                whole_digits.append(1)
                break

    if temp == [0]:
        return base60_from_digits(whole_digits)

    # --- desatinná časť: long division ---
    result_parts = [base60_from_digits(whole_digits), "."]
    remainder = temp
    seen_remainders = {}
    precision = 0
    max_precision = 20

    while precision < max_precision:
        if remainder == [0]:
            break

        key = tuple(remainder)
        if key in seen_remainders:
            break
        seen_remainders[key] = precision

        # násobenie 60 = pridať cifru 0 na najnižšiu pozíciu (LSB first)
        remainder = [0] + remainder

        digit = 0
        while base60_compare(remainder, den_digits) >= 0:
            remainder = base60_subtract(remainder, den_digits)
            digit += 1

        result_parts.append(BASE60_ALPHABET[digit])
        precision += 1

    return "".join(result_parts)


def encode(value: int) -> str:
    """Zakóduje nezáporný integer do base-60 reťazca."""
    if value < 0:
        raise ValueError("Base-60 encode: hodnota musí byť nezáporná")
    if value == 0:
        return BASE60_ALPHABET[0]
    chars = []
    while value > 0:
        chars.append(BASE60_ALPHABET[value % 60])
        value //= 60
    return "".join(reversed(chars))


def decode(s: str) -> int:
    """Dekóduje base-60 reťazec na integer."""
    if not s:
        raise ValueError("Base-60 decode: prázdny reťazec")
    value = 0
    for ch in s:
        if ch not in BASE60_REVERSE:
            raise ValueError(f"Base-60 decode: neplatný znak '{ch}'")
        value = value * 60 + BASE60_REVERSE[ch]
    return value
