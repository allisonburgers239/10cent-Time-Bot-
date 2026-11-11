"""Earnings histories + prices for 'fallen' stocks: removed from the S&P 500 since 2000 and not in
today's top-450 universe (data/earnings/fallen_sp500_removed_2000-2026.json, from Wikipedia's
'Historical components of the S&P 500'). Only the ones still quoted on Yahoo come back; acquired or
delisted names are gone (noted in the output), so this reduces survivorship bias, it does not remove it.
Writes data/earnings/fallen/<T>.csv and data/earnings/prices_fallen.pkl.
"""
from __future__ import annotations

import json
import pickle
import sys
import time
from pathlib import Path

import pandas as pd
import yfinance as yf

ROOT = Path(__file__).resolve().parent.parent
DIR = ROOT / "data" / "earnings"


def main() -> int:
    names = json.load(open(DIR / "fallen_sp500_removed_2000-2026.json"))
    ok, gone = [], []
    for i, name in enumerate(names):
        out = DIR / "fallen" / f"{name}.csv"
        if out.exists():
            ok.append(name); continue
        try:
            e = yf.Ticker(name.replace(".", "-")).get_earnings_dates(limit=100)
            if e is None or e.empty:
                gone.append(name); continue
            e = e.rename(columns={"EPS Estimate": "eps_est", "Reported EPS": "eps_act", "Surprise(%)": "surprise_pct"})
            e.index.name = "report_ts"; e.to_csv(out); ok.append(name)
        except Exception:  # noqa: BLE001
            gone.append(name)
        time.sleep(0.3)
        if (i + 1) % 50 == 0:
            print(f"{i + 1}/{len(names)} ok {len(ok)} gone {len(gone)}", flush=True)
    print(f"earnings: {len(ok)} still quoted, {len(gone)} gone (acquired/delisted): {' '.join(gone)}")
    opens, closes = [], []
    syms = [n.replace(".", "-") for n in ok] + ["SPY"]
    for i in range(0, len(syms), 100):
        raw = yf.download(syms[i:i + 100], period="max", interval="1d", auto_adjust=True, progress=False, threads=True)
        opens.append(raw["Open"]); closes.append(raw["Close"])
    o = pd.concat(opens, axis=1); c = pd.concat(closes, axis=1)
    back = {n.replace(".", "-"): n for n in ok}
    o.columns = [back.get(x, x) for x in o.columns]; c.columns = [back.get(x, x) for x in c.columns]
    o.index = pd.DatetimeIndex(o.index).tz_localize(None); c.index = pd.DatetimeIndex(c.index).tz_localize(None)
    pickle.dump({"open": o, "close": c}, open(DIR / "prices_fallen.pkl", "wb"))
    print(f"prices saved for {c.shape[1]} symbols")
    return 0


if __name__ == "__main__":
    sys.exit(main())
