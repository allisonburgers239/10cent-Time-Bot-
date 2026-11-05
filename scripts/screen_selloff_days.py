"""Selloff days: who is forced to sell, when do they stop, and which side pays? (2026-11-05)

Temur: "sell-offs like this from news are common - how do we capitalize, shorting or?"
Every test below is costed (1 bp/side ETFs; VX futures 0.3%/side) and split in halves.

  1  After a big down close (<= -2 / -3 / -4%): next overnight, next day session, next 1/5/10 days.
     SPY 1993-, QQQ 1999-, IWM 2000-. Which part of the bounce is overnight (what E already gets)?
  2  Intraday continuation on selloff days (hourly 2015-, 30-min 2020-): if the first hour is
     <= -1.5% / -2%, short from 10:30 to the close? If 09:30->12:00 <= -2%, short the afternoon?
  3  The day after: short from 10:30 to close the day after a <= -3% day; fade a gap-up the day after.
  4  Volatility: VIX up >= 30% over 2 days (or VIX >= 25 / 30): short the constant-maturity VX
     position (cm30) for 5 / 10 days, 2004-2026 (CBOE per-contract data). Tail stats shown.
  5  Sector cross-section after a <= -3% SPY day: worst sector vs best sector next 5 days (hourly 2015-).
  6  What E v2 (+VIX scaling) actually earns on these nights, from the library, so we know what is
     already captured before adding anything.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

from ten_cent_bot import overnight as ov
from ten_cent_bot import vx_data
from ten_cent_bot.tv_data import load_tv_csv

ROOT = Path(__file__).resolve().parent.parent
TZ = "America/New_York"


def tstat(x) -> float:
    x = pd.Series(x).dropna()
    return float(x.mean() / x.std() * np.sqrt(len(x))) if len(x) > 2 and x.std() > 0 else 0.0


def halves(x) -> str:
    x = pd.Series(x).dropna(); h = len(x) // 2
    return f"{x.iloc[:h].mean() * 1e4:+.0f}/{x.iloc[h:].mean() * 1e4:+.0f}bp"


def row(name, x, extra=""):
    x = pd.Series(x).dropna()
    print(f"  {name:52s} n {len(x):4d}  mean {x.mean() * 1e4:+6.0f}bp  hit {(x > 0).mean():.2f}  t {tstat(x):+4.1f}  halves {halves(x)} {extra}")


def main() -> None:
    raw = yf.download(["SPY", "QQQ", "IWM", "GLD", "^VIX"], period="max", interval="1d", auto_adjust=True, progress=False)
    vix = raw["Close"]["^VIX"].dropna()
    c = 1e-4
    print("=== 1. After a big down close: where is the bounce? (daily, SPY 1993-, QQQ 1999-, IWM 2000-) ===")
    for t in ("SPY", "QQQ", "IWM"):
        d = pd.DataFrame({"open": raw["Open"][t], "close": raw["Close"][t]}).dropna()
        cc = d.close.pct_change()
        on = d.open.shift(-1) / d.close - 1
        day_next = d.close.shift(-1) / d.open.shift(-1) - 1
        r1 = d.close.shift(-1) / d.close - 1; r5 = d.close.shift(-5) / d.close - 1; r10 = d.close.shift(-10) / d.close - 1
        for thr in (-0.02, -0.03, -0.04):
            m = cc <= thr
            print(f"  {t} day <= {thr * 100:.0f}% (n {int(m.sum())}): next overnight {on[m].mean() * 1e4:+.0f}bp t{tstat(on[m]):+.1f} | next day-session {day_next[m].mean() * 1e4:+.0f}bp t{tstat(day_next[m]):+.1f} | next 1d {r1[m].mean() * 1e4:+.0f} | 5d {r5[m].mean() * 1e4:+.0f}bp t{tstat(r5[m]):+.1f} | 10d {r10[m].mean() * 1e4:+.0f}bp | halves(5d) {halves(r5[m])} | unconditional 5d {r5.mean() * 1e4:+.0f}bp")

    print("\n=== 2. Intraday continuation on selloff days: short the rest of the day after a bad first hour? ===")
    for name, f, first_end in [("SPY 30m 2020-", "BATS_SPY, 30.csv", "10:00"), ("SPY 60m 2015-", "BATS_SPY, 60.csv", "10:30"), ("QQQ 60m 2015-", "BATS_QQQ, 60.csv", "10:30"), ("IWM 60m 2015-", "BATS_IWM, 60.csv", "10:30")]:
        df = load_tv_csv(ROOT / f); df.index = df.index.tz_convert(TZ); df = df.between_time("09:30", "15:59")
        hm = df.index.strftime("%H:%M"); g = df.groupby(df.index.date)
        t = pd.DataFrame({"open": g.open.first(), "close": g.close.last(), "c1": g.close.first(),
                          "o1200": df[hm == "12:00"].groupby(df[hm == "12:00"].index.date).open.first() if (hm == "12:00").any() else g.open.first(),
                          "o1530": df[hm == "15:30"].groupby(df[hm == "15:30"].index.date).open.first() if (hm == "15:30").any() else g.close.last()})
        t.index = pd.to_datetime(t.index); t["pc"] = t.close.shift(1)
        first = t.c1 / t.open - 1; rest = t.close / t.c1 - 1; to1530 = t.o1530 / t.c1 - 1
        morning = t.o1200 / t.open - 1; afternoon = t.close / t.o1200 - 1
        for thr in (-0.01, -0.015, -0.02):
            m = first <= thr
            if m.sum() >= 10:
                short_rest = -rest[m] - 2 * c; short_1530 = -to1530[m] - 2 * c
                print(f"  {name:14s} first bar <= {thr * 100:+.1f}% (n {int(m.sum())}): short to close {short_rest.mean() * 1e4:+.0f}bp t{tstat(short_rest):+.1f} hit {(short_rest > 0).mean():.2f} halves {halves(short_rest)} | short to 15:30 {short_1530.mean() * 1e4:+.0f}bp t{tstat(short_1530):+.1f}")
        m = morning <= -0.02
        if m.sum() >= 10:
            sa = -afternoon[m] - 2 * c
            print(f"  {name:14s} morning (to 12:00) <= -2% (n {int(m.sum())}): short the afternoon {sa.mean() * 1e4:+.0f}bp t{tstat(sa):+.1f} hit {(sa > 0).mean():.2f} halves {halves(sa)}")
        # day after a big down day
        big_prev = (t.close / t.pc - 1).shift(1) <= -0.03
        gap_up = (t.open / t.pc - 1) > 0.005
        sh_after = -(t.close / t.c1 - 1)[big_prev] - 2 * c
        fade = -(t.close / t.open - 1)[big_prev & gap_up] - 2 * c
        print(f"  {name:14s} DAY AFTER a <= -3% day (n {int(big_prev.sum())}): short 10:30->close {sh_after.mean() * 1e4:+.0f}bp t{tstat(sh_after):+.1f} | gap-up fade open->close (n {int((big_prev & gap_up).sum())}) {fade.mean() * 1e4:+.0f}bp t{tstat(fade):+.1f}")

    print("\n=== 4. Short volatility after a spike: constant-maturity VX position, CBOE 2004-2026, 0.3%/side ===")
    vxraw = vx_data.load_raw(ROOT / "data" / "cboe_vx" / "raw")
    cur = vx_data.build_curve(vxraw, min_days=2)
    cm = cur["cm30_return"].dropna(); cm.index = pd.to_datetime(cm.index)
    v = vix.copy(); v.index = pd.DatetimeIndex(v.index).tz_localize(None)
    v = v.reindex(cm.index).ffill()
    spike2 = v / v.shift(2) - 1
    for name, m in [("VIX up >= 30% in 2 days", spike2 >= 0.30), ("VIX up >= 50% in 2 days", spike2 >= 0.50), ("VIX >= 25", v >= 25), ("VIX >= 30", v >= 30), ("VIX >= 25 and curve inverted (VX1 > VX2)", (v >= 25) & (cur["curve"].VX1.reindex(cm.index) > cur["curve"].VX2.reindex(cm.index)))]:
        for H in (5, 10):
            idx = np.flatnonzero(m.fillna(False).to_numpy())
            rets = []; last = -1
            for i in idx:
                if i <= last or i + H >= len(cm):
                    continue
                r = -(np.prod(1 + cm.iloc[i + 1:i + 1 + H].to_numpy()) - 1) - 2 * 0.003
                rets.append(r); last = i + H
            if len(rets) >= 5:
                rets = pd.Series(rets)
                print(f"  short VX after {name:40s} hold {H:2d}d: n {len(rets):3d} mean {rets.mean() * 100:+5.2f}% hit {(rets > 0).mean():.2f} t {tstat(rets):+4.1f} worst {rets.min() * 100:+.1f}% best {rets.max() * 100:+.1f}% | first/second half {rets.iloc[:len(rets) // 2].mean() * 100:+.2f}/{rets.iloc[len(rets) // 2:].mean() * 100:+.2f}")
    uncond = -(cm) ; print(f"  (unconditional short VX, daily: {uncond.mean() * 1e4:+.0f}bp/day, Sharpe {uncond.mean() / uncond.std() * np.sqrt(252):.2f}, worst day {uncond.min() * 100:+.0f}%)")

    print("\n=== 5. Sector cross-section after a <= -3% SPY day: worst-3 sectors vs best-3 over the next 5 days (hourly 2015-) ===")
    secs = ["XLB", "XLE", "XLF", "XLI", "XLK", "XLP", "XLU", "XLV", "XLY"]
    closes = {}
    for s in secs + ["SPY"]:
        df = load_tv_csv(ROOT / f"BATS_{s}, 60.csv"); df.index = df.index.tz_convert(TZ)
        closes[s] = df.close.groupby(df.index.date).last()
    C = pd.DataFrame(closes); C.index = pd.to_datetime(C.index)
    R = C.pct_change(); fwd5 = C.shift(-5) / C - 1
    big = R.SPY <= -0.03
    worst, best = [], []
    for d in R.index[big]:
        r = R.loc[d, secs].dropna()
        if len(r) < 9 or d not in fwd5.index:
            continue
        worst.append(fwd5.loc[d, r.nsmallest(3).index].mean() - 2 * c); best.append(fwd5.loc[d, r.nlargest(3).index].mean() - 2 * c)
    worst, best = pd.Series(worst), pd.Series(best)
    print(f"  n {len(worst)}: worst-3 next 5d {worst.mean() * 1e4:+.0f}bp t{tstat(worst):+.1f} | best-3 {best.mean() * 1e4:+.0f}bp t{tstat(best):+.1f} | worst minus best {(worst - best).mean() * 1e4:+.0f}bp t{tstat(worst - best):+.1f} | SPY next 5d {fwd5.SPY[big].mean() * 1e4:+.0f}bp")

    print("\n=== 6. What E v2 + VIX scaling already earns on the night after a big down day (library) ===")
    for t in ("SPY", "QQQ", "IWM"):
        d = pd.DataFrame({"open": raw["Open"][t], "close": raw["Close"][t]}).dropna()
        res = ov.backtest_single(d, ov.E_V2_VOL_CONFIG, vix=vix)
        net = res["net_return"]; pos = res["position"]; cc = d.close.pct_change()
        for thr in (-0.02, -0.03):
            m = cc <= thr
            print(f"  {t} after a <= {thr * 100:.0f}% day: nights {int(m.sum())}, avg position {pos[m].mean():.2f}x, avg net {net[m].mean() * 1e4:+.0f}bp, share of the sleeve's total P&L {net[m].sum() / net.sum():.0%} from {m.mean():.1%} of nights")


if __name__ == "__main__":
    main()
