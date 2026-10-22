"""Paper-only market-structure detectors for liquid index ETFs.

The detectors intentionally operate on completed OHLCV bars and return facts,
not trade orders. They are suitable for research alerts and must be scored
against future bars before being treated as a strategy.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Iterable, Mapping, Any


@dataclass(frozen=True)
class Pattern:
    kind: str
    side: str
    index: int
    low: float
    high: float
    trigger: float
    score: int
    details: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _f(bar: Mapping[str, Any], key: str) -> float:
    return float(bar[key])


def _atr(bars: list[Mapping[str, Any]], end: int, period: int = 14) -> float:
    start = max(1, end - period + 1)
    trs = []
    for i in range(start, end + 1):
        prev = _f(bars[i - 1], "close")
        trs.append(max(_f(bars[i], "high") - _f(bars[i], "low"),
                       abs(_f(bars[i], "high") - prev),
                       abs(_f(bars[i], "low") - prev)))
    return sum(trs) / len(trs) if trs else 0.0


def detect_fvgs(bars: Iterable[Mapping[str, Any]], min_gap_atr: float = 0.10) -> list[Pattern]:
    """Find three-candle fair-value gaps that remain unfilled at detection."""
    rows = list(bars)
    out: list[Pattern] = []
    for i in range(2, len(rows)):
        left, mid, right = rows[i - 2], rows[i - 1], rows[i]
        atr = _atr(rows, i)
        if atr <= 0:
            continue
        if _f(right, "low") > _f(left, "high"):
            low, high, side = _f(left, "high"), _f(right, "low"), "bullish"
        elif _f(right, "high") < _f(left, "low"):
            low, high, side = _f(right, "high"), _f(left, "low"), "bearish"
        else:
            continue
        if high - low < atr * min_gap_atr:
            continue
        later = rows[i + 1:]
        filled = any(_f(b, "low") <= high and _f(b, "high") >= low for b in later)
        if filled:
            continue
        body = abs(_f(mid, "close") - _f(mid, "open"))
        score = 60 + min(25, int((high - low) / atr * 20)) + (10 if body >= atr * 0.5 else 0)
        out.append(Pattern("fvg", side, i, low, high, _f(right, "close"), min(score, 95),
                           f"gap={high-low:.4f}; atr={atr:.4f}"))
    return out


def detect_liquidity_events(
    bars: Iterable[Mapping[str, Any]], lookback: int = 20, tolerance: float = 0.0005
) -> list[Pattern]:
    """Find stop-runs (sweeps) and closes beyond prior liquidity (runs)."""
    rows = list(bars)
    out: list[Pattern] = []
    for i in range(lookback, len(rows)):
        b = rows[i]
        prior_high = max(_f(x, "high") for x in rows[i - lookback:i])
        prior_low = min(_f(x, "low") for x in rows[i - lookback:i])
        close, high, low = _f(b, "close"), _f(b, "high"), _f(b, "low")
        atr = _atr(rows, i)
        if atr <= 0:
            continue
        if high > prior_high * (1 + tolerance) and close < prior_high:
            out.append(Pattern("liquidity_sweep", "bearish", i, prior_high, high, close,
                               70, f"prior_high={prior_high:.4f}; rejection={high-close:.4f}"))
        elif low < prior_low * (1 - tolerance) and close > prior_low:
            out.append(Pattern("liquidity_sweep", "bullish", i, low, prior_low, close,
                               70, f"prior_low={prior_low:.4f}; rejection={close-low:.4f}"))
        elif close > prior_high and close - _f(b, "open") >= atr * 0.25:
            out.append(Pattern("liquidity_run", "bullish", i, prior_high, high, close,
                               65, f"breakout={close-prior_high:.4f}; atr={atr:.4f}"))
        elif close < prior_low and _f(b, "open") - close >= atr * 0.25:
            out.append(Pattern("liquidity_run", "bearish", i, low, prior_low, close,
                               65, f"breakdown={prior_low-close:.4f}; atr={atr:.4f}"))
    return out


def detect_gap_fills(bars: Iterable[Mapping[str, Any]], min_gap_pct: float = 0.002) -> list[Pattern]:
    """Find regular-session gaps and report only those that later filled."""
    rows = list(bars)
    out: list[Pattern] = []
    for i in range(1, len(rows)):
        prev, b = rows[i - 1], rows[i]
        prev_close, open_ = _f(prev, "close"), _f(b, "open")
        gap_pct = (open_ / prev_close) - 1 if prev_close else 0
        if abs(gap_pct) < min_gap_pct:
            continue
        filled = (_f(b, "low") <= prev_close) if gap_pct > 0 else (_f(b, "high") >= prev_close)
        if not filled:
            continue
        out.append(Pattern("gap_fill", "bearish" if gap_pct > 0 else "bullish", i,
                           min(open_, prev_close), max(open_, prev_close), prev_close,
                           55, f"gap_pct={gap_pct*100:.2f}%"))
    return out


def scan(bars_5m: Iterable[Mapping[str, Any]], bars_15m: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Return 5m events annotated with a simple 15m directional context."""
    five = list(bars_5m)
    fifteen = list(bars_15m)
    events = detect_fvgs(five) + detect_liquidity_events(five) + detect_gap_fills(five)
    context = "neutral"
    if len(fifteen) >= 2:
        context = "bullish" if _f(fifteen[-1], "close") >= _f(fifteen[-2], "close") else "bearish"
    result = []
    for event in events:
        row = event.as_dict()
        row["context_15m"] = context
        row["confluence"] = event.side == context
        row["score"] = min(100, event.score + (10 if row["confluence"] else 0))
        result.append(row)
    return sorted(result, key=lambda x: (x["index"], -x["score"]))
