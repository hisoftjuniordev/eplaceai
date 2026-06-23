"""General input validators for IBAN, amounts, dates."""
from __future__ import annotations

import re
from datetime import date


def validate_iban(iban: str) -> str:
    """Basic structural IBAN validation (length + alphanumeric)."""
    clean = iban.replace(" ", "").upper()
    if not re.match(r"^[A-Z]{2}[0-9]{2}[A-Z0-9]{11,30}$", clean):
        raise ValueError(f"Neveljaven format IBAN: {iban}")
    # mod-97 check
    rearranged = clean[4:] + clean[:4]
    numeric = "".join(str(ord(c) - 55) if c.isalpha() else c for c in rearranged)
    if int(numeric) % 97 != 1:
        raise ValueError(f"IBAN kontrolna vsota ni veljavna: {iban}")
    return clean


def validate_positive_amount(value: float, field: str = "znesek") -> float:
    if value < 0:
        raise ValueError(f"{field} ne sme biti negativen")
    if value > 999_999.99:
        raise ValueError(f"{field} presega maksimalni dovoljeni znesek")
    return value


def validate_date_range(date_from: date, date_to: date) -> None:
    if date_to < date_from:
        raise ValueError("date_to mora biti >= date_from")
