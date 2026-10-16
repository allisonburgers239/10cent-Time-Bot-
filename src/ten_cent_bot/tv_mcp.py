"""Load TradingView MCP `get_ohlcv` responses saved as JSON (format=columns).

Files live in data/tv/<EXCHANGE>_<SYMBOL>_<TF>.json and are the verbatim
tool response: {"bars": {"t": [...], "o": [...], "h": [...], "l": [...],
"c": [...], "v": [...]}, "symbol": ..., "interval": ..., ...}.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd


def load_tv_json(path: str | Path) -> pd.DataFrame:
    d = json.loads(Path(path).read_text())
    b = d["bars"]
    df = pd.DataFrame({k: b[k] for k in ("o", "h", "l", "c", "v") if k in b})
    df.index = pd.to_datetime(pd.Series(b["t"]), unit="s", utc=True).dt.tz_convert(None)
    df.index.name = "time"
    df = df.rename(columns={"o": "open", "h": "high", "l": "low", "c": "close", "v": "volume"})
    df.attrs["symbol"] = d.get("symbol")
    df.attrs["interval"] = d.get("interval")
    return df.sort_index()


def load_pair(data_dir: Path, exchange: str, root: str, tf: str = "1M") -> tuple[pd.Series, pd.Series] | None:
    """Front (1!) and second (2!) month close series, month-end aligned."""
    p1 = data_dir / f"{exchange}_{root}1!_{tf}.json"
    p2 = data_dir / f"{exchange}_{root}2!_{tf}.json"
    if not (p1.exists() and p2.exists()):
        return None
    f1 = load_tv_json(p1)["close"]
    f2 = load_tv_json(p2)["close"]
    if tf == "1M":
        f1 = month_end_index(f1)
        f2 = month_end_index(f2)
    return f1, f2


def month_end_index(s: pd.Series) -> pd.Series:
    """TradingView stamps a monthly bar at its session-open in UTC, which for
    CME products is 22:00/23:00 UTC on the LAST day of the previous month.
    Shift by 12h before taking the month so the bar lands in the month it
    belongs to, then label by month-end."""
    idx = (s.index + pd.Timedelta(hours=12)).to_period("M").to_timestamp("M")
    out = pd.Series(s.values, index=idx, name=s.name)
    return out[~out.index.duplicated(keep="last")].sort_index()
