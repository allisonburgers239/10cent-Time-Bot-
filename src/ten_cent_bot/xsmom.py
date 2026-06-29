"""Sleeve D: Cross-Sectional Momentum (XSMOM).

Each month, rank a basket of assets by trailing N-month return. Long the
top `top_n` equal-weighted, short the bottom `top_n` equal-weighted.
Cash-neutral, monthly rebalance, long/short.

Different from Sleeve B (TSMOM):
  - TSMOM uses ABSOLUTE momentum: sign of an asset's own trailing return.
  - XSMOM uses RELATIVE momentum: rank vs peers in the universe.
  - Same input data; mathematically independent signals.

References:
  Jegadeesh & Titman (1993), "Returns to Buying Winners and Selling Losers", JF.
  Asness, Moskowitz & Pedersen (2013), "Value and Momentum Everywhere", JF.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .metrics import max_drawdown, sharpe, sortino


@dataclass(frozen=True)
class XSMOMConfig:
    lookback_months: int = 12
    top_n: int = 3  # number of assets to be long, and to be short
    leverage: float = 1.0
    transaction_cost_bps: float = 10.0  # per unit of turnover


def backtest(monthly_prices: pd.DataFrame, config: XSMOMConfig | None = None) -> dict:
    """Cross-sectional momentum on a basket of monthly prices.

    Returns a dict with signal, position, asset_pnl, portfolio returns and equity.
    """
    cfg = config or XSMOMConfig()
    n_assets = monthly_prices.shape[1]
    if cfg.top_n * 2 > n_assets:
        raise ValueError(
            f"top_n*2={cfg.top_n * 2} exceeds universe size {n_assets}"
        )

    monthly_returns = monthly_prices.pct_change()
    momentum = monthly_prices / monthly_prices.shift(cfg.lookback_months) - 1
    ranks = momentum.rank(axis=1, method="first", ascending=False)

    weight = 1.0 / cfg.top_n
    signal = pd.DataFrame(0.0, index=ranks.index, columns=ranks.columns)
    signal[ranks <= cfg.top_n] = weight
    signal[ranks > (n_assets - cfg.top_n)] = -weight

    position = signal * cfg.leverage
    # Position decided at end of t-1 is applied to return during t.
    position_lagged = position.shift(1)

    asset_pnl = position_lagged * monthly_returns
    portfolio_return_gross = asset_pnl.sum(axis=1)

    turnover = position_lagged.diff().abs().sum(axis=1)
    monthly_cost = turnover * cfg.transaction_cost_bps / 10_000.0
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
