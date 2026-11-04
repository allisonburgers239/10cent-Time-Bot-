"""Intraday forced-flow screen on the most liquid US names (2026-11-04).

Temur's lens: find people who must trade at a fixed time inside the day.
  A. Leveraged-ETF rebalancing: on big days the funds must trade MORE in the day's direction
     into the 16:00 close. Test: last-30-min return conditional on the 09:30->15:30 move,
     by |move| bucket. Prediction: continuation, growing with |move|.
  B. VWAP-order footprint: large institutional orders are worked all day. Test: afternoon
     (12:00->16:00) return vs morning (09:30->12:00) sign, on high relative-volume days vs normal.
  C. Options-expiration Fridays: dealer hedging pins price. Test: last-hour |return| and the
     last-hour reversal toward the day's VWAP on monthly OPEX vs other Fridays.
  D. Month-end / quarter-end: pension rebalancing in the last 30 minutes. Test: last-30-min return
     on the last trading day of the month/quarter vs other days, SPY/QQQ/IWM.
  E. Gap continuation by gap size in the stock itself: open->10:00 and open->close return
     conditional on the overnight gap bucket.
  Each with t-stats and both-halves splits; costs 1 bp/side for ETFs, 2 bp for stocks.
Data: every 5-min file in the repo (ETFs and stocks, ~1 year), SPY 30-min 2020-, hourly 2015-.
"""
from __future__ import annotations

import datetime as dt
import glob
from pathlib import Path

import numpy as np
import pandas as pd

from ten_cent_bot.tv_data import load_tv_csv

ROOT = Path(__file__).resolve().parent.parent
TZ = "America/New_York"


def tstat(x) -> float:
    x = pd.Series(x).dropna()
    return float(x.mean() / x.std() * np.sqrt(len(x))) if len(x) > 2 and x.std() > 0 else 0.0


def halves(x) -> str:
    x = pd.Series(x).dropna(); h = len(x) // 2
    return f"{x.iloc[:h].mean() * 1e4:+.0f}/{x.iloc[h:].mean() * 1e4:+.0f}bp"


def third_friday(y, m):
    d = dt.date(y, m, 15)
    while d.weekday() != 4:
        d += dt.timedelta(days=1)
    return d


def day_table(df: pd.DataFrame) -> pd.DataFrame:
    """Per-day session landmarks from intraday bars (RTH)."""
    df = df.between_time("09:30", "15:59")
    g = df.groupby(df.index.date)
    hm = df.index.strftime("%H:%M")
    def at(hhmm, col="open"):
        s = df[hm == hhmm].groupby(df[hm == hhmm].index.date)[col].first(); return s
    t = pd.DataFrame({"open": g.open.first(), "close": g.close.last(), "o1530": at("15:30"), "o1500": at("15:00"), "o1200": at("12:00"), "c1000": at("09:55", "close") if (hm == "09:55").any() else at("09:30", "close")})
    if "volume" in df.columns and (df.volume != 1).any():
        t["vol"] = g.volume.sum()
    t["prev_close"] = t.close.shift(1)
    t["gap"] = t.open / t.prev_close - 1
    t["d_to_1530"] = t.o1530 / t.open - 1
    t["last30"] = t.close / t.o1530 - 1
    t["last60"] = t.close / t.o1500 - 1
    t["morning"] = t.o1200 / t.open - 1
    t["afternoon"] = t.close / t.o1200 - 1
    t["first30"] = t.c1000 / t.open - 1
    t["day"] = t.close / t.open - 1
    t.index = pd.to_datetime(t.index)
    return t.dropna(subset=["open", "close"])


def section_A(tables: dict[str, pd.DataFrame], cost: float) -> None:
    print("\n=== A. Leveraged-ETF rebalancing: last 30 min vs the day's move to 15:30 ===")
    for name, t in tables.items():
        x = t.dropna(subset=["d_to_1530", "last30"])
        if len(x) < 60:
            continue
        cells = []
        for lo, hi, lab in [(0.0, 0.005, "<0.5%"), (0.005, 0.01, "0.5-1%"), (0.01, 0.02, "1-2%"), (0.02, 9, ">2%")]:
            m = (x.d_to_1530.abs() >= lo) & (x.d_to_1530.abs() < hi)
            r = np.sign(x.d_to_1530[m]) * x.last30[m] - 2 * cost
            if len(r) >= 8:
                cells.append(f"|move| {lab}: {r.mean() * 1e4:+5.1f}bp n{len(r):4d} t{tstat(r):+4.1f}")
        big = x[x.d_to_1530.abs() >= 0.01]
        strat = np.sign(big.d_to_1530) * big.last30 - 2 * cost
        print(f"  {name:10s} " + " | ".join(cells) + f"  || trade |move|>=1%: {strat.mean() * 1e4:+.1f}bp/day n{len(strat)} t{tstat(strat):+.1f} halves {halves(strat)}")


def section_B(tables: dict[str, pd.DataFrame], cost: float) -> None:
    print("\n=== B. VWAP-order footprint: afternoon vs morning sign, high-volume days vs normal ===")
    for name, t in tables.items():
        x = t.dropna(subset=["morning", "afternoon"])
        if len(x) < 60:
            continue
        cont = np.sign(x.morning) * x.afternoon - 2 * cost
        line = f"  {name:10s} all days: {cont.mean() * 1e4:+5.1f}bp t{tstat(cont):+4.1f} n{len(cont)}"
        if "vol" in x.columns:
            vr = x.vol / x.vol.rolling(20).mean().shift(1)
            hi = cont[vr >= 1.5]; lo = cont[vr < 1.5]
            line += f" | volume >= 1.5x: {hi.mean() * 1e4:+5.1f}bp t{tstat(hi):+4.1f} n{len(hi)} | normal: {lo.mean() * 1e4:+5.1f}bp t{tstat(lo):+4.1f}"
        big = cont[x.morning.abs() >= 0.01]
        line += f" | |morning|>=1%: {big.mean() * 1e4:+5.1f}bp t{tstat(big):+4.1f} n{len(big)}"
        print(line)


