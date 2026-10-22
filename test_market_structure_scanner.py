from market_structure_scanner import (
    detect_fvgs, detect_gap_fills, detect_liquidity_events, scan,
)


def bar(o, h, l, c, v=1000):
    return {"open": o, "high": h, "low": l, "close": c, "volume": v}


def test_bullish_fvg_is_detected_and_unfilled():
    rows = [bar(100, 101, 99, 100), bar(100.5, 104, 100.5, 103), bar(103, 105, 102, 104)]
    events = detect_fvgs(rows)
    assert len(events) == 1
    assert events[0].kind == "fvg"
    assert events[0].side == "bullish"


def test_fvg_is_omitted_after_fill():
    rows = [bar(100, 101, 99, 100), bar(100.5, 104, 100.5, 103), bar(103, 105, 102, 104), bar(103, 104, 100, 101)]
    assert detect_fvgs(rows) == []


def test_sweep_and_run_are_distinguished():
    rows = [bar(100, 101, 99, 100) for _ in range(20)]
    rows += [bar(100, 102, 99.8, 100.5), bar(100.5, 103, 100.4, 102.5)]
    events = detect_liquidity_events(rows)
    assert any(x.kind == "liquidity_sweep" for x in events)
    assert any(x.kind == "liquidity_run" for x in events)


def test_gap_fill_reports_direction():
    rows = [bar(100, 101, 99, 100), bar(103, 104, 99.5, 100.5)]
    events = detect_gap_fills(rows)
    assert len(events) == 1
    assert events[0].kind == "gap_fill"
    assert events[0].side == "bearish"


def test_scan_adds_15m_context_and_confluence():
    five = [bar(100, 101, 99, 100), bar(100.5, 104, 100.5, 103), bar(103, 105, 102, 104)]
    fifteen = [bar(100, 101, 99, 100), bar(100, 103, 99.5, 102)]
    events = scan(five, fifteen)
    assert events[0]["context_15m"] == "bullish"
    assert events[0]["confluence"] is True
    assert events[0]["score"] > events[0]["score"] - 10
