"""Sleeve G candidate: CFTC COT / AMDX weekly bias on NQ.

Systematizes Ali's discretionary AMDX framework into deterministic rules
that can be audited. Fetches free CFTC Traders in Financial Futures (TFF)
weekly data via the public Socrata API, computes AM/HF/Dealer net
positions, and applies the Part-6 rules with concrete numeric thresholds.

Sources:
  CFTC TFF Socrata endpoint:
    https://publicreporting.cftc.gov/resource/gpe5-46if.json
  Contract used: "NASDAQ-100 Consolidated - CHICAGO MERCANTILE EXCHANGE"

Timing (important):
  - Position snapshot: Tuesday (report_date_as_yyyy_mm_dd)
  - Report release:    Friday 3:30 PM ET (Tuesday date + 3 days)
  - Trade window:      Following Monday open -> next Friday close
  Implementation aligns COT weekly signal to the NEXT weekly return.
"""
from __future__ import annotations

import json
import urllib.parse
import urllib.request
from dataclasses import dataclass

import numpy as np
import pandas as pd


TFF_ENDPOINT = "https://publicreporting.cftc.gov/resource/gpe5-46if.json"
NQ_CONSOLIDATED = "NASDAQ-100 Consolidated - CHICAGO MERCANTILE EXCHANGE"


@dataclass(frozen=True)
class AMDXConfig:
    """Numeric threshold set that systematizes MD Part 6's discretionary rules."""

    # Rolling window for percentile ranking of HF net position (weeks)
    hf_pctl_window: int = 52
    # HF percentile below this = "recent short extreme"
    hf_extreme_low_pct: float = 0.20
    # HF percentile above this = "mid-range" cutoff for accumulation rule
    hf_mid_pct: float = 0.50
    # Weeks over which AM change is measured for "declining" flag
    am_delta_window: int = 2
    # Threshold: AM net position level considered "elevated" (rolling median)
    am_elevated_use_median: bool = True
    # Signal frequency: only trade on non-zero signals (bullish/bearish)
    trade_neutral_as_flat: bool = True
    # Cost per position change (bps of notional; NQ round-trip ~2 bps retail)
    cost_bps_per_change: float = 2.0
    # Position size when signal fires (1.0 = full notional)
    position_size: float = 1.0


def fetch_tff_history(
    contract: str = NQ_CONSOLIDATED,
    start: str = "2010-01-01",
) -> pd.DataFrame:
    """Pull the full TFF weekly report history for one contract."""
    # SoQL query - filter by contract, sort ascending, all rows
    params = {
        "$where": f"market_and_exchange_names = '{contract}' AND report_date_as_yyyy_mm_dd >= '{start}T00:00:00.000'",
        "$order": "report_date_as_yyyy_mm_dd asc",
        "$limit": "5000",
    }
    url = TFF_ENDPOINT + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": "ten-cent-bot/0.1"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        rows = json.loads(resp.read())

    df = pd.DataFrame(rows)
    if df.empty:
        return df

    # Parse and coerce
    df["date"] = pd.to_datetime(df["report_date_as_yyyy_mm_dd"]).dt.tz_localize(None)
    numeric_cols = [
        "open_interest_all",
        "dealer_positions_long_all",
        "dealer_positions_short_all",
        "asset_mgr_positions_long",
        "asset_mgr_positions_short",
        "lev_money_positions_long",
        "lev_money_positions_short",
        "nonrept_positions_long_all",
        "nonrept_positions_short_all",
    ]
    for c in numeric_cols:
        df[c] = pd.to_numeric(df[c], errors="coerce")

    df = df.set_index("date").sort_index()

    df["am_net"] = df["asset_mgr_positions_long"] - df["asset_mgr_positions_short"]
    df["hf_net"] = df["lev_money_positions_long"] - df["lev_money_positions_short"]
    df["dealer_net"] = (
        df["dealer_positions_long_all"] - df["dealer_positions_short_all"]
    )
    df["retail_net"] = (
        df["nonrept_positions_long_all"] - df["nonrept_positions_short_all"]
    )

    return df[
        [
            "open_interest_all",
            "am_net",
            "hf_net",
            "dealer_net",
            "retail_net",
        ]
    ]


