"""Sleeve B robustness audit on a CME futures basket.

This is the deployment-target audit. The original audit_tsmom.py validates
the strategy on an ETF basket; this re-runs the same seven-section harness
on the futures basket we'd actually trade through Tradovate.

Universe (continuous front-month from yfinance, all with ~25y history):
  ES=F  S&P 500          (equity, large-cap)
  NQ=F  Nasdaq 100       (equity, tech)
  ZN=F  10-yr Treasury   (rates, intermediate)
  ZB=F  30-yr Treasury   (rates, long duration)
  GC=F  Gold             (precious metal)
  SI=F  Silver           (precious metal)
  HG=F  Copper           (industrial metal / global growth proxy)
  CL=F  Crude Oil        (energy)
  6E=F  Euro FX          (currency)
  ZC=F  Corn             (agricultural)

(RTY=F / Russell 2000 dropped - yfinance only has it from mid-2017,
which was the binding constraint in the initial run. Net diversification
is actually better with this basket - we trade equity small-cap for
FX + ag exposure.)

Same TSMOMConfig defaults as the ETF audit so the two are
directly comparable.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import yfinance as yf

from ten_cent_bot.tsmom import TSMOMConfig, backtest, summary

BASKET = [
    "ES=F", "NQ=F",          # equities
    "ZN=F", "ZB=F",          # rates
    "GC=F", "SI=F", "HG=F",  # metals
    "CL=F",                  # energy
    "6E=F",                  # FX
    "ZC=F",                  # grains
]


def fetch_monthly_prices() -> pd.DataFrame:
    data = yf.download(
        BASKET, period="max", interval="1d", auto_adjust=True, progress=False
    )
    prices = data["Close"] if isinstance(data.columns, pd.MultiIndex) else data
    return prices.resample("ME").last().dropna()


def run(monthly: pd.DataFrame, cfg: TSMOMConfig) -> dict:
    return summary(backtest(monthly, cfg))


def section_baseline(monthly: pd.DataFrame) -> dict:
    print("\n=== 1. Baseline (default config) ===")
    cfg = TSMOMConfig()
    s = run(monthly, cfg)
    print(
        f"Period: {monthly.index.min().date()} -> {monthly.index.max().date()} "
        f"({len(monthly)} months, {len(monthly.columns)} contracts)"
    )
    print(f"  Sharpe:        {s['sharpe']:.4f}")
    print(f"  CAGR:          {s['cagr']:.4f}")
    print(f"  Annual vol:    {s['annual_vol']:.4f}")
    print(f"  Max DD:        {s['max_drawdown']:.4f}")
    print(f"  Monthly win %: {s.get('monthly_win_rate', 'n/a')}")
    return s


def section_walk_forward(monthly: pd.DataFrame) -> None:
    print("\n=== 2. Walk-Forward (Train / Test) ===")
    n = len(monthly)
    split = n // 2
    train = monthly.iloc[:split]
    test = monthly.iloc[split - 12 :]
    s_tr = run(train, TSMOMConfig())
    s_te = run(test, TSMOMConfig())
    print(
        f"Train: {train.index.min().date()} -> {train.index.max().date()} "
        f"({len(train)} months)  Sharpe {s_tr['sharpe']:.3f}, MaxDD {s_tr['max_drawdown']:.3f}"
    )
    print(
        f"Test:  {test.index.min().date()} -> {test.index.max().date()} "
        f"({len(test)} months)  Sharpe {s_te['sharpe']:.3f}, MaxDD {s_te['max_drawdown']:.3f}"
    )
    delta = abs(s_tr["sharpe"] - s_te["sharpe"])
    print(
        f"  |Sharpe(train) - Sharpe(test)| = {delta:.3f}  "
        f"=> {'CONSISTENT' if delta < 0.35 else 'DIVERGENT'}"
    )


def section_parameter_sensitivity(monthly: pd.DataFrame) -> None:
    print("\n=== 3. Parameter Sensitivity ===")
    rows = []
    for lb in [3, 6, 9, 12, 15, 18, 24]:
        for tv in [0.05, 0.10, 0.15]:
            for ml in [1.5, 2.0, 3.0]:
                cfg = TSMOMConfig(lookback_months=lb, target_vol=tv, max_leverage=ml)
                s = run(monthly, cfg)
                rows.append(
                    {
                        "lookback": lb,
                        "target_vol": tv,
                        "max_lev": ml,
                        "sharpe": s["sharpe"],
                        "cagr": s["cagr"],
                        "max_dd": s["max_drawdown"],
                    }
                )
    df = pd.DataFrame(rows)
    print(f"  Configs tested:              {len(df)}")
    print(f"  Sharpe mean +/- std:         {df['sharpe'].mean():.3f} +/- {df['sharpe'].std():.3f}")
    print(f"  Sharpe min / median / max:   {df['sharpe'].min():.3f} / {df['sharpe'].median():.3f} / {df['sharpe'].max():.3f}")
    print(f"  % configs with Sharpe > 0:   {(df['sharpe'] > 0).mean():.1%}")
    print(f"  % configs with Sharpe > 0.5: {(df['sharpe'] > 0.5).mean():.1%}")
    best = df.iloc[df["sharpe"].idxmax()]
    worst = df.iloc[df["sharpe"].idxmin()]
    print(f"  Best:  lookback={int(best.lookback):>2}m  tv={best.target_vol}  lev={best.max_lev}  -> Sharpe {best.sharpe:.3f}")
    print(f"  Worst: lookback={int(worst.lookback):>2}m  tv={worst.target_vol}  lev={worst.max_lev}  -> Sharpe {worst.sharpe:.3f}")

    print("\n  Sharpe averaged by lookback:")
    print(df.groupby("lookback")["sharpe"].mean().round(3).to_string())


def section_sub_periods(monthly: pd.DataFrame) -> None:
    print("\n=== 4. Sub-Period Analysis (rolling 4-year windows) ===")
    cfg = TSMOMConfig()
    period_months = 48
    rows = []
    n = len(monthly)
    for start in range(0, n - period_months + 1, 24):
        end = min(start + period_months + 12, n)
        sub = monthly.iloc[start:end]
        if len(sub) < 24:
            continue
        s = run(sub, cfg)
        rows.append(
            {
                "from": sub.index[12].date() if len(sub) > 12 else sub.index[0].date(),
                "to": sub.index[-1].date(),
                "sharpe": s["sharpe"],
                "cagr": s["cagr"],
                "max_dd": s["max_drawdown"],
            }
        )
    df = pd.DataFrame(rows)
    print(df.to_string(index=False))
    print(f"\n  Sub-periods with Sharpe > 0:    {(df['sharpe'] > 0).sum()}/{len(df)}")
    print(f"  Sub-periods with Sharpe > 0.3:  {(df['sharpe'] > 0.3).sum()}/{len(df)}")


def section_leave_one_out(monthly: pd.DataFrame) -> None:
    print("\n=== 5. Leave-One-Out Contract Drop ===")
    cfg = TSMOMConfig()
    base = run(monthly, cfg)["sharpe"]
    rows = []
    for col in monthly.columns:
        s = run(monthly.drop(columns=[col]), cfg)
        rows.append({"dropped": col, "sharpe": s["sharpe"], "delta_vs_base": s["sharpe"] - base, "cagr": s["cagr"]})
    df = pd.DataFrame(rows).sort_values("delta_vs_base")
    print(f"  Baseline (all {len(monthly.columns)} contracts) Sharpe: {base:.4f}\n")
    print(df.to_string(index=False))
    print(f"\n  Max single-contract delta: {df['delta_vs_base'].abs().max():.3f}  => {'NOT DOMINATED' if df['delta_vs_base'].abs().max() < 0.20 else 'CONCENTRATED'}")


def section_cost_sensitivity(monthly: pd.DataFrame) -> None:
    print("\n=== 6. Transaction-Cost Sensitivity ===")
    rows = []
    for bps in [0, 1, 2, 5, 10, 20, 50, 100, 200]:
        s = run(monthly, TSMOMConfig(transaction_cost_bps=bps))
        rows.append({"cost_bps": bps, "sharpe": s["sharpe"], "cagr": s["cagr"]})
    df = pd.DataFrame(rows)
    print(df.to_string(index=False))
    print("  (Note: futures round-trip costs typically 1-5 bps for micros, vs 10bps for ETFs.)")


def section_placebo(monthly: pd.DataFrame, n_seeds: int = 100) -> None:
    print(f"\n=== 7. Randomized-Signal Placebo ({n_seeds} seeds) ===")
    cfg = TSMOMConfig()
    real = summary(backtest(monthly, cfg))["sharpe"]

    monthly_returns = monthly.pct_change()
    realized_vol = monthly_returns.rolling(cfg.lookback_months).std() * np.sqrt(12)
    raw_weight = (cfg.target_vol / realized_vol).clip(upper=cfg.max_leverage)

    rng = np.random.default_rng(42)
    placebo_sharpes = []

    for _ in range(n_seeds):
        signs = pd.DataFrame(
            rng.choice([-1.0, 1.0], size=monthly.shape, p=[0.5, 0.5]),
            index=monthly.index,
            columns=monthly.columns,
        )
        position = (raw_weight * signs).shift(1)
        asset_pnl = position * monthly_returns
        port_gross = asset_pnl.mean(axis=1)
        cost = position.diff().abs().mean(axis=1) * cfg.transaction_cost_bps / 10_000.0
        net = (port_gross - cost).dropna()
        if len(net) == 0 or net.std(ddof=0) == 0:
            continue
        ann_ret = net.mean() * 12
        ann_vol = net.std(ddof=0) * np.sqrt(12)
        placebo_sharpes.append(ann_ret / ann_vol)

    arr = np.array(placebo_sharpes)
    p_value = float((arr >= real).mean())
    print(f"  Real TSMOM Sharpe:           {real:.4f}")
    print(f"  Placebo Sharpe mean +/- std: {arr.mean():.4f} +/- {arr.std():.4f}")
    print(f"  Placebo p5 / p50 / p95:      {np.percentile(arr, 5):.3f} / {np.percentile(arr, 50):.3f} / {np.percentile(arr, 95):.3f}")
    print(f"  P(placebo >= real):          {p_value:.3f}")
    if p_value < 0.05:
        verdict = "REAL EDGE (real signal beats random at p<0.05)"
    elif p_value < 0.20:
        verdict = "WEAK EDGE"
    else:
        verdict = "NO DETECTABLE EDGE"
    print(f"  Verdict: {verdict}")


def main() -> None:
    print("Fetching futures basket prices ...")
    monthly = fetch_monthly_prices()

    section_baseline(monthly)
    section_walk_forward(monthly)
    section_parameter_sensitivity(monthly)
    section_sub_periods(monthly)
    section_leave_one_out(monthly)
    section_cost_sensitivity(monthly)
    section_placebo(monthly)

    print("\n=== Audit complete ===")


if __name__ == "__main__":
    main()
