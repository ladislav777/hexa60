# ============================================
# base60.py – spätná kompatibilita (legacy)
# ============================================
# Tento súbor bol pôvodne DUPLICITA s vlastnou 60-znakovou abecedou, ktorá
# obsahovala '+' (v rozpore s tvrdením "identifier-safe") a blokovala po
# 3 bajtoch. Výstup bol NEEZHODNÝ s BASE60_BINAR pre tie isté vstupné dáta:
#
#   base60.py     : b"Hello world" -> 0M_yz0Yw-z0cEFE07jU
#   BASE60_BINAR  : b"Hello world" -> 0P5_C0abTN0e6aL07zJ
#
# Preto sa odstránil. Kód sa deleguje na hexa60 (jediný zdroj pravdy).
# Nový kód používajte cez `import hexa60`; konštanty zostávajú kvôli starým
# importom, ich hodnoty sú teraz štandardné.

from hexa60 import ALPHABET, BASE, LOOKUP
from hexa60 import base60_to_bytes, bytes_to_base60

# Zdedené mená; hodnoty sa rovnajú štandardu.
BASE60_ALPHABET = ALPHABET

__all__ = [
    "BASE60_ALPHABET",
    "BASE",
    "LOOKUP",
    "int_to_base60",
    "base60_to_int",
    "bytes_to_base60",
    "base60_to_bytes",
]

# Nasledujúce dve funkcie sú definované v BASE60_CORE (legacy int helper).
from BASE60_CORE import base60_to_int, int_to_base60  # noqa: E402
