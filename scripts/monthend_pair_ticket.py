"""Month-end pair ticket (Sleeve M candidate), dry-run + forward log. Run at ~15:45 ET on every
session; it only says something on the signal session, the holding sessions and the exit session.

  ENTER  on the session with 5 sessions left in the month (today included): MTD spread of SPY vs TLT
         through the current price; > +3% -> SHORT SPY / LONG TLT at the close; < -3% -> the reverse.
  HOLD   on the sessions in between.
  EXIT   on the month's last session: close both legs at the close.
Every run appends a row to results/monthend_pair_log.csv (--log) with the prices seen, so the
forward record can be scored against the audit without any broker.

Usage: python scripts/monthend_pair_ticket.py [--equity 25000] [--log] [--date YYYY-MM-DD]
"""
from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path

import pandas as pd
import yfinance as yf

from ten_cent_bot import calendar_nyse as cal
from ten_cent_bot import monthend_pair as mp

ROOT = Path(__file__).resolve().parents[1]
LOG = ROOT / "results" / "monthend_pair_log.csv"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--equity", type=float, default=25000)
    ap.add_argument("--log", action="store_true")
    ap.add_argument("--date", default=None, help="pretend today is this session (uses that day's close)")
    a = ap.parse_args()
    cfg = mp.DEFAULT_CONFIG
    today = dt.date.fromisoformat(a.date) if a.date else dt.date.today()
    if not cal.is_trading_day(today):
        print(f"{today}: not a trading session"); return 0
    px = yf.download([cfg.stock, cfg.bond], period="3mo", interval="1d", auto_adjust=True, progress=False)["Close"]
    px.index = pd.DatetimeIndex(px.index).tz_localize(None)
    px = px[px.index <= pd.Timestamp(today)]
    if a.date is None:  # live: today's last print may not be in the daily bar yet
        for s in (cfg.stock, cfg.bond):
            last = yf.Ticker(s).fast_info.get("last_price")
            if last:
                px.loc[pd.Timestamp(today), s] = float(last)
        px = px.sort_index()
    prev_month_last = px[px.index.to_period("M") < pd.Timestamp(today).to_period("M")].index[-1]
    s_mtd = px[cfg.stock].iloc[-1] / px.loc[prev_month_last, cfg.stock] - 1
    b_mtd = px[cfg.bond].iloc[-1] / px.loc[prev_month_last, cfg.bond] - 1
    spread = s_mtd - b_mtd
    left = mp.sessions_left_in_month(today)
    side = mp.decision(s_mtd, b_mtd, cfg)
    if left == cfg.last_sessions:
        action = {1: f"ENTER: LONG {cfg.stock} / SHORT {cfg.bond} at today's close", -1: f"ENTER: SHORT {cfg.stock} / LONG {cfg.bond} at today's close", 0: "NO TRADE this month (spread inside the band)"}[side]
    elif 1 < left < cfg.last_sessions:
        action = "HOLD (if a position was entered on the signal session)"
    elif left == 1:
        action = "EXIT at today's close (close both legs)"
    else:
        action = f"nothing - {left} sessions left in the month, signal session is in {left - cfg.last_sessions} sessions"
    leg = a.equity / 2
    print(f"{today} ({left} sessions left in {today:%B}): MTD {cfg.stock} {s_mtd:+.2%}, {cfg.bond} {b_mtd:+.2%}, spread {spread:+.2%} (band +/-{cfg.threshold:.0%})")
    print(f"  {action}")
    if left == cfg.last_sessions and side:
        print(f"  size: ${leg:,.0f} per leg = {leg / px[cfg.stock].iloc[-1]:.0f} {cfg.stock} and {leg / px[cfg.bond].iloc[-1]:.0f} {cfg.bond} shares (at {px[cfg.stock].iloc[-1]:.2f} / {px[cfg.bond].iloc[-1]:.2f})")
    if a.log:
        row = pd.DataFrame([{"date": str(today), "sessions_left": left, "stock_px": round(float(px[cfg.stock].iloc[-1]), 2), "bond_px": round(float(px[cfg.bond].iloc[-1]), 2),
                             "stock_mtd": round(float(s_mtd), 5), "bond_mtd": round(float(b_mtd), 5), "spread": round(float(spread), 5), "side": side if left == cfg.last_sessions else "", "action": action.split(":")[0].split(" (")[0]}])
        LOG.parent.mkdir(exist_ok=True); row.to_csv(LOG, mode="a", header=not LOG.exists(), index=False)
        print(f"  logged to {LOG.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
