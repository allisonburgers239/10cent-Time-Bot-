"""Sleeve H candidate: Commodity COT hedger-pressure strategy.

Implements Hong & Yogo (2012) hedger pressure as a systematic signal
on 12 CME/ICE commodity futures. This is a DIFFERENT strategy from
Sleeve G (which used TFF Asset Manager/Leveraged Funds categories on
NQ). Here we use the Disaggregated COT report's Producer/Merchant
category, whose positioning IS the risk-premium signal in the
published literature.

Hedger Pressure:
    HP = (short_hedger - long_hedger) / (short_hedger + long_hedger)

Sign convention: positive HP = commercials net short = producers
hedging output = speculators demanded to bear risk => higher expected
future return on the long-speculator side.

Two signal variants:
  - Time-series (per commodity): long when HP is in top half of its
    trailing 52-week distribution.
  - Cross-sectional (portfolio): each week, long top-N commodities by
    HP, short bottom-N. Equal-weight.

References:
  Hong & Yogo (2012), "What Does Futures Market Interest Tell Us About
    the Macroeconomy and Asset Prices?", JFE.
  Basu & Miffre (2013), "Capturing the risk premium of commodity
    futures: The role of hedging pressure", Journal of Banking &
    Finance.
"""
from __future__ import annotations

import json
import urllib.parse
import urllib.request
from dataclasses import dataclass

import numpy as np
import pandas as pd


DA_ENDPOINT = "https://publicreporting.cftc.gov/resource/72hh-3qpy.json"


# {yfinance_symbol: CFTC contract name in Disaggregated report}
COMMODITY_UNIVERSE: dict[str, str] = {
    "GC=F": "GOLD - COMMODITY EXCHANGE INC.",
    "SI=F": "SILVER - COMMODITY EXCHANGE INC.",
    "HG=F": "COPPER-GRADE #1 - COMMODITY EXCHANGE INC.",
    "CL=F": "CRUDE OIL, LIGHT SWEET - NEW YORK MERCANTILE EXCHANGE",
    "NG=F": "NATURAL GAS - NEW YORK MERCANTILE EXCHANGE",
    "ZC=F": "CORN - CHICAGO BOARD OF TRADE",
    "ZS=F": "SOYBEANS - CHICAGO BOARD OF TRADE",
    "ZW=F": "WHEAT-SRW - CHICAGO BOARD OF TRADE",
    "SB=F": "SUGAR NO. 11 - ICE FUTURES U.S.",
    "CT=F": "COTTON NO. 2 - ICE FUTURES U.S.",
    "KC=F": "COFFEE C - ICE FUTURES U.S.",
    "LE=F": "LIVE CATTLE - CHICAGO MERCANTILE EXCHANGE",
}


@dataclass(frozen=True)
class HPConfig:
    lookback_weeks: int = 52
    signal_mode: str = "time_series"  # "time_series" or "cross_sectional"
    ts_long_threshold: float = 0.5     # long when HP percentile > this
    ts_short_threshold: float = 0.0    # short when < this (0 disables shorts)
    cs_top_n: int = 3                  # cross-sectional long-N / short-N
    cs_long_only: bool = False
    cost_bps_per_change: float = 10.0  # per unit turnover
    position_size: float = 1.0


def fetch_disaggregated(contract: str) -> pd.DataFrame:
    """Fetch full weekly Disaggregated COT history for one contract."""
    params = {
        "$where": f"market_and_exchange_names = '{contract}'",
        "$order": "report_date_as_yyyy_mm_dd asc",
        "$limit": "5000",
    }
    url = DA_ENDPOINT + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": "ten-cent-bot/0.1"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        rows = json.loads(resp.read())
    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["report_date_as_yyyy_mm_dd"]).dt.tz_localize(None)
    # Note: Producer/Merchant fields don't have _all suffix in Disaggregated
    #       Swap short has a DOUBLE underscore. All other fields end in _all.
    numeric_cols = [
        "open_interest_all",
        "prod_merc_positions_long",
        "prod_merc_positions_short",
        "swap_positions_long_all",
        "swap__positions_short_all",
        "m_money_positions_long_all",
        "m_money_positions_short_all",
        "other_rept_positions_long",
        "other_rept_positions_short",
    ]
    for c in numeric_cols:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    return df.set_index("date").sort_index()


