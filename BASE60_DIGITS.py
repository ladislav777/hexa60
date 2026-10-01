# ============================================
# BASE60_DIGITS.py – spätná kompatibilita (legacy)
# ============================================
# Tento súbor bol pôvodne zdrojom pravdy pre abecedu, ale obsahoval iba
# 59 znakov (chýbal '-') a nezhodoval sa s README. Pravdivým zdrojom pravdy
# je teraz hexa60.ALPHABET – 60 unikátnych znakov.
#
# Nový kód používajte hexa60; tieto konštanty zostávajú pre starších klientov.

from hexa60 import ALPHABET, BASE, LOOKUP

# Zdedený názov; hodnota sa rovná ALPHABET.
BASE60_DIGITS = ALPHABET
