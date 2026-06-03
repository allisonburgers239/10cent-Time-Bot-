from __future__ import annotations

import numpy as np
import pandas as pd


def sharpe(returns: pd.Series, periods_per_year: int = 252) -> float:
    if len(returns) == 0 or returns.std(ddof=0) == 0:
        return 0.0
    return float(returns.mean() / returns.std(ddof=0) * np.sqrt(periods_per_year))


def sortino(returns: pd.Series, periods_per_year: int = 252) -> float:
    if len(returns) == 0:
        return 0.0
    downside = returns[returns < 0]
    if len(downside) == 0 or downside.std(ddof=0) == 0:
        return 0.0
    return float(returns.mean() / downside.std(ddof=0) * np.sqrt(periods_per_year))


def max_drawdown(equity: pd.Series) -> float:
    if len(equity) == 0:
        return 0.0
    peak = equity.cummax()
    dd = (equity - peak) / peak
    return float(dd.min())


def calmar(returns: pd.Series, equity: pd.Series, periods_per_year: int = 252) -> float:
    mdd = max_drawdown(equity)
    if mdd == 0:
        return 0.0
    annual_return = returns.mean() * periods_per_year
    return float(annual_return / abs(mdd))


def win_rate(pnl: pd.Series) -> float:
    if len(pnl) == 0:
        return 0.0
    return float((pnl > 0).mean())


def profit_factor(pnl: pd.Series) -> float:
    gains = pnl[pnl > 0].sum()
    losses = -pnl[pnl < 0].sum()
    if losses == 0:
        return float("inf") if gains > 0 else 0.0
    return float(gains / losses)


def summary(trades: pd.DataFrame, equity_col: str = "equity_after", pnl_col: str = "net_pnl_dollars") -> dict:
    """Headline stats for a completed backtest. Assumes one row per trade."""
    if trades.empty:
        return {
            "trades": 0,
            "net_pnl": 0.0,
            "sharpe": 0.0,
            "sortino": 0.0,
            "max_drawdown": 0.0,
            "calmar": 0.0,
            "win_rate": 0.0,
            "profit_factor": 0.0,
        }
    pnl = trades[pnl_col]
    equity = trades[equity_col]
    # Approximate annualization: one trade per day, 252 trading days.
    return {
        "trades": int(len(trades)),
        "net_pnl": float(pnl.sum()),
        "sharpe": sharpe(pnl / equity.shift(1).fillna(equity.iloc[0])),
        "sortino": sortino(pnl / equity.shift(1).fillna(equity.iloc[0])),
        "max_drawdown": max_drawdown(equity),
        "calmar": calmar(
            pnl / equity.shift(1).fillna(equity.iloc[0]),
            equity,
        ),
        "win_rate": win_rate(pnl),
        "profit_factor": profit_factor(pnl),
    }
