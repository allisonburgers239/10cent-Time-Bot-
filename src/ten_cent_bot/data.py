from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd


def load_bars(path: str | Path, source_tz: str = "UTC") -> pd.DataFrame:
    """Load OHLCV bars from CSV or Parquet.

    Expects columns: timestamp, open, high, low, close, volume.
    Returns a DataFrame with a tz-aware DatetimeIndex.
    """
    p = Path(path)
    if p.suffix == ".parquet":
        df = pd.read_parquet(p)
    elif p.suffix == ".csv":
        df = pd.read_csv(p)
    else:
        raise ValueError(f"Unsupported file type: {p.suffix}")

    df["timestamp"] = pd.to_datetime(df["timestamp"])
    if df["timestamp"].dt.tz is None:
        df["timestamp"] = df["timestamp"].dt.tz_localize(source_tz)
    return (
        df.set_index("timestamp")
        .sort_index()[["open", "high", "low", "close", "volume"]]
    )


def generate_synthetic_bars(
    start: str = "2024-01-02",
    days: int = 60,
    seed: int = 42,
    base_price: float = 18_000.0,
    bar_minutes: int = 5,
) -> pd.DataFrame:
    """Synthetic 5-min bars across NY trading hours for pipeline smoke tests.

    This is NOT a realistic market simulation. Use real data (Polygon, Databento,
    CME via your broker) before drawing any conclusion from a backtest.
    """
    rng = np.random.default_rng(seed)
    rows: list[dict] = []
    price = base_price

    start_date = pd.Timestamp(start, tz="America/New_York")
    bars_per_day = (16 * 60 - (9 * 60 + 30)) // bar_minutes  # 78 bars

    day_offset = 0
    days_emitted = 0
    while days_emitted < days:
        date = start_date + pd.Timedelta(days=day_offset)
        day_offset += 1
        if date.weekday() >= 5:
            continue
        session_start = date.replace(hour=9, minute=30, second=0, microsecond=0)
        for i in range(bars_per_day):
            ts = session_start + pd.Timedelta(minutes=bar_minutes * i)
            move = rng.normal(0, 8)
            open_p = price
            close_p = open_p + move
            high = max(open_p, close_p) + abs(rng.normal(0, 3))
            low = min(open_p, close_p) - abs(rng.normal(0, 3))
            vol = int(rng.integers(1_000, 5_000))
            rows.append(
                {
                    "timestamp": ts.tz_convert("UTC"),
                    "open": float(open_p),
                    "high": float(high),
                    "low": float(low),
                    "close": float(close_p),
                    "volume": vol,
                }
            )
            price = close_p
        days_emitted += 1

    return pd.DataFrame(rows).set_index("timestamp").sort_index()
