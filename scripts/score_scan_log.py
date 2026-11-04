"""Score the daily scan log (results/scan_log.csv).

For every logged row whose day has closed, fetch that day's close and the next
day's open, and compute:
  ret_to_close  = close / price at scan time - 1      (the day-trade claim)
  ret_overnight = next open / close - 1               (does the imbalance carry?)
Then group by verdict. The pre-registered claim (2026-11-04): BUY_IMBALANCE
names beat SELL_IMBALANCE names on ret_to_close, by more than costs (2 bp/side
+ slippage, call it 10 bp on these names). Anything else is a new hypothesis,
not a result.

Usage: python scripts/score_scan_log.py
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
LOG = ROOT / "results" / "scan_log.csv"


def main() -> None:
    if not LOG.exists():
        print("no log yet"); return
    import yfinance as yf

    log = pd.read_csv(LOG)
    log["day"] = pd.to_datetime(log.scan_time_et).dt.date
    log = log[log.verdict.ne("NO_DATA") & log["last"].notna()]
    today = pd.Timestamp.now(tz="America/New_York").date()
    rows = []
    for (sym, day), g in log.groupby(["symbol", "day"]):
        if day >= today:
            continue  # not closed yet
        tk = sym.split(":")[-1]
        try:
            h = yf.Ticker(tk).history(start=str(day), end=str(day + pd.Timedelta(days=5)), interval="1d")
        except Exception:  # noqa: BLE001
            continue
        if h.empty or h.index[0].date() != day:
            continue
        close = float(h.Close.iloc[0]); nxt_open = float(h.Open.iloc[1]) if len(h) > 1 else np.nan
        r = g.iloc[-1]  # the latest scan that day
        rows.append({"symbol": sym, "day": day, "verdict": r.verdict, "scan_price": r["last"], "close": close,
                     "ret_to_close_bp": (close / r["last"] - 1) * 1e4, "ret_overnight_bp": (nxt_open / close - 1) * 1e4 if nxt_open == nxt_open else np.nan,
                     "gap_pct": r.get("gap_pct", np.nan), "news_12h": r.get("news_12h", np.nan)})
    if not rows:
        print("nothing scorable yet (need at least one closed day in the log)"); return
    t = pd.DataFrame(rows)
    pd.set_option("display.width", 220)
    print(t.round(1).to_string(index=False))
    print("\nBy verdict (ret_to_close, bp):")
    for v, g in t.groupby("verdict"):
        x = g.ret_to_close_bp.dropna()
        tstat = x.mean() / x.std() * np.sqrt(len(x)) if len(x) > 2 and x.std() > 0 else float("nan")
        print(f"  {v:15s} n {len(x):3d}  mean {x.mean():+7.1f}  median {x.median():+7.1f}  hit {(x > 0).mean():.2f}  t {tstat:+.2f}")
    b = t[t.verdict == "BUY_IMBALANCE"].ret_to_close_bp; s = t[t.verdict == "SELL_IMBALANCE"].ret_to_close_bp
    if len(b) > 2 and len(s) > 2:
        diff = b.mean() - s.mean(); se = np.sqrt(b.var() / len(b) + s.var() / len(s))
        print(f"\nPre-registered test: BUY - SELL = {diff:+.1f} bp, t = {diff / se:+.2f}  (needs ~30 days; costs ~10 bp per side)")


if __name__ == "__main__":
    main()
