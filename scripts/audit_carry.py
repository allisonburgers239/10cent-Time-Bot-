"""Sleeve K audit: futures carry on whatever 1!/2! monthly pairs exist in
data/tv/ (TradingView MCP exports), plus the breadth/roll-adjustment
check for Sleeve B on the same data.

Roll-adjusted monthly return (the thing a monthly-rebalanced holder
actually earns):
    no roll in month t :  F1_t / F1_{t-1} - 1
    roll in month t    :  F1_t / F2_{t-1} - 1     (hold last month's 2nd
                          contract, which became the front)
Roll months come from each market's listed-contract cycle (CYCLES below);
'in' = contract expires inside its named month (ES Mar expires in March),
'before' = expires the month before (CL Apr expires ~Mar 20).

Sections: 0 carry stats + IC, 1 baseline TS carry, 2 walk-forward,
3 grid, 4 sub-periods, 5 leave-one-out, 6 cost, 7 placebo,
8 TSMOM adjusted vs unadjusted on the same markets + B/K blend.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats as sps

from ten_cent_bot import carry as K
from ten_cent_bot import tsmom
from ten_cent_bot.tv_mcp import load_pair

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "tv"
ALL = (1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12)
CYCLES: dict[str, tuple[tuple[int, ...], str]] = {
    "ES": ((3, 6, 9, 12), "in"), "NQ": ((3, 6, 9, 12), "in"),
    "6E": ((3, 6, 9, 12), "in"), "6B": ((3, 6, 9, 12), "in"), "6J": ((3, 6, 9, 12), "in"),
    "6A": ((3, 6, 9, 12), "in"), "6C": ((3, 6, 9, 12), "in"), "6S": ((3, 6, 9, 12), "in"),
    "ZN": ((3, 6, 9, 12), "in"), "ZB": ((3, 6, 9, 12), "in"), "ZF": ((3, 6, 9, 12), "in"),
    "GC": ((2, 4, 6, 8, 10, 12), "in"), "SI": ((3, 5, 7, 9, 12), "in"), "HG": ((3, 5, 7, 9, 12), "in"),
    "PL": ((1, 4, 7, 10), "in"), "PA": ((3, 6, 9, 12), "in"),
    "CL": (ALL, "before"), "NG": (ALL, "before"), "RB": (ALL, "before"), "HO": (ALL, "before"),
    "ZC": ((3, 5, 7, 9, 12), "in"), "ZW": ((3, 5, 7, 9, 12), "in"), "ZS": ((1, 3, 5, 7, 8, 9, 11), "in"),
    "SB": ((3, 5, 7, 10), "before"), "KC": ((3, 5, 7, 9, 12), "in"), "CT": ((3, 5, 7, 10, 12), "in"),
    "LE": ((2, 4, 6, 8, 10, 12), "in"), "HE": ((2, 4, 5, 6, 7, 8, 10, 12), "in"),
}
EXCHANGES = ["CME_MINI", "CME", "CBOT", "COMEX", "NYMEX", "ICEUS", "NYBOT"]


def roll_in_month(root: str, idx: pd.DatetimeIndex) -> pd.Series:
    months, where = CYCLES[root]
    out = []
    for ts in idx:
        m = ts.month
        probe = m if where == "in" else (m % 12) + 1
        out.append(probe in months)
    return pd.Series(out, index=idx)


def load_all() -> tuple[pd.DataFrame, pd.DataFrame]:
    f1s, f2s = {}, {}
    for root in CYCLES:
        for ex in EXCHANGES:
            pair = load_pair(DATA, ex, root)
            if pair:
                f1s[root], f2s[root] = pair
                break
    f1 = pd.DataFrame(f1s).sort_index()
    f2 = pd.DataFrame(f2s).sort_index()
    return f1, f2


def _adjust(a: pd.Series, b: pd.Series, roll: pd.Series) -> pd.Series:
    r_cont = a / a.shift(1) - 1
    r_roll = a / b.shift(1) - 1
    return r_roll.where(roll, r_cont)


def _roll_series(root: str, idx: pd.DatetimeIndex, where: str) -> pd.Series:
    months, _ = CYCLES[root]
    return pd.Series([((ts.month if where == "in" else (ts.month % 12) + 1) in months) for ts in idx], index=idx)


# Mechanics-based default: cash-settled or expiry-rolled contracts roll inside
# the contract month; physically delivered ones roll at first notice, the
# month before.  Overridden per market by the yfinance check below when a
# yfinance front-month series exists.
DEFAULT_RULE = {r: ("in" if r in ("ES", "NQ", "6E", "6B", "6J", "6A", "6C", "6S", "HE") else "before") for r in CYCLES}


def detect_roll_rule(root: str, tv_close: pd.Series) -> tuple[str, str]:
    """Yahoo's `=F` series rolls at expiry; TradingView's 1! rolls at first
    notice for deliverable contracts.  Months where the two monthly returns
    disagree by > 3 sigma are therefore TradingView's roll months.  Return
    (rule, note)."""
    try:
        import yfinance as yf
        y = yf.download(f"{root}=F", period="max", interval="1d", auto_adjust=True, progress=False)["Close"].squeeze()
        y.index = pd.to_datetime(y.index).tz_localize(None)
        ym = y.resample("ME").last()
    except Exception:
        return DEFAULT_RULE[root], "no yfinance"
    j = pd.concat([tv_close.rename("tv"), ym.rename("yf")], axis=1).dropna()
    if len(j) < 60:
        return DEFAULT_RULE[root], "short overlap"
    d = (j.tv.pct_change() - j.yf.pct_change()).dropna()
    big = d[d.abs() > 3 * d.std()]
    if len(big) < 3:
        return DEFAULT_RULE[root], f"only {len(big)} disagreement months"
    months, _ = CYCLES[root]
    hit_in = np.mean([ts.month in months for ts in big.index])
    hit_before = np.mean([((ts.month % 12) + 1) in months for ts in big.index])
    note = f"{len(big)} disagreement months: in-match {hit_in:.0%}, before-match {hit_before:.0%}"
    if len(big) >= 5 and abs(hit_in - hit_before) >= 0.25:
        return ("in" if hit_in > hit_before else "before"), note + " -> decisive"
    return DEFAULT_RULE[root], note + " -> not decisive, default"


def adjusted_returns(f1: pd.DataFrame, f2: pd.DataFrame, verbose: bool = True) -> pd.DataFrame:
    out = {}
    if verbose:
        print("  roll rule per market (from yfinance disagreement months; default by contract mechanics):")
    for c in f1.columns:
        a, b = f1[c], f2[c].reindex(f1.index)
        rule, note = detect_roll_rule(c, a)
        out[c] = _adjust(a, b, _roll_series(c, f1.index, rule))
        if verbose:
            print(f"    {c:<4} {rule:<7} ({note})")
    return pd.DataFrame(out)


def ew_long_benchmark(rets: pd.DataFrame, cost_bps=10.0) -> pd.Series:
    rv = rets.rolling(12).std() * np.sqrt(12)
    w = (0.10 / rv).clip(upper=2.0).shift(1)
    return (w * rets).mean(axis=1) - w.diff().abs().mean(axis=1) * cost_bps / 1e4


def summ(r: pd.Series) -> str:
    r = r.dropna()
    if len(r) < 24:
        return "n/a"
    sh = r.mean() / r.std() * np.sqrt(12)
    eq = (1 + r).cumprod()
    mdd = ((eq - eq.cummax()) / eq.cummax()).min()
    return f"Sharpe {sh:5.2f}  CAGR {((1+r.mean())**12-1):6.2%}  Vol {r.std()*np.sqrt(12):5.1%}  MaxDD {mdd:6.1%}  n={len(r)}"


def sharpe_m(r: pd.Series) -> float:
    r = r.dropna()
    return float(r.mean() / r.std() * np.sqrt(12)) if len(r) > 12 and r.std() > 0 else np.nan


def main() -> None:
    f1, f2 = load_all()
    if f1.empty:
        print("no 1!/2! pairs found in data/tv"); return
    f1 = f1.loc["1995-01-01":]; f2 = f2.reindex(f1.index)
    print(f"markets with both legs: {list(f1.columns)}  ({f1.index.min().date()} -> {f1.index.max().date()})")
    cry = K.compute_carry(f1, f2)
    print("\n=== roll adjustment ===")
    r_adj = adjusted_returns(f1, f2)
    r_raw = f1.pct_change()

    print("\n=== 0. Carry statistics and predictive power ===")
    print(f"  {'mkt':<4} {'mean carry':>10} {'%backwd':>8} {'IC(t,t+1)':>10} {'t(sign)':>8}  {'roll-adj minus raw ann.ret':>26}")
    ics = []
    for c in f1.columns:
        x = cry[c]; y = r_adj[c].shift(-1)
        j = pd.concat([x, y], axis=1).dropna()
        ic = sps.spearmanr(j.iloc[:, 0], j.iloc[:, 1]).statistic if len(j) > 24 else np.nan
        sgn = np.sign(j.iloc[:, 0]) * j.iloc[:, 1]
        t = sgn.mean() / (sgn.std(ddof=1) / np.sqrt(len(sgn))) if len(sgn) > 24 else np.nan
        diff = (r_adj[c].mean() - r_raw[c].mean()) * 12
        ics.append(ic)
        print(f"  {c:<4} {x.mean():>10.3f} {(x>0).mean():>8.0%} {ic:>10.3f} {t:>8.2f}  {diff:>26.2%}")
    cs_ic = []
    for t_, row in cry.iterrows():
        nxt = r_adj.shift(-1).loc[t_]
        j = pd.concat([row, nxt], axis=1).dropna()
        if len(j) >= 5:
            cs_ic.append(sps.spearmanr(j.iloc[:, 0], j.iloc[:, 1]).statistic)
    cs_ic = pd.Series(cs_ic)
    print(f"  mean per-market IC {np.nanmean(ics):.3f};  cross-sectional IC mean {cs_ic.mean():.3f}, t={cs_ic.mean()/(cs_ic.std()/np.sqrt(len(cs_ic))):.2f} over {len(cs_ic)} months")

    base = K.CarryConfig()
    print("\n=== 1. Baseline: time-series carry, vol-scaled, 10bps (roll-adjusted returns) ===")
    bt = K.backtest(f1, cry, base); bt["monthly_return_net"] = None  # recompute on adjusted
    def run(cfg, rets):
        res = K.backtest(f1, cry, cfg)
        pos = res["position"]
        net = (pos * rets).mean(axis=1) - pos.diff().abs().mean(axis=1) * cfg.transaction_cost_bps / 1e4
        return net
    net = run(base, r_adj)
    print("  TS carry           " + summ(net))
    print("  EW long benchmark  " + summ(ew_long_benchmark(r_adj)))
    print("  TS carry on RAW    " + summ(run(base, r_raw)) + "   <- unadjusted series, for comparison")

    print("\n=== 2. Walk-forward halves ===")
    n = len(net.dropna()) // 2; idx = net.dropna().index
    print("  train " + summ(net.loc[: idx[n]]) + "\n  test  " + summ(net.loc[idx[n]:]))

    print("\n=== 3. Grid ===")
    rows = []
    for mode in ["time_series", "cross_sectional"]:
        for sm in [1, 3, 6]:
            for tv in [0.05, 0.10, 0.15]:
                cfg = K.CarryConfig(mode=mode, smooth_months=sm, target_vol=tv)
                rows.append({"mode": mode, "smooth": sm, "tv": tv, "sharpe": sharpe_m(run(cfg, r_adj))})
    g = pd.DataFrame(rows)
    print(g.pivot_table(index=["mode", "smooth"], columns="tv", values="sharpe").round(2).to_string())
    print(f"  Sharpe>0: {(g.sharpe>0).mean():.0%}, mean {g.sharpe.mean():.2f}")

    print("\n=== 4. Sub-periods (4y) ===")
    for start in range(1996, 2027, 4):
        r = net[(net.index.year >= start) & (net.index.year < start + 4)]
        if len(r.dropna()) >= 24:
            print(f"  {start}-{start+3}: " + summ(r))

    print("\n=== 5. Leave-one-out ===")
    full = sharpe_m(net)
    for c in f1.columns:
        keep = [k for k in f1.columns if k != c]
        res = K.backtest(f1[keep], cry[keep], base)["position"]
        nn = (res * r_adj[keep]).mean(axis=1) - res.diff().abs().mean(axis=1) * 10 / 1e4
        print(f"  drop {c}: {sharpe_m(nn):5.2f} ({sharpe_m(nn)-full:+.2f})")

    print("\n=== 6. Cost sensitivity ===")
    for c in [0, 10, 25, 50, 100]:
        print(f"  {c:>3} bps: " + summ(run(K.CarryConfig(transaction_cost_bps=c), r_adj)))

    print("\n=== 7. Placebo: carry signal block-shuffled in time per market (100 seeds) ===")
    rng = np.random.default_rng(9)
    rv = r_adj.rolling(12).std() * np.sqrt(12)
    w = (0.10 / rv).clip(upper=2.0)
    pl = []
    for _ in range(100):
        sh = cry.copy()
        for c in sh.columns:
            v = sh[c].values.copy()
            blocks = [v[i:i+12] for i in range(0, len(v), 12)]
            rng.shuffle(blocks)
            sh[c] = np.concatenate(blocks)[: len(v)]
        pos = (w * np.sign(sh)).shift(1)
        pl.append(sharpe_m((pos * r_adj).mean(axis=1) - pos.diff().abs().mean(axis=1) * 10 / 1e4))
    pl = np.array(pl); p = float((pl >= full).mean())
    print(f"  real {full:.2f}  placebo {pl.mean():.2f} +/- {pl.std():.2f}  P(placebo>=real)={p:.3f}  {'REAL' if p<0.05 else 'WEAK' if p<0.2 else 'NONE'}")

    print("\n=== 8. Sleeve B (12m TSMOM) on the same markets: roll-adjusted vs raw, and B+K blend ===")
    def tsmom_on(rets):
        px = (1 + rets.fillna(0)).cumprod()
        res = tsmom.backtest(px)
        pos = res["position"]
        return pos, (pos * rets).mean(axis=1) - pos.diff().abs().mean(axis=1) * 10 / 1e4
    pos_adj, b_adj = tsmom_on(r_adj)
    pos_raw, b_raw = tsmom_on(r_raw)
    print("  TSMOM roll-adjusted  " + summ(b_adj))
    print("  TSMOM raw 1! series  " + summ(b_raw))
    print("  corr(B adj, K)       " + f"{pd.concat([b_adj, net], axis=1).dropna().corr().iloc[0,1]:+.2f}")
    pos_k = K.backtest(f1, cry, base)["position"]
    for wa in [1.0, 0.7, 0.5, 0.3, 0.0]:
        blend = K.blend_positions(pos_adj, pos_k, w_a=wa)
        nb = (blend * r_adj[blend.columns]).mean(axis=1) - blend.diff().abs().mean(axis=1) * 10 / 1e4
        print(f"  blend B {wa:.1f} / K {1-wa:.1f}   " + summ(nb))


if __name__ == "__main__":
    main()
