"""Sleeve B: Time-Series Momentum (TSMOM).

Canonical Moskowitz-Ooi-Pedersen formulation:
  - signal = sign(price_t / price_{t-12m} - 1) per asset
  - weight = target_vol / realized_vol_12m, capped at max_leverage
  - monthly rebalance, equal-weight across the basket
  - long/short

Reference:
  Moskowitz, Ooi & Pedersen (2012), "Time Series Momentum", JFE.
  Hurst, Ooi & Pedersen (2017), "A Century of Evidence on Trend-Following".
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class TSMOMConfig:
    lookback_months: int = 12
    target_vol: float = 0.10  # 10% annualized vol per position
    max_leverage: float = 2.0  # cap on absolute position
    transaction_cost_bps: float = 10.0  # round-trip per rebalance


def backtest(monthly_prices: pd.DataFrame, config: TSMOMConfig | None = None) -> dict:
    """Run TSMOM on a basket of monthly prices.

    `monthly_prices` columns are ticker symbols, rows are month-end dates.
    Returns a dict with signals, positions, returns, and the equity curve.
    """
    cfg = config or TSMOMConfig()

    monthly_returns = monthly_prices.pct_change()

    signal = np.sign(monthly_prices / monthly_prices.shift(cfg.lookback_months) - 1)
    realized_vol = monthly_returns.rolling(cfg.lookback_months).std() * np.sqrt(12)
    raw_weight = (cfg.target_vol / realized_vol).clip(upper=cfg.max_leverage)
    position = raw_weight * signal

    # Decision at end of month t-1 is applied to return during month t.
    position_lagged = position.shift(1)
    asset_pnl = position_lagged * monthly_returns
    portfolio_ret_gross = asset_pnl.mean(axis=1)

    monthly_cost = (
        position_lagged.diff().abs().mean(axis=1)
        * cfg.transaction_cost_bps
        / 10_000.0
    )
    portfolio_ret_net = portfolio_ret_gross - monthly_cost

    equity = (1 + portfolio_ret_net.fillna(0)).cumprod()

    return {
        "signal": signal,
        "position": position_lagged,
        "asset_pnl": asset_pnl,
        "monthly_return_gross": portfolio_ret_gross,
        "monthly_return_net": portfolio_ret_net,
        "monthly_cost": monthly_cost,
        "equity": equity,
    }


def summary(result: dict) -> dict:
    ret = result["monthly_return_net"].dropna()
    eq = result["equity"]
    if len(ret) == 0:
        return {}
    annual_ret = float((1 + ret.mean()) ** 12 - 1)
    annual_vol = float(ret.std() * np.sqrt(12))
    sharpe = annual_ret / annual_vol if annual_vol > 0 else 0.0
    downside = ret[ret < 0]
    sortino = (
        (ret.mean() * 12) / (downside.std() * np.sqrt(12))
        if len(downside) > 0 and downside.std() > 0
        else 0.0
    )
    peak = eq.cummax()
    mdd = float(((eq - peak) / peak).min())
    calmar = annual_ret / abs(mdd) if mdd != 0 else 0.0
    return {
        "months": int(len(ret)),
        "cagr": annual_ret,
        "annual_vol": annual_vol,
        "sharpe": float(sharpe),
        "sortino": float(sortino),
        "max_drawdown": mdd,
        "calmar": float(calmar),
        "monthly_win_rate": float((ret > 0).mean()),
        "total_return": float(eq.iloc[-1] - 1),
    }
