"""Early-session scan analysis (Temur's idea, 2026-11-04).

Inputs: TradingView 5-minute extended-hours chart exports for the symbols the
screener returned (gap >= |3|%, relative volume >= 2.5x, fresh news), saved as
results/scan_<EXCHANGE>_<TICKER>_5m_ETH.csv.

For each symbol, for the LAST session in the file:
  pre-market high / low / volume (04:00-09:29 ET)
  session VWAP from 09:30 (volume-weighted typical price)
  early VWAP = VWAP after the first 30 minutes (what "holding above early VWAP" refers to)
  share of regular-session bars that closed above VWAP, current close vs VWAP,
  whether price is above the pre-market high (held the gap) or below the open (gap fading)
  institutional-imbalance verdict:
     BUY  imbalance: >= 70% of bars above VWAP and last close > VWAP and close > premarket high
     SELL imbalance: >= 70% of bars below VWAP and last close < VWAP and close < premarket low
     otherwise: no clear imbalance (two-sided)

Usage: python scripts/scan_gap_volume_vwap.py [YYYY-MM-DD]
"""
from __future__ import annotations

import glob
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from ten_cent_bot.tv_data import load_tv_csv

ROOT = Path(__file__).resolve().parent.parent
TZ = "America/New_York"


def analyse(path: str, day: str | None) -> dict | None:
    df = load_tv_csv(path)
    df.index = df.index.tz_convert(TZ)
    if "volume" not in df.columns or (df.volume == 1).all():
        return None
    d = pd.Timestamp(day).date() if day else df.index[-1].date()
    s = df[df.index.date == d]
    if len(s) < 20:
        return None
    pre = s.between_time("04:00", "09:29")
    reg = s.between_time("09:30", "15:59")
    if len(reg) < 6:
        return None
    tp = (reg.high + reg.low + reg.close) / 3
    vwap = (tp * reg.volume).cumsum() / reg.volume.cumsum()
    early = vwap.iloc[5] if len(vwap) > 5 else vwap.iloc[-1]  # after 6 bars = 10:00
    above = (reg.close > vwap)
    last = reg.close.iloc[-1]
    pm_high = float(pre.high.max()) if len(pre) else np.nan
    pm_low = float(pre.low.min()) if len(pre) else np.nan
    prev = df[df.index.date < d]
    prev_close = float(prev.between_time("09:30", "15:59").close.iloc[-1]) if len(prev) else np.nan
    gap = reg.open.iloc[0] / prev_close - 1 if prev_close == prev_close else np.nan
    share_above = float(above.mean())
    verdict = "no clear imbalance"
    if share_above >= 0.7 and last > vwap.iloc[-1] and (np.isnan(pm_high) or last > pm_high):
        verdict = "BUY imbalance: holding above VWAP, above pre-market high"
    elif share_above <= 0.3 and last < vwap.iloc[-1] and (np.isnan(pm_low) or last < pm_low):
        verdict = "SELL imbalance: cascading below VWAP, below pre-market low"
    elif share_above >= 0.7 and last > vwap.iloc[-1]:
        verdict = "holding above VWAP but still under the pre-market high"
    elif share_above <= 0.3 and last < vwap.iloc[-1]:
        verdict = "below VWAP but still above the pre-market low"
    return {
        "symbol": Path(path).stem.replace("scan_", "").replace("_5m_ETH", "").replace("_", ":"),
        "day": str(d), "prev_close": prev_close, "gap_pct": gap * 100, "open": float(reg.open.iloc[0]),
        "pm_high": pm_high, "pm_low": pm_low, "pm_volume": int(pre.volume.sum()) if len(pre) else 0,
        "early_vwap": float(early), "vwap_now": float(vwap.iloc[-1]), "last": float(last),
        "last_vs_vwap_pct": (last / vwap.iloc[-1] - 1) * 100, "share_bars_above_vwap": share_above,
        "last_vs_pm_high_pct": (last / pm_high - 1) * 100 if pm_high == pm_high else np.nan,
        "reg_volume": int(reg.volume.sum()), "bars": len(reg), "verdict": verdict,
    }


def main() -> None:
    day = sys.argv[1] if len(sys.argv) > 1 else None
    rows = []
    for f in sorted(glob.glob(str(ROOT / "results" / "scan_*_5m_ETH.csv"))):
        r = analyse(f, day)
        if r:
            rows.append(r)
    if not rows:
        print("no scan files"); return
    t = pd.DataFrame(rows)
    pd.set_option("display.width", 250)
    cols = ["symbol", "day", "gap_pct", "pm_high", "pm_volume", "early_vwap", "vwap_now", "last", "last_vs_vwap_pct", "share_bars_above_vwap", "last_vs_pm_high_pct", "verdict"]
    print(t[cols].round(2).to_string(index=False))


if __name__ == "__main__":
    main()
