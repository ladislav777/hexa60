"""
Base60Tensor -- batch aritmetika v base-60 cez PyTorch.

Oproti prvemu navrhu:
  * konverzia string->cislo je VEKTORIZOVANA (numpy lookup), nie Python smycka
  * scitanie/odcitanie/nasobenie robia DIGITOVU aritmetiku s prenasakom
  * ziadne modulo namiesto scitania, ziadne tiche orezy, ziadne .get(ch, 0)
  * zlyhanie je vzdy chyba, nikdy ticha substitúcia

Pozor na kapacitu: hodnoty drzime ako [batch, max_digits] cislic (0-59),
nie ako int64. Cislice su neobmedzene dlhe; obmedzeny je len batch.
"""
from __future__ import annotations

import numpy as np
import torch

from hexa60 import ALPHABET, BASE

DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")

# ---------------------------------------------------------------- tabulky
_ASCII = np.frombuffer(ALPHABET.encode("ascii"), dtype=np.uint8)
_CHAR_TO_DIGIT = np.full(256, 255, dtype=np.uint8)
_CHAR_TO_DIGIT[_ASCII] = np.arange(BASE, dtype=np.uint8)
_DIGIT_TO_CHAR = np.array(list(ALPHABET), dtype="<U1")

_ZERO_CH = ALPHABET[0]


class Base60ValueError(ValueError):
    """Neplatny vstup -- vzdy hlasne, nikdy ticho."""


def _strings_to_rows(strings, max_digits: int) -> np.ndarray:
    """[batch] stringov -> [batch, max_digits] uint8 cislic, MSB first."""
    if max_digits < 1:
        raise Base60ValueError(f"max_digits musi byt >= 1, je {max_digits}")
    strings = list(strings)
    if not strings:
        return np.zeros((0, max_digits), dtype=np.uint8)
    if not all(isinstance(s, str) for s in strings):
        raise Base60ValueError("vsetky vstupy musia byt str")

    if not all(s.isascii() for s in strings):
        raise Base60ValueError("vstup obsahuje ne-ASCII znak")
    if any(len(s) == 0 for s in strings):
        raise Base60ValueError("prazdny retazec nie je platne cislo")
    too_long = [s for s in strings if len(s) > max_digits]
    if too_long:
        raise Base60ValueError(
            f"vstup ma viac nez {max_digits} cislic (napr. {too_long[0]!r}); "
            f"zvysite max_digits -- tiche orezanie by vratilo nespravne cislo"
        )

    padded = "".join(s.rjust(max_digits, _ZERO_CH) for s in strings)
    arr = np.frombuffer(padded.encode("ascii"), dtype=np.uint8).reshape(
        len(strings), max_digits
    )
    digits = _CHAR_TO_DIGIT[arr]
    bad = digits == 255
    if bad.any():
        chars = sorted({chr(c) for c in arr[bad]})
        raise Base60ValueError(f"neplatne znaky v base-60: {chars}")
    return digits


def _rows_to_strings(t: torch.Tensor) -> list[str]:
    """[batch, max_digits] cislic -> list stringov (bez veducich nul)."""
    arr = t.detach().to("cpu").numpy().astype(np.int64)
    n, width = arr.shape
    if n == 0:
        return []
    is_zero = arr == 0
    has_nz = ~is_zero.all(axis=1)
    # CHYBA: `is_zero.argmax(...)` hladalo PRVU NULU, nie prvú nenulu.
    # argmax na booleovom poli vracia index prveho True, takze pre
    # [14,48,4,5,26,24,57,0] to vracalo index 7 a vysledok bol "0".
    # Potrebujeme index prvej NENULOVE cifry -> argmax na ~is_zero.
    first = np.where(has_nz, (~is_zero).argmax(axis=1), width - 1)
    chars = _DIGIT_TO_CHAR[arr]
    out = []
    for row, start in zip(chars, first):
        s = "".join(row[start:])
        out.append(s if s else _ZERO_CH)
    return out


def _rows_to_tensor(rows: np.ndarray) -> torch.Tensor:
    return torch.from_numpy(rows.astype(np.int64)).to(DEVICE)



