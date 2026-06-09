"""Sleeve C: Crypto cash-and-carry via perpetual funding rates.

The trade: long spot + short perp = delta-neutral. As the short side, we
collect funding payments when funding is positive.

Data source: Deribit's public funding-rate history API. Deribit pays funding
continuously (charged hourly via `interest_1h`), so we aggregate the
hourly stream to 8-hour bars before applying the signal - this matches the
discrete-funding convention used by most exchanges and the published
literature.

Binance and Bybit both geo-block US IPs for futures endpoints, so Deribit
is the practical free choice. (See `/api/v2/public/get_funding_rate_history`.)
"""
from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request

import numpy as np
import pandas as pd

from .metrics import max_drawdown, sharpe, sortino

DERIBIT_FUNDING_URL = "https://www.deribit.com/api/v2/public/get_funding_rate_history"


def _fetch_window(instrument: str, start_ms: int, end_ms: int) -> list:
    params = {
        "instrument_name": instrument,
        "start_timestamp": start_ms,
        "end_timestamp": end_ms,
    }
    url = DERIBIT_FUNDING_URL + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": "ten-cent-bot/0.1"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read()).get("result") or []


def fetch_funding_history(
    instrument: str,
    start: str,
    end: str | None = None,
    window_days: int = 30,
) -> pd.DataFrame:
    """Paginate Deribit funding history. Returns HOURLY DataFrame with `rate`.

    Deribit caps responses to ~720 records per request, hence the 30-day window.
    """
    end = end or pd.Timestamp.utcnow().strftime("%Y-%m-%d")
    cursor = int(pd.Timestamp(start, tz="UTC").timestamp() * 1000)
    end_ms = int(pd.Timestamp(end, tz="UTC").timestamp() * 1000)
    window_ms = window_days * 24 * 3600 * 1000

    records: list = []
    while cursor < end_ms:
        chunk_end = min(cursor + window_ms, end_ms)
        batch = _fetch_window(instrument, cursor, chunk_end)
        records.extend(batch)
        cursor = chunk_end + 1
        time.sleep(0.1)

    if not records:
        return pd.DataFrame(columns=["rate"])

    df = pd.DataFrame(records)
    df["timestamp"] = pd.to_datetime(df["timestamp"].astype("int64"), unit="ms", utc=True)
    df["rate"] = df["interest_1h"].astype(float)
    return (
        df.drop_duplicates(subset=["timestamp"])
        .set_index("timestamp")
        .sort_index()[["rate"]]
    )


def aggregate_to_8h(hourly: pd.DataFrame) -> pd.DataFrame:
    """Sum hourly funding into 8-hour bars - matches discrete-funding exchanges."""
    return hourly.resample("8h").sum()


def backtest(
    funding_history: pd.DataFrame,
    cost_bps_per_change: float = 5.0,
    two_sided: bool = False,
) -> dict:
    """Cash-and-carry backtest. Long-only-positive by default (retail-realistic)."""
    rates = funding_history["rate"]
    if two_sided:
        position = pd.Series(np.sign(rates.values), index=rates.index, dtype=float)
    else:
        position = (rates > 0).astype(float)

    per_period_return = position * rates

    position_changes = position.diff().abs()
    if len(position_changes) > 0:
        position_changes.iloc[0] = float(np.abs(position.iloc[0]))
    costs = position_changes * cost_bps_per_change / 10_000.0

    per_period_return_net = per_period_return - costs
    equity = (1 + per_period_return_net.fillna(0)).cumprod()

    return {
        "rates": rates,
        "position": position,
        "per_period_return_gross": per_period_return,
        "per_period_return_net": per_period_return_net,
        "costs": costs,
        "equity": equity,
    }


def summary(result: dict, periods_per_year: int = 365 * 3) -> dict:
    """Default periods_per_year = 1095 (three 8-hour funding periods per day)."""
    ret = result["per_period_return_net"].dropna()
    eq = result["equity"]
    if len(ret) == 0:
        return {}
    annual_ret = float((1 + ret.mean()) ** periods_per_year - 1)
    annual_vol = float(ret.std(ddof=0) * np.sqrt(periods_per_year))
    return {
        "periods": int(len(ret)),
        "years": round(len(ret) / periods_per_year, 2),
        "cagr": annual_ret,
        "annual_vol": annual_vol,
        "sharpe": sharpe(ret, periods_per_year),
        "sortino": sortino(ret, periods_per_year),
        "max_drawdown": max_drawdown(eq),
        "pct_holding": float((result["position"] != 0).mean()),
        "total_return": float(eq.iloc[-1] - 1),
    }
