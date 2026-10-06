# ============================================================================
# HEXA-60 CORE™ — High-Throughput Base60 Encoding Engine
# Copyright (c) 2026 Ladislav Müller (IČO: 40189589). All rights reserved.
#
# PROPRIETARY AND CONFIDENTIAL SOFTWARE.
# Unauthorized copying, distribution, or modification of this file, via any
# medium, is strictly prohibited under applicable copyright laws and B2B EULA.
# ============================================================================

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
