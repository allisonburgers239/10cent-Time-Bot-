"""Fetch earnings-report history (date, time of day, EPS estimate/actual/surprise) for the large-cap
universe from Yahoo, one cached CSV per ticker in data/earnings/. Yahoo caps history at 100 events
(~25 years). Universe = top 450 US stocks by market cap from TradingView's public scanner on the
date in the file name (data/earnings/universe_YYYY-MM-DD.json) - today's survivors, so any
long-only drift is survivorship-biased; screen_earnings_events.py controls for that with a
same-stock random-date placebo.

Usage: python scripts/fetch_earnings.py [--limit N] [--refresh]
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import pandas as pd
import yfinance as yf

ROOT = Path(__file__).resolve().parent.parent
DIR = ROOT / "data" / "earnings"


def universe() -> list[tuple[str, str, float]]:
    f = sorted(DIR.glob("universe_*.json"))[-1]
    rows = json.load(open(f))
    return [(r[0], r[2], r[1]) for r in rows]


def yf_symbol(name: str) -> str:
    return name.replace(".", "-")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--refresh", action="store_true")
    a = ap.parse_args()
    uni = universe()
    if a.limit:
        uni = uni[: a.limit]
    ok = skipped = failed = 0
    for i, (name, sector, mcap) in enumerate(uni):
        out = DIR / f"{name}.csv"
        if out.exists() and not a.refresh:
            skipped += 1
            continue
        try:
            e = yf.Ticker(yf_symbol(name)).get_earnings_dates(limit=100)
            if e is None or e.empty:
                failed += 1; print(f"{name}: no data"); continue
            e = e.rename(columns={"EPS Estimate": "eps_est", "Reported EPS": "eps_act", "Surprise(%)": "surprise_pct"})
            e.index.name = "report_ts"
            e.to_csv(out)
            ok += 1
        except Exception as ex:  # noqa: BLE001
            failed += 1; print(f"{name}: {ex}")
        time.sleep(0.4)
        if (i + 1) % 50 == 0:
            print(f"{i + 1}/{len(uni)} ok {ok} skipped {skipped} failed {failed}", flush=True)
    print(f"done: ok {ok} skipped {skipped} failed {failed}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
