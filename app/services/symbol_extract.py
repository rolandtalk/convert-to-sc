from __future__ import annotations

import re


_STOP_WORDS = {
    "A",
    "AN",
    "AND",
    "ARE",
    "AS",
    "AT",
    "BE",
    "BUT",
    "BY",
    "CHART",
    "FOR",
    "FROM",
    "HOLD",
    "IF",
    "IN",
    "INTO",
    "IS",
    "IT",
    "KEEP",
    "LOOK",
    "NEXT",
    "NOT",
    "OF",
    "ON",
    "OR",
    "OUT",
    "REVIEW",
    "SC",
    "SEE",
    "TEXT",
    "THAT",
    "THE",
    "THESE",
    "THIS",
    "TO",
    "WATCH",
    "WATCHING",
    "WEEK",
    "WITH",
}


def extract_symbols(text: str) -> list[str]:
    matches = re.findall(r"\b[A-Z]{1,5}\b", text.upper())
    symbols: list[str] = []
    seen: set[str] = set()
    for match in matches:
        if match in _STOP_WORDS:
            continue
        if match in seen:
            continue
        seen.add(match)
        symbols.append(match)
    return symbols
