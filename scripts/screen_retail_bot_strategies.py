"""Screen the strategies retail bots / TradingView users most often run.

Three families, each tested on the TradingView chart exports in the repo root
(30-min SPY 2020-, ES1! regular-hours 30-min 2021-, 60-min SPY/QQQ/IWM 2015-)
plus daily yfinance where a longer sample matters:

  intraday_mom  - Gao/Han/Li/Zhou (2018) first half-hour -> last half-hour
  orb           - opening-range breakout (Zarattini & Aziz 2023 shape, 30-min OR)
  supertrend    - ATR trend-following (most-published TV strategy)
  monday_range  - Monday high/low breakout and its fade (Ali's "Monday Range" script)
  fvg           - ICT fair value gap, continuation and return-to-gap entries (Ali's FVG script)

Usage: python scripts/screen_retail_bot_strategies.py <section|all>

Costs: 1 bp per side on ETFs, 1 tick + $0.62 per side on ES-as-MES-equivalent
(approximated as 1 bp per side too; ES RTH file is back-adjusted).
Every section prints Sharpe, annual return, hit rate and the per-year P&L so a
one-year fluke cannot hide behind the average.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

from ten_cent_bot.tv_data import load_tv_csv

ROOT = Path(__file__).resolve().parent.parent
TZ = "America/New_York"
COST_SIDE = 1e-4  # 1 bp per side

FILES = {
    "SPY 30m": "BATS_SPY, 30.csv",
    "ES RTH 30m": "CME_MINI_ES1!, 30 RTH.csv",
    "SPY 60m": "BATS_SPY, 60.csv",
    "QQQ 60m": "BATS_QQQ, 60.csv",
    "IWM 60m": "BATS_IWM, 60.csv",
}


def load(name: str) -> pd.DataFrame:
    df = load_tv_csv(ROOT / FILES[name])
    df.index = df.index.tz_convert(TZ)
    df["d"] = df.index.date
    df["hm"] = df.index.strftime("%H:%M")
    return df


def sh(x: pd.Series, ppy: int = 252) -> float:
    x = x.dropna()
    return float(x.mean() / x.std() * np.sqrt(ppy)) if len(x) > 2 and x.std() > 0 else 0.0


def by_year(x: pd.Series) -> str:
    idx = pd.to_datetime(pd.Index(x.index))
    yrs = x.groupby(idx.year).sum() * 100
    return " ".join(f"{y}:{v:+.1f}" for y, v in yrs.items())


def line(name: str, r: pd.Series, extra: str = "") -> None:
    r = r.dropna()
    hit = float((r > 0).mean()) if len(r) else 0.0
    print(
        f"  {name:34s} n {len(r):5d}  Sharpe {sh(r):+5.2f}  ann {r.mean() * 252 * 100:+6.1f}%  "
        f"hit {hit:.3f}  worst-yr {r.groupby(pd.to_datetime(pd.Index(r.index)).year).sum().min() * 100:+.1f}%  {extra}"
    )
    print(f"      by year: {by_year(r)}")


# ---------------------------------------------------------------- intraday momentum


def day_table(df: pd.DataFrame, first_end: str, last_start: str) -> pd.DataFrame:
    g = df.groupby("d")
    t = pd.DataFrame(
        {
            "open": g["open"].first(),
            "first_close": df[df.hm == first_end].groupby("d")["close"].first(),
            "last_open": df[df.hm == last_start].groupby("d")["open"].first(),
            "close": g["close"].last(),
        }
    ).dropna()
    t["prev_close"] = t["close"].shift(1)
    t["r_on"] = t.open / t.prev_close - 1
    t["r_first"] = t.first_close / t.open - 1
    t["r_last"] = t.close / t.last_open - 1
    return t.dropna()


def section_intraday_mom() -> None:
    print("\n=== Intraday momentum: sign(first bar) -> last bar, 1bp/side ===")
    for name in FILES:
        t = day_table(load(name), "09:30", "15:30")
        strat = np.sign(t.r_first) * t.r_last - 2 * COST_SIDE
        fade = -np.sign(t.r_first) * t.r_last - 2 * COST_SIDE
        corr = float(t.r_first.corr(t.r_last))
        line(f"{name} momentum", strat, f"corr(first,last) {corr:+.3f}")
        line(f"{name} fade", fade)


# ---------------------------------------------------------------- ORB


def orb_returns(df: pd.DataFrame, or_end: str, risk: float = 0.01, max_lev: float = 4.0) -> pd.Series:
    """Zarattini-Aziz shape on 30-min bars: OR = first bar. Long if OR close > open,
    short if below, entry at next bar open, stop at far side of OR, exit at close.
    Position sized so a stop-out loses `risk` of equity, capped at `max_lev`x."""
    out = {}
    for d, day in df.groupby("d"):
        if len(day) < 4 or day.hm.iloc[0] != "09:30":
            continue
        orb = day[day.hm <= or_end]
        rest = day[day.hm > or_end]
        if len(orb) == 0 or len(rest) == 0:
            continue
        o, c = orb.open.iloc[0], orb.close.iloc[-1]
        hi, lo = orb.high.max(), orb.low.min()
        if c == o:
            continue
        side = 1 if c > o else -1
        entry = rest.open.iloc[0]
        stop = lo if side == 1 else hi
        dist = abs(entry - stop) / entry
        if dist <= 0:
            continue
        lev = min(risk / dist, max_lev)
        # walk bars for a stop hit
        exit_px = rest.close.iloc[-1]
        for _, b in rest.iterrows():
            if side == 1 and b.low <= stop:
                exit_px = stop
                break
            if side == -1 and b.high >= stop:
                exit_px = stop
                break
        r = side * (exit_px / entry - 1) * lev - 2 * COST_SIDE * lev
        out[d] = r
    return pd.Series(out)


def section_orb() -> None:
    print("\n=== Opening-range breakout (30-min OR, stop = far side, exit at close, 1% risk, 4x cap) ===")
    for name in ["SPY 30m", "ES RTH 30m"]:
        df = load(name)
        line(f"{name} ORB-30 long+short", orb_returns(df, "09:30"))
        r = orb_returns(df, "09:30")
        t = day_table(df, "09:30", "15:30")
        longs = r[np.sign(t.r_first.reindex(r.index)) > 0]
        shorts = r[np.sign(t.r_first.reindex(r.index)) < 0]
        line(f"{name} ORB-30 long side only", longs)
        line(f"{name} ORB-30 short side only", shorts)
    for name in ["SPY 60m", "QQQ 60m", "IWM 60m"]:
        line(f"{name} ORB-60 long+short", orb_returns(load(name), "09:30"))


# ---------------------------------------------------------------- Supertrend


def supertrend(df: pd.DataFrame, period: int = 10, mult: float = 3.0) -> pd.Series:
    hl2 = (df.high + df.low) / 2
    tr = pd.concat(
        [df.high - df.low, (df.high - df.close.shift()).abs(), (df.low - df.close.shift()).abs()], axis=1
    ).max(axis=1)
    atr = tr.ewm(alpha=1 / period, adjust=False).mean()
    upper = (hl2 + mult * atr).to_numpy()
    lower = (hl2 - mult * atr).to_numpy()
    close = df.close.to_numpy()
    n = len(df)
    dirn = np.ones(n, dtype=int)
    fu, fl = upper.copy(), lower.copy()
    for i in range(1, n):
        fl[i] = lower[i] if (lower[i] > fl[i - 1] or close[i - 1] < fl[i - 1]) else fl[i - 1]
        fu[i] = upper[i] if (upper[i] < fu[i - 1] or close[i - 1] > fu[i - 1]) else fu[i - 1]
        if dirn[i - 1] == 1:
            dirn[i] = -1 if close[i] < fl[i] else 1
        else:
            dirn[i] = 1 if close[i] > fu[i] else -1
    return pd.Series(dirn, index=df.index)


def section_supertrend() -> None:
    print("\n=== Supertrend(10, 3): long/flat and long/short, 1bp/side per flip ===")
    for name in ["SPY 60m", "QQQ 60m", "IWM 60m"]:
        df = load(name)
        d = supertrend(df)
        ret = df.close.pct_change()
        pos = d.shift(1)
        flips = (pos != pos.shift(1)).astype(float)
        lf = ((pos > 0).astype(float) * ret - flips * COST_SIDE).groupby(df.d).sum()
        ls = (pos * ret - flips * 2 * COST_SIDE).groupby(df.d).sum()
        bh = ret.groupby(df.d).sum()
        line(f"{name} long/flat", lf, f"vs buy&hold Sharpe {sh(bh):+.2f}")
        line(f"{name} long/short", ls)
    import yfinance as yf

    for tk in ["SPY", "QQQ", "IWM", "GLD", "BTC-USD"]:
        raw = yf.download(tk, period="max", interval="1d", auto_adjust=True, progress=False)
        raw.columns = [c[0].lower() if isinstance(c, tuple) else c.lower() for c in raw.columns]
        df = raw[["open", "high", "low", "close"]].dropna()
        df.index = pd.Index(df.index.date)
        d = supertrend(df)
        ret = df.close.pct_change()
        pos = d.shift(1)
        flips = (pos != pos.shift(1)).astype(float)
        ppy = 365 if tk == "BTC-USD" else 252
        lf = (pos > 0).astype(float) * ret - flips * COST_SIDE
        ls = pos * ret - flips * 2 * COST_SIDE
        bh = ret.dropna()
        print(
            f"  {tk + ' daily long/flat':34s} n {len(lf.dropna()):5d}  Sharpe {sh(lf, ppy):+5.2f}  "
            f"ann {lf.mean() * ppy * 100:+6.1f}%  | long/short Sharpe {sh(ls, ppy):+5.2f}  | buy&hold Sharpe {sh(bh, ppy):+5.2f}  since {df.index[0]}"
        )


# ---------------------------------------------------------------- Monday range


def monday_range(df: pd.DataFrame, mode: str) -> pd.Series:
    """mode 'break': first 60-min close above Monday high (Tue-Fri) -> long, stop Monday mid,
    exit Friday close; mirror for shorts. mode 'fade': same trigger, opposite direction,
    target Monday mid, stop one Monday-range beyond the break."""
    out = {}
    df = df.copy()
    df["wk"] = df.index.to_period("W-SUN")
    for wk, w in df.groupby("wk"):
        days = sorted(set(w.d))
        if len(days) < 3:
            continue
        mon = w[w.index.dayofweek == 0]
        if len(mon) == 0:
            continue
        hi, lo = mon.high.max(), mon.low.min()
        mid = (hi + lo) / 2
        rng = hi - lo
        rest = w[w.index.dayofweek > 0]
        if len(rest) == 0 or rng <= 0:
            continue
        trig = rest[(rest.close > hi) | (rest.close < lo)]
        if len(trig) == 0:
            continue
        t0 = trig.index[0]
        side = 1 if trig.close.iloc[0] > hi else -1
        after = rest[rest.index > t0]
        if len(after) == 0:
            continue
        entry = after.open.iloc[0]
        if mode == "fade":
            side = -side
            stop = entry + (-side) * rng
            target = mid
        else:
            stop = mid
            target = None
        exit_px = after.close.iloc[-1]
        for _, b in after.iterrows():
            if side == 1 and b.low <= stop:
                exit_px = stop
                break
            if side == -1 and b.high >= stop:
                exit_px = stop
                break
            if target is not None and ((side == 1 and b.high >= target) or (side == -1 and b.low <= target)):
                exit_px = target
                break
        dist = abs(entry - stop) / entry
        lev = min(0.01 / dist, 4.0) if dist > 0 else 0
        out[days[-1]] = side * (exit_px / entry - 1) * lev - 2 * COST_SIDE * lev
    return pd.Series(out)


def section_monday_range() -> None:
    print("\n=== Monday range: breakout (stop mid, exit Fri) and fade (target mid), 1% risk, 4x cap, weekly ===")
    for name in ["SPY 60m", "QQQ 60m", "IWM 60m", "ES RTH 30m"]:
        df = load(name)
        for mode in ["break", "fade"]:
            r = monday_range(df, mode)
            r = r.dropna()
            idx = pd.to_datetime(pd.Index(r.index))
            print(
                f"  {name + ' ' + mode:34s} weeks {len(r):4d}  Sharpe {sh(r, 52):+5.2f}  ann {r.mean() * 52 * 100:+6.1f}%  "
                f"hit {(r > 0).mean():.3f}  worst-yr {r.groupby(idx.year).sum().min() * 100:+.1f}%"
            )
            print(f"      by year: {by_year(r)}")


# ---------------------------------------------------------------- Fair value gap (ICT)


def fvg_returns(df: pd.DataFrame, hold_bars: int, mode: str) -> pd.Series:
    """Bullish FVG: low[t] > high[t-2] (3-bar imbalance); bearish mirror.
    mode 'continue': trade in the gap's direction at next open, exit after hold_bars.
    mode 'fill': wait for price to come back into the gap within the day, then trade in the
    gap's direction from the fill bar's close (the ICT 'return to FVG' entry), exit after hold_bars."""
    out = {}
    hi2 = df.high.shift(2)
    lo2 = df.low.shift(2)
    bull = (df.low > hi2)
    bear = (df.high < lo2)
    closes = df.close.to_numpy()
    opens = df.open.to_numpy()
    highs = df.high.to_numpy()
    lows = df.low.to_numpy()
    days = df.d.to_numpy()
    idx = df.index
    n = len(df)
    for i in np.flatnonzero((bull | bear).to_numpy()):
        if i + 1 + hold_bars >= n:
            break
        side = 1 if bull.iloc[i] else -1
        gap_top = lows[i] if side == 1 else lo2.iloc[i]
        gap_bot = hi2.iloc[i] if side == 1 else highs[i]
        if mode == "continue":
            j = i + 1
            entry = opens[j]
            exit_px = closes[min(j + hold_bars - 1, n - 1)]
        else:
            j = None
            for k in range(i + 1, n):
                if days[k] != days[i]:
                    break
                if side == 1 and lows[k] <= gap_top and highs[k] >= gap_bot:
                    j = k
                    break
                if side == -1 and highs[k] >= gap_bot and lows[k] <= gap_top:
                    j = k
                    break
            if j is None or j + hold_bars >= n:
                continue
            entry = closes[j]
            exit_px = closes[j + hold_bars]
        out[idx[j]] = side * (exit_px / entry - 1) - 2 * COST_SIDE
    return pd.Series(out)


def section_fvg() -> None:
    print("\n=== Fair value gap (ICT): 3-bar imbalance, continuation vs return-to-gap entry, 1bp/side ===")
    for name in ["SPY 30m", "ES RTH 30m", "QQQ 60m"]:
        df = load(name)
        for mode in ["continue", "fill"]:
            for hold in [1, 4]:
                r = fvg_returns(df, hold, mode)
                daily = r.groupby(pd.Index(r.index).date).sum()
                line(f"{name} FVG {mode} hold {hold} bars", daily, f"trades {len(r)} per-trade {r.mean() * 1e4:+.1f} bps")


SECTIONS = {
    "intraday_mom": section_intraday_mom,
    "orb": section_orb,
    "supertrend": section_supertrend,
    "monday_range": section_monday_range,
    "fvg": section_fvg,
}

if __name__ == "__main__":
    which = sys.argv[1] if len(sys.argv) > 1 else "all"
    for k, fn in SECTIONS.items():
        if which in ("all", k):
            fn()
