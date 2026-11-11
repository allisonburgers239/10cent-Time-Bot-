"""Audit: month-end stock/bond rebalancing pair, through the library (2026-11-11).

Rule (ten_cent_bot.monthend_pair): at the close with 5 sessions left in the month, if MTD(SPY) -
MTD(TLT) > +3% go short SPY / long TLT, if < -3% the reverse, hold to the month's last close,
1 bp/side x 4 legs. Daily adjusted closes from Yahoo, 2002-07 (TLT inception) ->.

Sections: 0 library == screen, 1 baseline, 2 walk-forward (rule chosen on 2002-2013), 3 grid,
4 by year, 5 bond proxy (TLT / IEF / AGG) and stock proxy (SPY / QQQ / IWM), 6 costs, 7 placebo
(same rule on random mid-month windows, 1000 draws), 8 tail, 9 legs separately, 10 overlap with
E v3 and the book, 11 sizing on a $25k account.
"""
from __future__ import annotations

from dataclasses import replace

import numpy as np
import pandas as pd
import yfinance as yf

from ten_cent_bot import monthend_pair as mp
from ten_cent_bot import overnight as ov

RNG = np.random.default_rng(5)


def tstat(x) -> float:
    x = pd.Series(x).dropna()
    return float(x.mean() / x.std() * np.sqrt(len(x))) if len(x) > 2 and x.std() > 0 else 0.0


def sh(x) -> float:
    x = pd.Series(x).dropna()
    return float(x.mean() / x.std() * np.sqrt(252)) if x.std() > 0 else 0.0


def dd(x) -> float:
    e = (1 + pd.Series(x).fillna(0)).cumprod(); return float((e / e.cummax() - 1).min())


def line(label, ev):
    t = ev[ev.side != 0]
    yrs = ev.month.str[:4].nunique()
    print(f"  {label:48s} n {len(t):3d}  mean {t.net.mean() * 1e4:+5.0f}bp  hit {(t.net > 0).mean():.2f}  t {tstat(t.net):+4.1f}  halves {t.net.iloc[:len(t) // 2].mean() * 1e4:+.0f}/{t.net.iloc[len(t) // 2:].mean() * 1e4:+.0f}  per year {t.net.sum() / yrs * 100:+.1f}%")


