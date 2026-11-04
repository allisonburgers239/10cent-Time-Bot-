"""Scalp / day-trade strategy battery on 5-minute bars (2026-11-04).

Temur's framing: it is a game of percentages - a 30% win rate is fine if the
winners are big enough. So every strategy here reports win rate, average
winner, average loser, payoff ratio and expectancy per trade, with costs, on
every instrument we have 5-minute bars for: ETFs (QQQ/SPY/IWM, 1 year),
single stocks exported from TradingView (TSLA/NVDA/PLTR/AMD/AAPL/COIN/MSTR/
AMZN, ~1 year), micro futures (MNQ/MES/M2K/MGC, ~3.5 months, 23h sessions
restricted to 09:30-16:00 ET here) and crypto perps (BTC/ETH, 1 year).

Fill model: enter at the NEXT bar's open after the signal bar; stops and
targets are checked against each bar's high/low (if both are touched in the
same bar the stop is assumed first); otherwise exit at the close of the last
allowed bar or the day's last bar. Costs per side: ETF 1 bp, stocks 2 bp,
MNQ 0.2 / MES 0.5 / M2K 0.9 / MGC 0.4 bp (1 tick + $0.62), crypto 5 bp.

Strategies (long and short where the rule is symmetric):
  orb5_R        opening-range (first 5-min bar) breakout, stop = other side, target R x risk (R = EOD/2/5/10)
  orb30_R       30-min opening range, breakout close, stop = range mid, target R x risk (EOD/2/4)
  pdhl_break    break of prior day's high/low, stop 0.5 ATR, target 3 ATR, else EOD
  stoprun       new 20-bar low that closes back above the old low (and mirror), stop = that low, target 3R
  rsi2_5m       RSI(2) on 5-min closes <10 long / >90 short, hold 3 bars (10:00-15:30 only)
  ema9_21       EMA 9/21 cross, exit on reverse cross or EOD
  brk20_trail   20-bar high breakout, chandelier trailing stop 2 ATR, EOD exit (mirror for lows)
  climax_fade   bar with range > 3 ATR: fade its direction next bar, hold 3 bars
  first30_cont  direction of the first bar, held to 10:00
  last30_long   buy the 15:30 bar open, sell the close
  mom3 / fade3  three same-colour closes -> continue / fade, hold 1 bar
Plus the unconditional return by time-of-day bucket, and a random-entry placebo.

Usage: python scripts/screen_scalp_strategies.py [instrument substring]
"""
from __future__ import annotations

import glob
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from ten_cent_bot.tv_data import load_tv_csv

ROOT = Path(__file__).resolve().parent.parent
TZ = "America/New_York"
RNG = np.random.default_rng(11)
OPTIMISTIC = "--optimistic" in sys.argv   # target checked before stop when a bar touches both
LONG_ONLY = "--long-only" in sys.argv


def find(pattern: str) -> str | None:
    hits = sorted(glob.glob(str(ROOT / pattern)))
    return hits[0] if hits else None


# (label, file glob, cost bp per side, session-restrict to 09:30-16:00?)
INSTRUMENTS = [
    ("QQQ", "BATS_QQQ, 5.csv", 1.0, True),
    ("SPY", "BATS_SPY, 5.csv", 1.0, True),
    ("IWM", "BATS_IWM, 5.csv", 1.0, True),
    ("TSLA", "*TSLA, 5.csv", 2.0, True),
    ("NVDA", "*NVDA, 5.csv", 2.0, True),
    ("PLTR", "*PLTR, 5.csv", 2.0, True),
    ("AMD", "*AMD, 5.csv", 2.0, True),
    ("AAPL", "*AAPL, 5.csv", 2.0, True),
    ("COIN", "*COIN, 5.csv", 2.0, True),
    ("MSTR", "*MSTR, 5.csv", 2.0, True),
    ("AMZN", "*AMZN, 5.csv", 2.0, True),
    ("MNQ", "CME_MINI_MNQ1!, 5.csv", 0.2, True),
    ("MES", "CME_MINI_MES1!, 5.csv", 0.5, True),
    ("M2K", "CME_MINI_M2K1!, 5.csv", 0.9, True),
    ("MGC", "COMEX_MINI_MGC1!, 5.csv", 0.4, True),
    ("BTC", "BINANCE_BTCUSDT.P, 5.csv", 5.0, False),
    ("ETH", "BINANCE_ETHUSDT.P, 5.csv", 5.0, False),
]


