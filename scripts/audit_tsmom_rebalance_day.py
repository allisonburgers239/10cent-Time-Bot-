"""Robustness: does Sleeve B's Sharpe depend on rebalancing exactly at
month-end?  Same rule (tsmom.backtest, 12m lookback, 10bps) on the 10-ETF
basket, but the 'month' is sampled on different calendar offsets, plus a
tranched version (half the book on each of two offsets).  If month-end is
an outlier the audited 0.71 carries timing luck; if the offsets cluster,
the edge is the rule, not the day.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import yfinance as yf

from ten_cent_bot import tsmom
from ten_cent_bot.metrics import max_drawdown, sharpe

B10 = ["SPY", "QQQ", "IWM", "EFA", "EEM", "TLT", "IEF", "GLD", "USO", "DBC"]


def sample(px: pd.DataFrame, day: int) -> pd.DataFrame:
    """Last available close on or before `day` of each month (day=31 -> month-end)."""
    idx = px.index
    key = pd.Series(idx.to_period("M"), index=idx)
    if day >= 28:
        return px.resample("ME").last()
    mask = pd.Series(idx.day <= day, index=idx)
    out = px[mask].groupby(key[mask]).last()
    out.index = out.index.to_timestamp("M")
    return out


def main():
    px = yf.download(B10, period="max", interval="1d", auto_adjust=True, progress=False)["Close"]
    px.index = pd.to_datetime(px.index).tz_localize(None)
    px = px.loc["2006-06-01":]
    print("=== Sleeve B (10 ETFs), rebalance-day offsets, 2007-06 -> 2026-10 ===")
    res = {}
    for day in [5, 10, 15, 20, 25, 31]:
        r = tsmom.backtest(sample(px, day))["monthly_return_net"].dropna().loc["2007-06-30":]
        res[day] = r
        n = len(r) // 2
        print(f"  day {day:>2}: Sharpe {sharpe(r,12):5.2f}  CAGR {((1+r.mean())**12-1):6.2%}  MaxDD {max_drawdown((1+r).cumprod()):6.1%}  halves {sharpe(r.iloc[:n],12):.2f}/{sharpe(r.iloc[n:],12):.2f}")
    vals = [sharpe(r, 12) for r in res.values()]
    print(f"  mean {np.mean(vals):.2f}  std {np.std(vals):.2f}  month-end rank {sorted(vals, reverse=True).index(sharpe(res[31],12))+1}/6")
    tr = (res[15].reindex(res[31].index).fillna(0) + res[31]) / 2
    print(f"  tranched (15th + month-end, half each): Sharpe {sharpe(tr.dropna(),12):.2f}  MaxDD {max_drawdown((1+tr.dropna()).cumprod()):.1%}")
    print("  Reading: dispersion across offsets is the timing-luck band around the audited number.")


if __name__ == "__main__":
    main()
