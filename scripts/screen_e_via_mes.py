"""Screen: can Sleeve E run on MES (Tradovate) instead of SPY (equity broker)?

Uses the repo's 5-minute TradingView exports for the overlapping window:
MES1! (2026-03-15 -> 2026-06-30) and SPY (2025-06 -> 2026-06).  For each
trading day: MES price at the 16:00 ET print and at the 09:30 ET print next
day vs SPY's 15:55-bar close and 09:30-bar open, plus SPY's official
close/open from yfinance.  Reports correlation, beta, tracking error and
mean difference of the overnight legs.  Short window: a tracking check,
not a return estimate.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

from ten_cent_bot.tv_data import load_tv_csv

ROOT = Path(__file__).resolve().parents[1]


def overnight_from_bars(bars: pd.DataFrame, entry_hhmm: str, exit_hhmm: str) -> pd.Series:
    """Close of the bar stamped entry_hhmm (bar open time) on day t -> open of
    the bar stamped exit_hhmm on the next trading day."""
    local = bars.tz_convert("America/New_York")
    ent = local.between_time(entry_hhmm, entry_hhmm)["close"]
    ext = local.between_time(exit_hhmm, exit_hhmm)["open"]
    ent.index = ent.index.tz_localize(None).normalize(); ext.index = ext.index.tz_localize(None).normalize()
    ent = ent[~ent.index.duplicated()]; ext = ext[~ext.index.duplicated()]
    nxt = pd.Series(ext.index, index=ext.index).shift(-1)  # not used
    days = sorted(set(ent.index) & set(ext.index))
    out = {}
    for i, d in enumerate(days[:-1]):
        d2 = days[i + 1]
        out[d] = ext[d2] / ent[d] - 1
    return pd.Series(out, name="on").sort_index()


def main():
    mes = load_tv_csv(ROOT / "CME_MINI_MES1!, 5.csv")
    spy = load_tv_csv(ROOT / "BATS_SPY, 5.csv")
    on_mes = overnight_from_bars(mes, "15:55", "09:30")
    on_spy_bar = overnight_from_bars(spy, "15:55", "09:30")
    yd = yf.download("SPY", start="2026-03-01", end="2026-07-05", interval="1d", auto_adjust=False, progress=False)
    on_spy_off = ((yd["Open"].squeeze().shift(-1) - yd["Close"].squeeze()) / yd["Close"].squeeze()).dropna()
    on_spy_off.index = pd.to_datetime(on_spy_off.index).tz_localize(None)
    j = pd.concat([on_mes.rename("MES"), on_spy_bar.rename("SPY_bars"), on_spy_off.rename("SPY_official")], axis=1).dropna()
    print(f"overlap {j.index.min().date()} -> {j.index.max().date()}, {len(j)} nights")
    print("\n  mean overnight (bp/night):  " + "  ".join(f"{c} {j[c].mean()*1e4:+.1f}" for c in j.columns))
    print("  std (bp):                   " + "  ".join(f"{c} {j[c].std()*1e4:.1f}" for c in j.columns))
    print("\n  correlation matrix:\n" + j.corr().round(3).to_string())
    for a, b in [("MES", "SPY_official"), ("MES", "SPY_bars"), ("SPY_bars", "SPY_official")]:
        beta = np.polyfit(j[b], j[a], 1)[0]
        te = (j[a] - j[b]).std() * 1e4
        print(f"\n  {a} vs {b}: beta {beta:.3f}, mean diff {(j[a]-j[b]).mean()*1e4:+.1f}bp, tracking error {te:.1f}bp/night, |diff|>10bp on {((j[a]-j[b]).abs()>0.001).mean():.0%} of nights")
    print("\n  Cost context: MES round trip ~0.6-0.7bp (1 tick + commission) vs SPY 1-2bp at a retail equity broker.")
    print("  Note: MES includes the 16:00-17:00 and 18:00-09:30 Globex sessions; dividends accrue to SPY, not MES (basis drift ~1.3%/yr, visible in mean diff over long windows, not here).")


if __name__ == "__main__":
    main()
