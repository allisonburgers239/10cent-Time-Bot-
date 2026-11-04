"""Forced-flow idea #1: big stocks that fell >= 15% in a week on heavy volume (2026-11-04).

Premise: part of the selling is risk-rule forced liquidation, done at any price; the week after
should bounce. Earnings-driven drops are a different animal and are excluded.

Universe: US stocks with market cap > $5B TODAY (TradingView public scanner). This has
survivorship bias: a stock that crashed and never recovered is less likely to be in today's
list, which flatters the bounce. Reported as such; the result is an upper bound.

Rule: weekly bars (Mon-Fri). A crash week = close/prior close - 1 <= -15% AND week volume >= 2x
the trailing 20-week average. Entry at that week's close, hold 5 trading days (next week's close).
Earnings exclusion: any earnings date inside the crash week or the 2 days before it (yfinance
earnings_dates, ~ last 8-10 years per stock).
Baseline: all weeks' next-week return for the same stocks. Placebo: random weeks, same count.
Cost 3 bp per side (single stocks).

Usage: python scripts/screen_crash_week_reversal.py [--years 10] [--n 400]
"""
from __future__ import annotations

import argparse

import numpy as np
import pandas as pd
import requests
import yfinance as yf

UA = {"User-Agent": "Mozilla/5.0"}


def universe(n: int) -> list[str]:
    r = requests.post("https://scanner.tradingview.com/america/scan", json={
        "filter": [{"left": "type", "operation": "equal", "right": "stock"}, {"left": "exchange", "operation": "in_range", "right": ["NASDAQ", "NYSE", "AMEX"]}, {"left": "market_cap_basic", "operation": "greater", "right": 5e9}],
        "columns": ["name", "market_cap_basic"], "sort": {"sortBy": "market_cap_basic", "sortOrder": "desc"}, "range": [0, n]}, headers=UA, timeout=30)
    return [x["d"][0] for x in r.json()["data"] if "." not in x["d"][0]]


def tstat(x) -> float:
    x = pd.Series(x).dropna()
    return float(x.mean() / x.std() * np.sqrt(len(x))) if len(x) > 2 and x.std() > 0 else 0.0


