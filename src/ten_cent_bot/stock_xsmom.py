"""Sleeve F candidate: Stock-level cross-sectional momentum.

The Jegadeesh-Titman canonical formulation, plus the more modern
"residual momentum" variant (Blitz-Hanauer-Vidojevic 2020) that
regresses out market beta first and ranks by residuals.

Long the top-N momentum stocks, short the bottom-N, monthly rebalance.
Optional long-only variant.

Different from Sleeve D (which failed) because Sleeve D ranked 9
sector aggregates. Individual stocks are the universe where the
momentum effect is best-documented.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .metrics import max_drawdown, sharpe, sortino


@dataclass(frozen=True)
class StockXSMOMConfig:
    lookback_months: int = 12
    top_n: int = 5
    long_only: bool = False
    residual: bool = False  # True = residualize returns vs market before ranking
    residual_window_months: int = 36  # rolling window for beta estimation
    transaction_cost_bps: float = 20.0  # per unit of turnover; wider than ETFs


def compute_residual_returns(
    stock_returns: pd.DataFrame,
    market_returns: pd.Series,
    window: int,
) -> pd.DataFrame:
    """Rolling-beta residualized returns per stock.

    beta_t = cov(stock, market, window) / var(market, window)
    residual_t = stock_t - beta_t * market_t
    """
    result = pd.DataFrame(index=stock_returns.index, columns=stock_returns.columns, dtype=float)
    market = market_returns.reindex(stock_returns.index)
    var = market.rolling(window).var()
    for col in stock_returns.columns:
        s = stock_returns[col]
        cov = s.rolling(window).cov(market)
        beta = cov / var.replace(0, np.nan)
        result[col] = s - beta * market
    return result


def backtest(
    monthly_prices: pd.DataFrame,
    market_prices: pd.Series | None = None,
    config: StockXSMOMConfig | None = None,
) -> dict:
    """Cross-sectional momentum on a stock universe.

    Args:
      monthly_prices: DataFrame indexed by month-end, stocks as columns.
      market_prices:  Series (e.g. SPY) at same frequency. Required if
                      residual=True.
      config:         StockXSMOMConfig; defaults to vanilla momentum.
    """
    cfg = config or StockXSMOMConfig()
    n_assets = monthly_prices.shape[1]
    if cfg.top_n * 2 > n_assets and not cfg.long_only:
        raise ValueError(
            f"top_n*2={cfg.top_n * 2} exceeds universe {n_assets}"
        )
    if cfg.residual and market_prices is None:
        raise ValueError("market_prices required when residual=True")

    monthly_returns = monthly_prices.pct_change()

    # Signal source: either raw prices or residualized returns
    if cfg.residual:
        market_ret = market_prices.pct_change()
        residual = compute_residual_returns(
            monthly_returns, market_ret, cfg.residual_window_months
        )
        # Cumulative residual return over lookback for the signal
        signal_source = residual.rolling(cfg.lookback_months).sum()
    else:
        signal_source = monthly_prices / monthly_prices.shift(cfg.lookback_months) - 1

    ranks = signal_source.rank(axis=1, method="first", ascending=False)

    weight = 1.0 / cfg.top_n
    signal = pd.DataFrame(0.0, index=ranks.index, columns=ranks.columns)
    signal[ranks <= cfg.top_n] = weight
    if not cfg.long_only:
        signal[ranks > (n_assets - cfg.top_n)] = -weight

    position = signal
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
