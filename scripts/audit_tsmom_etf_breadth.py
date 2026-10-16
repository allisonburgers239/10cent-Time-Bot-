"""Clean breadth test for Sleeve B on ETFs (no roll gaps), same code path
(ten_cent_bot.tsmom.backtest, default config, 10bps), common window 2007-06
onward so every basket sees the same months.

Baskets fixed in advance: B10 (deployed), +sectors (9 SPDRs), +countries
(EWJ FXI EWZ VGK EWY), +rates/credit (LQD HYG TIP), +commodities (SLV DBA),
all (29).  Report Sharpe/MaxDD, walk-forward, sub-periods, LOO of the
added group, placebo.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import yfinance as yf

from ten_cent_bot import tsmom
from ten_cent_bot.metrics import max_drawdown, sharpe

B10 = ["SPY", "QQQ", "IWM", "EFA", "EEM", "TLT", "IEF", "GLD", "USO", "DBC"]
SECT = ["XLE", "XLF", "XLK", "XLU", "XLV", "XLP", "XLI", "XLB", "XLY"]
CTRY = ["EWJ", "FXI", "EWZ", "VGK", "EWY"]
RATES = ["LQD", "HYG", "TIP"]
COMM = ["SLV", "DBA"]
BASKETS = {"B10 (deployed)": B10, "B10 + sectors": B10 + SECT, "B10 + countries": B10 + CTRY, "B10 + rates/credit": B10 + RATES, "B10 + commodities": B10 + COMM, "all 29": B10 + SECT + CTRY + RATES + COMM}


def run(m):
    return tsmom.backtest(m)["monthly_return_net"].dropna()


def main():
    px = yf.download(sorted(set(sum(BASKETS.values(), []))), period="max", interval="1d", auto_adjust=True, progress=False)["Close"]
    px.index = pd.to_datetime(px.index).tz_localize(None)
    m = px.resample("ME").last().loc["2006-06-01":]
    print("first month per ETF: " + ", ".join(f"{c}:{m[c].first_valid_index().strftime('%Y-%m')}" for c in m.columns))
    print(f"\n{'basket':<22} {'n':>3} {'Sharpe':>7} {'CAGR':>7} {'MaxDD':>7} {'WF train->test':>15} {'sub>0':>6}")
    rng = np.random.default_rng(6); base_r = None
    for name, tks in BASKETS.items():
        r = run(m[tks]).loc["2007-06-30":]
        if base_r is None: base_r = r
        n = len(r) // 2; subs = []
        for s0 in range(2008, 2027, 4):
            x = r[(r.index.year >= s0) & (r.index.year < s0 + 4)]
            if len(x) >= 24: subs.append(x.mean() > 0)
        print(f"{name:<22} {len(tks):>3} {sharpe(r,12):>7.2f} {((1+r.mean())**12-1):>7.2%} {max_drawdown((1+r).cumprod()):>7.1%} {sharpe(r.iloc[:n],12):>7.2f}->{sharpe(r.iloc[n:],12):<6.2f} {sum(subs):>3}/{len(subs)}")
    print("\n=== LOO on 'all 29': Sharpe when each ADDED group is removed ===")
    allk = BASKETS["all 29"]; full = sharpe(run(m[allk]).loc['2007-06-30':], 12)
    for g, tks in [("sectors", SECT), ("countries", CTRY), ("rates/credit", RATES), ("commodities", COMM)]:
        keep = [t for t in allk if t not in tks]
        print(f"  without {g:<13} {sharpe(run(m[keep]).loc['2007-06-30':],12):.2f} (full {full:.2f})")
    print("\n=== Placebo: random 10-ETF subsets of the 29 (100 draws) vs B10 ===")
    b10 = sharpe(base_r, 12); pl = []
    for _ in range(100):
        pick = list(rng.choice(allk, 10, replace=False)); pl.append(sharpe(run(m[pick]).loc["2007-06-30":], 12))
    pl = np.array(pl); print(f"  B10 {b10:.2f} vs random-10 {pl.mean():.2f} +/- {pl.std():.2f}, P(random>=B10)={float((pl>=b10).mean()):.2f}")
    print("  Reading: if random 10-ETF baskets match B10, the deployed basket choice is not special; if 'all 29' beats B10 in both halves, breadth helps on clean data.")


if __name__ == "__main__":
    main()