def compute_hedger_pressure(cot: pd.DataFrame) -> pd.Series:
    """HP = (short_hedger - long_hedger) / (short_hedger + long_hedger).

    Positive HP <=> commercials net short <=> high expected long-side return
    per Hong-Yogo hedging-pressure theory.
    """
    pm_long = cot["prod_merc_positions_long"]
    pm_short = cot["prod_merc_positions_short"]
    total = pm_short + pm_long
    return (pm_short - pm_long) / total.replace(0, np.nan)


def time_series_signal(hp: pd.Series, cfg: HPConfig | None = None) -> pd.Series:
    """Per-commodity signal from HP percentile."""
    cfg = cfg or HPConfig()
    pctl = hp.rolling(cfg.lookback_weeks).rank(pct=True)
    signal = pd.Series(0.0, index=hp.index)
    signal[pctl > cfg.ts_long_threshold] = 1.0
    if cfg.ts_short_threshold > 0:
        signal[pctl < cfg.ts_short_threshold] = -1.0
    return signal


def cross_sectional_signal(hp_frame: pd.DataFrame, cfg: HPConfig | None = None) -> pd.DataFrame:
    """Cross-sectional long top-N / short bottom-N by current HP each week."""
    cfg = cfg or HPConfig()
    ranks = hp_frame.rank(axis=1, ascending=False, method="first")
    n_assets = hp_frame.shape[1]
    weight = 1.0 / cfg.cs_top_n
    sig = pd.DataFrame(0.0, index=hp_frame.index, columns=hp_frame.columns)
    sig[ranks <= cfg.cs_top_n] = weight
    if not cfg.cs_long_only and n_assets >= 2 * cfg.cs_top_n:
        sig[ranks > (n_assets - cfg.cs_top_n)] = -weight
    return sig


def align_to_weekly_prices(
    signals: pd.Series | pd.DataFrame,
    weekly_prices: pd.Series | pd.DataFrame,
) -> pd.DataFrame | pd.Series:
    """Shift Tuesday-dated COT signals to Friday (report release), then let
    signal.shift(1) put the position on the next weekly return."""
    if isinstance(signals, pd.Series):
        s = signals.copy()
        s.index = s.index + pd.Timedelta(days=3)
        combined = pd.concat(
            [s.rename("signal"), weekly_prices.rename("close")], axis=1, sort=False
        ).sort_index()
        combined["signal"] = combined["signal"].ffill(limit=6)
        combined = combined.dropna(subset=["close"])
        combined["weekly_return"] = combined["close"].pct_change()
        return combined
    else:
        s = signals.copy()
        s.index = s.index + pd.Timedelta(days=3)
        p = weekly_prices.copy()
        # Reindex signal frame to price index
        aligned_sig = s.reindex(p.index, method="ffill", limit=6).fillna(0)
        weekly_ret = p.pct_change()
        return {"signal": aligned_sig, "weekly_return": weekly_ret, "close": p}


def backtest_time_series(combined: pd.DataFrame, cfg: HPConfig | None = None) -> dict:
    cfg = cfg or HPConfig()
    position = combined["signal"].shift(1) * cfg.position_size
    ret = combined["weekly_return"]
    gross = position * ret
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


def backtest_cross_sectional(
    signal_frame: pd.DataFrame,
    return_frame: pd.DataFrame,
    cfg: HPConfig | None = None,
) -> dict:
    """Portfolio backtest: signal(t-1) applied to return(t), summed across assets."""
    cfg = cfg or HPConfig()
    position = signal_frame.shift(1) * cfg.position_size
    asset_pnl = position * return_frame
    portfolio_return_gross = asset_pnl.sum(axis=1)
    turnover = position.diff().abs().sum(axis=1)
    cost = turnover * cfg.cost_bps_per_change / 10_000.0
    portfolio_return_net = (portfolio_return_gross - cost).fillna(0)
    equity = (1 + portfolio_return_net).cumprod()
    return {
        "position": position,
        "asset_pnl": asset_pnl,
        "portfolio_return_net": portfolio_return_net,
        "portfolio_return_gross": portfolio_return_gross,
        "cost": cost,
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
