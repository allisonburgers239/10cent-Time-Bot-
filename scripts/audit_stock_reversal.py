"""Audit: the two single-stock effects from screen_single_stocks.py, traded
as baskets.

K1  Weekly reversal (Lehmann 1990, Jegadeesh 1990): each Friday, rank the
    40-stock universe by trailing 5-day return; long the bottom 5, short the
    top 5, equal weight, hold 5 days.  Also long-only bottom-5 vs the
    equal-weight universe.  Cost 10bps per side per rebalance.
K2  "E on stocks": equal-weight overnight (close -> next open) across the 40
    names, 3bps/side (single-stock spreads), vs Sleeve E (SPY/QQQ/IWM, 1bp).

Survivorship warning: the universe is 40 names that are large TODAY.  That
flatters anything long-biased (K2, and the long leg of K1).  The L/S K1
spread is less exposed; the long-only numbers should be discounted.
Sections: baseline, walk-forward, grid (N, lookback), sub-periods, cost,
placebo, and for K2 a correlation/blend check with E.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import yfinance as yf

from ten_cent_bot.metrics import max_drawdown, sharpe

STOCKS = ["TSLA", "NVDA", "PLTR", "V", "AAPL", "MSFT", "AMZN", "GOOGL", "META", "NFLX", "AMD", "AVGO", "CRM", "ORCL", "UBER", "COIN",
          "JPM", "BAC", "GS", "MA", "PYPL", "XOM", "CVX", "JNJ", "PFE", "UNH", "MRK", "WMT", "COST", "HD", "NKE", "DIS", "MCD", "KO",
          "BA", "GE", "CAT", "F", "T", "INTC"]


def S(r, ppy):
    r = r.dropna(); eq = (1 + r).cumprod()
    return f"Sharpe {sharpe(r, ppy):5.2f}  CAGR {((1+r.mean())**ppy-1):6.2%}  Vol {r.std(ddof=0)*np.sqrt(ppy):5.1%}  MaxDD {max_drawdown(eq):6.1%}  n={len(r)}"


def weekly_reversal(px: pd.DataFrame, n: int = 5, lookback: int = 5, cost_bps: float = 10.0, long_only: bool = False):
    w = px.resample("W-FRI").last()
    past = w.pct_change(lookback // 5 if lookback >= 5 else 1) if lookback >= 5 else None
    past = w / w.shift(1) - 1 if lookback == 5 else w / w.shift(lookback // 5) - 1
    fwd = w.shift(-1) / w - 1
    pos = pd.DataFrame(0.0, index=w.index, columns=w.columns)
    for d in w.index:
        r = past.loc[d].dropna()
        if len(r) < 2 * n:
            continue
        rk = r.rank()
        pos.loc[d, rk[rk <= n].index] = 1.0 / n
        if not long_only:
            pos.loc[d, rk[rk > len(r) - n].index] = -1.0 / n
    gross = (pos * fwd).sum(axis=1)
    turn = pos.diff().abs().sum(axis=1).fillna(0)
    return (gross - turn * cost_bps / 1e4).dropna()


def main():
    data = yf.download(STOCKS, period="max", interval="1d", auto_adjust=True, progress=False)
    px = data["Close"].loc["2000-01-01":]; op = data["Open"].loc["2000-01-01":]
    px.index = pd.to_datetime(px.index).tz_localize(None); op.index = px.index
    print("=== K1. Weekly reversal, 40 stocks, 2000-2026 ===")
    ls = weekly_reversal(px); lo = weekly_reversal(px, long_only=True)
    w = px.resample("W-FRI").last(); ew = (w.shift(-1) / w - 1).mean(axis=1).dropna()
    print("  long-short bottom5/top5  " + S(ls, 52))
    print("  long-only bottom5        " + S(lo, 52))
    print("  EW universe (benchmark)  " + S(ew, 52))
    n = len(ls) // 2
    print(f"\n  walk-forward L/S: train {sharpe(ls.iloc[:n],52):.2f} -> test {sharpe(ls.iloc[n:],52):.2f}   ({ls.index[0].date()} -> {ls.index[n].date()} -> {ls.index[-1].date()})")
    print("\n  grid (L/S Sharpe): rows N, cols lookback weeks")
    rows = []
    for N in [3, 5, 8]:
        rows.append({"N": N, **{f"lb{lb}w": round(sharpe(weekly_reversal(px, n=N, lookback=lb * 5), 52), 2) for lb in [1, 2, 4]}})
    print(pd.DataFrame(rows).set_index("N").to_string())
    print("\n  sub-periods (L/S):")
    for start in range(2000, 2027, 4):
        r = ls[(ls.index.year >= start) & (ls.index.year < start + 4)]
        if len(r) > 50:
            print(f"    {start}-{start+3}: Sharpe {sharpe(r,52):+.2f}  CAGR {((1+r.mean())**52-1):+.1%}")
    print("\n  cost sensitivity (L/S): " + "  ".join(f"{c}bps {sharpe(weekly_reversal(px, cost_bps=c),52):.2f}" for c in [0, 5, 10, 20, 40]))
    rng = np.random.default_rng(3); real = sharpe(ls, 52); pl = []
    wk = px.resample("W-FRI").last(); fwd = wk.shift(-1) / wk - 1
    for _ in range(100):
        pos = pd.DataFrame(0.0, index=wk.index, columns=wk.columns)
        for d in wk.index:
            avail = wk.loc[d].dropna().index
            if len(avail) < 10:
                continue
            pick = rng.choice(avail, 10, replace=False)
            pos.loc[d, pick[:5]] = 0.2; pos.loc[d, pick[5:]] = -0.2
        r = ((pos * fwd).sum(axis=1) - pos.diff().abs().sum(axis=1).fillna(0) * 10 / 1e4).dropna()
        pl.append(sharpe(r, 52))
    pl = np.array(pl); print(f"  placebo (random 5/5 picks, same cost): real {real:.2f} vs {pl.mean():.2f} +/- {pl.std():.2f}, p={float((pl>=real).mean()):.3f}")

    print("\n=== K2. E on stocks: EW overnight across 40 names (3bps/side) vs E (SPY/QQQ/IWM, 1bp) ===")
    on = (op.shift(-1) / px - 1)
    e_stocks = (on - 6 / 1e4).mean(axis=1).dropna()
    d = yf.download(["SPY", "QQQ", "IWM"], period="max", interval="1d", auto_adjust=True, progress=False)
    e = pd.DataFrame({t: (d["Open"][t].shift(-1) - d["Close"][t]) / d["Close"][t] - 2 / 1e4 for t in ["SPY", "QQQ", "IWM"]}).mean(axis=1)
    e.index = pd.to_datetime(e.index).tz_localize(None)
    j = pd.concat([e_stocks.rename("E_stocks"), e.rename("E")], axis=1).dropna()
    print("  E on stocks  " + S(j.E_stocks, 252))
    print("  E            " + S(j.E, 252))
    print(f"  correlation {j.corr().iloc[0,1]:.2f};  50/50 blend " + S(0.5 * j.E_stocks + 0.5 * j.E, 252))
    n = len(j) // 2
    print(f"  walk-forward E_stocks: {sharpe(j.E_stocks.iloc[:n],252):.2f} -> {sharpe(j.E_stocks.iloc[n:],252):.2f};  E: {sharpe(j.E.iloc[:n],252):.2f} -> {sharpe(j.E.iloc[n:],252):.2f}")
    print("  cost sensitivity E_stocks: " + "  ".join(f"{c}bps/side {sharpe(((on - 2*c/1e4).mean(axis=1)).reindex(j.index).dropna(),252):.2f}" for c in [1, 3, 5, 10]))
    intra = (px / op - 1).mean(axis=1).reindex(j.index)
    print(f"  intraday EW basket for reference: " + S(intra, 252))
    print("  Survivorship: these 40 are today's large caps; a 2000-vintage universe would include names that died. Discount long-only results.")


if __name__ == "__main__":
    main()
