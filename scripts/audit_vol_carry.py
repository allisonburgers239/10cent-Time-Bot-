"""Sleeve V candidate: VIX-futures roll-down (volatility risk premium).

Short a constant-30-day VIX futures position when the curve is in
contango (front above spot), long when inverted, flat in between.
Data: CBOE per-contract settlements (scripts/fetch_cboe_vx.py) built into
VX1/VX2/CM30 by ten_cent_bot.vx_data; spot VIX from yfinance.

References: Simon & Campasano (2014) J. Derivatives; Cheng (2019) RFS;
Eraker & Wu (2017) JFE; Johnson (2017) JFQA.

Sections: 0 premium decomposition by year, 1 baseline, 2 walk-forward,
3 parameter grid, 4 sub-periods, 5 signal variants vs always-short,
6 cost sensitivity, 7 time-block placebo, 8 TAIL (the decision section).
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

from ten_cent_bot.metrics import max_drawdown, sharpe, sortino
from ten_cent_bot.vx_data import build_curve, load_raw

ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class VolCarryConfig:
    mode: str = "basis"          # basis | slope | always_short
    k: float = 0.05              # threshold on basis (VX1/VIX-1) or slope ln(VX2/VX1)
    target_vol: float = 0.10
    cap: float = 1.0             # max |position| as fraction of NAV
    vol_lookback: int = 20
    cost_bps: float = 15.0       # per unit of turnover (one side)
    allow_long: bool = True
    allow_short: bool = True


def load() -> tuple[pd.DataFrame, pd.Series, pd.Series]:
    raw = load_raw(ROOT / "data" / "cboe_vx" / "raw")
    built = build_curve(raw, min_days=2)  # roll the day before last trade so expiry days have no hole
    curve, cm = built["curve"], built["cm30_return"]
    vix = yf.download("^VIX", period="max", interval="1d", progress=False)["Close"].squeeze()
    vix.index = pd.to_datetime(vix.index).tz_localize(None)
    vix = vix.reindex(curve.index).ffill()
    return curve, cm, vix


def signal(curve: pd.DataFrame, vix: pd.Series, cfg: VolCarryConfig) -> pd.Series:
    if cfg.mode == "always_short":
        return pd.Series(-1.0, index=curve.index)
    x = (curve["VX1"] / vix - 1) if cfg.mode == "basis" else np.log(curve["VX2"] / curve["VX1"])
    s = pd.Series(0.0, index=curve.index)
    if cfg.allow_short:
        s[x > cfg.k] = -1.0
    if cfg.allow_long:
        s[x < -cfg.k] = 1.0
    return s


def backtest(curve: pd.DataFrame, cm: pd.Series, vix: pd.Series, cfg: VolCarryConfig) -> dict:
    sig = signal(curve, vix, cfg)
    rv = cm.rolling(cfg.vol_lookback, min_periods=10).std(ddof=0) * np.sqrt(252)
    lev = (cfg.target_vol / rv).clip(upper=cfg.cap)
    pos = (sig * lev).shift(1).fillna(0.0)          # decide at t-1 close, hold through t
    gross = pos * cm
    turnover = pos.diff().abs().fillna(0.0)
    cost = turnover * cfg.cost_bps / 10_000
    net = (gross - cost).fillna(0.0)
    return {"position": pos, "gross": gross, "net": net, "equity": (1 + net).cumprod(), "signal": sig}


def S(r: pd.Series) -> dict:
    r = r.dropna()
    eq = (1 + r).cumprod()
    return {"sharpe": sharpe(r, 252), "sortino": sortino(r, 252), "cagr": (1 + r.mean()) ** 252 - 1,
            "vol": r.std(ddof=0) * np.sqrt(252), "mdd": max_drawdown(eq), "n": len(r)}


def fmt(s: dict) -> str:
    return f"Sharpe {s['sharpe']:5.2f}  Sortino {s['sortino']:5.2f}  CAGR {s['cagr']:6.2%}  Vol {s['vol']:5.1%}  MaxDD {s['mdd']:6.1%}"


def main() -> None:
    curve, cm, vix = load()
    print(f"VX curve: {curve.index.min().date()} -> {curve.index.max().date()}, {len(curve)} days; CM30 return days {cm.notna().sum()}")

    print("\n=== 0. Premium decomposition by year ===")
    print("  year  %contango  mean(VX1-VIX)  mean slope  short-CM30 ann.ret  short-CM30 Sharpe  worst day")
    basis = curve["VX1"] - vix
    slope = np.log(curve["VX2"] / curve["VX1"])
    for y in sorted(set(curve.index.year)):
        m = curve.index.year == y
        r = -cm[m].dropna()
        if len(r) < 30:
            continue
        print(f"  {y}  {(basis[m] > 0).mean():8.0%}  {basis[m].mean():13.2f}  {slope[m].mean():10.3f}  {r.mean()*252:17.1%}  {sharpe(r,252):16.2f}  {r.min():8.1%}")

    base = VolCarryConfig()
    print(f"\n=== 1. Baseline ({base.mode}, k={base.k}, vol-target {base.target_vol:.0%}, cap {base.cap}, {base.cost_bps}bps/side) ===")
    bt = backtest(curve, cm, vix, base)
    s = S(bt["net"])
    print("  " + fmt(s))
    print(f"  time in market {(bt['position']!=0).mean():.0%}  (short {(bt['position']<0).mean():.0%}, long {(bt['position']>0).mean():.0%}), avg |pos| when in {bt['position'][bt['position']!=0].abs().mean():.2f}, turnover/yr {bt['position'].diff().abs().sum()/len(bt['position'])*252:.1f}x")

    print("\n=== 2. Walk-forward halves ===")
    n = len(curve) // 2
    for name, sl in [("train", slice(0, n)), ("test", slice(n, None))]:
        r = backtest(curve.iloc[sl], cm.iloc[sl], vix.iloc[sl], base)["net"]
        print(f"  {name}: {curve.index[sl][0].date()} -> {curve.index[sl][-1].date()}  " + fmt(S(r)))

    print("\n=== 3. Parameter grid ===")
    rows = []
    for mode in ["basis", "slope"]:
        for k in [0.0, 0.03, 0.05, 0.07, 0.10, 0.15]:
            for cap in [0.5, 1.0]:
                cfg = VolCarryConfig(mode=mode, k=k, cap=cap)
                st = S(backtest(curve, cm, vix, cfg)["net"])
                rows.append({"mode": mode, "k": k, "cap": cap, **st})
    g = pd.DataFrame(rows)
    print(g[["mode", "k", "cap", "sharpe", "sortino", "cagr", "mdd"]].to_string(index=False, float_format=lambda x: f"{x:.3f}"))
    print(f"  configs {len(g)}, Sharpe>0 {(g.sharpe>0).mean():.0%}, Sharpe>0.5 {(g.sharpe>0.5).mean():.0%}, mean {g.sharpe.mean():.2f}")

    print("\n=== 4. Sub-periods (4y) ===")
    net = bt["net"]
    for start in range(2004, 2027, 4):
        m = (net.index.year >= start) & (net.index.year < start + 4)
        if m.sum() < 200:
            continue
        print(f"  {start}-{start+3}: " + fmt(S(net[m])))

    print("\n=== 5. Signal variants (same sizing/cost) ===")
    for label, cfg in [
        ("always short CM30 (naive benchmark)", VolCarryConfig(mode="always_short")),
        ("basis, short side only", VolCarryConfig(allow_long=False)),
        ("basis, long side only", VolCarryConfig(allow_short=False)),
        ("slope k=0.05", VolCarryConfig(mode="slope")),
        ("basis k=0.05 (baseline)", base),
    ]:
        print(f"  {label:<38} " + fmt(S(backtest(curve, cm, vix, cfg)["net"])))

    print("\n=== 6. Cost sensitivity (bps per side of turnover) ===")
    for c in [0, 5, 10, 15, 25, 50, 100]:
        print(f"  {c:>4} bps: " + fmt(S(backtest(curve, cm, vix, VolCarryConfig(cost_bps=c))["net"])))

    print("\n=== 7. Placebo: signal shuffled in 20-day blocks (200 seeds) ===")
    rng = np.random.default_rng(3)
    sig = bt["signal"]
    rv = cm.rolling(base.vol_lookback, min_periods=10).std(ddof=0) * np.sqrt(252)
    lev = (base.target_vol / rv).clip(upper=base.cap)
    real = s["sharpe"]
    blocks = [sig.iloc[i:i + 20].values for i in range(0, len(sig), 20)]
    pl = []
    for _ in range(200):
        order = rng.permutation(len(blocks))
        shuf = pd.Series(np.concatenate([blocks[i] for i in order])[: len(sig)], index=sig.index)
        pos = (shuf * lev).shift(1).fillna(0.0)
        net_p = pos * cm - pos.diff().abs().fillna(0) * base.cost_bps / 1e4
        pl.append(sharpe(net_p.fillna(0), 252))
    pl = np.array(pl)
    p = float((pl >= real).mean())
    print(f"  real {real:.2f}  placebo {pl.mean():.2f} +/- {pl.std():.2f}  P(placebo>=real) = {p:.3f}  {'REAL' if p<0.05 else 'WEAK' if p<0.2 else 'NONE'}")

    print("\n=== 8. TAIL (decision section) ===")
    r = net.dropna()
    print(f"  skew {r.skew():.2f}  kurt {r.kurt():.1f}  worst day {r.min():.2%} ({r.idxmin().date()})  worst 5d {r.rolling(5).sum().min():.2%}  worst 20d {r.rolling(20).sum().min():.2%}")
    print(f"  ES99 (mean of worst 1% days) {r[r <= r.quantile(0.01)].mean():.2%}   days < -2% : {(r < -0.02).sum()}")
    spy = yf.download("SPY", period="max", interval="1d", auto_adjust=True, progress=False)["Close"].squeeze().pct_change()
    spy.index = pd.to_datetime(spy.index).tz_localize(None)
    j = pd.concat([r.rename("v"), spy.rename("spy")], axis=1).dropna()
    print(f"  corr with SPY daily {j.corr().iloc[0,1]:+.2f};  on SPY's worst 1% days sleeve avg {j[j.spy <= j.spy.quantile(0.01)].v.mean():+.2%}/day")
    for label, a, b in [("2008-09/10 GFC", "2008-09-01", "2008-10-31"), ("2010-05 flash", "2010-05-01", "2010-05-31"), ("2011-08 downgrade", "2011-08-01", "2011-08-31"),
                        ("2015-08-24", "2015-08-17", "2015-08-28"), ("2018-02-05 Volmageddon", "2018-01-29", "2018-02-09"), ("2020-02/03 COVID", "2020-02-20", "2020-03-20"),
                        ("2022 bear", "2022-01-01", "2022-12-31"), ("2024-08-05 yen unwind", "2024-07-29", "2024-08-09")]:
        w = r.loc[a:b]
        pos_w = bt["position"].loc[a:b]
        print(f"  {label:<24} {w.sum():+7.2%}  (avg pos {pos_w.mean():+.2f}, worst day {w.min():+.2%})")


if __name__ == "__main__":
    main()
