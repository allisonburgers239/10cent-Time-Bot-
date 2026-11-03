"""Equity history persistence - the input the kill switch never had.

data/equity_history.csv: one row per date (date, equity). Both ticket
scripts append after reading the account; the risk gate reads it.
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path

import pandas as pd


def load_equity_history(path: Path) -> pd.Series | None:
    if not path.exists():
        return None
    df = pd.read_csv(path, parse_dates=["date"])
    if df.empty:
        return None
    s = df.drop_duplicates("date", keep="last").set_index("date")["equity"].astype(float).sort_index()
    return s


def append_equity(path: Path, equity: float, on: dt.date | None = None) -> pd.Series:
    on = on or dt.date.today()
    path.parent.mkdir(parents=True, exist_ok=True)
    hist = load_equity_history(path)
    row = pd.DataFrame({"date": [pd.Timestamp(on)], "equity": [float(equity)]})
    if hist is not None:
        df = pd.concat([hist.rename("equity").reset_index(), row]).drop_duplicates("date", keep="last").sort_values("date")
    else:
        df = row
    df.to_csv(path, index=False)
    return df.set_index("date")["equity"]
