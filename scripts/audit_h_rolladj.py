"""Sleeve H (Hong-Yogo hedger pressure) re-run on roll-adjusted commodity
returns.  The original audit used yfinance front-month series (spliced).
Commodities are where the roll gap is largest, so this is the sleeve most
exposed to that flaw.  Monthly resolution (last COT report of the month ->
next month's return), 10 of H's 12 markets (CL, NG pairs missing).

Signals exactly as in ten_cent_bot.commodity_cot: cross-sectional top-N by
HP (long-only and long-short), and time-series 52-week percentile.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from audit_carry import adjusted_returns, load_all  # noqa: E402

from ten_cent_bot import commodity_cot as cc  # noqa: E402

ROOTS = {"GC=F": "GC", "SI=F": "SI", "HG=F": "HG", "ZC=F": "ZC", "ZS=F": "ZS", "ZW=F": "ZW", "SB=F": "SB", "CT=F": "CT", "KC=F": "KC", "LE=F": "LE"}


def sharpe_m(r):
    r = r.dropna(); return float(r.mean() / r.std() * np.sqrt(12)) if len(r) > 12 and r.std() > 0 else np.nan


def summ(r):
    r = r.dropna(); eq = (1 + r).cumprod()
    return f"Sharpe {sharpe_m(r):5.2f}  CAGR {((1+r.mean())**12-1):6.2%}  MaxDD {((eq-eq.cummax())/eq.cummax()).min():6.1%}  n={len(r)}"


def main():
    print("fetching Disaggregated COT ...")
    hp = {}
    for yf_sym, name in cc.COMMODITY_UNIVERSE.items():
        if yf_sym not in ROOTS:
            continue
        cot = cc.fetch_disaggregated(name)
        if cot.empty:
            print(f"  {ROOTS[yf_sym]}: no COT"); continue
        h = cc.compute_hedger_pressure(cot)
        # last report of each month, available by month-end (report lags 3 days; Tuesday->Friday)
        hp[ROOTS[yf_sym]] = h.resample("ME").last()
    hp = pd.DataFrame(hp)
    f1, f2 = load_all()
    mk = [m for m in hp.columns if m in f1.columns]
    f1 = f1[mk].loc["2006-01-01":]; f2 = f2[mk].reindex(f1.index)
    r_adj = adjusted_returns(f1, f2, verbose=False)
    r_raw = f1.pct_change()
    hp = hp[mk].reindex(f1.index)
    print(f"markets: {mk}; window {f1.index.min().date()} -> {f1.index.max().date()}")

    def run(sig: pd.DataFrame, rets: pd.DataFrame, cost=10.0) -> pd.Series:
        pos = sig.shift(1)
        return ((pos * rets).sum(axis=1) - pos.diff().abs().sum(axis=1) * cost / 1e4).dropna()

    def xs(top_n: int, long_only: bool) -> pd.DataFrame:
        ranks = hp.rank(axis=1, ascending=False, method="first"); n = hp.notna().sum(axis=1)
        sig = pd.DataFrame(0.0, index=hp.index, columns=hp.columns)
        sig[ranks.le(top_n)] = 1.0 / top_n
        if not long_only:
            sig[ranks.gt(n.values[:, None] - top_n) & hp.notna()] = -1.0 / top_n
        return sig

    def ts() -> pd.DataFrame:
        pct = hp.rolling(12).rank(pct=True)
        return (pct > 0.5).astype(float) / len(mk)

    print(f"\n{'variant':<26} {'roll-adjusted':<48} {'raw 1!':<48}")
    for label, sig in [("XS top-2 long-only", xs(2, True)), ("XS top-3 long-only", xs(3, True)), ("XS top-3 long-short", xs(3, False)), ("TS 12m percentile > 0.5", ts())]:
        print(f"{label:<26} {summ(run(sig, r_adj)):<48} {summ(run(sig, r_raw)):<48}")
    ew = pd.DataFrame(1.0 / len(mk), index=hp.index, columns=mk)
    print(f"{'EW long benchmark':<26} {summ(run(ew, r_adj)):<48} {summ(run(ew, r_raw)):<48}")

    print("\n=== Walk-forward (adjusted), XS top-3 long-short ===")
    ls = run(xs(3, False), r_adj); n = len(ls) // 2
    print("  train " + summ(ls.iloc[:n]) + "\n  test  " + summ(ls.iloc[n:]))

    print("\n=== Placebo: HP block-shuffled in time per market (12m blocks, 100 seeds), XS top-3 L/S on adjusted ===")
    rng = np.random.default_rng(8); real = sharpe_m(ls); pl = []
    for _ in range(100):
        sh = hp.copy()
        for c in sh.columns:
            v = sh[c].values.copy(); blocks = [v[i:i+12] for i in range(0, len(v), 12)]; rng.shuffle(blocks); sh[c] = np.concatenate(blocks)[: len(v)]
        ranks = sh.rank(axis=1, ascending=False, method="first"); nn = sh.notna().sum(axis=1)
        sig = pd.DataFrame(0.0, index=sh.index, columns=sh.columns); sig[ranks.le(3)] = 1 / 3; sig[ranks.gt(nn.values[:, None] - 3) & sh.notna()] = -1 / 3
        pl.append(sharpe_m(run(sig, r_adj)))
    pl = np.array(pl); print(f"  real {real:.2f} vs placebo {np.nanmean(pl):.2f} +/- {np.nanstd(pl):.2f}, p={float((pl>=real).mean()):.3f}")


if __name__ == "__main__":
    main()
