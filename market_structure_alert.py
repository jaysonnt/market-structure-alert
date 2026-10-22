#!/usr/bin/env python3
"""Paper-only market-structure scan for liquid index ETFs.

Runs on completed 5-minute bars with 15-minute context. It detects FVGs,
liquidity sweeps/runs, and filled gaps, logs every event, and emails a report.
It never places orders.
"""
from __future__ import annotations

import json
import os
import sqlite3
import sys
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from market_structure_scanner import scan

ET = ZoneInfo("America/New_York")
HERE = Path(__file__).resolve().parent
# All configuration is env-driven; nothing personal is baked in.
KEYS_DB = Path(os.environ.get("MS_KEYS_DB") or "~/Desktop/clawd/services/api_keys/data/keys.db").expanduser()
ALPACA_ENV = Path(os.environ.get("MS_ALPACA_ENV") or (Path.home() / "Desktop/options-bot/.env"))
TO = os.environ.get("MS_ALERT_TO")
LOG = HERE / "market_structure_alerts.jsonl"
SYMBOLS = ("SPY", "QQQ", "IWM", "DIA")


def key(name: str) -> str | None:
    with sqlite3.connect(KEYS_DB) as db:
        row = db.execute("SELECT value FROM keys WHERE name=?", (name,)).fetchone()
    return row[0] if row else None


def alpaca_creds() -> tuple[str, str]:
    values = {}
    with open(ALPACA_ENV) as f:
        for line in f:
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.strip().split("=", 1)
                values[k] = v
    return values["ALPACA_API_KEY"], values["ALPACA_SECRET_KEY"]


def get_json(url: str) -> dict:
    api, secret = alpaca_creds()
    req = urllib.request.Request(url, headers={
        "APCA-API-KEY-ID": api,
        "APCA-API-SECRET-KEY": secret,
    })
    with urllib.request.urlopen(req, timeout=30) as response:
        return json.load(response)


def bars(symbol: str, timeframe: str, start: datetime, end: datetime) -> list[dict]:
    start_s = start.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    end_s = end.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    url = (f"https://data.alpaca.markets/v2/stocks/{symbol}/bars"
           f"?timeframe={timeframe}&start={start_s}&end={end_s}"
           "&limit=10000&feed=iex")
    payload = get_json(url)
    out = []
    for row in payload.get("bars") or []:
        out.append({"timestamp": row.get("t"), "open": row["o"], "high": row["h"],
                    "low": row["l"], "close": row["c"], "volume": row.get("v", 0)})
    return out


def append_events(symbol: str, events: list[dict], now: datetime) -> None:
    """Append only new event identities; repeated scans must not duplicate history."""
    known: set[tuple] = set()
    if LOG.exists():
        with LOG.open() as existing:
            for line in existing:
                try:
                    row = json.loads(line)
                    known.add((row.get("symbol"), row.get("kind"), row.get("index"), row.get("trigger")))
                except json.JSONDecodeError:
                    continue
    with LOG.open("a") as f:
        for event in events:
            identity = (symbol, event.get("kind"), event.get("index"), event.get("trigger"))
            if identity in known:
                continue
            known.add(identity)
            record = {"observed_at": now.isoformat(), "symbol": symbol, **event}
            f.write(json.dumps(record, sort_keys=True) + "\n")


def render(reports: dict[str, list[dict]], now: datetime) -> str:
    lines = [
        "PAPER-ONLY MARKET STRUCTURE SCAN",
        f"{now.astimezone(ET):%Y-%m-%d %H:%M ET} · completed 5m bars · 15m context",
        "No orders are placed. Every detection is a research observation.",
        "",
    ]
    total = sum(len(v) for v in reports.values())
    if not total:
        return "\n".join(lines + ["No FVG, liquidity, or gap-fill events detected."])
    for symbol, events in reports.items():
        if not events:
            continue
        lines.append(f"{symbol} ({len(events)} events)")
        for e in events:
            lines.append(f"  {e['kind']} {e['side']} · score {e['score']} · "
                         f"15m {e['context_15m']} · confluence={e['confluence']} · {e['details']}")
        lines.append("")
    lines += [
        "These patterns are not proven probabilities. Review the logged outcomes",
        "before risking capital; this scanner is research/paper mode only.",
    ]
    return "\n".join(lines)


def send_email(text: str, now: datetime) -> str:
    api_key, sender = key("RESEND_API_KEY"), key("RESEND_FROM")
    if not api_key or not sender:
        raise RuntimeError("Resend keys missing")
    if not TO:
        raise RuntimeError("Recipient not configured; set MS_ALERT_TO")
    payload = json.dumps({
        "from": sender,
        "to": [TO],
        "subject": f"Market structure scan · {now.astimezone(ET):%b %d %H:%M ET}",
        "text": text,
    }).encode()
    req = urllib.request.Request("https://api.resend.com/emails", data=payload,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json",
                 "User-Agent": "clawd-market-structure/1.0"})
    with urllib.request.urlopen(req, timeout=30) as response:
        return str(json.load(response).get("id"))


def main() -> None:
    now = datetime.now(timezone.utc)
    if "--test" in sys.argv:
        print(send_email("TEST\n\n" + render({}, now), now))
        return
    end = now - timedelta(minutes=5)
    start = end - timedelta(days=3)
    reports = {}
    for symbol in SYMBOLS:
        five = bars(symbol, "5Min", start, end)
        fifteen = bars(symbol, "15Min", start, end)
        events = scan(five, fifteen)
        reports[symbol] = events
        append_events(symbol, events, now)
    report = render(reports, now)
    print(report)
    print("email:", send_email(report, now))


if __name__ == "__main__":
    main()