@dataclass
class Trade:
    i: int          # entry bar index (fills at this bar's open)
    side: int       # +1 / -1
    stop: float | None = None
    target: float | None = None
    max_bars: int | None = None
    eod: bool = True


def load(pattern: str, rth: bool) -> pd.DataFrame | None:
    f = find(pattern)
    if f is None:
        return None
    df = load_tv_csv(f)
    df.index = df.index.tz_convert(TZ)
    if rth:
        df = df.between_time("09:30", "15:55")
    df = df[["open", "high", "low", "close"]].copy()
    df["d"] = df.index.date if rth else (df.index.tz_convert("UTC")).date
    df["hm"] = df.index.strftime("%H:%M")
    tr = pd.concat([df.high - df.low, (df.high - df.close.shift()).abs(), (df.low - df.close.shift()).abs()], axis=1).max(axis=1)
    df["atr"] = tr.rolling(20).mean().bfill()
    df["pos"] = np.arange(len(df))
    # last bar index of each day
    last_of_day = df.groupby("d")["pos"].transform("max")
    df["last"] = last_of_day
    return df


def fill(df: pd.DataFrame, t: Trade, cost_bp: float) -> tuple[float, int] | None:
    o, h, l, c = df.open.to_numpy(), df.high.to_numpy(), df.low.to_numpy(), df.close.to_numpy()
    last = int(df["last"].iloc[t.i]) if t.eod else len(df) - 1
    if t.i > last or t.i >= len(df):
        return None
    entry = o[t.i]
    end = last if t.max_bars is None else min(last, t.i + t.max_bars - 1)
    exit_px = c[end]
    exit_i = end
    for k in range(t.i, end + 1):
        hit_stop = t.stop is not None and ((t.side == 1 and l[k] <= t.stop) or (t.side == -1 and h[k] >= t.stop))
        hit_tgt = t.target is not None and ((t.side == 1 and h[k] >= t.target) or (t.side == -1 and l[k] <= t.target))
        if hit_stop and hit_tgt:
            exit_px, exit_i = (t.target if OPTIMISTIC else t.stop), k
            break
        if hit_stop:
            exit_px, exit_i = t.stop, k
            break
        if hit_tgt:
            exit_px, exit_i = t.target, k
            break
    r = t.side * (exit_px / entry - 1) - 2 * cost_bp / 1e4
    return r, exit_i


# ------------------------------------------------------------------ strategies
# each returns a list of Trade


def s_orb5(df: pd.DataFrame, R: float | None) -> list[Trade]:
    out = []
    for d, g in df.groupby("d"):
        if len(g) < 10 or g.hm.iloc[0] != "09:30":
            continue
        b = g.iloc[0]
        side = 1 if b.close > b.open else (-1 if b.close < b.open else 0)
        if side == 0:
            continue
        i = int(g.pos.iloc[1])
        entry = g.open.iloc[1]
        stop = b.low if side == 1 else b.high
        risk = abs(entry - stop)
        if risk <= 0:
            continue
        target = None if R is None else entry + side * R * risk
        out.append(Trade(i, side, stop, target))
    return out


def s_orb30(df: pd.DataFrame, R: float | None) -> list[Trade]:
    out = []
    for d, g in df.groupby("d"):
        if len(g) < 20 or g.hm.iloc[0] != "09:30":
            continue
        orh, orl = g.high.iloc[:6].max(), g.low.iloc[:6].min()
        mid = (orh + orl) / 2
        for k in range(6, len(g) - 1):
            cl = g.close.iloc[k]
            side = 1 if cl > orh else (-1 if cl < orl else 0)
            if side:
                i = int(g.pos.iloc[k + 1]); entry = g.open.iloc[k + 1]
                risk = abs(entry - mid)
                if risk <= 0:
                    break
                out.append(Trade(i, side, mid, None if R is None else entry + side * R * risk))
                break
    return out


