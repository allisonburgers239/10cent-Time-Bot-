"""Temur's "3 hit" trendline method, made precise and tested.

Rule as described: two swing points (hits) define a trendline; the third time
price comes back to that line we expect a reaction (a bounce). Said to work on
15-min bars and better on higher timeframes (30m, 1h, 2h, 3h, 6h).

Precise version used here:
  swing low  at bar i  = low[i] is the lowest low of bars i-k .. i+k   (k = pivot strength)
  swing high at bar i  = high[i] is the highest high of i-k .. i+k
  support line  = two consecutive swing lows  (P1, P2), any slope
  resistance    = two consecutive swing highs (P1, P2), any slope
  the line is known only k bars after P2 (that is when P2 is confirmed)
  third hit     = first bar j after that where the bar reaches the line:
                    support:    low[j]  <= line(j) + tol  and  close[j] >= line(j) - tol
                    resistance: high[j] >= line(j) - tol  and  close[j] <= line(j) + tol
                  tol = tolAtr * ATR(14).  A bar that closes through the line by more
                  than tol is a BREAK, not a hit (counted separately).
  trade         = buy the close of the hit bar at support / sell at resistance,
                  exit after H bars (H = 1, 4, 8, 16) or when the line breaks by tol.
  fourth hit    = same, for lines that have already held three times.

What counts as "it works": the mean forward return after a third hit (long at
support, short at resistance) beats (a) the unconditional forward return and
(b) a placebo where the line is shifted by a random amount so the touch is at a
meaningless level. Costs: 1 bp per side.

Data: the TradingView exports in the repo root. 5-min files are resampled to
15-min; 60-min files to 2h/3h/6h (bars aligned to the session).

Usage: python scripts/screen_three_hit_trendline.py [k] [tolAtr]
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

from ten_cent_bot.tv_data import load_tv_csv

ROOT = Path(__file__).resolve().parent.parent
TZ = "America/New_York"
COST_SIDE = 1e-4
RNG = np.random.default_rng(7)

SOURCES = [
    # (label, file, resample rule or None)
    ("QQQ 15m (1y)", "BATS_QQQ, 5.csv", "15min"),
    ("SPY 15m (1y)", "BATS_SPY, 5.csv", "15min"),
    ("SPY 30m (2020-)", "BATS_SPY, 30.csv", None),
    ("ES RTH 30m (2021-)", "CME_MINI_ES1!, 30 RTH.csv", None),
    ("SPY 1h (2015-)", "BATS_SPY, 60.csv", None),
    ("QQQ 1h (2015-)", "BATS_QQQ, 60.csv", None),
    ("IWM 1h (2015-)", "BATS_IWM, 60.csv", None),
    ("ES 1h 23h (2023-)", "CME_MINI_ES1!, 60.csv", None),
    ("NQ 1h 23h (2023-)", "CME_MINI_NQ1!, 60.csv", None),
    ("QQQ 2h (2015-)", "BATS_QQQ, 60.csv", "2h"),
    ("QQQ 3h (2015-)", "BATS_QQQ, 60.csv", "3h"),
    ("SPY 2h (2015-)", "BATS_SPY, 60.csv", "2h"),
    ("NQ 3h 23h (2023-)", "CME_MINI_NQ1!, 60.csv", "3h"),
    ("NQ 6h 23h (2023-)", "CME_MINI_NQ1!, 60.csv", "6h"),
    ("SPY 1D (1993-)", None, "D"),
    ("QQQ 1D (1999-)", None, "D"),
]


def load(file: str | None, rule: str | None, label: str) -> pd.DataFrame:
    if file is None:
        import yfinance as yf

        tk = label.split()[0]
        raw = yf.download(tk, period="max", interval="1d", auto_adjust=True, progress=False)
        raw.columns = [c[0].lower() if isinstance(c, tuple) else c.lower() for c in raw.columns]
        return raw[["open", "high", "low", "close"]].dropna()
    df = load_tv_csv(ROOT / file)
    df.index = df.index.tz_convert(TZ)
    if rule:
        df = df.resample(rule, origin="start_day", offset="9h30min" if "RTH" in file or "BATS" in file else "0min").agg(
            {"open": "first", "high": "max", "low": "min", "close": "last"}
        ).dropna()
    return df[["open", "high", "low", "close"]]


def atr(df: pd.DataFrame, n: int = 14) -> np.ndarray:
    tr = pd.concat([df.high - df.low, (df.high - df.close.shift()).abs(), (df.low - df.close.shift()).abs()], axis=1).max(axis=1)
    return tr.rolling(n).mean().bfill().to_numpy()


def pivots(x: np.ndarray, k: int, kind: str) -> np.ndarray:
    n = len(x)
    out = []
    for i in range(k, n - k):
        w = x[i - k : i + k + 1]
        if kind == "low" and x[i] == w.min() and (w == x[i]).sum() == 1:
            out.append(i)
        if kind == "high" and x[i] == w.max() and (w == x[i]).sum() == 1:
            out.append(i)
    return np.array(out)


def events(df: pd.DataFrame, k: int, tol_atr: float, side: str, shift_sd: float = 0.0, min_hits: int = 2):
    """Return list of (hit_index, line_value, line_slope_per_bar, prior_hits) for third (or later) hits."""
    hi, lo, cl = df.high.to_numpy(), df.low.to_numpy(), df.close.to_numpy()
    a = atr(df)
    piv = pivots(lo if side == "support" else hi, k, "low" if side == "support" else "high")
    px = lo if side == "support" else hi
    n = len(df)
    out = []
    for a_i, b_i in zip(piv[:-1], piv[1:]):
        y1, y2 = px[a_i], px[b_i]
        slope = (y2 - y1) / (b_i - a_i)
        shift = RNG.normal(0, shift_sd) * a[b_i] if shift_sd > 0 else 0.0
        start = b_i + k + 1  # line known once P2 is confirmed
        hits = 2
        j = start
        last_end = min(n - 1, b_i + 60 * max(1, (b_i - a_i) // 10))  # follow the line for a bounded horizon
        while j <= min(n - 2, b_i + 10 * (b_i - a_i) + 50):
            line = y1 + slope * (j - a_i) + shift
            tol = tol_atr * a[j]
            if side == "support":
                broke = cl[j] < line - tol
                touched = lo[j] <= line + tol and cl[j] >= line - tol
            else:
                broke = cl[j] > line + tol
                touched = hi[j] >= line - tol and cl[j] <= line + tol
            if broke:
                out.append((j, line, slope, hits, "break"))
                break
            if touched:
                hits += 1
                out.append((j, line, slope, hits, "hit"))
                j += k  # don't count the same visit twice
                continue
            j += 1
    return out


def forward(df: pd.DataFrame, j: int, h: int, side: str, line: float, slope: float, tol: float) -> float:
    """Return of a trade entered at close[j], exited at close[j+h] or when the line breaks by tol."""
    cl = df.close.to_numpy()
    n = len(cl)
    end = min(j + h, n - 1)
    sgn = 1 if side == "support" else -1
    for m in range(j + 1, end + 1):
        ln = line + slope * (m - j)
        if (side == "support" and cl[m] < ln - tol) or (side == "resistance" and cl[m] > ln + tol):
            return sgn * (cl[m] / cl[j] - 1) - 2 * COST_SIDE
    return sgn * (cl[end] / cl[j] - 1) - 2 * COST_SIDE


def tstat(x: np.ndarray) -> float:
    return float(x.mean() / x.std() * np.sqrt(len(x))) if len(x) > 2 and x.std() > 0 else 0.0


def run(label: str, df: pd.DataFrame, k: int, tol_atr: float) -> None:
    a = atr(df)
    cl = df.close.to_numpy()
    n = len(df)
    ppy = {"15m": 26 * 252, "30m": 13 * 252, "1h": 7 * 252, "2h": 4 * 252, "3h": 3 * 252, "6h": 2 * 252, "1D": 252}
    tfk = next((kk for kk in ppy if f" {kk} " in label + " "), "1h")
    print(f"\n--- {label}: {n} bars, {df.index[0]} -> {df.index[-1]}  (pivot k={k}, tol={tol_atr} ATR) ---")
    print(f"  {'event':34s} {'n':>5s}  " + "  ".join(f"{'H='+str(h):>14s}" for h in (1, 4, 8, 16)))
    base = {h: np.array([cl[min(j + h, n - 1)] / cl[j] - 1 for j in range(0, n - 1)]) for h in (1, 4, 8, 16)}
    print(f"  {'any bar, long (baseline)':34s} {n - 1:>5d}  " + "  ".join(f"{base[h].mean() * 1e4:+6.1f}bp t{tstat(base[h]):+4.1f}" for h in (1, 4, 8, 16)))
    for side in ("support", "resistance"):
        for shift_sd, name in ((0.0, "real line"), (1.5, "placebo (line shifted)")):
            ev = events(df, k, tol_atr, side, shift_sd)
            third = [e for e in ev if e[4] == "hit" and e[3] == 3]
            fourth = [e for e in ev if e[4] == "hit" and e[3] >= 4]
            breaks = [e for e in ev if e[4] == "break" and e[3] == 2]
            for grp, gname in ((third, "3rd hit"), (fourth, "4th+ hit")):
                if len(grp) < 5:
                    continue
                cells = []
                for h in (1, 4, 8, 16):
                    r = np.array([forward(df, j, h, side, line, slope, tol_atr * a[j]) for j, line, slope, _, _ in grp])
                    cells.append(f"{r.mean() * 1e4:+6.1f}bp t{tstat(r):+4.1f}")
                print(f"  {side + ' ' + gname + ', ' + name:34s} {len(grp):>5d}  " + "  ".join(cells))
            if shift_sd == 0.0 and len(breaks) >= 5:
                # breakout version: trade WITH the break (sell a broken support, buy a broken resistance)
                cells = []
                for h in (1, 4, 8, 16):
                    sgn = -1 if side == "support" else 1
                    r = np.array([sgn * (cl[min(j + h, n - 1)] / cl[j] - 1) - 2 * COST_SIDE for j, *_ in breaks])
                    cells.append(f"{r.mean() * 1e4:+6.1f}bp t{tstat(r):+4.1f}")
                print(f"  {side + ' broken before 3rd hit, go with it':34s} {len(breaks):>5d}  " + "  ".join(cells))
        # how often does the third hit hold at all?
        ev = events(df, k, tol_atr, side, 0.0)
        reached = sum(1 for e in ev if e[3] == 3 and e[4] == "hit")
        broke_first = sum(1 for e in ev if e[3] == 2 and e[4] == "break")
        if reached + broke_first > 0:
            print(f"  {side}: lines that got a 3rd hit {reached}, lines broken before any 3rd hit {broke_first}  -> 3rd hit happens {reached / (reached + broke_first):.0%} of the time")


def main() -> None:
    k = int(sys.argv[1]) if len(sys.argv) > 1 else 5
    tol = float(sys.argv[2]) if len(sys.argv) > 2 else 0.25
    for label, file, rule in SOURCES:
        try:
            df = load(file, rule, label)
        except Exception as e:  # noqa: BLE001
            print(f"\n--- {label}: skipped ({e})")
            continue
        run(label, df, k, tol)


if __name__ == "__main__":
    main()
