"""90-minute session cycles (Ali's idea, 2026-11-06): does the market move in 90-minute blocks?

Blocks (ET, regular session): 09:30-11:00, 11:00-12:30, 12:30-14:00, 14:00-15:30, 15:30-16:00 (half block).
Three testable readings of "90-minute cycles", each costed (1 bp/side ETFs, 0.2 bp MNQ, 2 bp stocks):
  A  Block momentum / reversal: sign of block k -> return of block k+1 (continuation if +, reversal if -).
  B  Sweep-and-reverse: when block k+1 trades through block k's high (or low) and then closes back inside
     it, fade the sweep (short after a high sweep, long after a low sweep) to the block's close.
  C  Open-range-of-block breakout: the first 30 minutes of a block set a range; trade the first close
     outside it in the remaining 60 minutes, exit at the block's close (the "cycle expansion" trade).
Controls: the same tests on arbitrary 90-minute blocks shifted by 45 minutes (if the effect is specific
to the 09:30-anchored cycle it should vanish on the shifted grid), and a random-sign placebo.
Data: every 5-minute file in the repo (ETFs + 20 stocks ~1y, micro futures 3.5 months) and SPY 30-min 2020-.
"""
from __future__ import annotations

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


def blocks(df: pd.DataFrame, offset_min: int = 0) -> pd.DataFrame:
    """Aggregate RTH bars into 90-minute blocks anchored at 09:30 (+offset)."""
    d = df.between_time("09:30", "15:59")
    origin = "9h30min" if offset_min == 0 else f"{9 * 60 + 30 + offset_min}min"
    g = d.resample("90min", origin="start_day", offset=origin).agg({"open": "first", "high": "max", "low": "min", "close": "last"}).dropna()
    g["day"] = g.index.date
    g["k"] = g.groupby("day").cumcount()
    return g


def section_A(name, b, cost):
    r = b.close / b.open - 1
    nxt = r.groupby(b.day).shift(-1)
    cont = np.sign(r) * nxt - 2 * cost
    cells = []
    for k in range(4):
        m = (b.k == k) & nxt.notna()
        x = cont[m]
        if len(x) >= 20:
            cells.append(f"blk{k + 1}->{k + 2}: {x.mean() * 1e4:+5.1f}bp t{tstat(x):+4.1f} n{len(x)}")
    allx = cont.dropna()
    print(f"  {name:10s} follow block sign: {allx.mean() * 1e4:+5.1f}bp t{tstat(allx):+4.1f} n{len(allx)} | " + " | ".join(cells))


def section_B(name, b, cost):
    hi_prev = b.high.groupby(b.day).shift(1); lo_prev = b.low.groupby(b.day).shift(1)
    swept_hi = (b.high > hi_prev) & (b.close < hi_prev)
    swept_lo = (b.low < lo_prev) & (b.close > lo_prev)
    # the fade is taken at the sweep-block close and held to the NEXT block's close
    nxt = (b.close / b.open - 1).groupby(b.day).shift(-1)
    fade_hi = -nxt[swept_hi] - 2 * cost; fade_lo = nxt[swept_lo] - 2 * cost
    both = pd.concat([fade_hi, fade_lo])
    print(f"  {name:10s} fade a swept high: {fade_hi.mean() * 1e4:+5.1f}bp t{tstat(fade_hi):+4.1f} n{len(fade_hi)} | fade a swept low: {fade_lo.mean() * 1e4:+5.1f}bp t{tstat(fade_lo):+4.1f} n{len(fade_lo)} | both {both.mean() * 1e4:+5.1f}bp t{tstat(both):+4.1f}")


def section_C(name, df5, cost):
    d = df5.between_time("09:30", "15:59")
    out = []
    for day, g in d.groupby(d.index.date):
        if len(g) < 60:
            continue
        hm = g.index.strftime("%H:%M")
        for start, end in (("09:30", "11:00"), ("11:00", "12:30"), ("12:30", "14:00"), ("14:00", "15:30")):
            blk = g[(hm >= start) & (hm < end)]
            if len(blk) < 12:
                continue
            or_ = blk.iloc[:6]; rest = blk.iloc[6:]
            hi, lo = or_.high.max(), or_.low.min()
            for i in range(len(rest) - 1):
                c = rest.close.iloc[i]
                side = 1 if c > hi else (-1 if c < lo else 0)
                if side:
                    entry = rest.open.iloc[i + 1]; ex = rest.close.iloc[-1]
                    out.append(side * (ex / entry - 1) - 2 * cost); break
    x = pd.Series(out)
    print(f"  {name:10s} block-range breakout, exit at block close: {x.mean() * 1e4:+5.1f}bp/trade t{tstat(x):+4.1f} n{len(x)} hit {(x > 0).mean():.2f}")


def main() -> None:
    files = [(Path(p).stem.split(",")[0].replace("BATS_", ""), p, 2e-4) for p in sorted(glob.glob(str(ROOT / "BATS_*, 5.csv")))]
    files = [(n, p, 1e-4 if n in ("SPY", "QQQ", "IWM") or n.startswith("XL") else c) for n, p, c in files]
    files += [("MNQ", str(ROOT / "CME_MINI_MNQ1!, 5.csv"), 0.2e-4), ("MES", str(ROOT / "CME_MINI_MES1!, 5.csv"), 0.5e-4)]
    data = {}
    for n, p, c in files:
        df = load_tv_csv(p); df.index = df.index.tz_convert(TZ); data[n] = (df, c)
    spy30 = load_tv_csv(ROOT / "BATS_SPY, 30.csv"); spy30.index = spy30.index.tz_convert(TZ)
    print("=== A. Block momentum: does block k's direction carry into block k+1? (09:30-anchored 90-min blocks) ===")
    for n, (df, c) in data.items():
        section_A(n, blocks(df), c)
    section_A("SPY30 2020-", blocks(spy30), 1e-4)
    print("\n  -- control: same test on blocks shifted by 45 minutes (10:15-11:45, ...) --")
    for n in ("SPY", "QQQ", "MNQ", "NVDA", "TSLA"):
        if n in data:
            section_A(n + " shifted", blocks(data[n][0], 45), data[n][1])
    section_A("SPY30 shifted", blocks(spy30, 45), 1e-4)
    print("\n=== B. Sweep of the previous block's high/low that closes back inside -> fade it over the next block ===")
    for n, (df, c) in data.items():
        section_B(n, blocks(df), c)
    section_B("SPY30 2020-", blocks(spy30), 1e-4)
    print("\n=== C. Breakout of each block's first-30-minute range, exit at the block's close ===")
    for n, (df, c) in data.items():
        section_C(n, df, c)
    # pooled placebo for C: random direction
    print("  (placebo for C: with random long/short the expectation is minus costs, i.e. about -2 to -4 bp)")


if __name__ == "__main__":
    main()
