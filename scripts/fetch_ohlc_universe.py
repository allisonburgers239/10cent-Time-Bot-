"""Daily adjusted OHLC for the survivors (top-450) and fallen (ex-S&P 500) sets + SPY -> data/earnings/ohlc.pkl
(dict: 'survivors' / 'fallen' -> dict of open/high/low/close DataFrames). Re-fetch takes ~2 minutes."""
from __future__ import annotations
import json, pickle, sys
from pathlib import Path
import pandas as pd
import yfinance as yf
DIR = Path(__file__).resolve().parent.parent / "data" / "earnings"

def grab(names):
    syms = [n.replace(".", "-") for n in names] + ["SPY"]
    parts = {k: [] for k in ("Open", "High", "Low", "Close")}
    for i in range(0, len(syms), 100):
        raw = yf.download(syms[i:i + 100], period="max", interval="1d", auto_adjust=True, progress=False, threads=True)
        for k in parts: parts[k].append(raw[k])
        print(i + 100, flush=True)
    out = {}
    for k, v in parts.items():
        df = pd.concat(v, axis=1); df = df.loc[:, ~df.columns.duplicated()]
        df.columns = [c.replace("-", ".") if c.replace("-", ".") in names else c for c in df.columns]
        df.index = pd.DatetimeIndex(df.index).tz_localize(None); out[k.lower()] = df[df.index >= "2000-01-01"]
    return out

def main():
    surv = [r[0] for r in json.load(open(sorted(DIR.glob("universe_*.json"))[-1]))]
    fallen = sorted(p.stem for p in (DIR / "fallen").glob("*.csv"))
    pickle.dump({"survivors": grab(surv), "fallen": grab(fallen)}, open(DIR / "ohlc.pkl", "wb"))
    print("saved")
if __name__ == "__main__":
    sys.exit(main())
