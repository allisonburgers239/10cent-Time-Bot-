"""Sleeve E extension audit: add GLD to the overnight basket.

Pre-registered in screen_overnight_universe.py as the 'E+gold' group before
results were seen.  Runs through the shipped code path
(ten_cent_bot.overnight.backtest_portfolio) so what is audited is what would
run.  Variants fixed in advance: E, E+GLD (equal weight, 4 tickers), with and
without the E v2 reversal overlay (overlay on all four / on equities only).

Sections: 1 baseline, 2 walk-forward, 3 weight grid (GLD share), 4 sub-
periods, 5 leave-one-out, 6 cost, 7 placebo (GLD's overnight sign
randomized), 8 tail + crash windows, 9 tradability note (MGC on Tradovate;
MGC 5-min tracking check pending Ali's re-export).
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import yfinance as yf

from ten_cent_bot import overnight as ov
from ten_cent_bot.metrics import max_drawdown, sharpe, sortino

TK = ["SPY", "QQQ", "IWM", "GLD"]


def S(r):
    r = r.dropna(); eq = (1 + r).cumprod()
    return {"sharpe": sharpe(r, 252), "sortino": sortino(r, 252), "cagr": (1 + r.mean()) ** 252 - 1, "mdd": max_drawdown(eq), "n": len(r)}


def fmt(s): return f"Sharpe {s['sharpe']:5.2f}  Sortino {s['sortino']:5.2f}  CAGR {s['cagr']:6.2%}  MaxDD {s['mdd']:6.1%}"


def port(frames, cfg, weights=None):
    res = ov.backtest_portfolio(frames, cfg)["per_ticker"]
    df = pd.DataFrame({t: r["net_return"] for t, r in res.items()}).dropna()
    if weights is None:
        return df.mean(axis=1)
    w = pd.Series(weights); w = w / w.sum()
    return (df[w.index] * w).sum(axis=1)


def main():
    d = yf.download(TK, period="max", interval="1d", auto_adjust=True, progress=False)
    frames = {t: pd.DataFrame({"open": d["Open"][t], "close": d["Close"][t]}).dropna() for t in TK}
    for f in frames.values():
        f.index = pd.to_datetime(f.index).tz_localize(None)
    start = max(f.index.min() for f in frames.values())
    frames = {t: f.loc[start:] for t, f in frames.items()}
    eq_frames = {t: frames[t] for t in ["SPY", "QQQ", "IWM"]}
    base, v2 = ov.OvernightConfig(), ov.E_V2_CONFIG
    E = port(eq_frames, base); EG = port(frames, base); E2 = port(eq_frames, v2); E2G_all = port(frames, v2)
    E2G_eqonly = (pd.concat([pd.DataFrame({t: ov.backtest_single(frames[t], v2)["net_return"] for t in ["SPY", "QQQ", "IWM"]}), ov.backtest_single(frames["GLD"], base)["net_return"].rename("GLD")], axis=1).dropna()).mean(axis=1)
    print(f"window {start.date()} -> {frames['SPY'].index.max().date()}")
    print("\n=== 1. Baseline (equal weight, 1bp/side) ===")
    for lab, r in [("E", E), ("E + GLD", EG), ("E v2", E2), ("E v2 + GLD (overlay on all 4)", E2G_all), ("E v2 + GLD (overlay on equities only)", E2G_eqonly)]:
        print(f"  {lab:<40} " + fmt(S(r)))
    gld = ov.backtest_single(frames["GLD"], base)["net_return"]
    print(f"  GLD overnight alone                      " + fmt(S(gld)) + f"   corr with E {gld.corr(E):+.2f}")

    print("\n=== 2. Walk-forward halves ===")
    n = len(E) // 2
    for lab, r in [("E", E), ("E + GLD", EG), ("E v2 + GLD (all)", E2G_all)]:
        print(f"  {lab:<20} {sharpe(r.iloc[:n],252):.2f} -> {sharpe(r.iloc[n:],252):.2f}   MaxDD {max_drawdown((1+r.iloc[:n]).cumprod()):.1%} / {max_drawdown((1+r.iloc[n:]).cumprod()):.1%}")

    print("\n=== 3. GLD weight grid (rest equal across SPY/QQQ/IWM), base E ===")
    for wg in [0.0, 0.15, 0.25, 0.33, 0.4, 0.5]:
        w = {"SPY": (1 - wg) / 3, "QQQ": (1 - wg) / 3, "IWM": (1 - wg) / 3, "GLD": wg}
        r = port(frames, base, w); print(f"  GLD {wg:.2f}: " + fmt(S(r)))

    print("\n=== 4. Sub-periods (4y): E -> E+GLD Sharpe / MaxDD ===")
    for s0 in range(2005, 2027, 4):
        w = (E.index.year >= s0) & (E.index.year < s0 + 4)
        if w.sum() < 300: continue
        print(f"  {s0}-{s0+3}: {sharpe(E[w],252):+.2f}/{max_drawdown((1+E[w]).cumprod()):.1%} -> {sharpe(EG[w],252):+.2f}/{max_drawdown((1+EG[w]).cumprod()):.1%}")

    print("\n=== 5. Leave-one-out (E+GLD) ===")
    for drop in TK:
        keep = {t: f for t, f in frames.items() if t != drop}
        print(f"  drop {drop}: " + fmt(S(port(keep, base))))

    print("\n=== 6. Cost (bps/side, all legs) ===")
    for c in [0.5, 1, 2, 3, 5]:
        cfg = ov.OvernightConfig(cost_bps_per_side=c)
        print(f"  {c:>3} bps: E {sharpe(port(eq_frames, cfg),252):.2f} -> E+GLD {sharpe(port(frames, cfg),252):.2f}")

    print("\n=== 7. Placebo: GLD's nightly sign randomized (200 seeds), E+GLD Sharpe ===")
    rng = np.random.default_rng(4); real = S(EG)["sharpe"]
    eqs = pd.DataFrame({t: ov.backtest_single(frames[t], base)["net_return"] for t in ["SPY", "QQQ", "IWM"]})
    g_on = frames["GLD"]["open"].shift(-1) / frames["GLD"]["close"] - 1
    pl = []
    for _ in range(200):
        gp = g_on * rng.choice([-1.0, 1.0], len(g_on)) - 2 / 1e4
        pl.append(sharpe(pd.concat([eqs, gp.rename("GLD")], axis=1).dropna().mean(axis=1), 252))
    pl = np.array(pl); print(f"  real {real:.3f} vs placebo {pl.mean():.3f} +/- {pl.std():.3f}  P(placebo>=real)={float((pl>=real).mean()):.3f}")

    print("\n=== 8. Tail / crash windows: E vs E+GLD ===")
    for lab, a, b in [("2008-09..11", "2008-09-01", "2008-11-30"), ("2020-02..03", "2020-02-20", "2020-03-31"), ("2022", "2022-01-01", "2022-12-31"), ("2025-04", "2025-04-01", "2025-04-15")]:
        print(f"  {lab:<12} E {E.loc[a:b].sum():+7.2%}   E+GLD {EG.loc[a:b].sum():+7.2%}   GLD leg {gld.loc[a:b].sum():+7.2%}")
    print(f"  worst night: E {E.min():.2%} ({E.idxmin().date()})  E+GLD {EG.min():.2%} ({EG.idxmin().date()})")
    print("\n=== 9. Tradability: GLD overnight = 16:00 -> 09:30 ET. MGC (micro gold, Tradovate) trades through; tracking check needs the MGC 5-min re-export on issue #3 (current file has 2 days).")


if __name__ == "__main__":
    main()