def main() -> None:
    raw = yf.download(["SPY", "QQQ", "IWM", "TLT", "IEF", "AGG", "GLD", "^VIX"], period="max", interval="1d", auto_adjust=True, progress=False)
    C = raw["Close"]; C.index = pd.DatetimeIndex(C.index).tz_localize(None)
    O = raw["Open"]; O.index = C.index
    spy, tlt = C["SPY"].dropna(), C["TLT"].dropna()
    cfg = mp.DEFAULT_CONFIG
    ev = mp.events(spy, tlt, cfg)

    print("=== 0. Library == screen (same rule hand-computed) ===")
    df = pd.DataFrame({"s": spy, "b": tlt}).dropna(); per = df.index.to_period("M"); manual = []
    for m in per.unique()[1:]:
        idx = np.flatnonzero(per == m)
        if len(idx) <= 5: continue
        p0, sig, e = idx[0] - 1, idx[-1] - 5, idx[-1]
        spread = (df.s.iloc[sig] / df.s.iloc[p0] - 1) - (df.b.iloc[sig] / df.b.iloc[p0] - 1)
        side = -1 if spread > 0.03 else (1 if spread < -0.03 else 0)
        manual.append(side * ((df.s.iloc[e] / df.s.iloc[sig] - 1) - (df.b.iloc[e] / df.b.iloc[sig] - 1)) - (4e-4 if side else 0))
    print(f"  {len(ev)} months, max |library - manual| = {np.abs(ev.net.to_numpy() - np.array(manual)).max():.2e}")

    print("\n=== 1. Baseline (SPY/TLT, 3%, last 5 sessions, 1 bp/side) ===")
    line("all events", ev)
    line("   short-stock side (stocks beat bonds)", ev[ev.side != 1])
    line("   long-stock side (stocks lagged)", ev[ev.side != -1])
    r = mp.daily_returns(spy, tlt, cfg)
    print(f"  daily series: Sharpe {sh(r):.2f} (in-market days only {sh(r[r != 0]):.2f}), MaxDD {dd(r):+.1%}, time in market {(r != 0).mean():.0%}, CAGR {r.mean() * 252:+.1%} of pair notional")

    print("\n=== 2. Walk-forward: rule chosen on 2002-2013 by t-stat, judged on 2014-2026 ===")
    grid = [(thr, L) for thr in (0.02, 0.03, 0.04, 0.05) for L in (2, 3, 5, 7)]
    def ev_for(thr, L, lo=None, hi=None):
        s, b = spy, tlt
        if lo: s, b = s[s.index >= lo], b[b.index >= lo]
        if hi: s, b = s[s.index < hi], b[b.index < hi]
        return mp.events(s, b, replace(cfg, threshold=thr, last_sessions=L))
    best = max(grid, key=lambda g: tstat(ev_for(*g, hi="2014-01-01").pipe(lambda e: e[e.side != 0].net)))
    tr = ev_for(*best, hi="2014-01-01"); te = ev_for(*best, lo="2014-01-01"); te_def = ev_for(0.03, 5, lo="2014-01-01")
    print(f"  chosen on train: thr {best[0]:.0%}, L={best[1]} (train t {tstat(tr[tr.side != 0].net):+.1f})")
    line("  TEST 2014-2026, chosen cell", te); line("  TEST 2014-2026, default 3%/5", te_def)
    for lo, hi in (("2002-07-01", "2010-01-01"), ("2010-01-01", "2018-01-01"), ("2018-01-01", "2027-01-01")):
        line(f"  sub-period {lo[:4]}-{int(hi[:4]) - 1}", ev_for(0.03, 5, lo, hi))

    print("\n=== 3. Grid: threshold (rows) x last sessions (cols), mean bp net / t / n ===")
    for thr in (0.02, 0.03, 0.04, 0.05):
        cells = []
        for L in (2, 3, 5, 7):
            e = ev_for(thr, L); t = e[e.side != 0]
            cells.append(f"L={L}: {t.net.mean() * 1e4:+4.0f} t{tstat(t.net):+.1f} n{len(t)}")
        print(f"  thr {thr:.0%}: " + " | ".join(cells))

    print("\n=== 4. By year (net, bp summed over the year's events) ===")
    t = ev[ev.side != 0]
    print("  " + " ".join(f"{y}:{v * 1e4:+.0f}({n})" for (y, v), (_, n) in zip(t.groupby(t.month.str[:4]).net.sum().items(), t.groupby(t.month.str[:4]).size().items())))
    print(f"  positive years {int((t.groupby(t.month.str[:4]).net.sum() > 0).sum())} of {t.month.str[:4].nunique()}")

    print("\n=== 5. Proxies: bond leg TLT / IEF / AGG; stock leg SPY / QQQ / IWM ===")
    for b in ("TLT", "IEF", "AGG"):
        line(f"  SPY vs {b}", mp.events(spy, C[b].dropna(), replace(cfg, bond=b)))
    for s in ("QQQ", "IWM"):
        line(f"  {s} vs TLT", mp.events(C[s].dropna(), tlt, replace(cfg, stock=s)))

    print("\n=== 6. Cost sensitivity (bp per side, 4 legs) ===")
    for c in (0.5, 1.0, 2.0, 3.0, 5.0):
        line(f"  {c} bp/side", mp.events(spy, tlt, replace(cfg, cost_bps_per_side=c)))

    print("\n=== 7. Placebo: same rule, random 5-session windows that do not touch the last 5 sessions (1000 draws) ===")
    real = ev[ev.side != 0].net.mean() + 4e-4
    fake = []
    months = per.unique()[1:]
    for _ in range(1000):
        vals = []
        for m in months:
            idx = np.flatnonzero(per == m)
            if len(idx) < 16: continue
            k = RNG.integers(idx[0] + 6, idx[-1] - 5)   # window end at least 5 sessions before month end
            spread = (df.s.iloc[k - 5] / df.s.iloc[idx[0] - 1] - 1) - (df.b.iloc[k - 5] / df.b.iloc[idx[0] - 1] - 1)
            side = -1 if spread > 0.03 else (1 if spread < -0.03 else 0)
            if side: vals.append(side * ((df.s.iloc[k] / df.s.iloc[k - 5] - 1) - (df.b.iloc[k] / df.b.iloc[k - 5] - 1)))
        fake.append(np.mean(vals))
    fake = np.array(fake)
    print(f"  real gross {real * 1e4:+.0f}bp | placebo mean {fake.mean() * 1e4:+.0f}bp sd {fake.std() * 1e4:.0f}bp | p(placebo >= real) = {(fake >= real).mean():.3f}")
    # a second control: shift the whole window one week earlier (sessions -10..-5)
    vals = []
    for m in months:
        idx = np.flatnonzero(per == m)
        if len(idx) < 12: continue
        k = idx[-1] - 5
        spread = (df.s.iloc[k - 5] / df.s.iloc[idx[0] - 1] - 1) - (df.b.iloc[k - 5] / df.b.iloc[idx[0] - 1] - 1)
        side = -1 if spread > 0.03 else (1 if spread < -0.03 else 0)
        if side: vals.append(side * ((df.s.iloc[k] / df.s.iloc[k - 5] - 1) - (df.b.iloc[k] / df.b.iloc[k - 5] - 1)) - 4e-4)
    vals = pd.Series(vals)
    print(f"  the week BEFORE (sessions -10..-5), same rule: {vals.mean() * 1e4:+.0f}bp t {tstat(vals):+.1f} n {len(vals)}  (should be ~0 if the flow is month-end specific)")

    print("\n=== 8. Tail ===")
    t = ev[ev.side != 0].sort_values("net")
    print("  worst 5: " + ", ".join(f"{r.month} {r.net * 1e4:+.0f}" for _, r in t.head(5).iterrows()))
    print("  best 5: " + ", ".join(f"{r.month} {r.net * 1e4:+.0f}" for _, r in t.tail(5).iterrows()))
    print(f"  p5 {t.net.quantile(0.05) * 1e4:+.0f}bp  p95 {t.net.quantile(0.95) * 1e4:+.0f}bp  worst daily pair move {r.min():+.2%}  max consecutive losers {max((len(list(g)) for k, g in __import__('itertools').groupby(t.sort_values('signal_date').net < 0) if k), default=0)}")

    print("\n=== 9. Legs separately (is it the stock leg, the bond leg, or the pair?) ===")
    t = ev[ev.side != 0]
    for lab, x in (("stock leg alone (side x SPY return)", t.side * t.stock_ret - 2e-4), ("bond leg alone (-side x TLT return)", -t.side * t.bond_ret - 2e-4)):
        print(f"  {lab:48s} mean {x.mean() * 1e4:+.0f}bp t {tstat(x):+.1f} hit {(x > 0).mean():.2f}")

    print("\n=== 10. Overlap with E v3 (daily) and effect on an E v3 book ===")
    vix = C["^VIX"].dropna()
    e_rets = []
    for s in ("SPY", "QQQ", "IWM", "GLD"):
        d = pd.DataFrame({"open": O[s], "close": C[s]}).dropna()
        e_rets.append(ov.backtest_single(d, ov.E_V2_VOL_CONFIG, vix=vix)["net_return"])
    e3 = pd.concat(e_rets, axis=1).mean(axis=1).dropna()
    both = pd.DataFrame({"e3": e3, "m": r}).dropna(); both = both[both.index >= "2004-11-01"]
    print(f"  corr(E v3 daily, pair daily) = {both.e3.corr(both.m):+.3f} (in-market days only {both[both.m != 0].e3.corr(both[both.m != 0].m):+.3f})")
    print(f"  E v3 alone Sharpe {sh(both.e3):.2f} MaxDD {dd(both.e3):+.1%} | pair alone {sh(both.m):.2f} | E v3 + pair at 0.5x notional: Sharpe {sh(both.e3 + 0.5 * both.m):.2f} MaxDD {dd(both.e3 + 0.5 * both.m):+.1%} | at 1x: {sh(both.e3 + both.m):.2f} MaxDD {dd(both.e3 + both.m):+.1%}")
    e3h, mh = both.e3[both.index >= "2014-01-01"], both.m[both.index >= "2014-01-01"]
    print(f"  2014-: E v3 {sh(e3h):.2f} -> E v3 + pair 0.5x {sh(e3h + 0.5 * mh):.2f} -> 1x {sh(e3h + mh):.2f}")

    print("\n=== 11. Sizing on a $25k account (ETF rail; no micro Treasury future exists, ZN is ~$110k) ===")
    t = ev[ev.side != 0]
    for notional in (12500, 25000):
        print(f"  pair notional ${notional:,} per leg: avg {t.net.mean() * notional:+.0f}$/event, ~{len(t) / t.month.str[:4].nunique():.1f} events/yr -> {t.net.sum() / t.month.str[:4].nunique() * notional:+.0f}$/yr; worst event {t.net.min() * notional:+.0f}$; needs margin for the short leg")
    print("  the short leg is an ETF short (SPY or TLT) - needs a margin account; the long leg is cash. Hold is 5 sessions, so borrow cost is negligible.")


if __name__ == "__main__":
    main()
