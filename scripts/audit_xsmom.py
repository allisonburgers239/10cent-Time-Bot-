"""Robustness audit for Sleeve D (cross-sectional sector momentum).

Same seven-section format used for Sleeves B and C:
  1. Baseline (sanity re-run)
  2. Walk-forward train/test split
  3. Parameter sensitivity grid
  4. Sub-period analysis (rolling 4-year windows)
  5. Leave-one-out sector drop
  6. Transaction-cost sensitivity
  7. Random-rank placebo (100 seeds) - replaces momentum ranks with
     random permutations, controls for whether the signal is real
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import yfinance as yf

from ten_cent_bot.xsmom import XSMOMConfig, backtest, summary

SECTORS = ["XLB", "XLE", "XLF", "XLI", "XLK", "XLP", "XLU", "XLV", "XLY"]


def fetch_monthly_prices() -> pd.DataFrame:
    data = yf.download(
        SECTORS, period="max", interval="1d", auto_adjust=True, progress=False
    )
    prices = data["Close"] if isinstance(data.columns, pd.MultiIndex) else data
    return prices.resample("ME").last().dropna()


def run(monthly: pd.DataFrame, cfg: XSMOMConfig) -> dict:
    return summary(backtest(monthly, cfg))


def section_baseline(monthly: pd.DataFrame) -> None:
    print("\n=== 1. Baseline (default config) ===")
    s = run(monthly, XSMOMConfig())
    print(
        f"Period: {monthly.index.min().date()} -> {monthly.index.max().date()} "
        f"({len(monthly)} months, {len(monthly.columns)} sectors)"
    )
    print(f"  Sharpe:        {s['sharpe']:.4f}")
    print(f"  CAGR:          {s['cagr']:.4f}")
    print(f"  Annual vol:    {s['annual_vol']:.4f}")
    print(f"  Max DD:        {s['max_drawdown']:.4f}")
    print(f"  Monthly win %: {s['monthly_win_rate']:.4f}")


def section_walk_forward(monthly: pd.DataFrame) -> None:
    print("\n=== 2. Walk-Forward (Train / Test split) ===")
    n = len(monthly)
    split = n // 2
    train = monthly.iloc[:split]
    test = monthly.iloc[split - 12 :]

    s_tr = run(train, XSMOMConfig())
    s_te = run(test, XSMOMConfig())
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
    n_assets = monthly.shape[1]
    for lb in [3, 6, 9, 12, 15, 18, 24]:
        for top_n in [1, 2, 3, 4]:
            if top_n * 2 > n_assets:
                continue
            for lev in [1.0, 1.5, 2.0]:
                cfg = XSMOMConfig(lookback_months=lb, top_n=top_n, leverage=lev)
                s = run(monthly, cfg)
                rows.append(
                    {
                        "lookback": lb,
                        "top_n": top_n,
                        "leverage": lev,
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
    print(f"  % configs with Sharpe > 0.3: {(df['sharpe'] > 0.3).mean():.1%}")
    best = df.iloc[df["sharpe"].idxmax()]
    worst = df.iloc[df["sharpe"].idxmin()]
    print(
        f"  Best:  lookback={int(best.lookback):>2}m  top_n={int(best.top_n)}  "
        f"lev={best.leverage}  -> Sharpe {best.sharpe:.3f}"
    )
    print(
        f"  Worst: lookback={int(worst.lookback):>2}m  top_n={int(worst.top_n)}  "
        f"lev={worst.leverage}  -> Sharpe {worst.sharpe:.3f}"
    )

    print("\n  Sharpe averaged by lookback:")
    print(df.groupby("lookback")["sharpe"].mean().round(3).to_string())


def section_sub_periods(monthly: pd.DataFrame) -> None:
    print("\n=== 4. Sub-Period Analysis (rolling 4-year windows) ===")
    cfg = XSMOMConfig()
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
    print("\n=== 5. Leave-One-Out Sector Drop ===")
    cfg = XSMOMConfig()
    base = run(monthly, cfg)["sharpe"]
    rows = []
    for col in monthly.columns:
        reduced = monthly.drop(columns=[col])
        if reduced.shape[1] < 2 * cfg.top_n:
            continue
        s = run(reduced, cfg)
        rows.append(
            {
                "dropped": col,
                "sharpe": s["sharpe"],
                "delta_vs_base": s["sharpe"] - base,
                "cagr": s["cagr"],
            }
        )
    df = pd.DataFrame(rows).sort_values("delta_vs_base")
    print(f"  Baseline (all sectors): Sharpe {base:.4f}\n")
    print(df.to_string(index=False))
    max_delta = df["delta_vs_base"].abs().max()
    print(
        f"\n  Max single-sector delta: {max_delta:.3f}  "
        f"=> {'NOT DOMINATED' if max_delta < 0.20 else 'CONCENTRATED'}"
    )


def section_cost_sensitivity(monthly: pd.DataFrame) -> None:
    print("\n=== 6. Transaction-Cost Sensitivity ===")
    rows = []
    for bps in [0, 5, 10, 20, 50, 100, 200]:
        s = run(monthly, XSMOMConfig(transaction_cost_bps=bps))
        rows.append({"cost_bps": bps, "sharpe": s["sharpe"], "cagr": s["cagr"]})
    df = pd.DataFrame(rows)
    print(df.to_string(index=False))


def section_placebo(monthly: pd.DataFrame, n_seeds: int = 100) -> None:
    print(f"\n=== 7. Random-Rank Placebo ({n_seeds} seeds) ===")
    cfg = XSMOMConfig()
    real = run(monthly, cfg)["sharpe"]

    monthly_returns = monthly.pct_change()
    n_assets = monthly.shape[1]
    rng = np.random.default_rng(42)

    placebo_sharpes = []
    for _ in range(n_seeds):
        # Random permutation of ranks per month
        ranks_random = pd.DataFrame(
            np.array(
                [rng.permutation(np.arange(1, n_assets + 1)) for _ in range(len(monthly))]
            ),
            index=monthly.index,
            columns=monthly.columns,
        )
        weight = 1.0 / cfg.top_n
        signal = pd.DataFrame(0.0, index=monthly.index, columns=monthly.columns)
        signal[ranks_random <= cfg.top_n] = weight
        signal[ranks_random > (n_assets - cfg.top_n)] = -weight
        position = (signal * cfg.leverage).shift(1)
        asset_pnl = position * monthly_returns
        port_ret = asset_pnl.sum(axis=1)
        turnover = position.diff().abs().sum(axis=1)
        cost = turnover * cfg.transaction_cost_bps / 10_000.0
        net = (port_ret - cost).dropna()
        if len(net) == 0 or net.std(ddof=0) == 0:
            continue
        ann_ret = net.mean() * 12
        ann_vol = net.std(ddof=0) * np.sqrt(12)
        placebo_sharpes.append(ann_ret / ann_vol)

    arr = np.array(placebo_sharpes)
    p_value = float((arr >= real).mean())
    print(f"  Real Sharpe:             {real:.4f}")
    print(f"  Placebo Sharpe mean +/-: {arr.mean():.4f} +/- {arr.std():.4f}")
    print(f"  Placebo p5 / p95:        {np.percentile(arr, 5):.3f} / {np.percentile(arr, 95):.3f}")
    print(f"  P(placebo >= real):      {p_value:.3f}")
    if p_value < 0.05:
        verdict = "REAL EDGE (real signal beats random ranks at p<0.05)"
    elif p_value < 0.20:
        verdict = "WEAK EDGE"
    else:
        verdict = "NO DETECTABLE EDGE"
    print(f"  Verdict: {verdict}")


def main() -> None:
    print("Fetching sector ETF prices ...")
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
