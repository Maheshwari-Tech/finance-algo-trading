from __future__ import annotations

import re

_E164 = re.compile(r"^\+[1-9]\d{7,14}$")


def normalize_mobile(raw: str, default_country_code: str) -> str:
    """Return E.164 (e.g. +<country><number>). Accepts local 10-digit numbers, country-prefixed digits and +country forms."""
    cleaned = re.sub(r"[\s\-().]", "", raw or "")
    if cleaned.startswith("+"):
        candidate = cleaned
    elif cleaned.startswith("00"):
        candidate = "+" + cleaned[2:]
    elif len(cleaned) == 10:
        candidate = f"+{default_country_code}{cleaned}"
    else:
        candidate = "+" + cleaned
    if not _E164.match(candidate):
        raise ValueError("Enter a valid mobile number")
    return candidate
