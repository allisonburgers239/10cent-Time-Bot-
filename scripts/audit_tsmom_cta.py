"""Robustness audit for CTA-enhanced Sleeve B (tsmom_cta).

Runs on the same 10-ETF basket as the v1 audit for direct comparability.
Adds a leading "Section 0" that ablates each CTA layer to isolate what
each adds; then runs the standard 7-section audit on the full CTA config.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import yfinance as yf

from ten_cent_bot import tsmom
from ten_cent_bot import tsmom_cta

BASKET = ["SPY", "QQQ", "IWM", "EFA", "EEM", "TLT", "IEF", "GLD", "USO", "DBC"]


def fetch_monthly_prices() -> pd.DataFrame:
    data = yf.download(
        BASKET, period="max", interval="1d", auto_adjust=True, progress=False
    )
    prices = data["Close"] if isinstance(data.columns, pd.MultiIndex) else data
    return prices.resample("ME").last().dropna()


def _summarize(res):
    return tsmom_cta.summary(res)


def run_cta(monthly, cfg):
    return _summarize(tsmom_cta.backtest(monthly, cfg))


def run_v1(monthly, cfg):
    return tsmom.summary(tsmom.backtest(monthly, cfg))


# -------------------------- Section 0: ablation -------------------


def section_ablation(monthly: pd.DataFrame) -> tsmom_cta.TSMOMCTAConfig:
    """Compare baseline (v1) vs each CTA layer individually vs full stack."""
    print("\n=== 0. Layer Ablation (does each CTA layer add value?) ===")

    variants: dict[str, dict] = {}
    variants["v1 baseline"] = run_v1(monthly, tsmom.TSMOMConfig())

    # Layer 1 only: multi-horizon signal (nothing else)
    variants["CTA: multi-horizon only"] = run_cta(
        monthly,
        tsmom_cta.TSMOMCTAConfig(
            min_signal_strength=0.0,
            vol_regime_enabled=False,
            corr_filter_enabled=False,
        ),
    )
    # Layer 2 only: trend-strength filter (single 12m horizon)
    variants["CTA: trend-strength only"] = run_cta(
        monthly,
        tsmom_cta.TSMOMCTAConfig(
            lookback_horizons=(12,),
            horizon_weights=(1.0,),
            min_signal_strength=0.5,
            vol_regime_enabled=False,
            corr_filter_enabled=False,
        ),
    )
    # Layer 3 only: vol-regime filter
    variants["CTA: vol-regime only"] = run_cta(
        monthly,
        tsmom_cta.TSMOMCTAConfig(
            lookback_horizons=(12,),
            horizon_weights=(1.0,),
            min_signal_strength=0.0,
            vol_regime_enabled=True,
            corr_filter_enabled=False,
        ),
    )
    # Layer 4 only: correlation filter
    variants["CTA: corr-filter only"] = run_cta(
        monthly,
        tsmom_cta.TSMOMCTAConfig(
            lookback_horizons=(12,),
            horizon_weights=(1.0,),
            min_signal_strength=0.0,
            vol_regime_enabled=False,
            corr_filter_enabled=True,
        ),
    )
    # Full stack
    variants["CTA: FULL stack"] = run_cta(monthly, tsmom_cta.TSMOMCTAConfig())

    print(
        f"  {'variant':>28}  {'Sharpe':>7}  {'CAGR':>7}  {'AnnVol':>7}  {'MaxDD':>7}  {'Calmar':>7}"
    )
    print("  " + "-" * 74)
    for name, stats in variants.items():
        print(
            f"  {name:>28}  {stats.get('sharpe', 0):>7.3f}  "
            f"{stats.get('cagr', 0):>7.4f}  {stats.get('annual_vol', 0):>7.4f}  "
            f"{stats.get('max_drawdown', 0):>7.4f}  {stats.get('calmar', 0):>7.3f}"
        )
    return tsmom_cta.TSMOMCTAConfig()


# -------------------------- Sections 1-7 --------------------------


def section_baseline(monthly: pd.DataFrame) -> None:
    print("\n=== 1. Baseline (full CTA config) ===")
    s = run_cta(monthly, tsmom_cta.TSMOMCTAConfig())
    print(
        f"Period: {monthly.index.min().date()} -> {monthly.index.max().date()} "
        f"({len(monthly)} months)"
    )
    print(f"  Sharpe:        {s['sharpe']:.4f}")
    print(f"  CAGR:          {s['cagr']:.4f}")
    print(f"  Max DD:        {s['max_drawdown']:.4f}")
    print(f"  Monthly win %: {s.get('monthly_win_rate', 'n/a')}")


def section_walk_forward(monthly: pd.DataFrame) -> None:
    print("\n=== 2. Walk-Forward (train / test) ===")
    n = len(monthly)
    split = n // 2
    train = monthly.iloc[:split]
    test = monthly.iloc[split - 12 :]
    s_tr = run_cta(train, tsmom_cta.TSMOMCTAConfig())
    s_te = run_cta(test, tsmom_cta.TSMOMCTAConfig())
    print(
        f"Train ({train.index.min().date()} -> {train.index.max().date()}): "
        f"Sharpe {s_tr['sharpe']:.3f}, MaxDD {s_tr['max_drawdown']:.3f}"
    )
    print(
        f"Test  ({test.index.min().date()} -> {test.index.max().date()}): "
        f"Sharpe {s_te['sharpe']:.3f}, MaxDD {s_te['max_drawdown']:.3f}"
    )
    delta = abs(s_tr["sharpe"] - s_te["sharpe"])
    print(f"  delta = {delta:.3f}  =>  {'CONSISTENT' if delta < 0.35 else 'DIVERGENT'}")


def section_parameter_sensitivity(monthly: pd.DataFrame) -> None:
    print("\n=== 3. Parameter Sensitivity ===")
    rows = []
    for horizons in [(12,), (6, 12), (3, 6, 12), (6, 12, 18)]:
        weights = tuple([1.0 / len(horizons)] * len(horizons))
        for min_ss in [0.0, 0.25, 0.5, 1.0]:
            for vre in [True, False]:
                for cfe in [True, False]:
                    cfg = tsmom_cta.TSMOMCTAConfig(
                        lookback_horizons=horizons,
                        horizon_weights=weights,
                        min_signal_strength=min_ss,
                        vol_regime_enabled=vre,
                        corr_filter_enabled=cfe,
                    )
                    s = run_cta(monthly, cfg)
                    rows.append(
                        {
                            "horizons": str(horizons),
                            "min_ss": min_ss,
                            "vre": vre,
                            "cfe": cfe,
                            "sharpe": s.get("sharpe", 0),
                            "cagr": s.get("cagr", 0),
                        }
                    )
    df = pd.DataFrame(rows)
    print(f"  Configs tested:              {len(df)}")
    print(
        f"  Sharpe mean +/- std:         {df['sharpe'].mean():.3f} +/- {df['sharpe'].std():.3f}"
    )
    print(
        f"  Sharpe min / median / max:   "
        f"{df['sharpe'].min():.3f} / {df['sharpe'].median():.3f} / {df['sharpe'].max():.3f}"
    )
    print(f"  % configs Sharpe > 0:        {(df['sharpe'] > 0).mean():.1%}")
    print(f"  % configs Sharpe > baseline: (baseline=0.72 on ETF)")
    print(f"  % configs Sharpe > 0.72:     {(df['sharpe'] > 0.72).mean():.1%}")
    best = df.iloc[df["sharpe"].idxmax()]
    worst = df.iloc[df["sharpe"].idxmin()]
    print(f"  Best config:  {best.to_dict()}")
    print(f"  Worst config: {worst.to_dict()}")


def section_sub_periods(monthly: pd.DataFrame) -> None:
    print("\n=== 4. Sub-Period Analysis (rolling 4y windows) ===")
    cfg = tsmom_cta.TSMOMCTAConfig()
    period_months = 48
    rows = []
    n = len(monthly)
    for start in range(0, n - period_months + 1, 24):
        end = min(start + period_months + 12, n)
        sub = monthly.iloc[start:end]
        if len(sub) < 24:
            continue
        s = run_cta(sub, cfg)
        rows.append(
            {
                "from": sub.index[12].date() if len(sub) > 12 else sub.index[0].date(),
                "to": sub.index[-1].date(),
                "sharpe": s.get("sharpe", 0),
                "cagr": s.get("cagr", 0),
                "max_dd": s.get("max_drawdown", 0),
            }
        )
    df = pd.DataFrame(rows)
    print(df.to_string(index=False))
    print(f"\n  Sub-periods Sharpe > 0:    {(df['sharpe'] > 0).sum()}/{len(df)}")
    print(f"  Sub-periods Sharpe > 0.3:  {(df['sharpe'] > 0.3).sum()}/{len(df)}")


def section_leave_one_out(monthly: pd.DataFrame) -> None:
    print("\n=== 5. Leave-One-Out Asset Drop ===")
    cfg = tsmom_cta.TSMOMCTAConfig()
    base = run_cta(monthly, cfg).get("sharpe", 0)
    rows = []
    for col in monthly.columns:
        s = run_cta(monthly.drop(columns=[col]), cfg)
        rows.append(
            {
                "dropped": col,
                "sharpe": s.get("sharpe", 0),
                "delta": s.get("sharpe", 0) - base,
                "cagr": s.get("cagr", 0),
            }
        )
    df = pd.DataFrame(rows).sort_values("delta")
    print(f"  Baseline (all {len(monthly.columns)}): Sharpe {base:.4f}\n")
    print(df.to_string(index=False))
    print(
        f"\n  Max single-asset delta: {df['delta'].abs().max():.3f}  "
        f"=> {'NOT DOMINATED' if df['delta'].abs().max() < 0.20 else 'CONCENTRATED'}"
    )


def section_cost_sensitivity(monthly: pd.DataFrame) -> None:
    print("\n=== 6. Cost Sensitivity ===")
    rows = []
    for bps in [0, 5, 10, 20, 50, 100, 200]:
        cfg = tsmom_cta.TSMOMCTAConfig(transaction_cost_bps=bps)
        s = run_cta(monthly, cfg)
        rows.append({"cost_bps": bps, "sharpe": s.get("sharpe", 0), "cagr": s.get("cagr", 0)})
    df = pd.DataFrame(rows)
    print(df.to_string(index=False))


def section_placebo(monthly: pd.DataFrame, n_seeds: int = 100) -> None:
    print(f"\n=== 7. Placebo (random signal, {n_seeds} seeds) ===")
    cfg = tsmom_cta.TSMOMCTAConfig()
    real = run_cta(monthly, cfg).get("sharpe", 0)

    monthly_returns = monthly.pct_change()
    long_lb = max(cfg.lookback_horizons)
    realized_vol = monthly_returns.rolling(long_lb).std() * np.sqrt(12)
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
        placebo_sharpes.append(
            float(net.mean() * 12 / (net.std(ddof=0) * np.sqrt(12)))
        )

    arr = np.array(placebo_sharpes)
    p_value = float((arr >= real).mean())
    print(f"  Real CTA Sharpe:             {real:.4f}")
    print(f"  Placebo Sharpe mean +/-:     {arr.mean():.4f} +/- {arr.std():.4f}")
    print(f"  Placebo p5 / p50 / p95:      {np.percentile(arr, 5):.3f} / {np.percentile(arr, 50):.3f} / {np.percentile(arr, 95):.3f}")
    print(f"  P(placebo >= real):          {p_value:.3f}")
    verdict = (
        "REAL EDGE" if p_value < 0.05 else "WEAK EDGE" if p_value < 0.20 else "NO EDGE"
    )
    print(f"  Verdict: {verdict}")


def main() -> None:
    print("Fetching basket prices ...")
    monthly = fetch_monthly_prices()

    section_ablation(monthly)
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
