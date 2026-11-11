"""Sleeve M candidate: month-end stock/bond rebalancing pair (2026-11-11).

Who is forced: pensions, balanced and target-date funds hold fixed stock/bond mixes and rebalance
into month-end. After a month in which stocks beat bonds by more than `threshold` they sell stocks
and buy bonds in the last sessions (and the reverse after stocks lag). The rule fades that flow:

  at the close of the session with `last_sessions` sessions still to come in the month, compute
  MTD(stock) - MTD(bond) (through that close, from the prior month's last close);
  if spread > +threshold: SHORT stock / LONG bond; if spread < -threshold: LONG stock / SHORT bond;
  hold to the month's last close. Equal dollar legs. Cost: 4 legs x cost_bps_per_side.

Screened in scripts/screen_other_players.py, audited in scripts/audit_monthend_pair.py.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

import numpy as np
import pandas as pd

from . import calendar_nyse as cal


@dataclass(frozen=True)
class MonthEndConfig:
    stock: str = "SPY"
    bond: str = "TLT"
    threshold: float = 0.03
    last_sessions: int = 5
    cost_bps_per_side: float = 1.0


DEFAULT_CONFIG = MonthEndConfig()


def decision(stock_mtd: float, bond_mtd: float, cfg: MonthEndConfig = DEFAULT_CONFIG) -> int:
    """+1 = long stock / short bond, -1 = short stock / long bond, 0 = stand aside."""
    spread = stock_mtd - bond_mtd
    if spread > cfg.threshold:
        return -1
    if spread < -cfg.threshold:
        return 1
    return 0


def sessions_left_in_month(d: dt.date) -> int:
    """Trading sessions from d (inclusive, if d is a session) to the end of d's calendar month."""
    n = 0
    x = d
    while x.month == d.month:
        if cal.is_trading_day(x):
            n += 1
        x += dt.timedelta(days=1)
    return n


def events(stock: pd.Series, bond: pd.Series, cfg: MonthEndConfig = DEFAULT_CONFIG) -> pd.DataFrame:
    """One row per month: signal date, side, spread, and the pair return to the month's last close
    (net of 4 legs of cost when side != 0). Only information through the signal close is used."""
    df = pd.DataFrame({"s": stock, "b": bond}).dropna()
    per = df.index.to_period("M")
    rows = []
    months = per.unique()
    for i, m in enumerate(months):
        if i == 0:
            continue
        idx = np.flatnonzero(per == m)
        if len(idx) <= cfg.last_sessions:
            continue
        prev_close = idx[0] - 1
        sig = idx[-1] - cfg.last_sessions          # the session with last_sessions still to come
        end = idx[-1]
        s_mtd = df.s.iloc[sig] / df.s.iloc[prev_close] - 1
        b_mtd = df.b.iloc[sig] / df.b.iloc[prev_close] - 1
        side = decision(s_mtd, b_mtd, cfg)
        s_ret = df.s.iloc[end] / df.s.iloc[sig] - 1
        b_ret = df.b.iloc[end] / df.b.iloc[sig] - 1
        gross = side * (s_ret - b_ret)
        net = gross - (4 * cfg.cost_bps_per_side * 1e-4 if side else 0.0)
        rows.append({"month": str(m), "signal_date": df.index[sig], "end_date": df.index[end], "spread": s_mtd - b_mtd,
                     "side": side, "stock_ret": s_ret, "bond_ret": b_ret, "gross": gross, "net": net})
    return pd.DataFrame(rows)


def daily_returns(stock: pd.Series, bond: pd.Series, cfg: MonthEndConfig = DEFAULT_CONFIG) -> pd.Series:
    """Daily P&L series of the pair (0 when flat) on the stock/bond calendar; costs charged on the
    entry day. For Sharpe / drawdown / overlap with other sleeves."""
    df = pd.DataFrame({"s": stock, "b": bond}).dropna()
    r = pd.Series(0.0, index=df.index)
    ds, db = df.s.pct_change(), df.b.pct_change()
    for _, ev in events(stock, bond, cfg).iterrows():
        if ev.side == 0:
            continue
        window = (df.index > ev.signal_date) & (df.index <= ev.end_date)
        r[window] = ev.side * (ds[window] - db[window])
        first = df.index[window][0]
        r[first] -= 4 * cfg.cost_bps_per_side * 1e-4
    return r


def summary(ev: pd.DataFrame) -> dict:
    t = ev[ev.side != 0]
    n = len(t)
    return {"events": n, "mean_bp": float(t.net.mean() * 1e4) if n else 0.0, "hit": float((t.net > 0).mean()) if n else 0.0,
            "t": float(t.net.mean() / t.net.std() * np.sqrt(n)) if n > 2 else 0.0,
            "per_year_pct": float(t.net.sum() / max(1, ev.month.str[:4].nunique()) * 100)}
