"""Follow-up to screen_auctions_and_taxloss.py: the pre-auction bond dip without double counting.
10y and 30y auctions sit on consecutive days, so per-auction stats overlap. Here: ONE daily position.
Short TLT (total-return series, so the short pays the dividend) at the close on any session that is
1..N sessions before a 10y/20y/30y nominal auction; flat otherwise. 1 bp/side on each change of position.
Sections: baseline N=3, grid N=1..5 and which auctions, halves / by year, walk-forward, placebo
(the same calendar shifted by k sessions, k = -15..+15), IEF and ZN-proxy check, overlap with Sleeve M.
"""
from __future__ import annotations
from pathlib import Path
import numpy as np
import pandas as pd
import yfinance as yf
from ten_cent_bot import monthend_pair as mp

ROOT = Path(__file__).resolve().parent.parent


def sh(x): x = pd.Series(x).dropna(); return float(x.mean() / x.std() * np.sqrt(252)) if x.std() > 0 else 0.0
def tstat(x): x = pd.Series(x).dropna(); return float(x.mean() / x.std() * np.sqrt(len(x))) if len(x) > 2 and x.std() > 0 else 0.0
def dd(x): e = (1 + pd.Series(x).fillna(0)).cumprod(); return float((e / e.cummax() - 1).min())


def main():
    a = pd.read_csv(ROOT / "data" / "treasury_auctions.csv", parse_dates=["auction_date"])
    a = a[(a.inflation_index_security == "No") & (a.floating_rate == "No")]
    yrs = a.security_term.str.extract(r"(\d+)-Year")[0].astype(float)
    a["bucket"] = np.where(yrs >= 29, "30y", np.where(yrs >= 19, "20y", np.where(yrs >= 9, "10y", np.where(yrs >= 6, "7y", "short"))))
    px = yf.download(["TLT", "IEF", "SPY"], period="max", interval="1d", auto_adjust=True, progress=False)["Close"]
    px.index = pd.DatetimeIndex(px.index).tz_localize(None); px = px.dropna(); px = px[px.index >= "2006-01-01"]
    cal = px.index; r = px.pct_change().fillna(0)

    def series(buckets, N, sym="TLT", shift=0):
        pos = np.zeros(len(cal))
        for d in set(a[a.bucket.isin(buckets)].auction_date):
            if d not in cal: continue
            p = cal.get_loc(d) + shift
            for k in range(1, N + 1):          # hold the short over the returns of days p-N+1 .. p-1 ... i.e. close(p-N-1+1)->close(p-1)
                if 0 <= p - k < len(cal): pos[p - k] = 1
        pos = pd.Series(pos, index=cal)
        cost = pos.diff().abs().fillna(0) * 1e-4
        return -pos * r[sym] - cost, pos

    LONG = ["10y", "20y", "30y"]
    ret, pos = series(LONG, 3)
    act = ret[pos == 1]
    print("=== Baseline: short TLT over the 3 sessions before any 10y/20y/30y auction (returns of days -3,-2,-1) ===")
    print(f"  days in the market {int(pos.sum())} ({pos.mean():.0%}), mean {act.mean() * 1e4:+.1f}bp/day t {tstat(act):+.1f}; whole-calendar Sharpe {sh(ret):.2f}, CAGR {ret.mean() * 252:+.1%}, MaxDD {dd(ret):+.1%}; TLT buy&hold Sharpe {sh(r.TLT):.2f}")
    h = len(ret) // 2
    print(f"  halves: {sh(ret.iloc[:h]):.2f} / {sh(ret.iloc[h:]):.2f}; 2006-2012 {sh(ret[:'2012']):.2f}, 2013-2019 {sh(ret['2013':'2019']):.2f}, 2020- {sh(ret['2020':]):.2f}")
    print("  by year (%): " + " ".join(f"{y}:{v * 100:+.1f}" for y, v in ret.groupby(ret.index.year).sum().items()))
    print(f"  in rising-yield years only? TLT down years: {sh(pd.concat([ret[ret.index.year == y] for y in range(2006, 2027) if r.TLT[r.index.year == y].sum() < 0])):.2f}; TLT up years: {sh(pd.concat([ret[ret.index.year == y] for y in range(2006, 2027) if r.TLT[r.index.year == y].sum() >= 0])):.2f}")
    print("\n=== Grid: sessions before (N) x which auctions -> Sharpe / bp per active day ===")
    for name, b in (("30y only", ["30y"]), ("10y only", ["10y"]), ("10y+30y", ["10y", "30y"]), ("10y+20y+30y", LONG), ("+7y", LONG + ["7y"])):
        print(f"  {name:12s} " + " | ".join(f"N={N}: {sh(series(b, N)[0]):.2f} / {series(b, N)[0][series(b, N)[1] == 1].mean() * 1e4:+.1f}" for N in (1, 2, 3, 4, 5)))
    print("\n=== Walk-forward: pick (auctions, N) on 2006-2015 by Sharpe, judge on 2016- ===")
    cells = [(b, N) for b in (["30y"], ["10y"], ["10y", "30y"], LONG) for N in (1, 2, 3, 4, 5)]
    best = max(cells, key=lambda c: sh(series(*c)[0][:"2015"]))
    print(f"  chosen: {best[0]} N={best[1]} train {sh(series(*best)[0][:'2015']):.2f} -> TEST 2016-: {sh(series(*best)[0]['2016':]):.2f}; default (10/20/30y, N=3) test {sh(ret['2016':]):.2f}")
    print("\n=== Placebo: the same auction calendar shifted by k sessions (k=0 is real) -> bp per active day ===")
    print("  " + " ".join(f"{k:+d}:{series(LONG, 3, shift=k)[0][series(LONG, 3, shift=k)[1] == 1].mean() * 1e4:+.1f}" for k in range(-15, 16, 3)))
    sh_shift = [sh(series(LONG, 3, shift=k)[0]) for k in range(-20, 21) if abs(k) >= 6]
    print(f"  Sharpe of 30 shifted calendars: mean {np.mean(sh_shift):.2f}, max {np.max(sh_shift):.2f}; real {sh(ret):.2f}; share of shifts >= real: {np.mean(np.array(sh_shift) >= sh(ret)):.2f}")
    print("\n=== Other instruments ===")
    for sym in ("IEF",):
        x, p = series(LONG, 3, sym); print(f"  short {sym}: Sharpe {sh(x):.2f}, {x[p == 1].mean() * 1e4:+.1f}bp/day t {tstat(x[p == 1]):+.1f}")
    eq = -pos * r.SPY; print(f"  (same days, short SPY instead: {eq[pos == 1].mean() * 1e4:+.1f}bp/day - should be about minus the equity drift, i.e. not a general risk-off window)")
    print("\n=== Overlap with Sleeve M (month-end pair) ===")
    m = mp.daily_returns(px.SPY, px.TLT).reindex(cal).fillna(0)
    both_on = ((m != 0) & (pos == 1)).sum()
    print(f"  days where both are on: {int(both_on)} of {int(pos.sum())}; corr daily {ret.corr(m):+.3f}; M alone {sh(m):.2f}, pre-auction alone {sh(ret):.2f}, M + pre-auction {sh(m + ret):.2f} MaxDD {dd(m + ret):+.1%}")
    print(f"  per $12.5k of TLT short: {act.mean() * 12500:+.1f}$/active day, {ret.mean() * 252 * 12500:+.0f}$/yr, worst day {ret.min() * 12500:+.0f}$")


if __name__ == "__main__":
    main()