def s_pdhl(df: pd.DataFrame) -> list[Trade]:
    out = []
    days = list(df.groupby("d"))
    for (d0, g0), (d1, g1) in zip(days[:-1], days[1:]):
        pdh, pdl = g0.high.max(), g0.low.min()
        done = set()
        for k in range(1, len(g1) - 1):
            cl = g1.close.iloc[k]
            for side, lvl in ((1, pdh), (-1, pdl)):
                if side in done:
                    continue
                if (side == 1 and cl > lvl) or (side == -1 and cl < lvl):
                    i = int(g1.pos.iloc[k + 1]); entry = g1.open.iloc[k + 1]; a = g1.atr.iloc[k]
                    out.append(Trade(i, side, entry - side * 0.5 * a, entry + side * 3 * a))
                    done.add(side)
    return out


def s_stoprun(df: pd.DataFrame) -> list[Trade]:
    out = []
    lo20 = df.low.rolling(20).min().shift(1)
    hi20 = df.high.rolling(20).max().shift(1)
    for k in range(21, len(df) - 1):
        if df["d"].iloc[k] != df["d"].iloc[k + 1]:
            continue
        if df.low.iloc[k] < lo20.iloc[k] and df.close.iloc[k] > lo20.iloc[k]:
            entry = df.open.iloc[k + 1]; stop = df.low.iloc[k]; risk = entry - stop
            if risk > 0:
                out.append(Trade(k + 1, 1, stop, entry + 3 * risk))
        if df.high.iloc[k] > hi20.iloc[k] and df.close.iloc[k] < hi20.iloc[k]:
            entry = df.open.iloc[k + 1]; stop = df.high.iloc[k]; risk = stop - entry
            if risk > 0:
                out.append(Trade(k + 1, -1, stop, entry - 3 * risk))
    return out


def rsi(x: pd.Series, n: int = 2) -> pd.Series:
    d = x.diff()
    up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    dn = (-d).clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    return 100 - 100 / (1 + up / dn.replace(0, np.nan))


def s_rsi2(df: pd.DataFrame) -> list[Trade]:
    out = []
    r = rsi(df.close, 2).to_numpy()
    hm = df.hm.to_numpy()
    for k in range(5, len(df) - 1):
        if not ("10:00" <= hm[k] <= "15:30"):
            continue
        if r[k] < 10:
            out.append(Trade(k + 1, 1, max_bars=3))
        elif r[k] > 90:
            out.append(Trade(k + 1, -1, max_bars=3))
    return out


def s_ema(df: pd.DataFrame) -> list[Trade]:
    out = []
    e9 = df.close.ewm(span=9, adjust=False).mean().to_numpy()
    e21 = df.close.ewm(span=21, adjust=False).mean().to_numpy()
    d = df["d"].to_numpy()
    k = 22
    while k < len(df) - 1:
        up = e9[k] > e21[k] and e9[k - 1] <= e21[k - 1]
        dn = e9[k] < e21[k] and e9[k - 1] >= e21[k - 1]
        if (up or dn) and d[k] == d[k + 1]:
            side = 1 if up else -1
            # hold until reverse cross or EOD
            m = k + 1
            while m < len(df) - 1 and d[m + 1] == d[k] and not ((side == 1 and e9[m] < e21[m]) or (side == -1 and e9[m] > e21[m])):
                m += 1
            out.append(Trade(k + 1, side, max_bars=max(1, m - k)))
            k = m
        k += 1
    return out


def s_brk20_trail(df: pd.DataFrame) -> list[Trade]:
    out = []
    hi20 = df.high.rolling(20).max().shift(1).to_numpy()
    lo20 = df.low.rolling(20).min().shift(1).to_numpy()
    c, h, l, a, d = df.close.to_numpy(), df.high.to_numpy(), df.low.to_numpy(), df.atr.to_numpy(), df["d"].to_numpy()
    k = 21
    while k < len(df) - 1:
        side = 1 if c[k] > hi20[k] else (-1 if c[k] < lo20[k] else 0)
        if side and d[k] == d[k + 1]:
            # simulate chandelier trailing stop manually: walk bars
            m = k + 1; best = h[m] if side == 1 else l[m]; last = int(df["last"].iloc[m]); exit_m = last
            trail = best - side * 2 * a[k]
            for j in range(m, last + 1):
                if (side == 1 and l[j] <= trail) or (side == -1 and h[j] >= trail):
                    exit_m = j
                    break
                best = max(best, h[j]) if side == 1 else min(best, l[j])
                trail = best - side * 2 * a[k]
            out.append(Trade(m, side, stop=None, max_bars=exit_m - m + 1))
            k = exit_m
        k += 1
    return out


