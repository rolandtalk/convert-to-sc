from __future__ import annotations

from typing import Any

import numpy as np
import yfinance as yf


def _pct(curr: float, prev: float) -> float | None:
    if prev is None or prev == 0 or np.isnan(prev) or np.isnan(curr):
        return None
    return (curr - prev) / prev * 100


def _rsi_14(closes) -> float | None:
    if len(closes) < 15:
        return None
    deltas = np.diff(closes)
    gains = np.where(deltas > 0, deltas, 0)
    losses = np.where(deltas < 0, -deltas, 0)
    avg_gain = np.mean(gains[-14:])
    avg_loss = np.mean(losses[-14:])
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return float(100 - (100 / (1 + rs)))


def compute_metrics(symbol: str) -> dict[str, Any]:
    ticker = yf.Ticker(symbol)
    hist = ticker.history(period="6mo", interval="1d", auto_adjust=False)
    if hist.empty or "Close" not in hist:
        return {}

    closes = hist["Close"].dropna().to_numpy()
    if len(closes) < 61:
        return {}

    current = float(closes[-1])
    return {
        "perf_1d": _pct(current, float(closes[-2])) if len(closes) >= 2 else None,
        "perf_5d": _pct(current, float(closes[-6])) if len(closes) >= 6 else None,
        "perf_20d": _pct(current, float(closes[-21])) if len(closes) >= 21 else None,
        "perf_60d": _pct(current, float(closes[-61])) if len(closes) >= 61 else None,
        "rsi_14": _rsi_14(closes),
    }
