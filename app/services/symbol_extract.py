from __future__ import annotations

from app.services.ticker_universe import extract_valid_symbols


def extract_symbols(text: str) -> list[str]:
    return extract_valid_symbols(text)
