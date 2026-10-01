# ============================================
# BASE60_CORE.py – spätná kompatibilita (legacy)
# ============================================
# Tento modul bol pôvodne zdrojom int <-> text konverzie. Teraz používa
# abecedu z hexa60 (60 znakov) namiesto pôvodných 59.
#
# Tieto funkcie NIE SÚ súčasťou špecifikácie HEXA60 – bulk formát má vlastné
# API (hexa60.encode / hexa60.decode). Používajte ich len pri práci so starými
# uloženými hodnotami.

from hexa60 import ALPHABET, BASE, LOOKUP

BASE60_DIGITS = ALPHABET

__all__ = ["int_to_base60", "base60_to_int", "BASE60_DIGITS", "BASE"]


def int_to_base60(n: int) -> str:
    """Integer → base-60 string (nezáporné čísla)."""
    if n < 0:
        raise ValueError("Len nezáporné čísla")
    if n == 0:
        return ALPHABET[0]

    result = []
    while n > 0:
        n, idx = divmod(n, BASE)
        result.append(ALPHABET[idx])
    return "".join(reversed(result))


def base60_to_int(s: str) -> int:
    """Base-60 string → integer. Vyhadzuje ValueError pri neznámom znaku."""
    if not s:
        raise ValueError("Prázdny reťazec")
    result = 0
    for ch in s:
        if ch not in LOOKUP:
            raise ValueError(f"Neplatný znak v Base-60: {ch!r}")
        result = result * BASE + LOOKUP[ch]
    return result


# ============================================
# SELF-TEST
# ============================================
if __name__ == "__main__":
    import sys

    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except (ValueError, OSError):
            pass

    print("=" * 50)
    print("BASE60_CORE – SELF-TEST")
    print("=" * 50)
    ok = True
    for i in [0, 1, 59, 60, 3600, 123456789]:
        s = int_to_base60(i)
        back = base60_to_int(s)
        status = "OK" if back == i else "FAIL"
        if back != i:
            ok = False
        print(f"  {i:>10} -> {s:>15} -> {back:>10}  {status}")
    print("=" * 50)
    print("VÝSLEDOK:", "Všetko prešlo" if ok else "Niečo zlyhalo")
