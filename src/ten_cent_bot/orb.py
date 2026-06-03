from __future__ import annotations

from dataclasses import dataclass
from datetime import time

import pandas as pd


@dataclass(frozen=True)
class ORBConfig:
    session_open: time = time(9, 30)
    session_close: time = time(16, 0)
    opening_range_bars: int = 1  # 1 bar of 5 min = 5-min opening range
    vol_filter_lookback: int = 14
    vol_filter_min_ratio: float = 0.5
    timezone: str = "America/New_York"


def generate_signals(bars: pd.DataFrame, config: ORBConfig | None = None) -> pd.DataFrame:
    """Opening-Range Breakout signal generation for index futures 5-min bars.

    Assumptions baked in for v0:
      - `bars` has a tz-aware DatetimeIndex (UTC or any tz; converted internally).
      - Columns: open, high, low, close, volume.
      - Entry is a limit fill AT the opening-range extreme on first bar that
        breaks it (slightly optimistic; revisit with a "next-bar fill at close"
        variant during execution-cost validation).
      - Stop is the opposite OR extreme.
      - The entry bar itself is not checked for stop hit (assume limit fill
        at the level and walk forward from the next bar).
      - One trade per session.
      - Exit on stop or at session close, whichever comes first.
    """
    cfg = config or ORBConfig()

    if bars.index.tz is None:
        raise ValueError("bars must have a tz-aware DatetimeIndex")

    local = bars.tz_convert(cfg.timezone)
    or_history: list[float] = []
    trades: list[dict] = []

    for date, day_bars in local.groupby(local.index.date):
        session = day_bars.between_time(cfg.session_open, cfg.session_close)
        if len(session) < cfg.opening_range_bars + 1:
            continue

        or_bars = session.iloc[: cfg.opening_range_bars]
        or_high = float(or_bars["high"].max())
        or_low = float(or_bars["low"].min())
        or_range = or_high - or_low

        if (
            cfg.vol_filter_lookback > 0
            and len(or_history) >= cfg.vol_filter_lookback
        ):
            recent = or_history[-cfg.vol_filter_lookback :]
            avg_range = sum(recent) / len(recent)
            if or_range < cfg.vol_filter_min_ratio * avg_range:
                or_history.append(or_range)
                continue
        or_history.append(or_range)

        remaining = session.iloc[cfg.opening_range_bars :]

        side: str | None = None
        entry_idx = None
        entry_price = 0.0
        stop = 0.0
        for idx, bar in remaining.iterrows():
            if bar["high"] > or_high:
                side, entry_idx, entry_price, stop = "long", idx, or_high, or_low
                break
            if bar["low"] < or_low:
                side, entry_idx, entry_price, stop = "short", idx, or_low, or_high
                break

        if side is None:
            continue

        post_entry_loc = remaining.index.get_loc(entry_idx) + 1
        after_entry = remaining.iloc[post_entry_loc:]

        exit_idx = None
        exit_price: float | None = None
        exit_reason: str | None = None
        for idx, bar in after_entry.iterrows():
            if side == "long" and bar["low"] <= stop:
                exit_idx, exit_price, exit_reason = idx, stop, "stop"
                break
            if side == "short" and bar["high"] >= stop:
                exit_idx, exit_price, exit_reason = idx, stop, "stop"
                break

        if exit_idx is None:
            last = session.iloc[-1]
            exit_idx = last.name
            exit_price = float(last["close"])
            exit_reason = "session_close"

        pnl_points = (
            float(exit_price - entry_price)
            if side == "long"
            else float(entry_price - exit_price)
        )

        trades.append(
            {
                "date": date,
                "side": side,
                "or_high": or_high,
                "or_low": or_low,
                "entry_time": entry_idx,
                "entry_price": float(entry_price),
                "stop": float(stop),
                "exit_time": exit_idx,
                "exit_price": float(exit_price),
                "exit_reason": exit_reason,
                "pnl_points": pnl_points,
            }
        )

    return pd.DataFrame(trades)
