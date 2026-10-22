# market-structure-alert

Paper-only market-structure detectors for liquid index ETFs (SPY, QQQ, IWM, DIA):
a scanner that finds fair-value gaps, liquidity sweeps/runs, and gap fills on
completed 5-minute bars with 15-minute context, an alert runner that logs every
event and emails a report, and the systemd user units that schedule it during
market hours.

It never places orders — every detection is a research observation, and the
patterns are not proven probabilities. Score outcomes against future bars
before treating anything as a strategy.

## What's here

- `market_structure_scanner.py` — pure, stdlib-only detectors operating on
  completed OHLCV bars. Functions take bar dicts in, return facts out.
- `market_structure_alert.py` — the runner: pulls recent Alpaca/iex bars for the
  symbol set, scans them, appends new event identities to a JSONL log
  (repeated scans never duplicate history), and emails the report via the
  Resend API. `--test` sends a test email only.
- `test_market_structure_scanner.py` — pytest suite covering FVG
  detection/omission-after-fill, sweep vs. run, gap-fill direction, and the
  15m-confluence scoring.
- `market-structure-alert.service` / `.timer` — systemd user units running the
  scan in five-minute windows through the regular session.

## Configuration (all env-driven, nothing baked in)

| Variable | Purpose |
|---|---|
| `MS_ALERT_TO` | Recipient email for reports (required for delivery) |
| `MS_KEYS_DB` | SQLite keys DB holding `RESEND_API_KEY` / `RESEND_FROM` |
| `MS_ALPACA_ENV` | dotenv file holding Alpaca data credentials |

All three default to the paths this tool uses inside my home lab console; they
are read at runtime, so nothing sensitive lives in the repo.

## Run the tests

```bash
python3 -m pytest test_market_structure_scanner.py
```

## Schedule it (user units)

```bash
cp market-structure-alert.service market-structure-alert.timer \
   ~/.config/systemd/user/
systemctl --user enable --now market-structure-alert.timer
```

## Status

Extracted from my private operations console. Part of an ongoing series of
projects being published from that console.

## License

MIT — see [LICENSE](LICENSE).
