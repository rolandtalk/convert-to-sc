from __future__ import annotations

from bs4 import BeautifulSoup
import requests


def _as_float(v: str) -> float | None:
    try:
        return float(v.replace(",", "").strip())
    except Exception:
        return None


def scrape_sctr_list(url: str, limit: int = 300) -> list[dict]:
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    # StockCharts page layout can change. We search for rows with a likely symbol + rank pattern.
    rows: list[dict] = []
    for tr in soup.select("tr"):
        cells = [c.get_text(" ", strip=True) for c in tr.select("td")]
        if len(cells) < 2:
            continue
        rank = None
        symbol = None
        sctr = None

        if cells[0].isdigit() and len(cells[1]) <= 8:
            rank = int(cells[0])
            symbol = cells[1].upper()
            if len(cells) >= 3:
                sctr = _as_float(cells[2])

        if rank is None or symbol is None:
            continue
        if not symbol.replace("-", "").replace(".", "").isalnum():
            continue

        rows.append({"rank": rank, "symbol": symbol, "sctr": sctr})
        if len(rows) >= limit:
            break

    if not rows:
        raise RuntimeError("Failed to parse SCTR symbols from source page. Layout may have changed.")

    rows.sort(key=lambda x: x["rank"])
    return rows[:limit]
