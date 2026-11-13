"""Old resistance -> new support after a sharp selloff (Temur's NVDA note, 2026-11-13).

NVDA fell 243 -> 148.80 (low, Nov 12) and closed 166 the same day, "bouncing off the 150 area, an
obvious previous resistance". Test the general claim on ~550 stocks 2002- (today's top 450 AND the
fallen ex-S&P names), with no discretion in what a level is:

  LEVEL   a pivot high: the highest high of the surrounding +-10 sessions AND of the prior 60 sessions
          (known 10 sessions later). It becomes "broken resistance" when a close exceeds it by 1%, and a
          real breakout once price has traded 8% above it. Levels expire 500 sessions after the break.
  EVENT   first session whose LOW comes back to within 1% above the level (or through it), while the
          stock is down >= 8% over the prior 5 sessions (the news-selloff proxy).
          HELD  = that session closes at/above the level (the "bounce off support").
          BROKE = it closes below.
  TRADE   buy the NEXT open (tradable), hold 5 / 10 / 20 sessions, market-adjusted vs SPY, 2 bp/side.
  CONTROLS
     A  the same stocks, same selloff (5-day <= -8%, same day's low is a 5-day low), but NO level within 5%.
     B  placebo levels: every real level shifted by -7% and +7%, same touch logic.
     C  touches of a real level WITHOUT a selloff (5-day return > -8%).
"""
from __future__ import annotations
import pickle
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
K, LOOK, BRK, EXT, EXPIRE, NEAR, DROP = 10, 60, 0.01, 0.08, 500, 0.01, -0.08
COST = 4e-4


def tstat(x):
    x = pd.Series(x).dropna()
    return float(x.mean() / x.std() * np.sqrt(len(x))) if len(x) > 2 and x.std() > 0 else 0.0


def pivots(high):
    n = len(high); out = []
    for i in range(LOOK, n - K):
        h = high[i]
        if np.isnan(h): continue
        if h >= np.nanmax(high[i - LOOK:i]) and h >= np.nanmax(high[i + 1:i + K + 1]):
            out.append(i)
    return out


def touches(o, h, l, c, shift=0.0):
    """Yield (day index, level, held) for the first return to each broken-and-extended level."""
    n = len(c); ev = []
    for p in pivots(h):
        L = h[p] * (1 + shift)
        b = None
        for i in range(p + K + 1, min(n, p + K + 1 + EXPIRE)):
            if c[i] > L * (1 + BRK): b = i; break
        if b is None: continue
        ext = False
        for i in range(b + 1, min(n, b + EXPIRE)):
            if not ext:
                if h[i] >= L * (1 + EXT): ext = True
                elif c[i] < L * 0.97: break            # failed breakout before extending
                continue
            if l[i] <= L * (1 + NEAR):
                ev.append((i, L, c[i] >= L)); break
    return ev


def run(px, label):
    O, H, Lo, C = px["open"], px["high"], px["low"], px["close"]
    spy_o, spy_c = O["SPY"].to_numpy(), C["SPY"].to_numpy()
    rows = []
    for t in C.columns:
        if t == "SPY" or C[t].notna().sum() < 800: continue
        o, h, l, c = (x[t].to_numpy() for x in (O, H, Lo, C))
        n = len(c)
        r5 = np.full(n, np.nan); r5[5:] = c[5:] / c[:-5] - 1
        def fwd(i, hold):
            if i + 1 + hold >= n or np.isnan(o[i + 1]) or np.isnan(c[i + hold]): return np.nan
            return (c[i + hold] / o[i + 1] - 1) - (spy_c[i + hold] / spy_o[i + 1] - 1) - COST
        level_days = {}
        for kind, shift in (("real", 0.0), ("placebo-", -0.07), ("placebo+", 0.07)):
            for i, L, held in touches(o, h, l, c, shift):
                if kind == "real": level_days[i] = L
                rows.append((label, t, C.index[i], kind, bool(r5[i] <= DROP), held, r5[i], l[i] / L - 1, fwd(i, 5), fwd(i, 10), fwd(i, 20), c[i] / l[i] - 1))
        # control A: selloff days with a fresh 5-day low and no real level within 5% of the low (one per 10 sessions)
        real_levels = np.array(sorted(set(level_days.values()))) if level_days else np.array([])
        last = -99
        for i in range(LOOK, n - 21):
            if i - last < 10 or np.isnan(r5[i]) or r5[i] > DROP or l[i] > np.nanmin(l[i - 4:i + 1]) + 1e-12: continue
            if i in level_days: continue
            if len(real_levels) and np.min(np.abs(real_levels / l[i] - 1)) < 0.05: continue
            rows.append((label, t, C.index[i], "control_selloff", True, c[i] >= o[i], r5[i], np.nan, fwd(i, 5), fwd(i, 10), fwd(i, 20), c[i] / l[i] - 1)); last = i
    return pd.DataFrame(rows, columns=["set", "ticker", "date", "kind", "selloff", "held", "r5", "low_vs_level", "f5", "f10", "f20", "close_off_low"])


