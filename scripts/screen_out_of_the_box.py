"""Out-of-the-box theory screen (2026-11-04).

Odd but published or at least falsifiable ideas, each tested on the longest
sample we can get. Index history comes from TradingView chart exports
(`TVC_DJI, 1D.csv` / `SP_SPX, 1D.csv`, ~80 years, close-to-close only because
historical index opens are not real), ETF overnight from yfinance (SPY 1993-),
futures sessions from the ES 30-min 23h export (2025-).

Sections:
  moon        - Dichev & Janes 2003: returns around new moon vs full moon
  preholiday  - Ariel 1990: the session and the night before an NYSE holiday
  opex        - monthly options-expiration week / day, quad witching
  tuesday     - "turnaround Tuesday": Monday down -> Tuesday
  gapfade     - overnight gap > 1% -> day-session reversal (and continuation)
  stress      - size the overnight hold by yesterday's volume / range (Nagel mechanism)
  btcweekend  - BTC weekend vs weekday days
  essession   - ES European session (02:00-09:30 ET) -> US day session

Every number: mean per period in bp, t-stat, Sharpe where a strategy is implied,
and first-half / second-half split. 1 bp per side where a trade is implied.
"""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from ten_cent_bot import calendar_nyse
from ten_cent_bot.tv_data import load_tv_csv

ROOT = Path(__file__).resolve().parent.parent
COST_SIDE = 1e-4
SYNODIC = 29.530588853
NEW_MOON_EPOCH = pd.Timestamp("2000-01-06 18:14", tz="UTC")


def tstat(x: pd.Series) -> float:
    x = x.dropna()
    return float(x.mean() / x.std() * np.sqrt(len(x))) if len(x) > 2 and x.std() > 0 else 0.0


def sh(x: pd.Series, ppy: int = 252) -> float:
    x = x.dropna()
    return float(x.mean() / x.std() * np.sqrt(ppy)) if len(x) > 2 and x.std() > 0 else 0.0


def halves(x: pd.Series) -> str:
    x = x.dropna()
    h = len(x) // 2
    return f"halves mean {x.iloc[:h].mean() * 1e4:+.1f}/{x.iloc[h:].mean() * 1e4:+.1f} bp"


def row(name: str, x: pd.Series, extra: str = "") -> None:
    x = x.dropna()
    print(f"  {name:44s} n {len(x):6d}  mean {x.mean() * 1e4:+6.1f} bp  t {tstat(x):+5.2f}  {halves(x)}  {extra}")


def load_index(fname: str) -> pd.DataFrame:
    df = load_tv_csv(ROOT / fname)
    df.index = df.index.tz_convert("America/New_York").normalize().tz_localize(None)
    return df[["open", "high", "low", "close"]]


def load_etf(ticker: str) -> pd.DataFrame:
    import yfinance as yf

    raw = yf.download(ticker, period="max", interval="1d", auto_adjust=True, progress=False)
    raw.columns = [c[0].lower() if isinstance(c, tuple) else c.lower() for c in raw.columns]
    df = raw[["open", "high", "low", "close", "volume"]].dropna()
    df.index = pd.DatetimeIndex(df.index).tz_localize(None).normalize()
    return df


def index_sources() -> dict[str, pd.DataFrame]:
    out = {}
    for name, f in [("DJI", "TVC_DJI, 1D.csv"), ("SPX", "SP_SPX, 1D.csv")]:
        if (ROOT / f).exists():
            out[name] = load_index(f)
    if not out:
        out["SPY(yf)"] = load_etf("SPY")
    return out


# ---------------------------------------------------------------- moon


def moon_phase(idx: pd.DatetimeIndex) -> pd.Series:
    """0 = new moon, 0.5 = full moon, as a fraction of the synodic month."""
    t = pd.DatetimeIndex(idx).tz_localize("UTC") + pd.Timedelta(hours=16)
    days = (t - NEW_MOON_EPOCH).total_seconds() / 86400.0
    return pd.Series((days / SYNODIC) % 1.0, index=idx)


