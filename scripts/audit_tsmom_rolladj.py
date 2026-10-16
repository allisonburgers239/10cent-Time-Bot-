"""Gap fix: Sleeve B's OWN deployment basket, 12-month TSMOM, roll-adjusted
vs raw, on the TradingView 1!/2! monthly pairs (9 of the 10 markets; CL is
missing because the energy pairs never landed).

Same code path as the deployed sleeve (ten_cent_bot.tsmom.backtest, default
config, 10bps).  Raw = TradingView 1! continuous (spliced, same flaw as the
yfinance series the original audit used).  Adjusted = roll-month returns
taken on the contract actually held (see audit_carry.adjusted_returns).
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from audit_carry import adjusted_returns, load_all  # noqa: E402

from ten_cent_bot import tsmom  # noqa: E402

B_BASKET = ["ES", "NQ", "ZN", "ZB", "GC", "SI", "HG", "CL", "6E", "ZC"]


def run(rets: pd.DataFrame) -> pd.Series:
    px = (1 + rets.fillna(0)).cumprod()
    res = tsmom.backtest(px)
    pos = res["position"]
    return ((pos * rets).mean(axis=1) - pos.diff().abs().mean(axis=1) * 10 / 1e4).dropna()


def summ(r: pd.Series) -> str:
    sh = r.mean() / r.std() * np.sqrt(12); eq = (1 + r).cumprod()
    return f"Sharpe {sh:5.2f}  CAGR {((1+r.mean())**12-1):6.2%}  Vol {r.std()*np.sqrt(12):5.1%}  MaxDD {((eq-eq.cummax())/eq.cummax()).min():6.1%}  n={len(r)}"


def main() -> None:
    f1, f2 = load_all()
    have = [m for m in B_BASKET if m in f1.columns]
    print(f"B basket markets available: {have} (missing: {[m for m in B_BASKET if m not in f1.columns]})")
    f1 = f1[have].loc["2000-01-01":]; f2 = f2[have].reindex(f1.index)
    r_adj = adjusted_returns(f1, f2, verbose=False)
    r_raw = f1.pct_change()
    print("\n=== Sleeve B basket, 12m TSMOM, 2000-09 -> 2026-10 (matches audit_tsmom_futures.py window) ===")
    a, b = run(r_adj.loc["2000-09-01":]), run(r_raw.loc["2000-09-01":])
    print("  roll-adjusted  " + summ(a))
    print("  raw 1!         " + summ(b))
    print(f"  README (yfinance raw, 10 mkts incl. CL): Sharpe 0.46 at 10bps")
    print("\n=== Walk-forward halves (adjusted) ===")
    n = len(a) // 2
    print("  train " + summ(a.iloc[:n]) + "\n  test  " + summ(a.iloc[n:]))
    print("\n=== 4y sub-periods: adjusted vs raw Sharpe ===")
    for start in range(2001, 2027, 4):
        x = a[(a.index.year >= start) & (a.index.year < start + 4)]; y = b[(b.index.year >= start) & (b.index.year < start + 4)]
        if len(x) >= 24:
            print(f"  {start}-{start+3}: adj {x.mean()/x.std()*np.sqrt(12):+.2f}   raw {y.mean()/y.std()*np.sqrt(12):+.2f}")
    print("\n=== Per-market standalone TSMOM Sharpe: adjusted vs raw ===")
    for m in have:
        x = run(r_adj[[m]].loc["2000-09-01":]); y = run(r_raw[[m]].loc["2000-09-01":])
        print(f"  {m:<3} adj {x.mean()/x.std()*np.sqrt(12):+.2f}   raw {y.mean()/y.std()*np.sqrt(12):+.2f}   annual return gap (adj-raw, long-only) {(r_adj[m]-r_raw[m]).loc['2000-09-01':].mean()*12:+.2%}")
    print("\n=== Position agreement: how often do adjusted and raw signals disagree on direction? ===")
    sa = np.sign(tsmom.backtest((1 + r_adj.fillna(0)).cumprod())["signal"]); sr = np.sign(tsmom.backtest((1 + r_raw.fillna(0)).cumprod())["signal"])
    dis = (sa != sr) & sa.notna() & sr.notna()
    print("  " + "  ".join(f"{m}:{dis[m].mean():.0%}" for m in have))
    rng = np.random.default_rng(3); real = a.mean() / a.std() * np.sqrt(12)
    pl = []
    for _ in range(100):
        sg = pd.DataFrame(rng.choice([-1.0, 1.0], size=r_adj.shape), index=r_adj.index, columns=r_adj.columns)
        rv = r_adj.rolling(12).std() * np.sqrt(12); pos = ((0.10 / rv).clip(upper=2.0) * sg).shift(1)
        pr = ((pos * r_adj).mean(axis=1) - pos.diff().abs().mean(axis=1) * 10 / 1e4).loc["2000-09-01":].dropna()
        pl.append(pr.mean() / pr.std() * np.sqrt(12))
    pl = np.array(pl); print(f"\n  placebo (random signs, adjusted returns): real {real:.2f} vs {pl.mean():.2f} +/- {pl.std():.2f}, p={float((pl>=real).mean()):.3f}")


if __name__ == "__main__":
    main()
