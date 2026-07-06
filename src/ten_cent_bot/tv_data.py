"""Load TradingView CSV exports.

TradingView's chart-to-CSV export format:
  header: time,open,high,low,close  (no volume column)
  time:   unix seconds, UTC
  prices: adjusted close basis
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd


def load_tv_csv(path: str | Path, tz: str = "America/New_York") -> pd.DataFrame:
    """Load one TradingView CSV export, return a tz-aware OHLCV DataFrame.

    Adds a placeholder `volume` column (constant) because our downstream ORB
    code expects the standard OHLCV schema, but the strategy itself does not
    use volume.
    """
    df = pd.read_csv(path)
    df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
    df = df.set_index("time").sort_index()
    df.columns = [c.lower() for c in df.columns]
    if "volume" not in df.columns:
        df["volume"] = 1  # placeholder; ORB doesn't consume volume
    return df[["open", "high", "low", "close", "volume"]]