# ---------------------------------------------------------------- API
class Base60Tensor:
    """Batch aritmetika v base-60."""

    @staticmethod
    def encode(values, max_digits: int = 8) -> torch.Tensor:
        """Zoznam base-60 stringov -> tenzor [batch, max_digits] cislic."""
        return _rows_to_tensor(_strings_to_rows(values, max_digits))

    @staticmethod
    def decode(tensor: torch.Tensor) -> list[str]:
        """Tenzor [batch, max_digits] cislic -> zoznam stringov."""
        if tensor.ndim != 2:
            raise Base60ValueError(
                f"ocakavam 2D [batch, digits], je {tuple(tensor.shape)}"
            )
        arr = tensor.detach().to("cpu").numpy()
        if arr.dtype.kind not in "iu":
            raise Base60ValueError(f"cislo musi byt integer, je {arr.dtype}")
        if arr.size and (arr.min() < 0 or arr.max() >= BASE):
            raise Base60ValueError(
                f"cisla musia byt v 0..{BASE - 1}, "
                f"dostal som min={arr.min()} max={arr.max()}"
            )
        return _rows_to_strings(tensor)

    @staticmethod
    def _align(a_list, b_list, max_digits):
        a = _strings_to_rows(a_list, max_digits)
        b = _strings_to_rows(b_list, max_digits)
        if a.shape[0] != b.shape[0]:
            raise Base60ValueError(
                f"nerovnake dazky batchov: {a.shape[0]} vs {b.shape[0]}"
            )
        return _rows_to_tensor(a), _rows_to_tensor(b)

    @staticmethod
    def add(a_list, b_list, max_digits: int = 8, check: bool = True) -> list[str]:
        """a + b, digitovo s prenasakom."""
        ta, tb = Base60Tensor._align(a_list, b_list, max_digits)
        out = torch.zeros_like(ta)
        carry = torch.zeros(ta.shape[0], dtype=torch.int64, device=ta.device)
        for j in range(max_digits - 1, -1, -1):
            s = ta[:, j] + tb[:, j] + carry
            out[:, j] = s % BASE
            carry = s // BASE
        if check and bool((carry != 0).any()):
            raise Base60ValueError(
                "pretecenie: vysledok ma viac nez max_digits cislic"
            )
        return _rows_to_strings(out)

    @staticmethod
    def subtract(a_list, b_list, max_digits: int = 8, check: bool = True) -> list[str]:
        """a - b, digitovo s pozickou. Ziadne zaporne cisla."""
        ta, tb = Base60Tensor._align(a_list, b_list, max_digits)
        out = torch.zeros_like(ta)
        borrow = torch.zeros(ta.shape[0], dtype=torch.int64, device=ta.device)
        for j in range(max_digits - 1, -1, -1):
            d = ta[:, j] - tb[:, j] - borrow
            borrow = (d < 0).to(torch.int64)
            out[:, j] = d + borrow * BASE
        if check and bool((borrow != 0).any()):
            raise Base60ValueError(
                "vysledok je zaporny; zapornych cisel nie je podpora"
            )
        return _rows_to_strings(out)

    @staticmethod
    def multiply(a_list, b_list, max_digits: int = 8, check: bool = True) -> list[str]:
        """a * b, dlhe nasobenie na cisliciach (konvolucia + prenos)."""
        ta, tb = Base60Tensor._align(a_list, b_list, max_digits)
        n, w = ta.shape
        raw = torch.zeros(n, 2 * w - 1, dtype=torch.int64, device=ta.device)
        for i in range(w):
            for j in range(w):
                # _align dava MSB first: exponent cisla na indexe i je
                # (w-1-i). Pri nasobeni sa exponenty scitavaju:
                #     (w-1-i) + (w-1-j) = 2*w-2-i-j
                # V raw preto POVAZUJEME index k ako exponent (LSB first),
                # teda raw[exponent]. Puvodny kod pouzival
                # `raw[:, i:i+w] += ta[:, i:i+1] * tb`, co daval poziciu
                # i+j -- to je posun k LSB a pre MSB first nesedelo.
                raw[:, 2 * w - 2 - i - j] += ta[:, i] * tb[:, j]
        # Prenos ide od LSB (najmensi exponent, najvacsi vysledny vplyv)
        # smerom k MSB. raw je LSB first, takze index rastie.
        carry = torch.zeros(n, dtype=torch.int64, device=ta.device)
        for j in range(0, 2 * w - 1):
            s = raw[:, j] + carry
            raw[:, j] = s % BASE
            carry = s // BASE
        # raw je LSB first: raw[k] ma exponent k (lebo exponent produktu
        # ta[i]*tb[j] je (w-1-i)+(w-1-j) = 2*w-2-i-j a ukladame ho na
        # index 2*w-2-i-j). Dolnych w cislic je preto raw[:, :w].
        #
        # _rows_to_strings ocakava MSB first, preto lo OTOACIME.
        # Zvysok raw[:, w:] musi byt nulovy, inak ma vysledok viac nez
        # max_digits cislic a nesmie sa potichu orezat.
        lo, hi = raw[:, :w].flip(-1), raw[:, w:]
        if check and bool(((carry != 0) | (hi != 0).any(dim=1)).any()):
            raise Base60ValueError(
                "pretecenie: vysledok ma viac nez max_digits cislic"
            )
        return _rows_to_strings(lo)

    @staticmethod
    def compare(a_list, b_list, max_digits: int = 8) -> list[int]:
        """-1 / 0 / 1 podla a < b, a == b, a > b."""
        ta, tb = Base60Tensor._align(a_list, b_list, max_digits)
        out = []
        for i in range(ta.shape[0]):
            av, bv = ta[i].tolist(), tb[i].tolist()
            out.append(0 if av == bv else (1 if av > bv else -1))
        return out
