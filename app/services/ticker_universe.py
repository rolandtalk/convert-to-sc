from __future__ import annotations

from functools import lru_cache
from pathlib import Path
import re


DATA_DIR = Path(__file__).resolve().parent.parent / "data"
TICKER_FILE = DATA_DIR / "us_tickers.txt"
TOKEN_PATTERN = re.compile(r"\b[A-Z]{1,5}(?:[.\- ][A-Z])?\b")

_WORD_DENYLIST = {
    "A",
    "AN",
    "AND",
    "ARE",
    "AS",
    "AT",
    "ABOVE",
    "BE",
    "BELOW",
    "BUY",
    "BUT",
    "BY",
    "CASH",
    "CHART",
    "FOR",
    "FROM",
    "HOLD",
    "IF",
    "IN",
    "INFO",
    "INTO",
    "IS",
    "IT",
    "KEEP",
    "LINE",
    "LOOK",
    "NAME",
    "NAMES",
    "NEXT",
    "NOT",
    "OF",
    "ON",
    "OR",
    "OUT",
    "REVIEW",
    "SC",
    "SEE",
    "SELL",
    "SWING",
    "TEXT",
    "THAT",
    "THE",
    "THESE",
    "THIS",
    "TO",
    "TOTAL",
    "WATCH",
    "WATCHING",
    "WEEK",
    "WITH",
}


def normalize_symbol(token: str) -> str:
    raw = re.sub(r"[^A-Z0-9.\- ]", "", token.upper()).strip()
    if not raw:
        return ""

    raw = raw.replace("-", ".").replace(" ", ".")
    raw = re.sub(r"\.{2,}", ".", raw).strip(".")
    return raw


@lru_cache(maxsize=1)
def load_ticker_universe() -> frozenset[str]:
    if not TICKER_FILE.exists():
        return frozenset()

    return frozenset(
        line.strip().upper()
        for line in TICKER_FILE.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    )


def is_valid_symbol(token: str) -> bool:
    normalized = normalize_symbol(token)
    if not normalized or normalized in _WORD_DENYLIST:
        return False
    return normalized in load_ticker_universe()


def validate_symbol_candidates(candidates: list[str]) -> list[str]:
    valid: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        normalized = normalize_symbol(candidate)
        if not normalized or normalized in seen:
            continue
        if not is_valid_symbol(normalized):
            continue
        seen.add(normalized)
        valid.append(normalized)
    return valid


def extract_valid_symbols(text: str) -> list[str]:
    candidates = [normalize_symbol(match) for match in TOKEN_PATTERN.findall(text.upper())]
    return validate_symbol_candidates(candidates)