def section_moon() -> None:
    print("\n=== Moon: close-to-close return in the 7-day window around NEW vs FULL moon ===")
    for name, df in index_sources().items():
        r = df.close.pct_change().dropna()
        ph = moon_phase(r.index)
        # distance to nearest new moon in days (0..14.77)
        d_new = np.minimum(ph, 1 - ph) * SYNODIC
        near_new = r[d_new <= 3.5]
        near_full = r[d_new >= SYNODIC / 2 - 3.5]
        row(f"{name} near NEW moon (+/-3.5d)", near_new, f"since {r.index[0].date()}")
        row(f"{name} near FULL moon (+/-3.5d)", near_full)
        diff = near_new.mean() - near_full.mean()
        se = np.sqrt(near_new.var() / len(near_new) + near_full.var() / len(near_full))
        print(f"      new - full = {diff * 1e4:+.1f} bp/day, t = {diff / se:+.2f}")
        # by decade
        dec = r.groupby([r.index.year // 10 * 10, (d_new <= 3.5).reindex(r.index)]).mean().unstack() * 1e4
        if True in dec.columns and False in dec.columns:
            print("      by decade (new-window mean bp vs rest): " + " ".join(f"{int(y)}s:{dec.loc[y, True]:+.1f}/{dec.loc[y, False]:+.1f}" for y in dec.index))


# ---------------------------------------------------------------- pre-holiday


def section_preholiday() -> None:
    print("\n=== Pre-holiday: the session before an NYSE holiday (index close-to-close) and the night before (SPY overnight) ===")
    for name, df in index_sources().items():
        r = df.close.pct_change().dropna()
        dates = pd.DatetimeIndex(r.index)
        nxt = pd.Series([calendar_nyse.next_trading_day(d.date()) for d in dates], index=r.index)
        gap_days = pd.Series([(n - d.date()).days for n, d in zip(nxt, dates)], index=r.index)
        pre_hol = gap_days > 3  # a weekend is 3 days; holiday weekend 4+, mid-week holiday 2 -> handle both
        pre_hol = pre_hol | ((gap_days == 2) & (dates.dayofweek < 4))
        row(f"{name} session BEFORE holiday", r[pre_hol], f"since {r.index[0].date()}")
        row(f"{name} all other sessions", r[~pre_hol])
        after = pre_hol.shift(1, fill_value=False)
        row(f"{name} session AFTER holiday", r[after])
    spy = load_etf("SPY")
    on = (spy.open.shift(-1) / spy.close - 1).dropna()
    dates = pd.DatetimeIndex(on.index)
    nxt = pd.Series([calendar_nyse.next_trading_day(d.date()) for d in dates], index=on.index)
    gap_days = pd.Series([(n - d.date()).days for n, d in zip(nxt, dates)], index=on.index)
    pre = (gap_days > 3) | ((gap_days == 2) & (dates.dayofweek < 4))
    row("SPY overnight INTO a holiday gap", on[pre])
    row("SPY overnight, normal nights", on[~pre])
    row("SPY overnight, plain weekends", on[gap_days == 3])


# ---------------------------------------------------------------- opex


def third_friday(y: int, m: int) -> dt.date:
    d = dt.date(y, m, 15)
    while d.weekday() != 4:
        d += dt.timedelta(days=1)
    return d


def section_opex() -> None:
    print("\n=== Options expiration: OPEX day, OPEX week (Mon-Fri), week after, quad witching (index close-to-close) ===")
    for name, df in index_sources().items():
        r = df.close.pct_change().dropna()
        r = r[r.index >= "1973-01-01"]  # listed index options era
        idx = pd.DatetimeIndex(r.index)
        tf = pd.Series([third_friday(d.year, d.month) for d in idx], index=r.index)
        d = pd.Series([x.date() for x in idx], index=r.index)
        delta = pd.Series([(a - b).days for a, b in zip(tf, d)], index=r.index)
        opex_day = delta == 0
        opex_week = (delta >= 0) & (delta <= 4)
        week_after = (delta < 0) & (delta >= -7)
        quad = opex_day & idx.month.isin([3, 6, 9, 12])
        row(f"{name} OPEX day", r[opex_day], f"since {r.index[0].date()}")
        row(f"{name} OPEX week (Mon-Fri)", r[opex_week])
        row(f"{name} week after OPEX", r[week_after])
        row(f"{name} quad-witching day", r[quad])
        row(f"{name} all days", r)


# ---------------------------------------------------------------- turnaround tuesday


def section_tuesday() -> None:
    print("\n=== Turnaround Tuesday: Tuesday return after a down Monday vs up Monday (close-to-close) ===")
    for name, df in index_sources().items():
        r = df.close.pct_change().dropna()
        idx = pd.DatetimeIndex(r.index)
        mon = r[idx.dayofweek == 0]
        tue = r[idx.dayofweek == 1]
        # pair each Tuesday with the Monday one trading day before
        prev = r.shift(1)
        tue_after_down = tue[(prev.reindex(tue.index) < 0) & (pd.DatetimeIndex(tue.index) - pd.Timedelta(days=1)).isin(mon.index)]
        tue_after_up = tue[(prev.reindex(tue.index) > 0) & (pd.DatetimeIndex(tue.index) - pd.Timedelta(days=1)).isin(mon.index)]
        row(f"{name} Tuesday after DOWN Monday", tue_after_down, f"since {r.index[0].date()}")
        row(f"{name} Tuesday after UP Monday", tue_after_up)
        # generic: any day after a down day (is it just reversal?)
        row(f"{name} any day after a down day", r[prev < 0])
        row(f"{name} any day after an up day", r[prev > 0])
        by_dec = tue_after_down.groupby(pd.DatetimeIndex(tue_after_down.index).year // 10 * 10).mean() * 1e4
        print("      Tue-after-down by decade (bp): " + " ".join(f"{int(y)}s:{v:+.1f}" for y, v in by_dec.items()))


# ---------------------------------------------------------------- gap fade


def section_gapfade() -> None:
    print("\n=== Gap fade: day-session return after an overnight gap (SPY/QQQ/IWM, real opens, yfinance) ===")
    for tk in ["SPY", "QQQ", "IWM"]:
        df = load_etf(tk)
        gap = df.open / df.close.shift(1) - 1
        day = df.close / df.open - 1
        for lo, hi, label in [(0.01, 9, "gap UP > 1%"), (-9, -0.01, "gap DOWN > 1%"), (0.005, 0.01, "gap up 0.5-1%"), (-0.01, -0.005, "gap down 0.5-1%")]:
            m = (gap > lo) & (gap < hi)
            row(f"{tk} day session after {label}", day[m], f"since {df.index[0].date()}")
        fade = -np.sign(gap) * day - 2 * COST_SIDE
        fade = fade[gap.abs() > 0.01]
        print(f"      {tk} fade-the-1%-gap strategy: Sharpe {sh(fade):+.2f} on {len(fade)} days, {halves(fade)}")


# ---------------------------------------------------------------- stress sizing


def section_stress() -> None:
    print("\n=== Stress sizing: overnight return by yesterday's volume ratio and range quintile (E overlay candidates) ===")
    for tk in ["SPY", "QQQ", "IWM"]:
        df = load_etf(tk)
        on = (df.open.shift(-1) / df.close - 1)
        volr = df.volume / df.volume.rolling(20).mean()
        rng = ((df.high - df.low) / df.close)
        rngr = rng / rng.rolling(20).mean()
        for feat, fname in [(volr, "volume/20d avg"), (rngr, "range/20d avg")]:
            q = pd.qcut(feat.dropna(), 5, labels=False)
            means = on.groupby(q).mean() * 1e4
            ts = on.groupby(q).apply(tstat)
            print(f"  {tk} overnight by {fname} quintile (bp, t): " + "  ".join(f"Q{int(k) + 1} {means[k]:+.1f}({ts[k]:+.1f})" for k in means.index))
            # overlay: 2x in top quintile, 1x otherwise, vs plain E
            pos = pd.Series(1.0, index=on.index)
            pos[feat >= feat.rolling(252).quantile(0.8)] = 2.0
            base = on - 2 * COST_SIDE
            ov = pos * on - 2 * COST_SIDE * pos
            print(f"      overlay 2x when {fname} in top 20% (rolling yr): Sharpe {sh(ov):+.2f} vs plain {sh(base):+.2f}; halves {sh(ov.iloc[:len(ov)//2]):.2f}/{sh(ov.iloc[len(ov)//2:]):.2f} vs {sh(base.iloc[:len(base)//2]):.2f}/{sh(base.iloc[len(base)//2:]):.2f}")


# ---------------------------------------------------------------- btc weekend


def section_btcweekend() -> None:
    print("\n=== BTC: weekend days vs weekdays, and Friday-close -> Monday-open style holds (daily, yfinance) ===")
    df = load_etf("BTC-USD")
    r = df.close.pct_change().dropna()
    idx = pd.DatetimeIndex(r.index)
    for dname, dnum in [("Mon", 0), ("Tue", 1), ("Wed", 2), ("Thu", 3), ("Fri", 4), ("Sat", 5), ("Sun", 6)]:
        row(f"BTC {dname}", r[idx.dayofweek == dnum], f"since {r.index[0].date()}" if dnum == 0 else "")
    wk = r[idx.dayofweek < 5]
    we = r[idx.dayofweek >= 5]
    print(f"      weekday Sharpe {sh(wk, 252):+.2f} vs weekend Sharpe {sh(we, 104):+.2f}; weekend share of total vol {we.std() / r.std():.2f}")


# ---------------------------------------------------------------- es sessions


def section_essession() -> None:
    print("\n=== ES sessions (30-min, 23h, 2025-): Asia 18:00-02:00, Europe 02:00-09:30, US 09:30-16:00 ET; does one predict the next? ===")
    for f in ["CME_MINI_ES1!, 30.csv", "CME_MINI_ES1!, 60.csv", "CME_MINI_NQ1!, 60.csv"]:
        if (ROOT / f).exists():
            print(f"  -- {f}")
            _es_sessions(load_tv_csv(ROOT / f))


def _es_sessions(df: pd.DataFrame) -> None:
    df.index = df.index.tz_convert("America/New_York")
    # trading date = date of the US session; bars from 18:00 prev day belong to it
    tdate = (df.index + pd.Timedelta(hours=6)).date
    df["td"] = tdate
    hm = df.index.strftime("%H:%M")
    df["sess"] = np.where((hm >= "18:00") | (hm < "02:00"), "asia", np.where(hm < "09:30", "europe", np.where(hm < "16:00", "us", "post")))
    g = df.groupby(["td", "sess"])
    o = g.open.first().unstack()
    c = g.close.last().unstack()
    ret = (c / o - 1).dropna(subset=["asia", "europe", "us"])
    for a, b in [("asia", "europe"), ("europe", "us"), ("asia", "us")]:
        corr = ret[a].corr(ret[b])
        strat = np.sign(ret[a]) * ret[b] - 2 * COST_SIDE
        row(f"sign({a}) -> {b} session", strat, f"corr {corr:+.3f}  Sharpe {sh(strat):+.2f}")
    both = np.sign(ret.asia + ret.europe) * ret.us - 2 * COST_SIDE
    row("sign(asia+europe) -> US session", both, f"Sharpe {sh(both):+.2f}")
    row("US session unconditional", ret.us)
    row("Europe session unconditional", ret.europe)
    row("Asia session unconditional", ret.asia)
    fade = -np.sign(ret.asia) * ret.us - 2 * COST_SIDE
    yrs = fade.groupby(pd.to_datetime(pd.Index(fade.index)).year).apply(lambda x: f"{x.sum() * 100:+.1f}%/{sh(x):+.1f}")
    print("      fade-Asia-in-US by year (P&L / Sharpe): " + " ".join(f"{y}:{v}" for y, v in yrs.items()))


SECTIONS = {
    "moon": section_moon,
    "preholiday": section_preholiday,
    "opex": section_opex,
    "tuesday": section_tuesday,
    "gapfade": section_gapfade,
    "stress": section_stress,
    "btcweekend": section_btcweekend,
    "essession": section_essession,
}

if __name__ == "__main__":
    which = sys.argv[1] if len(sys.argv) > 1 else "all"
    for k, fn in SECTIONS.items():
        if which in ("all", k):
            fn()
