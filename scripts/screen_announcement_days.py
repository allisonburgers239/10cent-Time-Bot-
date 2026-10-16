"""Screen: scheduled macro-announcement-day premium (Savor & Wilson 2013,
JFQA "How Much Do Investors Care About Macroeconomic Risk?").

Claim: the equity premium is earned disproportionately on days with
scheduled FOMC / CPI / employment announcements (compensation for bearing
macro-news risk), ~11bp on announcement days vs ~1bp otherwise, 1958-2009.

Dates:
  FOMC   data/fomc_dates.json (scraped from federalreserve.gov, 1994+)
  NFP    first Friday of the month (BLS convention; a handful of holiday
         shifts are ignored - adds noise, not bias)
  CPI    not available offline; omitted (TradingView calendar has ~no history)

Returns measured close(t-1) -> close(t), SPY 1993+, and split into the
overnight-before and intraday-of legs so the result can be compared with
Sleeve E (holds every overnight) and the FOMC intraday overlay (July screen).
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

ROOT = Path(__file__).resolve().parents[1]


def first_fridays(idx: pd.DatetimeIndex) -> set:
    s = pd.Series(idx, index=idx)
    fr = s[s.dt.dayofweek == 4]
    return set(fr.groupby(fr.dt.to_period("M")).first().dt.normalize())


def stat(x: pd.Series) -> str:
    t = x.mean() / (x.std(ddof=1) / np.sqrt(len(x)))
    return f"{x.mean()*1e4:+6.1f}bp  t={t:+5.2f}  n={len(x):>5}  ann.Sharpe-equiv {x.mean()/x.std()*np.sqrt(252):+.2f}"


def main() -> None:
    d = yf.download("SPY", period="max", interval="1d", auto_adjust=True, progress=False)
    df = pd.DataFrame({"open": d["Open"].squeeze(), "close": d["Close"].squeeze()}).dropna()
    df.index = pd.to_datetime(df.index).tz_localize(None).normalize()
    cc = df["close"].pct_change()
    on = df["open"] / df["close"].shift(1) - 1
    idr = df["close"] / df["open"] - 1

    fomc = {pd.Timestamp(y, m, dd) for y, m, dd in json.loads((ROOT / "data" / "fomc_dates.json").read_text())}
    nfp = first_fridays(df.index)
    fomc_days = df.index.isin(list(fomc))
    nfp_days = df.index.isin(list(nfp))
    ann = fomc_days | nfp_days

    print(f"SPY {df.index.min().date()} -> {df.index.max().date()}: FOMC days {fomc_days.sum()}, NFP days {nfp_days.sum()}, any {ann.sum()} ({ann.mean():.1%} of days)")
    for label, r in [("close->close", cc), ("overnight before (prev close->open)", on), ("intraday of (open->close)", idr)]:
        r = r.dropna(); m = pd.Series(ann, index=df.index).reindex(r.index).values
        f = pd.Series(fomc_days, index=df.index).reindex(r.index).values
        n = pd.Series(nfp_days, index=df.index).reindex(r.index).values
        print(f"\n--- {label}")
        print(f"  FOMC days        {stat(r[f])}")
        print(f"  NFP days         {stat(r[n])}")
        print(f"  any announcement {stat(r[m])}")
        print(f"  other days       {stat(r[~m])}")
        diff = r[m].mean() - r[~m].mean()
        se = np.sqrt(r[m].var(ddof=1) / m.sum() + r[~m].var(ddof=1) / (~m).sum())
        print(f"  announcement minus other: {diff*1e4:+.1f}bp  t={diff/se:+.2f}   share of total {label} return earned on announcement days: {r[m].sum()/r.sum():.0%}")

    print("\n--- close->close by sub-period: announcement-day mean / other-day mean (bp)")
    r = cc.dropna(); m = pd.Series(ann, index=df.index).reindex(r.index)
    for start in range(1993, 2027, 5):
        w = (r.index.year >= start) & (r.index.year < start + 5)
        if w.sum() < 300:
            continue
        a, o = r[w & m.values], r[w & ~m.values]
        print(f"  {start}-{start+4}: {a.mean()*1e4:+6.1f} / {o.mean()*1e4:+6.1f}   (t diff {((a.mean()-o.mean())/np.sqrt(a.var(ddof=1)/len(a)+o.var(ddof=1)/len(o))):+.2f})")

    rng = np.random.default_rng(2)
    real = r[m.values].mean() - r[~m.values].mean()
    k = int(m.sum())
    pl = np.array([(lambda s: r[s].mean() - r[~s].mean())(np.isin(np.arange(len(r)), rng.choice(len(r), k, replace=False))) for _ in range(500)])
    p = float((pl >= real).mean())
    print(f"\n  placebo (random day sets of the same size, 500x): real {real*1e4:+.1f}bp, placebo {pl.mean()*1e4:+.1f} +/- {pl.std()*1e4:.1f}bp, P(rand>=real)={p:.3f}  {'REAL' if p<0.05 else 'WEAK' if p<0.2 else 'NONE'}")


if __name__ == "__main__":
    main()
