"""Sleeve K candidate: futures carry (roll yield) on the Sleeve B basket.

carry = (F1/F2 - 1) * 12 / months_between   (annualized; > 0 = backwardation)

Time-series variant: sign(carry) per market, vol-scaled exactly like
tsmom.py, monthly.  Cross-sectional variant: long top-N / short bottom-N
by carry.  Blend helper for B + carry.

References: Koijen, Moskowitz, Pedersen, Vrugt (2018) JFE "Carry";
Gorton, Hayashi, Rouwenhorst (2013); Bakshi, Gao, Rossi (2019).
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

# Approximate months between the front and the next listed contract on
# TradingView's 1!/2! continuous series.  Only used to annualize for the
# cross-sectional ranking; the time-series sign rule does not need it.
MONTHS_BETWEEN: dict[str, float] = {
    "ES": 3, "NQ": 3, "ZN": 3, "ZB": 3, "ZF": 3, "6E": 3, "6B": 3, "6J": 3, "6A": 3, "6C": 3, "6S": 3,
    "GC": 2, "SI": 2.4, "HG": 2.4, "PL": 3, "PA": 3,
    "CL": 1, "NG": 1, "RB": 1, "HO": 1,
    "ZC": 2.4, "ZS": 1.7, "ZW": 2.4, "SB": 3, "KC": 2.4, "CT": 2.4, "LE": 2, "HE": 1.5,
}


@dataclass(frozen=True)
class CarryConfig:
    mode: str = "time_series"      # time_series | cross_sectional
    smooth_months: int = 1         # rolling mean of carry before signing
    target_vol: float = 0.10
    max_leverage: float = 2.0
    vol_lookback: int = 12
    cs_top_n: int = 3
    transaction_cost_bps: float = 10.0


def compute_carry(f1: pd.DataFrame, f2: pd.DataFrame) -> pd.DataFrame:
    ann = pd.Series({c: 12.0 / MONTHS_BETWEEN.get(c, 3) for c in f1.columns})
    return (f1 / f2 - 1.0) * ann


def backtest(monthly_prices: pd.DataFrame, carry: pd.DataFrame, cfg: CarryConfig | None = None) -> dict:
    cfg = cfg or CarryConfig()
    rets = monthly_prices.pct_change()
    c = carry.rolling(cfg.smooth_months).mean() if cfg.smooth_months > 1 else carry
    if cfg.mode == "time_series":
        signal = np.sign(c)
    else:
        ranks = c.rank(axis=1, ascending=False, method="first")
        n = c.notna().sum(axis=1)
        signal = pd.DataFrame(0.0, index=c.index, columns=c.columns)
        signal[ranks.le(cfg.cs_top_n)] = 1.0
        signal[ranks.gt(n.values[:, None] - cfg.cs_top_n) & c.notna()] = -1.0
    rv = rets.rolling(cfg.vol_lookback).std() * np.sqrt(12)
    weight = (cfg.target_vol / rv).clip(upper=cfg.max_leverage)
    position = (weight * signal).shift(1)
    pnl = position * rets
    gross = pnl.mean(axis=1)
    cost = position.diff().abs().mean(axis=1) * cfg.transaction_cost_bps / 1e4
    net = gross - cost
    return {"signal": signal, "position": position, "asset_pnl": pnl, "monthly_return_gross": gross,
            "monthly_return_net": net, "equity": (1 + net.fillna(0)).cumprod()}


def blend_positions(pos_a: pd.DataFrame, pos_b: pd.DataFrame, w_a: float = 0.5, cap: float = 2.0) -> pd.DataFrame:
    cols = pos_a.columns.intersection(pos_b.columns)
    return (w_a * pos_a[cols] + (1 - w_a) * pos_b[cols]).clip(-cap, cap)