def section_C(tables: dict[str, pd.DataFrame], cost: float) -> None:
    print("\n=== C. Options-expiration Fridays: last-hour behaviour vs other Fridays ===")
    for name, t in tables.items():
        x = t.dropna(subset=["last60", "d_to_1530"])
        if len(x) < 100:
            continue
        fri = x[x.index.dayofweek == 4]
        opex = fri[[d.date() == third_friday(d.year, d.month) for d in fri.index]]
        other = fri[[d.date() != third_friday(d.year, d.month) for d in fri.index]]
        # pin test: does the last hour reverse the day's move more on OPEX?
        rev_o = -np.sign(opex.d_to_1530) * opex.last60 - 2 * cost; rev_f = -np.sign(other.d_to_1530) * other.last60 - 2 * cost
        print(f"  {name:10s} OPEX n{len(opex):3d}: |last hour| {opex.last60.abs().mean() * 1e4:4.0f}bp, fade-the-day {rev_o.mean() * 1e4:+5.1f}bp t{tstat(rev_o):+4.1f} | other Fridays n{len(other):3d}: |last hour| {other.last60.abs().mean() * 1e4:4.0f}bp, fade {rev_f.mean() * 1e4:+5.1f}bp t{tstat(rev_f):+4.1f}")


def section_D(tables: dict[str, pd.DataFrame], cost: float) -> None:
    print("\n=== D. Month-end / quarter-end last 30 minutes (index ETFs) ===")
    for name, t in tables.items():
        if name.split()[0] not in ("SPY", "QQQ", "IWM"):
            continue
        x = t.dropna(subset=["last30"])
        idx = x.index
        last_of_month = pd.Series(idx.to_period("M"), index=idx).ne(pd.Series(idx.to_period("M"), index=idx).shift(-1))
        last_of_q = pd.Series(idx.to_period("Q"), index=idx).ne(pd.Series(idx.to_period("Q"), index=idx).shift(-1))
        me = x.last30[last_of_month]; qe = x.last30[last_of_q]; rest = x.last30[~last_of_month]
        print(f"  {name:10s} month-end n{len(me):3d}: {me.mean() * 1e4:+5.1f}bp t{tstat(me):+4.1f} | quarter-end n{len(qe):3d}: {qe.mean() * 1e4:+5.1f}bp t{tstat(qe):+4.1f} | other days: {rest.mean() * 1e4:+5.1f}bp t{tstat(rest):+4.1f}")


def section_E(tables: dict[str, pd.DataFrame], cost: float) -> None:
    print("\n=== E. Gap continuation in the stock itself: open->10:00 and open->close by gap size ===")
    for name, t in tables.items():
        x = t.dropna(subset=["gap", "first30", "day"])
        if len(x) < 60:
            continue
        cells = []
        for lo, hi, lab in [(0.005, 0.01, "0.5-1%"), (0.01, 0.02, "1-2%"), (0.02, 9, ">2%")]:
            m = (x.gap.abs() >= lo) & (x.gap.abs() < hi)
            f30 = np.sign(x.gap[m]) * x.first30[m] - 2 * cost; dd = np.sign(x.gap[m]) * x.day[m] - 2 * cost
            if len(f30) >= 8:
                cells.append(f"|gap| {lab}: ->10:00 {f30.mean() * 1e4:+5.1f}bp t{tstat(f30):+4.1f} / ->close {dd.mean() * 1e4:+5.1f}bp t{tstat(dd):+4.1f} n{len(f30)}")
        print(f"  {name:10s} " + " | ".join(cells))


def main() -> None:
    tables: dict[str, pd.DataFrame] = {}
    costs: dict[str, float] = {}
    for p in sorted(glob.glob(str(ROOT / "BATS_*, 5.csv"))):
        sym = Path(p).stem.split(",")[0].replace("BATS_", "")
        df = load_tv_csv(p); df.index = df.index.tz_convert(TZ)
        tables[f"{sym} 5m"] = day_table(df); costs[f"{sym} 5m"] = 1e-4 if sym in ("SPY", "QQQ", "IWM") or sym.startswith("XL") else 2e-4
    for sym, f in [("SPY", "BATS_SPY, 30.csv")]:
        df = load_tv_csv(ROOT / f); df.index = df.index.tz_convert(TZ)
        tables[f"{sym} 30m"] = day_table(df); costs[f"{sym} 30m"] = 1e-4
    for sym in ("SPY", "QQQ", "IWM"):
        df = load_tv_csv(ROOT / f"BATS_{sym}, 60.csv"); df.index = df.index.tz_convert(TZ)
        tables[f"{sym} 60m"] = day_table(df); costs[f"{sym} 60m"] = 1e-4
    cost = 1e-4
    print("instruments: " + ", ".join(f"{k} ({len(v)} days)" for k, v in tables.items()))
    section_A(tables, cost); section_B(tables, cost); section_C(tables, cost); section_D(tables, cost); section_E(tables, cost)


if __name__ == "__main__":
    main()
