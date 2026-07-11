"""CTA-enhanced TSMOM (Sleeve B v2).

Layers on top of the audit-clean baseline in `tsmom.py` (which stays
frozen as v1). Four enhancements, each individually toggleable so the
audit can test them in isolation:

1. Multi-horizon signal blend (3m/6m/12m instead of single 12m). When
   the horizons agree, gets full leverage; when they disagree, position
   is naturally down-sized. Smoothes the "trend-follower's purgatory"
   flat periods (2015-2019 in the baseline audit).

2. Trend-strength filter. Only trade when the momentum's z-score exceeds
   a threshold. Cuts trades where the trend is real but weak - those
   tend to eat costs without earning.

3. Vol-regime filter. Skip trading when portfolio-average realized vol
   sits in the extreme tails of its trailing distribution. Dead-flat
   regimes chop the strategy; crisis regimes see it lag transitions.

4. Correlation-adjusted gross exposure. When cross-asset correlations
   rise (regime shift), scale total gross exposure down. This is what
   protected CTAs from 2015-2019 relative to those without it.

Default config enables all four. Setting each flag to its identity value
(single horizon (12,), min_signal_strength=0.0, vol_regime_enabled=False,
corr_filter_enabled=False) reduces the strategy to the v1 baseline.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .metrics import max_drawdown, sharpe, sortino


@dataclass(frozen=True)
class TSMOMCTAConfig:
    # --- Multi-horizon signal blend ---------------------------------
    # Set to (12,) with (1.0,) to reduce to the v1 baseline signal.
    lookback_horizons: tuple[int, ...] = (3, 6, 12)
    horizon_weights: tuple[float, ...] = (0.25, 0.35, 0.40)

    # --- Vol scaling (same math as v1) ------------------------------
    target_vol: float = 0.10
    max_leverage: float = 2.0
    transaction_cost_bps: float = 10.0

    # --- Trend-strength filter --------------------------------------
    # Zero the signal when momentum's z-score is below this threshold.
    # 0.0 disables the filter; 0.5 kills the weakest ~30% of trades.
    min_signal_strength: float = 0.5

    # --- Vol-regime filter ------------------------------------------
    # Skip when portfolio avg realized vol is outside [min_pct, max_pct]
    # of its trailing distribution (rolling percentile rank).
    vol_regime_enabled: bool = True
    vol_regime_window_months: int = 60  # 5y rolling percentile window
    vol_regime_min_pct: float = 0.10
    vol_regime_max_pct: float = 0.90

    # --- Correlation-adjusted gross exposure ------------------------
    # When rolling avg pairwise correlation > threshold, multiply gross
    # exposure by scale_factor.
    corr_filter_enabled: bool = True
    corr_lookback: int = 12
    corr_high_threshold: float = 0.6
    corr_scale_factor: float = 0.5


def _rolling_avg_correlation(returns_df: pd.DataFrame, window: int) -> pd.Series:
    """Rolling window average pairwise correlation across all assets."""
    result = pd.Series(np.nan, index=returns_df.index)
    for i in range(window, len(returns_df) + 1):
        w = returns_df.iloc[i - window : i]
        corr = w.corr()
        n = len(corr)
        if n < 2:
            continue
        mask = ~np.eye(n, dtype=bool)
        result.iloc[i - 1] = float(corr.values[mask].mean())
    return result


def backtest(monthly_prices: pd.DataFrame, config: TSMOMCTAConfig | None = None) -> dict:
    cfg = config or TSMOMCTAConfig()

    if len(cfg.lookback_horizons) != len(cfg.horizon_weights):
        raise ValueError("lookback_horizons and horizon_weights must match length")
    weight_sum = float(sum(cfg.horizon_weights))
    if weight_sum <= 0:
        raise ValueError("horizon_weights must sum to > 0")

    monthly_returns = monthly_prices.pct_change()
    long_lookback = max(cfg.lookback_horizons)

    # --- 1. Multi-horizon signal blend ---
    blended = pd.DataFrame(0.0, index=monthly_prices.index, columns=monthly_prices.columns)
    for lb, w in zip(cfg.lookback_horizons, cfg.horizon_weights):
        s = np.sign(monthly_prices / monthly_prices.shift(lb) - 1)
        blended = blended.add(s * (w / weight_sum), fill_value=0.0)

    signal = blended

    # --- 2. Trend-strength filter ---
    if cfg.min_signal_strength > 0:
        mom = monthly_prices / monthly_prices.shift(long_lookback) - 1
        mom_std = monthly_returns.rolling(long_lookback).std() * np.sqrt(long_lookback)
        z_score = mom / mom_std.replace(0, np.nan)
        signal = signal.where(z_score.abs() >= cfg.min_signal_strength, 0.0)

    # --- 3. Vol scaling (same as baseline) ---
    realized_vol = monthly_returns.rolling(long_lookback).std() * np.sqrt(12)
    raw_weight = (cfg.target_vol / realized_vol).clip(upper=cfg.max_leverage)
    position = raw_weight * signal

    # --- 4. Vol-regime filter ---
    if cfg.vol_regime_enabled:
        avg_vol = realized_vol.mean(axis=1)
        vol_pct = avg_vol.rolling(cfg.vol_regime_window_months, min_periods=12).rank(pct=True)
        in_regime = (vol_pct >= cfg.vol_regime_min_pct) & (vol_pct <= cfg.vol_regime_max_pct)
        # Broadcast the regime mask across all columns
        mask = in_regime.reindex(position.index).fillna(False).astype(float)
        position = position.mul(mask, axis=0)

    # --- 5. Correlation-adjusted gross exposure ---
    if cfg.corr_filter_enabled:
        avg_corr = _rolling_avg_correlation(monthly_returns, cfg.corr_lookback)
        corr_scale = pd.Series(1.0, index=position.index)
        corr_scale = corr_scale.where(
            avg_corr < cfg.corr_high_threshold, cfg.corr_scale_factor
        )
        position = position.mul(corr_scale, axis=0)

    # Decision at end of t-1 applied to return during t.
    position_lagged = position.shift(1)
    asset_pnl = position_lagged * monthly_returns
    portfolio_return_gross = asset_pnl.mean(axis=1)

    monthly_cost = (
        position_lagged.diff().abs().mean(axis=1)
        * cfg.transaction_cost_bps
        / 10_000.0
    )
    portfolio_return_net = portfolio_return_gross - monthly_cost

    equity = (1 + portfolio_return_net.fillna(0)).cumprod()

    return {
        "signal": signal,
        "position": position_lagged,
        "asset_pnl": asset_pnl,
        "monthly_return_gross": portfolio_return_gross,
        "monthly_return_net": portfolio_return_net,
        "monthly_cost": monthly_cost,
        "equity": equity,
    }


def summary(result: dict) -> dict:
    ret = result["monthly_return_net"].dropna()
    eq = result["equity"]
    if len(ret) == 0:
        return {}
    annual_ret = float((1 + ret.mean()) ** 12 - 1)
    annual_vol = float(ret.std(ddof=0) * np.sqrt(12))
    mdd = max_drawdown(eq)
    return {
        "months": int(len(ret)),
        "cagr": annual_ret,
        "annual_vol": annual_vol,
        "sharpe": sharpe(ret, 12),
        "sortino": sortino(ret, 12),
        "max_drawdown": mdd,
        "calmar": float(annual_ret / abs(mdd)) if mdd != 0 else 0.0,
        "monthly_win_rate": float((ret > 0).mean()),
        "total_return": float(eq.iloc[-1] - 1),
    }