def show(df, label):
    def line(name, x):
        x = x[x.date >= "2002-01-01"]
        if len(x) < 15: print(f"  {name:66s} n {len(x)}"); return
        h = len(x) // 2; s = x.sort_values("date")
        print(f"  {name:66s} n {len(x):5d} | 5d {x.f5.mean() * 1e4:+5.0f}bp t{tstat(x.f5):+4.1f} | 10d {x.f10.mean() * 1e4:+5.0f}bp t{tstat(x.f10):+4.1f} | 20d {x.f20.mean() * 1e4:+5.0f}bp t{tstat(x.f20):+4.1f} hit {(x.f20 > 0).mean():.2f} halves(10d) {s.f10.iloc[:h].mean() * 1e4:+.0f}/{s.f10.iloc[h:].mean() * 1e4:+.0f}")
    print(f"=== {label} ===")
    real = df[df.kind == "real"]; pl = df[df.kind.str.startswith("placebo")]; ctl = df[df.kind == "control_selloff"]
    line("REAL level, selloff into it, HELD (closed back above)  <- the claim", real[real.selloff & real.held])
    line("REAL level, selloff into it, BROKE (closed below)", real[real.selloff & ~real.held])
    line("REAL level, selloff into it, all", real[real.selloff])
    line("B placebo level (+-7%), selloff, HELD", pl[pl.selloff & pl.held])
    line("B placebo level (+-7%), selloff, all", pl[pl.selloff])
    line("A same selloff, no level nearby, up-close day", ctl[ctl.held])
    line("A same selloff, no level nearby, all", ctl)
    line("C REAL level touched WITHOUT a selloff, HELD", real[~real.selloff & real.held])
    line("C REAL level touched WITHOUT a selloff, all", real[~real.selloff])
    big = real[real.selloff & real.held & (real.r5 <= -0.15)]
    line("REAL, HELD, selloff >= 15% in 5 days (NVDA-sized)", big)
    line("A control, selloff >= 15%, up-close day", ctl[ctl.held & (ctl.r5 <= -0.15)])
    wick = real[real.selloff & real.held & (real.close_off_low >= 0.05)]
    line("REAL, HELD, closed >= 5% off the low (NVDA: +11.7%)", wick)
    line("A control, closed >= 5% off the low", ctl[ctl.close_off_low >= 0.05])


def main():
    d = pickle.load(open(ROOT / "data" / "earnings" / "ohlc.pkl", "rb"))
    allrows = []
    for key in ("survivors", "fallen"):
        df = run(d[key], key); allrows.append(df); show(df, f"{key}: {df.ticker.nunique()} stocks")
    df = pd.concat(allrows); show(df, "BOTH SETS")
    r = df[(df.kind == "real") & df.selloff & df.held & (df.date >= "2002-01-01")]
    print("  by year, REAL+selloff+HELD, 10d bp (n): " + " ".join(f"{y}:{v * 1e4:+.0f}({n})" for (y, v), (_, n) in zip(r.groupby(r.date.dt.year).f10.mean().items(), r.groupby(r.date.dt.year).size().items())))
    nv = df[(df.ticker == "NVDA") & (df.date >= "2026-10-01")]
    print("  NVDA events since October:\n" + nv.to_string(index=False))
    df.to_csv(ROOT / "results" / "polarity_bounce_events_2026-11-13.csv", index=False)


if __name__ == "__main__":
    main()
