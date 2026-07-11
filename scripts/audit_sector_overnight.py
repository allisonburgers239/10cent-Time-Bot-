"""Screen: does the overnight-drift anomaly (Sleeve E) generalize to sectors?

Two data sources, cross-validated:
  1. Daily open/close from yfinance, 1998-2026 (28y) - the long history.
  2. The repo's TradingView 60-min BATS exports, 2015-2026 (11.5y) - the
     longest intraday data we own; used to verify the daily-bar result and
     to decompose the intraday session by hour.

Universe: 9 SPDR sectors (XLB/XLE/XLF/XLI/XLK/XLP/XLU/XLV/XLY).

Usage: python scripts/audit_sector_overnight.py
"""
from __future__ import annotations

import glob
import os

import numpy as np
import pandas as pd
import yfinance as yf

ANN = 252
SECTORS = ["XLB", "XLE", "XLF", "XLI", "XLK", "XLP", "XLU", "XLV", "XLY"]
COST_PER_SIDE = 0.0001  # 1bp/side


def sharpe(r: pd.Series) -> float:
    r = r.dropna()
    if len(r) < 20 or r.std() == 0:
        return float("nan")
    return float(r.mean() / r.std() * np.sqrt(ANN))


def maxdd(r: pd.Series) -> float:
    eq = (1 + r.fillna(0)).cumprod()
    return float((eq / eq.cummax() - 1).min())


def cagr(r: pd.Series) -> float:
    r = r.dropna()
    if not len(r):
        return float("nan")
    return float((1 + r).prod() ** (ANN / len(r)) - 1)


def daily(tkr: str) -> pd.DataFrame:
    d = yf.download(tkr, start="1998-12-22", progress=False, auto_adjust=False)
    if isinstance(d.columns, pd.MultiIndex):
        d.columns = d.columns.get_level_values(0)
    adj = d["Adj Close"] / d["Close"]
    return pd.DataFrame({"open": d["Open"] * adj, "close": d["Adj Close"]})


def main() -> None:
    print("=" * 70)
    print("PART 1 - Daily bars (yfinance), 1998-2026: overnight vs intraday")
    print("=" * 70)
    on_all, id_all = {}, {}
    print(f"{'':6}{'Overnight':>10}{'Intraday':>10}{'Buy&Hold':>10}   (Sharpe, net 2bp/rt overnight)")
    for t in SECTORS:
        px = daily(t)
        on = (px["open"] / px["close"].shift(1) - 1).dropna() - 2 * COST_PER_SIDE
        intra = (px["close"] / px["open"] - 1).dropna()
        bh = px["close"].pct_change().dropna()
        on_all[t], id_all[t] = on, intra
        print(f"  {t:<4}{sharpe(on):>10.2f}{sharpe(intra):>10.2f}{sharpe(bh):>10.2f}")

    port_on = pd.DataFrame(on_all).mean(axis=1).dropna()
    port_id = pd.DataFrame(id_all).mean(axis=1).dropna()
    print(f"\n  EW-9 portfolio: overnight Sharpe {sharpe(port_on):.2f} "
          f"(CAGR {cagr(port_on)*100:.1f}%, MaxDD {maxdd(port_on)*100:.0f}%) "
          f"vs intraday {sharpe(port_id):.2f}")

    print("\n  Sub-periods (EW-9 overnight, ~5y):")
    for y0 in range(1999, 2026, 5):
        m = port_on[(port_on.index.year >= y0) & (port_on.index.year < y0 + 5)]
        print(f"    {y0}-{min(y0+4,2026)}: {sharpe(m):5.2f}")

    half = len(port_on) // 2
    print(f"  Walk-forward halves: {sharpe(port_on.iloc[:half]):.2f} -> "
          f"{sharpe(port_on.iloc[half:]):.2f}")

    # Correlation with Sleeve E (SPY/QQQ/IWM overnight) - is this new or the same trade?
    e_rets = {}
    for t in ["SPY", "QQQ", "IWM"]:
        px = daily(t)
        e_rets[t] = (px["open"] / px["close"].shift(1) - 1).dropna() - 2 * COST_PER_SIDE
    port_e = pd.DataFrame(e_rets).mean(axis=1).dropna()
    both = pd.concat([port_on, port_e], axis=1, keys=["sec", "e"]).dropna()
    print(f"  Correlation with Sleeve E overnight portfolio: "
          f"{both['sec'].corr(both['e']):.3f}")

    print()
    print("=" * 70)
    print("PART 2 - Repo 60-min CSVs, 2015-2026: cross-check + hour-of-day")
    print("=" * 70)
    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    hourly = {}
    for t in SECTORS:
        matches = glob.glob(os.path.join(repo, f"BATS_{t}, 60.csv"))
        if not matches:
            continue
        df = pd.read_csv(matches[0])
        df["dt"] = (pd.to_datetime(df["time"], unit="s", utc=True)
                    .dt.tz_convert("America/New_York"))
        hourly[t] = df.set_index("dt").sort_index()

    # Overnight from 60-min bars: first RTH bar open / prev day last RTH close
    print("  Cross-check: overnight Sharpe from 60-min bars (2015-2026)")
    on60_all = {}
    for t, df in hourly.items():
        rth = df.between_time("09:30", "15:59")
        day = rth.groupby(rth.index.date)
        opens = day["open"].first()
        closes = day["close"].last()
        on60 = (opens / closes.shift(1) - 1).dropna() - 2 * COST_PER_SIDE
        on60.index = pd.to_datetime(on60.index)
        on60_all[t] = on60
    port_on60 = pd.DataFrame(on60_all).mean(axis=1).dropna()
    # same window from daily data
    win = port_on[port_on.index >= port_on60.index[0]]
    print(f"    60-min CSVs: {sharpe(port_on60):.2f}   yfinance daily same window: "
          f"{sharpe(win):.2f}")

    # Hour-of-day decomposition (EW-9): mean return per RTH hour bucket
    print("\n  Hour-of-day decomposition, EW-9, 2015-2026 (gross):")
    rows = {}
    for t, df in hourly.items():
        rth = df.between_time("09:30", "15:59")
        r = (rth["close"] / rth["open"] - 1)
        rows[t] = r.groupby(rth.index.hour).mean() * 1e4
    hod = pd.DataFrame(rows).mean(axis=1)
    labels = {9: "09:30-10", 10: "10-11", 11: "11-12", 12: "12-13",
              13: "13-14", 14: "14-15", 15: "15-16"}
    for h, v in hod.items():
        print(f"    {labels.get(h, h):<10} {v:+5.1f} bp/hour")

    # Last-hour drift screen: hold EW-9 15:00->close only
    print("\n  Last-hour-only strategy (EW-9, net 2bp/rt):")
    lh_all = {}
    for t, df in hourly.items():
        bar15 = df.between_time("15:00", "15:59")
        r = (bar15["close"] / bar15["open"] - 1) - 2 * COST_PER_SIDE
        r.index = pd.to_datetime(pd.Series(r.index).dt.date)
        lh_all[t] = r
    port_lh = pd.DataFrame(lh_all).mean(axis=1).dropna()
    print(f"    Sharpe {sharpe(port_lh):.2f}   "
          f"halves {sharpe(port_lh.iloc[:len(port_lh)//2]):.2f} -> "
          f"{sharpe(port_lh.iloc[len(port_lh)//2:]):.2f}")


if __name__ == "__main__":
    main()
