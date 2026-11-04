"""Own ideas round (2026-11-04): tests nobody published a recipe for, on the data
we have, each with a placebo or a sign-flip control and a first/second half split.

  vix_sizing     size the overnight hold by the VIX level (1993-): quintiles, an overlay, placebo
  sector_xs      cross-sectional sector overnight reversal (XLB..XLY, hourly 2015-):
                 long overnight the sectors that fell most during the day, short the ones that rose most
  spread         QQQ/SPY intraday ratio reversion (5-min 1y and hourly 2015-): z-score entry, exit at mean / EOD
  gap_fill       single stocks: does a gap fill, and is fading / riding it tradeable (5-min, 1y)
  btc_funding    BTC/ETH perp drift around the 00/08/16 UTC funding settlements (5-min)
  stock_xs       intraday relative strength among 8 stocks: long the strongest first hour,
                 short the weakest, 10:30 -> close; plus the reversal version

Usage: python scripts/screen_own_ideas.py <section|all>
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
RNG = np.random.default_rng(3)


def tstat(x) -> float:
    x = pd.Series(x).dropna()
    return float(x.mean() / x.std() * np.sqrt(len(x))) if len(x) > 2 and x.std() > 0 else 0.0


def sh(x, ppy=252) -> float:
    x = pd.Series(x).dropna()
    return float(x.mean() / x.std() * np.sqrt(ppy)) if len(x) > 2 and x.std() > 0 else 0.0


def halves(x) -> str:
    x = pd.Series(x).dropna(); h = len(x) // 2
    return f"halves Sharpe {sh(x.iloc[:h]):+.2f}/{sh(x.iloc[h:]):+.2f}"


def by_year(x) -> str:
    x = pd.Series(x).dropna(); idx = pd.to_datetime(pd.Index(x.index))
    return " ".join(f"{y}:{v * 100:+.1f}" for y, v in x.groupby(idx.year).sum().items())


def yf_daily(tickers):
    import yfinance as yf
    raw = yf.download(tickers, period="max", interval="1d", auto_adjust=True, progress=False)
    return raw


def load5(pattern: str, rth=True) -> pd.DataFrame | None:
    hits = sorted(glob.glob(str(ROOT / pattern)))
    if not hits:
        return None
    df = load_tv_csv(hits[0]); df.index = df.index.tz_convert(TZ)
    if rth:
        df = df.between_time("09:30", "15:55")
    df = df[["open", "high", "low", "close"]].copy(); df["d"] = df.index.date; df["hm"] = df.index.strftime("%H:%M")
    return df


# --------------------------------------------------------------------- VIX sizing


def section_vix_sizing() -> None:
    print("\n=== VIX-sized overnight hold (daily, 1993-): overnight return by VIX quintile, then an overlay ===")
    raw = yf_daily(["SPY", "QQQ", "IWM", "GLD", "^VIX"])
    vix = raw["Close"]["^VIX"].dropna()
    from ten_cent_bot.overnight import rsi
    cost = 1e-4
    for t in ["SPY", "QQQ", "IWM", "GLD"]:
        df = pd.DataFrame({"open": raw["Open"][t], "close": raw["Close"][t]}).dropna()
        on = (df.open.shift(-1) / df.close - 1)
        v = vix.reindex(df.index).ffill()
        q = pd.qcut(v, 5, labels=False)
        cells = " ".join(f"Q{int(k) + 1}(VIX<{v[q == k].max():.0f}) {on[q == k].mean() * 1e4:+.1f}bp t{tstat(on[q == k]):+.1f}" for k in sorted(q.dropna().unique()))
        print(f"  {t}: {cells}")
        # vol-scaled sizing: the classic "constant risk" rule, size = min(2, 20/VIX) vs E v2
        r2 = rsi(df.close, 2); pos = pd.Series(1.0, index=df.index); pos[r2 < 10] = 2.0
        e = pos * on - 2 * cost * pos
        for name, size in [("size=min(2,20/VIX)", np.minimum(2.0, 20.0 / v)), ("size=max(1,VIX/20) cap 2", np.clip(v / 20.0, 1.0, 2.0)), ("2x when VIX>25", np.where(v > 25, 2.0, 1.0))]:
            s = pd.Series(size, index=df.index)
            ov = s * pos * on - 2 * cost * s * pos
            # placebo: same size series shuffled
            sp = pd.Series(RNG.permutation(s.to_numpy()), index=df.index)
            pl = sp * pos * on - 2 * cost * sp * pos
            print(f"     {name:26s} Sharpe {sh(ov):.2f} vs E v2 {sh(e):.2f} | {halves(ov)} vs {halves(e)} | CAGR {ov.mean() * 252 * 100:.1f}% vs {e.mean() * 252 * 100:.1f}% | MaxDD {((1 + ov.fillna(0)).cumprod() / (1 + ov.fillna(0)).cumprod().cummax() - 1).min() * 100:.0f}% vs {((1 + e.fillna(0)).cumprod() / (1 + e.fillna(0)).cumprod().cummax() - 1).min() * 100:.0f}% | placebo {sh(pl):.2f}")


# --------------------------------------------------------------------- sector cross-section


def section_sector_xs() -> None:
    print("\n=== Sector cross-sectional overnight reversal (XLB..XLY hourly 2015-): rank today's intraday move, hold overnight ===")
    secs = ["XLB", "XLE", "XLF", "XLI", "XLK", "XLP", "XLU", "XLV", "XLY"]
    intra, on = {}, {}
    for s in secs:
        df = load_tv_csv(ROOT / f"BATS_{s}, 60.csv"); df.index = df.index.tz_convert(TZ)
        g = df.groupby(df.index.date)
        o, c = g.open.first(), g.close.last()
        intra[s] = c / o - 1
        on[s] = o.shift(-1) / c - 1
    intra = pd.DataFrame(intra).dropna(); on = pd.DataFrame(on).reindex(intra.index).dropna()
    intra = intra.reindex(on.index)
    cost = 1e-4
    rank = intra.rank(axis=1)
    k = 3
    low = (rank <= k); high = (rank > len(secs) - k)
    long_low = (on[low].mean(axis=1)); short_high = -(on[high].mean(axis=1))
    ls = (long_low + short_high) / 2 - 4 * cost
    ew = on.mean(axis=1) - 2 * cost
    lo_only = long_low - 2 * cost
    # cross-sectional correlation per day between intraday rank and overnight return
    xs_corr = pd.Series([np.corrcoef(intra.loc[d], on.loc[d])[0, 1] for d in on.index], index=on.index)
    print(f"  days {len(on)}; mean cross-sectional corr(intraday, overnight) {xs_corr.mean():+.3f} t{tstat(xs_corr):+.1f} (negative = reversal)")
    for name, r in [("long worst-3 / short best-3 overnight", ls), ("long worst-3 only", lo_only), ("equal-weight all 9 overnight (benchmark)", ew), ("short best-3 only", short_high - 2 * cost)]:
        print(f"  {name:42s} {r.mean() * 1e4:+.1f}bp/night t{tstat(r):+.1f} Sharpe {sh(r):+.2f} {halves(r)}")
        print(f"      by year: {by_year(r)}")
    # placebo: random ranks
    rr = pd.DataFrame(RNG.random(intra.shape), index=intra.index, columns=intra.columns).rank(axis=1)
    pl = ((on[rr <= k].mean(axis=1) - on[rr > len(secs) - k].mean(axis=1)) / 2 - 4 * cost)
    print(f"  placebo (random ranks) long/short: {pl.mean() * 1e4:+.1f}bp t{tstat(pl):+.1f} Sharpe {sh(pl):+.2f}")
    # momentum version
    mom = ((on[high].mean(axis=1) - on[low].mean(axis=1)) / 2 - 4 * cost)
    print(f"  momentum version (long best-3 / short worst-3): {mom.mean() * 1e4:+.1f}bp t{tstat(mom):+.1f} Sharpe {sh(mom):+.2f}")


# --------------------------------------------------------------------- QQQ/SPY spread


def spread_trades(q: pd.Series, s: pd.Series, window: int, z_in: float, cost_leg: float, per_day: bool) -> pd.Series:
    r = np.log(q / s)
    out = {}
    df = pd.DataFrame({"r": r})
    df["d"] = df.index.date
    groups = df.groupby("d") if per_day else [(None, df)]
    for d, g in groups:
        x = g.r
        m = x.rolling(window).mean(); sd = x.rolling(window).std()
        z = ((x - m) / sd).to_numpy(); xs = x.to_numpy()
        i = window
        while i < len(xs) - 1:
            if abs(z[i]) > z_in:
                side = -np.sign(z[i])  # z>0: QQQ rich -> short QQQ long SPY
                j = i + 1
                while j < len(xs) - 1 and np.sign(z[j]) == np.sign(z[i]):
                    j += 1
                ret = side * (xs[j] - xs[i + 1]) - 4 * cost_leg  # entered at bar i+1 close (approx), exit bar j close
                out[g.index[i + 1]] = ret
                i = j
            i += 1
    return pd.Series(out)


def section_spread() -> None:
    print("\n=== QQQ/SPY ratio reversion: z-score of log(QQQ/SPY) vs rolling mean, enter |z|>2, exit at z=0 (or EOD); 1bp/side/leg ===")
    q5, s5 = load5("BATS_QQQ, 5.csv"), load5("BATS_SPY, 5.csv")
    if q5 is not None and s5 is not None:
        idx = q5.index.intersection(s5.index)
        for w, z in [(24, 2.0), (36, 2.5), (60, 2.0)]:
            tr = spread_trades(q5.close[idx], s5.close[idx], w, z, 1e-4, per_day=True)
            daily = tr.groupby(pd.Index(tr.index).date).sum()
            print(f"  5-min 1y  window {w} z>{z}: trades {len(tr)} mean {tr.mean() * 1e4:+.1f}bp/trade t{tstat(tr):+.1f} win {(tr > 0).mean():.2f} daily Sharpe {sh(daily):+.2f} {halves(daily)}")
    q60 = load_tv_csv(ROOT / "BATS_QQQ, 60.csv"); s60 = load_tv_csv(ROOT / "BATS_SPY, 60.csv")
    idx = q60.index.intersection(s60.index)
    for w, z in [(20, 2.0), (50, 2.0), (100, 2.5)]:
        tr = spread_trades(q60.close[idx], s60.close[idx], w, z, 1e-4, per_day=False)
        daily = tr.groupby(pd.Index(tr.index).date).sum()
        print(f"  hourly 2015- window {w} z>{z}: trades {len(tr)} mean {tr.mean() * 1e4:+.1f}bp/trade t{tstat(tr):+.1f} win {(tr > 0).mean():.2f} daily Sharpe {sh(daily):+.2f} {halves(daily)}")
        print(f"      by year: {by_year(daily)}")


# --------------------------------------------------------------------- gap fill


def section_gap_fill() -> None:
    print("\n=== Single-stock gaps (5-min 1y): fill probability, and fade-to-prior-close vs ride-the-gap, 2bp/side ===")
    for tk in ["TSLA", "NVDA", "PLTR", "AMD", "AAPL", "COIN", "MSTR", "AMZN", "QQQ"]:
        df = load5(f"*{tk}, 5.csv")
        if df is None:
            continue
        g = df.groupby("d")
        o = g.open.first(); c = g.close.last(); hi = g.high.max(); lo = g.low.min()
        pc = c.shift(1)
        gap = o / pc - 1
        first_close = g.close.first()
        rows = []
        for lo_b, hi_b, lab in [(0.01, 0.02, "up 1-2%"), (0.02, 9, "up >2%"), (-0.02, -0.01, "down 1-2%"), (-9, -0.02, "down >2%")]:
            m = (gap > lo_b) & (gap <= hi_b)
            if m.sum() < 8:
                continue
            up = gap[m] > 0
            filled = np.where(up, lo[m] <= pc[m], hi[m] >= pc[m])
            # fade: enter at the first bar close toward prior close, target = prior close, stop = gap size beyond entry, else EOD
            res = []
            for d in gap[m].index:
                day = df[df.d == d]
                if len(day) < 10:
                    continue
                entry = day.close.iloc[0]; side = -1 if gap[d] > 0 else 1
                target = pc[d]; stop = entry - side * abs(entry - pc[d])
                exit_px = day.close.iloc[-1]
                for k in range(1, len(day)):
                    b = day.iloc[k]
                    if (side == 1 and b.low <= stop) or (side == -1 and b.high >= stop):
                        exit_px = stop; break
                    if (side == 1 and b.high >= target) or (side == -1 and b.low <= target):
                        exit_px = target; break
                res.append(side * (exit_px / entry - 1) - 4e-4)
            res = pd.Series(res)
            ride = -res - 8e-4 + 4e-4  # mirror trade, same costs
            rows.append(f"{lab}: n {int(m.sum())} filled {filled.mean():.0%} | fade {res.mean() * 1e4:+.0f}bp t{tstat(res):+.1f} | ride {ride.mean() * 1e4:+.0f}bp")
        print(f"  {tk}: " + " || ".join(rows))


# --------------------------------------------------------------------- BTC funding


def section_btc_funding() -> None:
    print("\n=== Perp drift around funding settlements (00/08/16 UTC), 5-min, mean return per window (bp) ===")
    for tk in ["BTCUSDT.P", "ETHUSDT.P"]:
        hits = sorted(glob.glob(str(ROOT / f"BINANCE_{tk}, 5.csv")))
        if not hits:
            continue
        df = load_tv_csv(hits[0])  # UTC index
        r = df.close.pct_change()
        mins = (df.index.hour * 60 + df.index.minute)
        rel = ((mins + 240) % 480) - 240  # minutes relative to the nearest funding time (-240..239)
        cells = []
        for a, b in [(-120, -60), (-60, -30), (-30, 0), (0, 30), (30, 60), (60, 120)]:
            m = (rel >= a) & (rel < b)
            x = r[m].dropna()
            cells.append(f"[{a:+d},{b:+d}) {x.mean() * 1e4 * 6:+.1f}bp/30min t{tstat(x):+.1f}")
        print(f"  {tk}: " + " | ".join(cells))
        # strategy: long the 30 min before funding, flat otherwise (and the mirror)
        pre = r[(rel >= -30) & (rel < 0)]
        daily = pre.groupby(pre.index.date).sum() - 3 * 1e-3  # three round trips at 5bp/side
        print(f"     hold the 30 min before each funding (3x/day) net of 5bp/side: {daily.mean() * 1e4:+.1f}bp/day Sharpe {sh(daily, 365):+.2f}")


# --------------------------------------------------------------------- stock cross-section intraday


def section_stock_xs() -> None:
    print("\n=== Intraday relative strength among 8 stocks: rank the first hour (09:30-10:30), trade 10:30 -> close, 2bp/side ===")
    tks = ["TSLA", "NVDA", "PLTR", "AMD", "AAPL", "COIN", "MSTR", "AMZN"]
    first, rest = {}, {}
    for tk in tks:
        df = load5(f"*{tk}, 5.csv")
        if df is None:
            continue
        g = df.groupby("d")
        o = g.open.first(); c = g.close.last()
        h1 = df[df.hm == "10:30"].groupby("d").open.first()
        first[tk] = h1 / o - 1; rest[tk] = c / h1 - 1
    first = pd.DataFrame(first).dropna(); rest = pd.DataFrame(rest).reindex(first.index).dropna(); first = first.reindex(rest.index)
    rk = first.rank(axis=1); n = first.shape[1]
    cost = 2e-4
    mom = (rest[rk > n - 2].mean(axis=1) - rest[rk <= 2].mean(axis=1)) / 2 - 2 * cost
    rev = -mom - 4 * cost + 2 * cost
    long_top = rest[rk > n - 2].mean(axis=1) - 2 * cost
    long_bot = rest[rk <= 2].mean(axis=1) - 2 * cost
    allm = rest.mean(axis=1) - 2 * cost
    xs = pd.Series([np.corrcoef(first.loc[d], rest.loc[d])[0, 1] for d in rest.index], index=rest.index)
    print(f"  days {len(rest)}, mean cross-sectional corr(first hour, rest of day) {xs.mean():+.3f} t{tstat(xs):+.1f}")
    for name, r in [("momentum: long top-2 / short bottom-2", mom), ("reversal: long bottom-2 / short top-2", rev), ("long top-2 only", long_top), ("long bottom-2 only", long_bot), ("long all 8 (benchmark)", allm)]:
        print(f"  {name:40s} {r.mean() * 1e4:+.1f}bp/day t{tstat(r):+.1f} Sharpe {sh(r):+.2f} {halves(r)}")


SECTIONS = {"vix_sizing": section_vix_sizing, "sector_xs": section_sector_xs, "spread": section_spread, "gap_fill": section_gap_fill, "btc_funding": section_btc_funding, "stock_xs": section_stock_xs}

if __name__ == "__main__":
    which = sys.argv[1] if len(sys.argv) > 1 else "all"
    for k, fn in SECTIONS.items():
        if which in ("all", k):
            fn()