def main() -> None:
    ap = argparse.ArgumentParser(); ap.add_argument("--years", type=int, default=10); ap.add_argument("--n", type=int, default=400)
    a = ap.parse_args()
    tickers = universe(a.n)
    print(f"universe: {len(tickers)} stocks > $5B today (survivorship-biased)")
    data = yf.download(tickers, period=f"{a.years}y", interval="1d", auto_adjust=True, progress=False, group_by="ticker", threads=True)
    spy = yf.download("SPY", period=f"{a.years}y", interval="1d", auto_adjust=True, progress=False)
    spy.columns = [c[0] if isinstance(c, tuple) else c for c in spy.columns]
    spyw = spy.Close.resample("W-FRI").last().pct_change()
    events = []; base = []; vol_only = []
    cost = 2 * 3e-4
    rng = np.random.default_rng(2)
    placebo_pool = []
    for t in tickers:
        try:
            df = data[t].dropna()
        except KeyError:
            continue
        if len(df) < 300:
            continue
        w = df.resample("W-FRI").agg({"Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"}).dropna()
        w["ret"] = w.Close.pct_change(); w["fwd"] = w.Close.shift(-1) / w.Close - 1
        w["volr"] = w.Volume / w.Volume.rolling(20).mean().shift(1)
        base.extend(w.fwd.dropna().tolist())
        crash = w[(w.ret <= -0.15) & (w.volr >= 2.0) & w.fwd.notna()]
        if len(crash) == 0:
            continue
        try:
            ed = yf.Ticker(t).get_earnings_dates(limit=60)
            edates = set(pd.to_datetime(ed.index).tz_localize(None).normalize()) if ed is not None and len(ed) else set()
        except Exception:  # noqa: BLE001
            edates = set()
        for d, row in crash.iterrows():
            wk_start = d - pd.Timedelta(days=6)
            has_earn = any((wk_start <= e <= d) for e in edates)
            events.append({"ticker": t, "week": d.date(), "wkret": row.ret, "volr": row.volr, "fwd": row.fwd - cost, "earnings": has_earn, "earn_known": len(edates) > 0, "spy_week": float(spyw.get(d, np.nan))})
        placebo_pool.append(w.fwd.dropna())
    ev = pd.DataFrame(events)
    b = pd.Series(base)
    print(f"crash weeks (<= -15%, volume >= 2x): {len(ev)} across {ev.ticker.nunique()} stocks; earnings data available for {ev.earn_known.mean():.0%} of them")
    for name, m in [("all crash weeks", ev.fwd.notna()), ("earnings week (excluded by the idea)", ev.earnings), ("NON-earnings crash weeks (the idea)", ~ev.earnings & ev.earn_known), ("unknown earnings status", ~ev.earn_known)]:
        x = ev[m].fwd
        if len(x) >= 5:
            print(f"  {name:40s} n {len(x):4d}  next-week mean {x.mean() * 100:+5.2f}%  median {x.median() * 100:+5.2f}%  hit {(x > 0).mean():.2f}  t {tstat(x):+4.1f}  worst {x.min() * 100:+.0f}%  best {x.max() * 100:+.0f}%")
    print(f"  baseline, all weeks all stocks: mean {b.mean() * 100:+.2f}%  (n {len(b)})")
    x = ev[~ev.earnings & ev.earn_known].fwd
    if len(x):
        print(f"  edge vs cost: mean {x.mean() * 1e4:+.0f}bp net of 6bp round trip; the idea's bar (3x cost = 18bp) {'MET' if x.mean() > 18e-4 else 'NOT met'}; by year: " + " ".join(f"{y}:{v * 100:+.1f}%/n{c}" for (y, v), c in zip(x.groupby(pd.to_datetime(ev[~ev.earnings & ev.earn_known].week).dt.year).mean().items(), x.groupby(pd.to_datetime(ev[~ev.earnings & ev.earn_known].week).dt.year).size())))
    ev["year"] = pd.to_datetime(ev.week).dt.year
    good = ~ev.earnings & ev.earn_known
    print("\n  --- is it forced selling in ONE stock, or the whole market crashing? (non-earnings crash weeks) ---")
    for name, m in [("market-wide week (SPY <= -5%)", good & (ev.spy_week <= -0.05)), ("idiosyncratic week (SPY > -5%)", good & (ev.spy_week > -0.05)), ("idiosyncratic, excluding 2020", good & (ev.spy_week > -0.05) & (ev.year != 2020)), ("idiosyncratic, excl. 2020 and 2025", good & (ev.spy_week > -0.05) & ~ev.year.isin([2020, 2025]))]:
        x = ev[m].fwd
        if len(x) >= 5:
            print(f"  {name:38s} n {len(x):4d}  next-week mean {x.mean() * 100:+5.2f}%  median {x.median() * 100:+5.2f}%  hit {(x > 0).mean():.2f}  t {tstat(x):+4.1f}")
    # drop-size buckets
    for lo, hi in [(-0.2, -0.15), (-0.3, -0.2), (-1, -0.3)]:
        m = (ev.wkret > lo) & (ev.wkret <= hi) & ~ev.earnings & ev.earn_known
        if m.sum() >= 5:
            print(f"  drop {lo * 100:.0f}..{hi * 100:.0f}%: n {int(m.sum())} next-week {ev[m].fwd.mean() * 100:+.2f}% hit {(ev[m].fwd > 0).mean():.2f}")
    # placebo: same number of random weeks
    pool = pd.concat(placebo_pool)
    pl = np.array([pool.sample(len(ev), random_state=int(rng.integers(1e9))).mean() for _ in range(300)])
    print(f"  placebo (random weeks, same count): mean {pl.mean() * 100:+.2f}% sd {pl.std() * 100:.2f} | p(placebo >= all-crash mean) = {(pl >= ev.fwd.mean() + cost).mean():.3f}")


if __name__ == "__main__":
    main()
