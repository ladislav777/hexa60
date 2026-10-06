# ============================================================================
# HEXA-60 CORE™ — High-Throughput Base60 Encoding Engine
# Copyright (c) 2026 Ladislav Müller (IČO: 40189589). All rights reserved.
#
# PROPRIETARY AND CONFIDENTIAL SOFTWARE.
# Unauthorized copying, distribution, or modification of this file, via any
# medium, is strictly prohibited under applicable copyright laws and B2B EULA.
# ============================================================================

# ============================================
# BASE60_BINAR.py – spätná kompatibilita (legacy)
# ============================================
# Pôvodná implementácia kódovala po 3-bajtových blokoch (3 -> 5 znakov, pomer
# 1,667) a ticho ignorovala neplatné znaky aj neplatné dĺžky, čím mohla
# vrátiť poškodené dáta bez varovania.
#
# Nový štandard je hexa60: bloky 8 -> 11 znakov (pomer 1,375), striktná
# validácia a výnimky LengthError / InvalidCharacterError.
#
# bytes_to_base60 / base60_to_bytes sú aliasy nového chunked API. Výstup je
# TERAZ INÝ FORMÁT než pôvodný 3 -> 5 – používajte ich len pre čerstvé dáta,
# nie na dekódovanie starých záznamov.

# Legacy API.
#
# NOTE: bytes_to_base60 is the bulk encoder per the HEXA60 spec, and the chunked
# wire format is now 8 -> 11 chars (was 3 -> 5). These legacy names therefore
# produce/consume the bulk format and cannot read the historical 3 -> 5 records.
from hexa60 import (
    BASE,
    TAIL_CHARS,
    base60_to_bytes,
    base60_to_bytes_lenient,
    bytes_to_base60,
    decode_chunked,
    encode_chunked,
)

__all__ = [
    "bytes_to_base60",
    "base60_to_bytes",
    "base60_to_bytes_lenient",
    "encode_chunked",
    "decode_chunked",
    "BASE",
    "TAIL_CHARS",
]

if __name__ == "__main__":
    for stream in (__import__("sys").stdout,):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except (ValueError, OSError):
                pass

    print("=" * 50)
    print("BASE60_BINAR – SELF-TEST (delegated to hexa60)")
    print("=" * 50)

    for text in ["A", "Hello", "Kosice", "Bratislava", "Vortex", "Slovensko 🦅"]:
        raw = text.encode("utf-8")
        enc = encode_chunked(raw)
        ok = decode_chunked(enc, strict=True) == raw
        assert ok, f"Round-trip zlyhal pre {text!r}"
        print(f"  {text!r:>25} -> {enc!r:>30}  OK")

    velke = bytes(range(256)) * 782  # 200 192 bajtov
    enc = encode_chunked(velke)
    assert decode_chunked(enc, strict=True) == velke
    print(f"\n  {len(velke)} bajtov -> {len(enc)} znakov, round-trip OK")
    print("=" * 50)
    print("VÝSLEDOK: Všetko prešlo.")

