"""Overnight premium on single stocks, survivorship-aware (2026-11-11).

October's screen (40 names) found overnight > intraday on 30/40 stocks. Re-test on the two sets
downloaded for the earnings screen: today's top 450 and the 162 stocks removed from the S&P 500
since 2000 that still trade. Equal-weight baskets, close -> next open, 2 bp/side, 2002-. Also
E v2's signal on stocks (RSI(2)<10 at the close -> 2x that night) on both sets, and the
diversified basket vs QQQ's own overnight, so we know whether an "E on stocks" sleeve has a case.
"""
from __future__ import annotations

import pickle
from pathlib import Path

import numpy as np
import pandas as pd

from ten_cent_bot import overnight as ov

ROOT = Path(__file__).resolve().parent.parent
DIR = ROOT / "data" / "earnings"
C = 2e-4


def sh(x) -> float:
    x = pd.Series(x).dropna()
    return float(x.mean() / x.std() * np.sqrt(252)) if x.std() > 0 else 0.0


def halves(x) -> str:
    x = pd.Series(x).dropna(); h = len(x) // 2
    return f"{sh(x.iloc[:h]):.2f}/{sh(x.iloc[h:]):.2f}"


def stats(name, r):
    r = pd.Series(r).dropna()
    dd = ((1 + r).cumprod() / (1 + r).cumprod().cummax() - 1).min()
    print(f"  {name:62s} Sharpe {sh(r):5.2f}  mean {r.mean() * 1e4:+5.1f}bp/night  CAGR {r.mean() * 252:+6.1%}  MaxDD {dd:+.0%}  halves {halves(r)}")


def load(which):
    px = pickle.load(open(DIR / which, "rb")); o, c = px["open"], px["close"]
    o = o[o.index >= "2002-01-01"]; c = c[c.index >= "2002-01-01"]
    return o, c


def per_stock(o, c, t):
    night = o[t].shift(-1) / c[t] - 1
    day = c[t] / o[t] - 1
    return night, day


def main() -> None:
    os_, cs = load("prices.pkl"); of, cf = load("prices_fallen.pkl")
    qqq_night = None
    for label, (o, c) in (("TOP-450 (today's survivors)", (os_, cs)), ("FALLEN (ex-S&P 500, still listed)", (of, cf))):
        syms = [t for t in c.columns if t != "SPY" and c[t].notna().sum() > 1000]
        N = pd.DataFrame({t: per_stock(o, c, t)[0] for t in syms}); D = pd.DataFrame({t: per_stock(o, c, t)[1] for t in syms})
        # drop bad prints: nights beyond +-50% are data errors or splits
        N = N.where(N.abs() < 0.5); D = D.where(D.abs() < 0.5)
        print(f"=== {label}: {len(syms)} stocks ===")
        ovn = N.mean(axis=1) - 2 * C; dayr = D.mean(axis=1) - 2 * C
        stats("equal-weight basket, overnight close->open (2 bp/side)", ovn)
        stats("equal-weight basket, day session open->close (2 bp/side)", dayr)
        gross = N.mean(axis=1); spy_n = (o["SPY"].shift(-1) / c["SPY"] - 1).reindex(gross.index)
        print(f"  GROSS overnight {gross.mean() * 1e4:+.1f}bp/night, basket sd {gross.std() * 1e4:.0f}bp/night, corr with SPY overnight {gross.corr(spy_n):.2f}, beta {gross.cov(spy_n) / spy_n.var():.2f}")
        print("  cost sensitivity (bp per side -> net Sharpe, CAGR): " + " | ".join(f"{cb}bp: {sh(gross - 2 * cb * 1e-4):.2f}, {(gross - 2 * cb * 1e-4).mean() * 252:+.1%}" for cb in (0, 0.25, 0.5, 1.0, 2.0)))
        per = pd.Series({t: sh(N[t] - 2 * C) for t in syms}); perd = pd.Series({t: sh(D[t] - 2 * C) for t in syms})
        print(f"  per stock: overnight Sharpe median {per.median():.2f} (positive in {(per > 0).mean():.0%}); day Sharpe median {perd.median():.2f}; overnight > day in {(per > perd).mean():.0%} of stocks")
        # E v2 on each stock: RSI(2)<10 at the close -> 2x that night; basket
        sig = pd.DataFrame({t: (ov.rsi(c[t].dropna(), 2) < 10).reindex(c.index) for t in syms}).fillna(False).astype(bool)
        pos = 1 + sig.astype(float)
        e2 = (pos * N - 2 * C * pos).mean(axis=1)
        stats("same basket with E v2 overlay (RSI2<10 -> 2x that night)", e2)
        e2g = (pos * N).mean(axis=1)
        print("  E v2 overlay cost sensitivity (bp per side -> net Sharpe): " + " | ".join(f"{cb}bp: {sh((pos * N - 2 * cb * 1e-4 * pos).mean(axis=1)):.2f}" for cb in (0, 0.25, 0.5, 1.0, 2.0)))
        on_sig = N[sig].stack(); off_sig = N[~sig].stack()
        print(f"  signal nights {len(on_sig):,}: mean {on_sig.mean() * 1e4:+.1f}bp vs other nights {off_sig.mean() * 1e4:+.1f}bp")
        # by 5-year block
        print("  overnight basket Sharpe by block: " + " ".join(f"{y}-{y + 4}:{sh(ovn[(ovn.index.year >= y) & (ovn.index.year < y + 5)]):.2f}" for y in range(2002, 2027, 5)))
        if label.startswith("TOP"):
            top50 = [t for t in syms if t in list(c.columns)[:60]][:50]
            stats("top-50 by today's cap only, overnight", N[top50].mean(axis=1) - 2 * C)
    # reference: QQQ / SPY overnight from the same price source
    for t in ("SPY", "AAPL", "NVDA", "AVGO", "AMD", "TSLA", "F", "INTC"):
        if t not in cs.columns and t not in cf.columns: continue
        src = (os_, cs) if t in cs.columns else (of, cf)
        n = src[0][t].shift(-1) / src[1][t] - 1 - 2e-4
        same = (src[0][t] == src[1][t].shift(1)).groupby(src[1].index.year).mean()
        stats(f"{t} overnight (1 bp/side), same source", n)
        print("     share of days where Yahoo open == previous close exactly, by year: " + " ".join(f"{y}:{v:.0%}" for y, v in same.items() if v > 0.02))


if __name__ == "__main__":
    main()
