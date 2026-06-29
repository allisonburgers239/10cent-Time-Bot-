"""Robustness audit for Sleeve C (crypto basis / cash-and-carry).

Same seven-section format as audit_tsmom.py, adapted for funding-rate harvest:
  1. Baseline (sanity re-run)
  2. Walk-forward train/test split (per symbol)
  3. Parameter sensitivity grid (aggregation x cost x threshold)
  4. Sub-period analysis (annual windows -- the 2022 crypto winter is the obvious risk)
  5. Signal-lag test (does the result survive without same-period look-ahead?)
  6. Cost sensitivity sweep
  7. Placebo: random hold/no-hold, MATCHED holding fraction
     (the harder bar -- controls for holding-fraction so we're testing
      whether the signal *selects* the right periods, not just how often
      we hold)
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from ten_cent_bot.basis import (
    aggregate_to_8h,
    backtest,
    fetch_funding_history,
    summary,
)

INSTRUMENTS = ["BTC-PERPETUAL", "ETH-PERPETUAL"]
START = "2020-01-01"
PERIODS_PER_YEAR_8H = 365 * 3


def aggregate_to_period(hourly: pd.DataFrame, hours: int) -> pd.DataFrame:
    return hourly.resample(f"{hours}h").sum()


def periods_per_year_for(hours: int) -> int:
    return int(round(8760 / hours))


def section_baseline(hourly_data: dict) -> None:
    print("\n=== 1. Baseline (default config) ===")
    for sym, hourly in hourly_data.items():
        eight = aggregate_to_8h(hourly)
        s = summary(backtest(eight), PERIODS_PER_YEAR_8H)
        print(
            f"  {sym}: Sharpe {s['sharpe']:.3f}, CAGR {s['cagr']:.4f}, "
            f"MaxDD {s['max_drawdown']:.4f}, holding {s['pct_holding']:.1%}, "
            f"years {s['years']}"
        )


def section_walk_forward(hourly_data: dict) -> None:
    print("\n=== 2. Walk-Forward (Train / Test) ===")
    for sym, hourly in hourly_data.items():
        eight = aggregate_to_8h(hourly)
        n = len(eight)
        split = n // 2
        train = eight.iloc[:split]
        test = eight.iloc[split:]
        s_tr = summary(backtest(train), PERIODS_PER_YEAR_8H)
        s_te = summary(backtest(test), PERIODS_PER_YEAR_8H)
        print(f"  {sym}:")
        print(
            f"    Train ({train.index.min().date()} -> {train.index.max().date()}, "
            f"{len(train)} periods): Sharpe {s_tr['sharpe']:.3f}, "
            f"hold {s_tr['pct_holding']:.1%}"
        )
        print(
            f"    Test  ({test.index.min().date()} -> {test.index.max().date()}, "
            f"{len(test)} periods): Sharpe {s_te['sharpe']:.3f}, "
            f"hold {s_te['pct_holding']:.1%}"
        )
        delta = abs(s_tr["sharpe"] - s_te["sharpe"])
        print(
            f"    Delta: {delta:.3f}  "
            f"=> {'CONSISTENT' if delta < 0.5 else 'DIVERGENT'}"
        )


def section_parameter_sensitivity(hourly_data: dict) -> None:
    print("\n=== 3. Parameter Sensitivity ===")
    for sym, hourly in hourly_data.items():
        rows = []
        for hours in [4, 8, 12, 24]:
            agg_base = aggregate_to_period(hourly, hours)
            for bps in [0, 5, 10, 20]:
                for threshold in [0.0, 5e-5, 1e-4]:
                    if threshold > 0:
                        rates = agg_base["rate"].where(agg_base["rate"] > threshold, 0)
                        agg = pd.DataFrame({"rate": rates})
                    else:
                        agg = agg_base
                    s = summary(
                        backtest(agg, cost_bps_per_change=bps),
                        periods_per_year_for(hours),
                    )
                    rows.append(
                        {
                            "hours": hours,
                            "cost_bps": bps,
                            "threshold": threshold,
                            "sharpe": s["sharpe"],
                            "cagr": s["cagr"],
                            "hold_pct": s["pct_holding"],
                        }
                    )
        df = pd.DataFrame(rows)
        print(f"\n  {sym}: {len(df)} configs")
        print(
            f"    Sharpe mean +/- std:       "
            f"{df['sharpe'].mean():.3f} +/- {df['sharpe'].std():.3f}"
        )
        print(
            f"    Sharpe min / median / max: "
            f"{df['sharpe'].min():.3f} / {df['sharpe'].median():.3f} / {df['sharpe'].max():.3f}"
        )
        print(f"    % configs with Sharpe > 0: {(df['sharpe'] > 0).mean():.1%}")
        print(
            f"    % configs with Sharpe > 1: {(df['sharpe'] > 1).mean():.1%}"
        )
        best = df.iloc[df["sharpe"].idxmax()]
        worst = df.iloc[df["sharpe"].idxmin()]
        print(
            f"    Best:  {int(best.hours)}h, cost={best.cost_bps}, "
            f"thr={best.threshold:.0e} -> {best.sharpe:.3f}"
        )
        print(
            f"    Worst: {int(worst.hours)}h, cost={worst.cost_bps}, "
            f"thr={worst.threshold:.0e} -> {worst.sharpe:.3f}"
        )


def section_sub_periods(hourly_data: dict) -> None:
    print("\n=== 4. Sub-Period Analysis (annual windows) ===")
    for sym, hourly in hourly_data.items():
        eight = aggregate_to_8h(hourly)
        rows = []
        for year in sorted(set(eight.index.year)):
            year_data = eight[eight.index.year == year]
            if len(year_data) < 100:
                continue
            s = summary(backtest(year_data), PERIODS_PER_YEAR_8H)
            rows.append(
                {
                    "year": year,
                    "sharpe": s["sharpe"],
                    "cagr": s["cagr"],
                    "max_dd": s["max_drawdown"],
                    "hold_pct": s["pct_holding"],
                    "mean_rate": year_data["rate"].mean(),
                }
            )
        df = pd.DataFrame(rows)
        print(f"\n  {sym}:")
        print(df.to_string(index=False))


def section_lag_test(hourly_data: dict) -> None:
    print("\n=== 5. Signal-Lag Test (anti-lookahead) ===")
    for sym, hourly in hourly_data.items():
        eight = aggregate_to_8h(hourly)
        rates = eight["rate"]

        s_concurrent = summary(backtest(eight), PERIODS_PER_YEAR_8H)["sharpe"]

        # Lagged: decide position using rate[t-1], earn rate[t]
        position = (rates.shift(1) > 0).astype(float)
        per_period_return = position * rates
        changes = position.diff().abs()
        if len(changes) > 0:
            first_pos = position.iloc[0]
            changes.iloc[0] = float(np.abs(first_pos)) if not pd.isna(first_pos) else 0.0
        costs = changes * 5.0 / 10_000.0
        net = (per_period_return - costs).fillna(0)
        if net.std(ddof=0) > 0:
            ann_ret = net.mean() * PERIODS_PER_YEAR_8H
            ann_vol = net.std(ddof=0) * np.sqrt(PERIODS_PER_YEAR_8H)
            sharpe_lag = ann_ret / ann_vol
        else:
            sharpe_lag = 0.0

        delta = s_concurrent - sharpe_lag
        print(f"  {sym}:")
        print(f"    Concurrent signal Sharpe:  {s_concurrent:.3f}")
        print(f"    Lagged 1-period Sharpe:    {sharpe_lag:.3f}")
        print(f"    Delta:                     {delta:.3f}")
        if abs(delta) > 1.0:
            verdict = "BIG DROP - concurrent uses look-ahead the strategy can't really have"
        elif abs(delta) > 0.3:
            verdict = "MODERATE - minor look-ahead, still real edge"
        else:
            verdict = "TRIVIAL - autocorrelation in funding makes the lag harmless"
        print(f"    Verdict: {verdict}")


def section_cost_sensitivity(hourly_data: dict) -> None:
    print("\n=== 6. Cost Sensitivity ===")
    for sym, hourly in hourly_data.items():
        eight = aggregate_to_8h(hourly)
        rows = []
        for bps in [0, 2, 5, 10, 20, 50, 100, 200]:
            s = summary(
                backtest(eight, cost_bps_per_change=bps), PERIODS_PER_YEAR_8H
            )
            rows.append({"cost_bps": bps, "sharpe": s["sharpe"], "cagr": s["cagr"]})
        df = pd.DataFrame(rows)
        print(f"\n  {sym}:")
        print(df.to_string(index=False))


def section_placebo(hourly_data: dict, n_seeds: int = 100) -> None:
    print(f"\n=== 7. Placebo: matched-fraction random ({n_seeds} seeds) ===")
    for sym, hourly in hourly_data.items():
        eight = aggregate_to_8h(hourly)
        rates = eight["rate"]
        real_sharpe = summary(backtest(eight), PERIODS_PER_YEAR_8H)["sharpe"]
        pct_pos = float((rates > 0).mean())

        rng = np.random.default_rng(42)
        placebo_sharpes = []
        for _ in range(n_seeds):
            position = pd.Series(
                rng.choice([0.0, 1.0], size=len(rates), p=[1 - pct_pos, pct_pos]),
                index=rates.index,
            )
            per_return = position * rates
            changes = position.diff().abs()
            if len(changes) > 0:
                changes.iloc[0] = float(position.iloc[0])
            costs = changes * 5.0 / 10_000.0
            net = per_return - costs
            if net.std(ddof=0) == 0:
                continue
            ann_ret = net.mean() * PERIODS_PER_YEAR_8H
            ann_vol = net.std(ddof=0) * np.sqrt(PERIODS_PER_YEAR_8H)
            placebo_sharpes.append(ann_ret / ann_vol)

        arr = np.array(placebo_sharpes)
        p_value = float((arr >= real_sharpe).mean())
        print(f"\n  {sym}:")
        print(f"    Real signal Sharpe:               {real_sharpe:.3f}")
        print(
            f"    Placebo (random, p=pct_positive): "
            f"{arr.mean():.3f} +/- {arr.std():.3f}"
        )
        print(
            f"    Placebo p5/p95:                   "
            f"[{np.percentile(arr, 5):.3f}, {np.percentile(arr, 95):.3f}]"
        )
        print(f"    P(placebo >= real):               {p_value:.3f}")
        if p_value < 0.05:
            verdict = "REAL EDGE (signal selects WHICH periods to hold, p<0.05)"
        elif p_value < 0.20:
            verdict = "WEAK EDGE"
        else:
            verdict = "NO TIMING EDGE (random with same holding fraction does as well)"
        print(f"    Verdict: {verdict}")


def main() -> None:
    print("Fetching funding history (takes a few minutes)...")
    hourly_data: dict = {}
    for sym in INSTRUMENTS:
        print(f"  fetching {sym}...")
        hourly_data[sym] = fetch_funding_history(sym, START)
        print(f"    {len(hourly_data[sym]):,} hourly records")

    section_baseline(hourly_data)
    section_walk_forward(hourly_data)
    section_parameter_sensitivity(hourly_data)
    section_sub_periods(hourly_data)
    section_lag_test(hourly_data)
    section_cost_sensitivity(hourly_data)
    section_placebo(hourly_data)

    print("\n=== Audit complete ===")


if __name__ == "__main__":
    main()
