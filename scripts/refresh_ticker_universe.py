from __future__ import annotations

from pathlib import Path
from urllib.request import urlopen
import json


SOURCES = {
    "nasdaq": "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt",
    "other": "https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt",
}

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "app" / "data"
TICKER_FILE = DATA_DIR / "us_tickers.txt"
META_FILE = DATA_DIR / "us_tickers.meta.json"


def _read_pipe_lines(url: str) -> list[list[str]]:
    with urlopen(url, timeout=60) as response:
        payload = response.read().decode("utf-8", errors="replace")
    rows = []
    for line in payload.splitlines():
        if not line or line.startswith("File Creation Time") or line.startswith("Symbol|Security Name|"):
            continue
        if line.startswith("ACT Symbol|Security Name|"):
            continue
        rows.append(line.split("|"))
    return rows


def _collect_symbols() -> list[str]:
    symbols: set[str] = set()

    for row in _read_pipe_lines(SOURCES["nasdaq"]):
        symbol = row[0].strip().upper()
        test_issue = row[3].strip().upper() if len(row) > 3 else ""
        if symbol and test_issue != "Y":
            symbols.add(symbol)

    for row in _read_pipe_lines(SOURCES["other"]):
        symbol = row[0].strip().upper()
        exchange = row[2].strip().upper() if len(row) > 2 else ""
        test_issue = row[6].strip().upper() if len(row) > 6 else ""
        if not symbol or test_issue == "Y":
            continue
        if exchange not in {"N", "A", "P", "V", "Z"}:
            continue
        symbols.add(symbol)

    return sorted(symbols)


def main() -> None:
    symbols = _collect_symbols()
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    TICKER_FILE.write_text("\n".join(symbols) + "\n", encoding="utf-8")
    META_FILE.write_text(
        json.dumps(
            {
                "sources": SOURCES,
                "count": len(symbols),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"Saved {len(symbols)} symbols to {TICKER_FILE}")


if __name__ == "__main__":
    main()
