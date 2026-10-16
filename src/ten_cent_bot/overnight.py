"""Sleeve E candidate: Overnight drift on major equity ETFs.

Buys at 4pm close, sells at 9:30am next day open. Flat during regular
trading hours. Long-only variant is the base case.

Reference: multiple 2010+ studies (Berkin-Swedroe; Kelly-Clark) show
most SPY returns come overnight, not intraday. Effect has persisted
through 2020-2025 in replications.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .metrics import max_drawdown, sharpe, sortino


@dataclass(frozen=True)
class OvernightConfig:
    cost_bps_per_side: float = 1.0  # 1bp per side = 2bp round-trip per hold-day
    use_trend_filter: bool = False
    trend_lookback: int = 200  # days
    exclude_days_of_week: tuple[int, ...] = ()  # 0=Mon..4=Fri
    # E v2: short-term-reversal sizing overlay (audited 2026-10-15, see
    # scripts/audit_overnight_reversal.py). On nights where the signal fires
    # the overnight position is multiplied by `reversal_multiplier`. Signal is
    # computed from closes up to and including the entry-day close only.
    #   reversal_signal: "none" | "streak" | "rsi2" | "either"
    reversal_signal: str = "none"
    reversal_streak_k: int = 3          # k consecutive down closes
    reversal_rsi_threshold: float = 10.0  # RSI(2) below this
    reversal_multiplier: float = 1.0


# Audited deployable setting for E v2 (RSI(2) < 10 -> 2x): Sharpe 0.47 -> 0.56,
# MaxDD -29% -> -31.5% on SPY/QQQ/IWM 2000-2026. Off by default above.
E_V2_CONFIG = OvernightConfig(reversal_signal="rsi2", reversal_multiplier=2.0)


def rsi(close: pd.Series, n: int = 2) -> pd.Series:
    """Wilder RSI (exponential, alpha = 1/n). Uses only past and current closes."""
    d = close.diff()
    up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    return 100 - 100 / (1 + up / dn.replace(0, np.nan))


def down_streak(close: pd.Series) -> pd.Series:
    """Number of consecutive down closes ending today (0 if today closed up)."""
    down = (close.pct_change() < 0).astype(int)
    return down.groupby((down != down.shift()).cumsum()).cumsum() * down


def reversal_signal(close: pd.Series, cfg: "OvernightConfig") -> pd.Series:
    """Boolean per day: does the sizing overlay fire for the overnight that
    starts at this day's close?  Only closes <= today are used."""
    if cfg.reversal_signal == "none":
        return pd.Series(False, index=close.index)
    streak = down_streak(close) >= cfg.reversal_streak_k
    low_rsi = rsi(close, 2) < cfg.reversal_rsi_threshold
    if cfg.reversal_signal == "streak":
        return streak
    if cfg.reversal_signal == "rsi2":
        return low_rsi.fillna(False)
    if cfg.reversal_signal == "either":
        return streak | low_rsi.fillna(False)
    raise ValueError(f"unknown reversal_signal {cfg.reversal_signal!r}")


def compute_overnight_returns(daily_ohlc: pd.DataFrame) -> pd.Series:
    """(open_{t+1} - close_t) / close_t."""
    return (daily_ohlc["open"].shift(-1) - daily_ohlc["close"]) / daily_ohlc["close"]


def compute_intraday_returns(daily_ohlc: pd.DataFrame) -> pd.Series:
    """(close_t - open_t) / open_t."""
    return (daily_ohlc["close"] - daily_ohlc["open"]) / daily_ohlc["open"]


def backtest_single(daily_ohlc: pd.DataFrame, config: OvernightConfig | None = None) -> dict:
    cfg = config or OvernightConfig()
    overnight_ret = compute_overnight_returns(daily_ohlc)

    position = pd.Series(1.0, index=daily_ohlc.index)

    if cfg.use_trend_filter:
        sma = daily_ohlc["close"].rolling(cfg.trend_lookback).mean()
        position = position.where(daily_ohlc["close"] > sma, 0.0)

    if cfg.exclude_days_of_week:
        dow = pd.Series(daily_ohlc.index.dayofweek, index=daily_ohlc.index)
        excluded = dow.isin(cfg.exclude_days_of_week)
        position = position.where(~excluded, 0.0)

    if cfg.reversal_signal != "none" and cfg.reversal_multiplier != 1.0:
        fire = reversal_signal(daily_ohlc["close"], cfg)
        position = position * np.where(fire, cfg.reversal_multiplier, 1.0)

    gross_return = position * overnight_ret
    # Cost: on any hold-day we buy at close then sell at next open (round trip)
    cost = position.abs() * cfg.cost_bps_per_side * 2 / 10_000.0
    net_return = gross_return - cost
    equity = (1 + net_return.fillna(0)).cumprod()

    return {
        "position": position,
        "overnight_return": overnight_ret,
        "gross_return": gross_return,
        "net_return": net_return,
        "equity": equity,
    }


def backtest_portfolio(data: dict[str, pd.DataFrame], config: OvernightConfig | None = None) -> dict:
    per_ticker = {t: backtest_single(df, config) for t, df in data.items()}
    combined = pd.DataFrame({t: r["net_return"] for t, r in per_ticker.items()})
    portfolio_ret = combined.mean(axis=1)
    equity = (1 + portfolio_ret.fillna(0)).cumprod()
    return {
        "per_ticker": per_ticker,
        "portfolio_return": portfolio_ret,
        "equity": equity,
    }


def summary_from_returns(ret: pd.Series, periods_per_year: int = 252) -> dict:
    ret = ret.dropna()
    if len(ret) == 0:
        return {}
    annual_ret = float((1 + ret.mean()) ** periods_per_year - 1)
    annual_vol = float(ret.std(ddof=0) * np.sqrt(periods_per_year))
    eq = (1 + ret.fillna(0)).cumprod()
    mdd = max_drawdown(eq)
    return {
        "days": int(len(ret)),
        "cagr": annual_ret,
        "annual_vol": annual_vol,
        "sharpe": sharpe(ret, periods_per_year),
        "sortino": sortino(ret, periods_per_year),
        "max_drawdown": mdd,
        "calmar": float(annual_ret / abs(mdd)) if mdd != 0 else 0.0,
        "win_rate": float((ret > 0).mean()),
    }
