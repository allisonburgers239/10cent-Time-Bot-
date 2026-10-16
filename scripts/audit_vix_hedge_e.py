"""Audit: long-VIX-futures-when-inverted as a crash hedge on Sleeve E.

From audit_vol_carry.py the long side of the basis rule (go long the 30-day
constant-maturity VX position when VX1 < VIX by more than k) was a poor
return sleeve (Sharpe 0.20) but made money in every crash window.  E loses
in exactly those windows.  Question: does a small long-vol overlay,
switched on only by inversion, improve E's drawdown without eating its
Sharpe?  Benchmark: an always-on small long-VX hedge (the naive version
that bleeds).

Signal known at the close of day t (VX settle 16:00, VIX close), position
held over day t+1.  E leg = overnight SPY/QQQ/IWM equal-weight, 1bp/side.
VX leg cost 15bps per side of turnover.  Overlay is additive notional
(not re-normalized), so the book's gross exposure rises on hedge days.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

from ten_cent_bot.metrics import max_drawdown, sharpe, sortino
from ten_cent_bot.vx_data import build_curve, load_raw

ROOT = Path(__file__).resolve().parents[1]


def S(r):
    r = r.dropna(); eq = (1 + r).cumprod()
    return {"sharpe": sharpe(r, 252), "sortino": sortino(r, 252), "cagr": (1 + r.mean()) ** 252 - 1, "mdd": max_drawdown(eq), "n": len(r)}


def fmt(s):
    return f"Sharpe {s['sharpe']:5.2f}  Sortino {s['sortino']:5.2f}  CAGR {s['cagr']:6.2%}  MaxDD {s['mdd']:6.1%}"


def main():
    raw = load_raw(ROOT / "data" / "cboe_vx" / "raw")
    built = build_curve(raw, min_days=2)
    curve, cm = built["curve"], built["cm30_return"]
    vix = yf.download("^VIX", period="max", interval="1d", progress=False)["Close"].squeeze()
    vix.index = pd.to_datetime(vix.index).tz_localize(None)
    vix = vix.reindex(curve.index).ffill()
    basis = curve["VX1"] / vix - 1

    data = yf.download(["SPY", "QQQ", "IWM"], period="max", interval="1d", auto_adjust=True, progress=False)
    on = pd.DataFrame({t: (data["Open"][t].shift(-1) - data["Close"][t]) / data["Close"][t] for t in ["SPY", "QQQ", "IWM"]})
    on.index = pd.to_datetime(on.index).tz_localize(None)
    e = (on - 2 / 1e4).mean(axis=1)  # E net of 1bp/side

    idx = curve.index.intersection(e.index)
    e = e.loc[idx]; cm = cm.reindex(idx); basis = basis.loc[idx]
    rv = cm.rolling(20, min_periods=10).std(ddof=0) * np.sqrt(252)
    lev = (0.10 / rv).clip(upper=1.0)

    def hedge_leg(k: float, always: bool = False) -> pd.Series:
        sig = pd.Series(1.0, index=idx) if always else (basis < -k).astype(float)
        pos = (sig * lev).shift(1).fillna(0.0)
        return pos * cm - pos.diff().abs().fillna(0) * 15 / 1e4

    print(f"Window {idx.min().date()} -> {idx.max().date()}, {len(idx)} days.  E alone: " + fmt(S(e)))
    print(f"  inversion frequency: k=0 {(basis<0).mean():.1%} of days, k=0.03 {(basis<-0.03).mean():.1%}, k=0.05 {(basis<-0.05).mean():.1%}")

    print("\n=== 1. E + w x hedge leg (hedge leg vol-targeted 10%, long CM30 only when VX1 < VIX*(1-k)) ===")
    print(f"  {'variant':<30} {'w':>4}  {'Sharpe':>6} {'Sortino':>7} {'CAGR':>7} {'MaxDD':>7}   dSharpe dMaxDD")
    base = S(e)
    rows = []
    for label, k, always in [("inverted k=0.00", 0.0, False), ("inverted k=0.03", 0.03, False), ("inverted k=0.05", 0.05, False), ("ALWAYS long (naive)", 0.0, True)]:
        h = hedge_leg(k, always)
        for w in [0.25, 0.5, 1.0, 2.0]:
            book = e + w * h
            s = S(book)
            rows.append((label, w, s))
            print(f"  {label:<30} {w:>4.2f}  {s['sharpe']:>6.2f} {s['sortino']:>7.2f} {s['cagr']:>7.2%} {s['mdd']:>7.1%}   {s['sharpe']-base['sharpe']:+.2f}   {s['mdd']-base['mdd']:+.1%}")

    print("\n=== 2. Crash windows: E vs E + 1.0 x hedge (k=0.03) ===")
    h = hedge_leg(0.03)
    book = e + h
    for label, a, b in [("2008-09..11", "2008-09-01", "2008-11-30"), ("2010-05 flash", "2010-05-01", "2010-05-31"), ("2011-08", "2011-08-01", "2011-09-30"), ("2015-08", "2015-08-17", "2015-09-30"),
                        ("2018-02", "2018-01-29", "2018-02-28"), ("2018-Q4", "2018-10-01", "2018-12-31"), ("2020-02..03", "2020-02-20", "2020-03-31"), ("2022 (year)", "2022-01-01", "2022-12-31"), ("2024-08", "2024-07-29", "2024-08-09"), ("2025-04", "2025-04-01", "2025-04-15")]:
        print(f"  {label:<14} E {e.loc[a:b].sum():+7.2%}   hedge leg {h.loc[a:b].sum():+7.2%}   book {book.loc[a:b].sum():+7.2%}   hedge on {((basis.loc[a:b] < -0.03).mean()):.0%} of days")

    print("\n=== 3. Walk-forward halves (E -> book, k=0.03, w=1) ===")
    n = len(idx) // 2
    for name, sl in [("train", slice(0, n)), ("test", slice(n, None))]:
        print(f"  {name}: E {S(e.iloc[sl])['sharpe']:.2f}/{S(e.iloc[sl])['mdd']:.1%} -> book {S(book.iloc[sl])['sharpe']:.2f}/{S(book.iloc[sl])['mdd']:.1%}")

    print("\n=== 4. Sub-periods (4y): E Sharpe/MaxDD -> book ===")
    for start in range(2004, 2027, 4):
        w = (idx.year >= start) & (idx.year < start + 4)
        if w.sum() < 300:
            continue
        print(f"  {start}-{start+3}: {S(e[w])['sharpe']:+.2f}/{S(e[w])['mdd']:.1%} -> {S(book[w])['sharpe']:+.2f}/{S(book[w])['mdd']:.1%}")

    print("\n=== 5. Placebo: inversion signal block-shuffled in time (20-day blocks, 200 seeds), k=0.03, w=1 ===")
    rng = np.random.default_rng(13)
    real = S(book)["sharpe"]; real_mdd = S(book)["mdd"]
    sig = (basis < -0.03).astype(float).values
    blocks = [sig[i:i + 20] for i in range(0, len(sig), 20)]
    pls, plm = [], []
    for _ in range(200):
        order = rng.permutation(len(blocks))
        sh = pd.Series(np.concatenate([blocks[i] for i in order])[: len(sig)], index=idx)
        pos = (sh * lev).shift(1).fillna(0.0)
        hb = pos * cm - pos.diff().abs().fillna(0) * 15 / 1e4
        s = S(e + hb); pls.append(s["sharpe"]); plm.append(s["mdd"])
    pls = np.array(pls); plm = np.array(plm)
    print(f"  Sharpe: real {real:.3f} vs placebo {pls.mean():.3f} +/- {pls.std():.3f}, P(placebo>=real)={float((pls>=real).mean()):.3f}")
    print(f"  MaxDD : real {real_mdd:.1%} vs placebo {plm.mean():.1%} +/- {plm.std():.1%}, P(placebo better)={float((plm>=real_mdd).mean()):.3f}")

    print("\n=== 6. Cost sensitivity on the hedge leg (bps/side), k=0.03, w=1 ===")
    for c in [5, 15, 30, 50]:
        sig_ = (basis < -0.03).astype(float); pos = (sig_ * lev).shift(1).fillna(0.0)
        hb = pos * cm - pos.diff().abs().fillna(0) * c / 1e4
        print(f"  {c:>3} bps: book " + fmt(S(e + hb)))


if __name__ == "__main__":
    main()