def s_climax_fade(df: pd.DataFrame) -> list[Trade]:
    out = []
    rng = (df.high - df.low).to_numpy(); a = df.atr.shift(1).to_numpy(); o, c = df.open.to_numpy(), df.close.to_numpy(); d = df["d"].to_numpy()
    for k in range(21, len(df) - 1):
        if rng[k] > 3 * a[k] and d[k] == d[k + 1]:
            out.append(Trade(k + 1, 1 if c[k] < o[k] else -1, max_bars=3))
    return out


def s_first30(df: pd.DataFrame) -> list[Trade]:
    out = []
    for d, g in df.groupby("d"):
        if len(g) < 8 or g.hm.iloc[0] != "09:30":
            continue
        b = g.iloc[0]; side = 1 if b.close > b.open else (-1 if b.close < b.open else 0)
        if side:
            out.append(Trade(int(g.pos.iloc[1]), side, max_bars=5))
    return out


def s_last30(df: pd.DataFrame) -> list[Trade]:
    out = []
    for d, g in df.groupby("d"):
        m = g[g.hm == "15:30"]
        if len(m):
            out.append(Trade(int(m.pos.iloc[0]), 1))
    return out


def s_mom3(df: pd.DataFrame, fade: bool) -> list[Trade]:
    out = []
    up = (df.close > df.open).to_numpy(); dn = (df.close < df.open).to_numpy(); d = df["d"].to_numpy()
    for k in range(2, len(df) - 1):
        if d[k] != d[k + 1]:
            continue
        if up[k] and up[k - 1] and up[k - 2]:
            out.append(Trade(k + 1, -1 if fade else 1, max_bars=1))
        elif dn[k] and dn[k - 1] and dn[k - 2]:
            out.append(Trade(k + 1, 1 if fade else -1, max_bars=1))
    return out


def s_placebo(df: pd.DataFrame, n: int = 400) -> list[Trade]:
    idx = RNG.choice(np.arange(1, len(df) - 5), size=min(n, len(df) - 6), replace=False)
    return [Trade(int(i), int(RNG.choice([1, -1])), max_bars=3) for i in sorted(idx)]


STRATS = {
    "orb5_EOD": lambda df: s_orb5(df, None), "orb5_2R": lambda df: s_orb5(df, 2), "orb5_5R": lambda df: s_orb5(df, 5), "orb5_10R": lambda df: s_orb5(df, 10),
    "orb30_EOD": lambda df: s_orb30(df, None), "orb30_2R": lambda df: s_orb30(df, 2), "orb30_4R": lambda df: s_orb30(df, 4),
    "pdhl_break": s_pdhl, "stoprun_3R": s_stoprun, "rsi2_5m": s_rsi2, "ema9_21": s_ema, "brk20_trail": s_brk20_trail,
    "climax_fade": s_climax_fade, "first30_cont": s_first30, "last30_long": s_last30,
    "mom3": lambda df: s_mom3(df, False), "fade3": lambda df: s_mom3(df, True), "placebo_rand": s_placebo,
}


