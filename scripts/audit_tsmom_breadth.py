"""Breadth test for Sleeve B: does the audited 12-month TSMOM rule get
better when the basket goes from 10 markets to ~30?

Same code path as the deployed sleeve (ten_cent_bot.tsmom.backtest, default
config, 10bps cost) and the same data source as audit_tsmom_futures.py
(yfinance front-month continuous `=F`, so the roll-gap caveat applies
equally to every basket here - this is apples to apples, not an absolute
Sharpe claim).

Hurst-Ooi-Pedersen (2017) and the CTA literature: breadth is the first-
order lever for trend-following Sharpe because single-market trend Sharpe
is ~0.2-0.3 with low pairwise correlation.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import yfinance as yf

from ten_cent_bot import tsmom

BASKETS = {
    "B deployed (10)": ["ES=F", "NQ=F", "ZN=F", "ZB=F", "GC=F", "SI=F", "HG=F", "CL=F", "6E=F", "ZC=F"],
    "equities (6)": ["ES=F", "NQ=F", "YM=F", "RTY=F", "NKD=F", "6E=F"],
}
BROAD = [
    "ES=F", "NQ=F", "YM=F", "RTY=F", "NKD=F",                    # equity index
    "ZT=F", "ZF=F", "ZN=F", "ZB=F",                               # rates
    "6E=F", "6B=F", "6J=F", "6A=F", "6C=F", "6S=F",               # FX
    "GC=F", "SI=F", "HG=F", "PL=F", "PA=F",                       # metals
    "CL=F", "NG=F", "RB=F", "HO=F",                               # energy
    "ZC=F", "ZS=F", "ZW=F", "ZM=F", "ZL=F", "KE=F",               # grains
    "KC=F", "SB=F", "CT=F", "CC=F",                               # softs
    "LE=F", "HE=F", "GF=F",                                       # livestock
]
BASKETS["broad (all)"] = BROAD
BASKETS["broad ex-equity"] = [s for s in BROAD if s not in ("ES=F", "NQ=F", "YM=F", "RTY=F", "NKD=F")]
BASKETS["commodities only"] = [s for s in BROAD if s in ("GC=F", "SI=F", "HG=F", "PL=F", "PA=F", "CL=F", "NG=F", "RB=F", "HO=F", "ZC=F", "ZS=F", "ZW=F", "ZM=F", "ZL=F", "KE=F", "KC=F", "SB=F", "CT=F", "CC=F", "LE=F", "HE=F", "GF=F")]
BASKETS["financials only"] = [s for s in BROAD if s in ("ES=F", "NQ=F", "YM=F", "RTY=F", "NKD=F", "ZT=F", "ZF=F", "ZN=F", "ZB=F", "6E=F", "6B=F", "6J=F", "6A=F", "6C=F", "6S=F")]


def monthly_closes(symbols: list[str]) -> pd.DataFrame:
    d = yf.download(symbols, period="max", interval="1d", auto_adjust=True, progress=False)["Close"]
    d.index = pd.to_datetime(d.index).tz_localize(None)
    m = d.resample("ME").last()
    return m.loc["2000-01-01":]


def main() -> None:
    px = monthly_closes(sorted(set(sum(BASKETS.values(), []))))
    print("history start per market:")
    starts = px.apply(lambda s: s.first_valid_index())
    print("  " + ", ".join(f"{k.replace('=F','')}:{v.year}" for k, v in starts.sort_values().items()))
    missing = [c for c in px.columns if px[c].notna().sum() < 36]
    if missing:
        print("  dropping (no data):", missing)
        px = px.drop(columns=missing)

    print(f"\n{'basket':<22} {'n':>3} {'Sharpe':>7} {'CAGR':>7} {'Vol':>6} {'MaxDD':>7}  {'sub-periods>0':>14}  placebo p")
    rng = np.random.default_rng(5)
    for name, syms in BASKETS.items():
        syms = [s for s in syms if s in px.columns]
        res = tsmom.backtest(px[syms])
        s = tsmom.summary(res)
        ret = res["monthly_return_net"].dropna()
        subs = []
        for start in range(2001, 2027, 4):
            r = ret[(ret.index.year >= start) & (ret.index.year < start + 4)]
            if len(r) >= 24:
                subs.append(r.mean() > 0)
        # placebo: random sign per market per month, same vol sizing
        real = s["sharpe"]
        pl = []
        for _ in range(100):
            sg = pd.DataFrame(rng.choice([-1.0, 1.0], size=px[syms].shape), index=px.index, columns=syms)
            mr = px[syms].pct_change()
            rv = mr.rolling(12).std() * np.sqrt(12)
            pos = ((0.10 / rv).clip(upper=2.0) * sg).shift(1)
            pr = (pos * mr).mean(axis=1) - pos.diff().abs().mean(axis=1) * 10 / 1e4
            pr = pr.dropna()
            pl.append(pr.mean() / pr.std() * np.sqrt(12) if pr.std() > 0 else 0)
        p = float((np.array(pl) >= real).mean())
        print(f"{name:<22} {len(syms):>3} {s['sharpe']:>7.2f} {s['cagr']:>7.2%} {s['annual_vol']:>6.1%} {s['max_drawdown']:>7.1%}  {sum(subs):>6}/{len(subs):<7}  {p:.3f}")

    print("\nPer-market standalone 12m TSMOM Sharpe (vol-scaled, 10bps):")
    rows = []
    for c in px.columns:
        r = tsmom.backtest(px[[c]])["monthly_return_net"].dropna()
        rows.append((c.replace("=F", ""), r.mean() / r.std() * np.sqrt(12) if r.std() > 0 else np.nan, len(r)))
    rows.sort(key=lambda x: -x[1])
    print("  " + "  ".join(f"{a}:{b:+.2f}" for a, b, n in rows))
    print(f"  mean {np.nanmean([b for _,b,_ in rows]):.2f}, median {np.nanmedian([b for _,b,_ in rows]):.2f}, share>0 {np.mean([b>0 for _,b,_ in rows]):.0%}")

    print("\nAverage pairwise correlation of monthly TSMOM P&L streams:")
    pnl = pd.DataFrame({c: tsmom.backtest(px[[c]])["monthly_return_net"] for c in px.columns})
    cm = pnl.corr().values
    print(f"  {cm[np.triu_indices_from(cm, 1)].mean():.3f}")


if __name__ == "__main__":
    main()
