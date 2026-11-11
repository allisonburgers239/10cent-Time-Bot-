"""Daily adjusted open/close for the earnings universe + SPY, cached to data/earnings/prices.pkl
(dict with 'open' and 'close' DataFrames, tz-naive dates, columns = TradingView names).
Usage: python scripts/fetch_earnings_prices.py
"""
from __future__ import annotations

import pickle
import sys
from pathlib import Path

import pandas as pd
import yfinance as yf

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fetch_earnings import DIR, universe, yf_symbol  # noqa: E402


def main() -> int:
    names = [n for n, _, _ in universe()] + ["SPY"]
    syms = [yf_symbol(n) for n in names]
    opens, closes = [], []
    for i in range(0, len(syms), 100):
        chunk = syms[i:i + 100]
        raw = yf.download(chunk, period="max", interval="1d", auto_adjust=True, progress=False, threads=True)
        opens.append(raw["Open"]); closes.append(raw["Close"])
        print(f"{i + len(chunk)}/{len(syms)}", flush=True)
    o = pd.concat(opens, axis=1); c = pd.concat(closes, axis=1)
    back = {yf_symbol(n): n for n in names}
    o.columns = [back.get(x, x) for x in o.columns]; c.columns = [back.get(x, x) for x in c.columns]
    o.index = pd.DatetimeIndex(o.index).tz_localize(None); c.index = pd.DatetimeIndex(c.index).tz_localize(None)
    pickle.dump({"open": o, "close": c}, open(DIR / "prices.pkl", "wb"))
    print(f"saved {c.shape[1]} symbols, {c.index[0].date()} -> {c.index[-1].date()}, {c.notna().sum().sum():,} closes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
