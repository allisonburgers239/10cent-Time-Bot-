"""Execution-reality analysis for Sleeve E on the repo's 5-min CSVs.

The E backtest assumes fills at the official 4:00pm close and 9:30am
open (auction prints) at 1bp/side. This script measures what happens
if fills are instead at nearby continuous-market prices - the realistic
case for a retail broker without reliable MOC/MOO access - using the
12.5 months of 5-min bars for SPY/QQQ/IWM.

This is the correct use of short intraday data: execution modeling,
not strategy selection.

Fill variants (entry evening -> exit morning):
  auction      official close -> official open   (yfinance daily, reference)
  bar1555      15:55 bar close -> 09:30 bar close (i.e. ~09:35)
  bar1550      15:50 bar close -> 09:35 bar close (~09:40)
  bar1545      15:45 bar close -> 09:40 bar close (~09:45)

Also reports the 5-min bar range at entry/exit times as a bound on
intrabar timing risk, and re-derives E's cost breakeven under each.

Usage: python scripts/execution_e_analysis.py
"""
from __future__ import annotations

import os

import numpy as np
import pandas as pd
import yfinance as yf

ANN = 252
TICKERS = ["SPY", "QQQ", "IWM"]


def sharpe(r: pd.Series) -> float:
    r = r.dropna()
    if len(r) < 20 or r.std() == 0:
        return float("nan")
    return float(r.mean() / r.std() * np.sqrt(ANN))


def load_5m(repo: str, tkr: str) -> pd.DataFrame:
    df = pd.read_csv(os.path.join(repo, f"BATS_{tkr}, 5.csv"))
    df["dt"] = (pd.to_datetime(df["time"], unit="s", utc=True)
                .dt.tz_convert("America/New_York"))
    return df.set_index("dt").sort_index()


def bar_close_at(df: pd.DataFrame, hhmm: str) -> pd.Series:
    """Close of the 5-min bar whose label (open time) is hhmm, per day."""
    bars = df.between_time(hhmm, hhmm)
    out = bars["close"]
    out.index = pd.to_datetime(pd.Series(bars.index).dt.date)
    return out


def bar_range_at(df: pd.DataFrame, hhmm: str) -> pd.Series:
    bars = df.between_time(hhmm, hhmm)
    rng = (bars["high"] - bars["low"]) / bars["close"]
    rng.index = pd.to_datetime(pd.Series(bars.index).dt.date)
    return rng


def main() -> None:
    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    print("=" * 72)
    print("SLEEVE E EXECUTION ANALYSIS (5-min BATS data, ~12.5 months)")
    print("=" * 72)

    variants = {
        "auction (close->open)": None,  # from daily bars
        "15:55 -> 09:35 bars": ("15:55", "09:30"),
        "15:50 -> 09:40 bars": ("15:50", "09:35"),
        "15:45 -> 09:45 bars": ("15:45", "09:40"),
    }

    per_ticker_gap = {}
    port = {v: {} for v in variants}
    for tkr in TICKERS:
        m5 = load_5m(repo, tkr)
        # reference auction prints from daily bars, same window
        d = yf.download(tkr, start=str(m5.index[0].date()), progress=False,
                        auto_adjust=False)
        if isinstance(d.columns, pd.MultiIndex):
            d.columns = d.columns.get_level_values(0)
        ref_on = (d["Open"] / d["Close"].shift(1) - 1).dropna()

        for name, spec in variants.items():
            if spec is None:
                port[name][tkr] = ref_on
                continue
            t_in, t_out = spec
            entry = bar_close_at(m5, t_in)
            exit_ = bar_close_at(m5, t_out)
            r = (exit_ / entry.shift(1) - 1).dropna()
            port[name][tkr] = r

        # per-night slippage vs auction for the primary variant
        v = port["15:55 -> 09:35 bars"][tkr]
        both = pd.concat([v, ref_on], axis=1, keys=["bar", "auc"]).dropna()
        gap = (both["bar"] - both["auc"]) * 1e4
        per_ticker_gap[tkr] = gap
        rng_in = bar_range_at(m5, "15:55")
        rng_out = bar_range_at(m5, "09:30")
        print(f"\n{tkr}: {len(both)} nights")
        print(f"  15:55->09:35 vs auction: mean {gap.mean():+5.2f}bp/night, "
              f"std {gap.std():.1f}bp, |mean| annual drag/boost "
              f"{gap.mean()*252/100:+.2f}%/yr")
        print(f"  5-min bar range (timing risk bound): 15:55 bar "
              f"{rng_in.mean()*1e4:.1f}bp, 09:30 bar {rng_out.mean()*1e4:.1f}bp")

    print("\nPortfolio (EW SPY/QQQ/IWM) over the 5-min window, gross of costs:")
    print(f"  {'variant':<24} {'Sharpe':>7} {'mean bp/night':>14}")
    rows = {}
    for name in variants:
        p = pd.DataFrame(port[name]).mean(axis=1).dropna()
        rows[name] = p
        print(f"  {name:<24} {sharpe(p):>7.2f} {p.mean()*1e4:>14.2f}")

    print("\nImplied execution cost vs auction fills (per night, portfolio):")
    base = rows["auction (close->open)"]
    for name, p in rows.items():
        if name.startswith("auction"):
            continue
        both = pd.concat([p, base], axis=1, keys=["v", "b"]).dropna()
        diff = (both["v"] - both["b"]) * 1e4
        print(f"  {name:<24} {diff.mean():+6.2f}bp/night  "
              f"(t={diff.mean()/(diff.std()/np.sqrt(len(diff))):+.2f})")

    print("\nContext: audited E assumes 1bp/side (2bp/night); breakeven ~3bp/side.")
    print("A fill-timing drag of Xbp/night consumes X/4 of the 4bp/night edge margin.")


if __name__ == "__main__":
    main()