def evaluate(df: pd.DataFrame, trades: list[Trade], cost_bp: float) -> dict | None:
    rows = []
    for t in trades:
        if LONG_ONLY and t.side != 1:
            continue
        f = fill(df, t, cost_bp)
        if f is None:
            continue
        r, ei = f
        rows.append((df.index[t.i], df["d"].iloc[t.i], r))
    if len(rows) < 8:
        return None
    tr = pd.DataFrame(rows, columns=["t", "d", "r"])
    daily = tr.groupby("d").r.sum()
    wins = tr.r[tr.r > 0]; losses = tr.r[tr.r <= 0]
    eq = (1 + daily).cumprod()
    n_days = len(df.groupby("d"))
    sharpe = float(daily.mean() / daily.std() * np.sqrt(252)) if daily.std() > 0 else 0.0
    # scale daily series to the full calendar (days without trades = 0)
    full = daily.reindex(sorted(set(df["d"])), fill_value=0.0)
    sharpe_full = float(full.mean() / full.std() * np.sqrt(252)) if full.std() > 0 else 0.0
    return {
        "n": len(tr), "win": float((tr.r > 0).mean()), "avg_win": float(wins.mean() * 1e4) if len(wins) else 0.0,
        "avg_loss": float(losses.mean() * 1e4) if len(losses) else 0.0,
        "payoff": float(wins.mean() / -losses.mean()) if len(wins) and len(losses) and losses.mean() < 0 else float("nan"),
        "exp_bp": float(tr.r.mean() * 1e4), "t": float(tr.r.mean() / tr.r.std() * np.sqrt(len(tr))) if tr.r.std() > 0 else 0.0,
        "total": float(eq.iloc[-1] - 1), "sharpe": sharpe_full, "maxdd": float((eq / eq.cummax() - 1).min()),
        "worst_m": float(tr.groupby(pd.to_datetime(tr.t).dt.tz_localize(None).dt.to_period("M")).r.sum().min()),
        "days": n_days,
    }


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    only = args[0] if args else None
    print(f"fill model: {'OPTIMISTIC (target first)' if OPTIMISTIC else 'conservative (stop first)'}; {'LONG ONLY' if LONG_ONLY else 'long+short'}")
    all_rows = []
    for label, pat, cost, rth in INSTRUMENTS:
        if only and only.lower() not in label.lower():
            continue
        df = load(pat, rth)
        if df is None:
            print(f"\n=== {label}: no file for {pat}")
            continue
        print(f"\n=== {label}: {len(df)} bars, {df.index[0].date()} -> {df.index[-1].date()}, {df['d'].nunique()} sessions, cost {cost} bp/side ===")
        # time-of-day drift
        r5 = df.close.pct_change()
        hm = df.hm
        buckets = [("09:30-10:00", "09:30", "09:55"), ("10:00-11:00", "10:00", "10:55"), ("11:00-14:00", "11:00", "13:55"), ("14:00-15:30", "14:00", "15:25"), ("15:30-16:00", "15:30", "15:55")]
        tod = []
        for name, a, b in buckets:
            m = (hm >= a) & (hm <= b)
            x = r5[m].dropna()
            if len(x):
                tod.append(f"{name} {x.mean() * 1e4:+.2f}bp/bar t{x.mean() / x.std() * np.sqrt(len(x)):+.1f}")
        print("  time-of-day (per 5-min bar): " + " | ".join(tod))
        print(f"  {'strategy':14s} {'n':>5s} {'win%':>5s} {'avgW':>7s} {'avgL':>7s} {'payoff':>6s} {'exp/trade':>9s} {'t':>5s} {'total':>7s} {'Sharpe':>6s} {'maxDD':>6s} {'worst mo':>8s}")
        for name, fn in STRATS.items():
            try:
                res = evaluate(df, fn(df), cost)
            except Exception as e:  # noqa: BLE001
                print(f"  {name:14s} error {e}")
                continue
            if res is None:
                print(f"  {name:14s} (fewer than 8 trades)")
                continue
            print(f"  {name:14s} {res['n']:5d} {res['win'] * 100:5.1f} {res['avg_win']:+7.1f} {res['avg_loss']:+7.1f} {res['payoff']:6.2f} {res['exp_bp']:+8.1f}bp {res['t']:+5.1f} {res['total'] * 100:+6.1f}% {res['sharpe']:+6.2f} {res['maxdd'] * 100:6.1f}% {res['worst_m'] * 100:+7.1f}%")
            all_rows.append((label, name, res))
    print("\n=== Top cells by t-stat of expectancy (needs n >= 40 and positive Sharpe) ===")
    top = sorted([r for r in all_rows if r[2]["n"] >= 40 and r[2]["sharpe"] > 0], key=lambda r: -r[2]["t"])[:15]
    for label, name, res in top:
        print(f"  {label:5s} {name:14s} n {res['n']:5d} win {res['win'] * 100:4.1f}% payoff {res['payoff']:4.2f} exp {res['exp_bp']:+6.1f}bp t {res['t']:+4.1f} Sharpe {res['sharpe']:+5.2f} total {res['total'] * 100:+6.1f}% maxDD {res['maxdd'] * 100:5.1f}%")


if __name__ == "__main__":
    main()