def compute_amdx_signals(cot: pd.DataFrame, cfg: AMDXConfig | None = None) -> pd.DataFrame:
    """Systematic AMDX phase detection from CFTC weekly net positions.

    Returns DataFrame with columns: phase (str), signal (-1/0/+1), and
    the derived features used in the rules.
    """
    cfg = cfg or AMDXConfig()
    df = cot.copy()

    # Rolling percentile rank of HF net (0 = most short, 1 = most long in window)
    df["hf_pctl"] = df["hf_net"].rolling(cfg.hf_pctl_window).rank(pct=True)

    # AM net's rolling median as the "elevated" threshold
    if cfg.am_elevated_use_median:
        df["am_threshold"] = df["am_net"].rolling(cfg.hf_pctl_window).median()
    else:
        df["am_threshold"] = 0.0

    # Deltas: how much AM/HF changed over the window
    df["am_delta"] = df["am_net"] - df["am_net"].shift(cfg.am_delta_window)
    df["hf_delta"] = df["hf_net"] - df["hf_net"].shift(1)

    # Rule application (order matters - matches MD Part 6)
    phase = pd.Series("Transition", index=df.index)
    signal = pd.Series(0.0, index=df.index)

    hf_low = df["hf_pctl"] <= cfg.hf_extreme_low_pct
    hf_mid = df["hf_pctl"] <= cfg.hf_mid_pct
    am_declining = df["am_delta"] < 0
    am_rising = df["am_delta"] > 0
    hf_covering = df["hf_delta"] > 0
    hf_shorting = df["hf_delta"] < 0
    am_elevated = df["am_net"] > df["am_threshold"]
    hf_pos = df["hf_net"] > 0
    hf_neg = df["hf_net"] < 0

    # 1. HF near short extreme AND AM declining -> X (bearish)
    mask = hf_low & am_declining
    phase.loc[mask] = "X_reversal"
    signal.loc[mask] = -1.0

    # 2. HF at short extreme AND still adding shorts -> M (neutral)
    mask = hf_low & hf_shorting & (phase == "Transition")
    phase.loc[mask] = "M_manipulation"
    signal.loc[mask] = 0.0

    # 3. HF short but covering AND AM elevated -> D (bullish)
    mask = hf_neg & hf_covering & am_elevated & (phase == "Transition")
    phase.loc[mask] = "D_distribution"
    signal.loc[mask] = 1.0

    # 4. HF flipped positive AND AM declining -> X (bearish, exhaustion top)
    mask = hf_pos & am_declining & (phase == "Transition")
    phase.loc[mask] = "X_exhaustion"
    signal.loc[mask] = -1.0

    # 5. AM rising AND HF short (not extreme) -> A (bullish)
    mask = am_rising & hf_neg & (~hf_low) & (phase == "Transition")
    phase.loc[mask] = "A_accumulation"
    signal.loc[mask] = 1.0

    df["phase"] = phase
    df["signal"] = signal
    return df


def align_to_weekly_price(
    signals: pd.DataFrame, weekly_prices: pd.DataFrame
) -> pd.DataFrame:
    """Align Tuesday-dated COT signals to weekly-Friday-dated NQ returns.

    Signal from report covering positions as of Tue W1 (released Fri W1) is
    applied to the trade held from close of Fri W1 through close of Fri W2.
    In practice: reindex COT to the FOLLOWING Friday, then use signal.shift(1)
    when combining with weekly returns.
    """
    sig = signals.copy()
    # Shift COT Tuesday date to the Friday of the SAME calendar week
    sig.index = sig.index + pd.Timedelta(days=3)
    # Align to actual weekly bar dates (find nearest Friday available)
    weekly_prices = weekly_prices.copy()
    combined = pd.concat(
        [sig[["signal", "phase"]], weekly_prices["Close"].rename("close")],
        axis=1,
        sort=False,
    ).sort_index()
    combined["signal"] = combined["signal"].ffill(limit=6)
    combined["phase"] = combined["phase"].ffill(limit=6)
    combined = combined.dropna(subset=["close"])
    combined["weekly_return"] = combined["close"].pct_change()
    return combined


def backtest(
    combined: pd.DataFrame,
    cfg: AMDXConfig | None = None,
) -> dict:
    """Backtest the AMDX signal: signal(t-1) applied to return(t)."""
    cfg = cfg or AMDXConfig()
    position = combined["signal"].shift(1) * cfg.position_size
    weekly_ret = combined["weekly_return"]

    gross = position * weekly_ret
    turnover = position.diff().abs().fillna(position.abs())
    cost = turnover * cfg.cost_bps_per_change / 10_000.0

    net = (gross - cost).fillna(0)
    equity = (1 + net).cumprod()

    return {
        "position": position,
        "gross_return": gross,
        "cost": cost,
        "net_return": net,
        "equity": equity,
    }


def summary_from_returns(ret: pd.Series, periods_per_year: int = 52) -> dict:
    from .metrics import max_drawdown, sharpe, sortino

    ret = ret.dropna()
    if len(ret) == 0:
        return {}
    annual = (1 + ret.mean()) ** periods_per_year - 1
    vol = ret.std(ddof=0) * np.sqrt(periods_per_year)
    eq = (1 + ret.fillna(0)).cumprod()
    mdd = max_drawdown(eq)
    return {
        "weeks": int(len(ret)),
        "cagr": float(annual),
        "annual_vol": float(vol),
        "sharpe": sharpe(ret, periods_per_year),
        "sortino": sortino(ret, periods_per_year),
        "max_drawdown": mdd,
        "win_rate": float((ret > 0).mean()),
    }
