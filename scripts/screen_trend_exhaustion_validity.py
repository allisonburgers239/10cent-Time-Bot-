"""Is "bullish daily trend + oversold 4-hour" a 3-5 day reversal edge? Tested on history.

Data: hourly files 2015- (SPY, QQQ, IWM, XLB..XLY) and the 1-year 5-minute stock files,
resampled to 4-hour session bars (09:30-13:30, 13:30-16:00). Daily EMA(200) from daily closes
built from the same files.

Signal bar: 4h close < lower BB(20,2) AND 4h RSI(14) < 30 AND daily close > EMA200 (using the
previous day's EMA so there is no look-ahead). Entry at the next 4h bar's open.
Measured: return after 2, 4, 6 and 10 four-hour bars (1-5 trading days) vs the unconditional
return over the same horizons, t-stats, and the same signal WITHOUT the trend filter, so we can
see whether the trend condition adds anything.
Also a stop-based version: stop at the lowest low of the last 10 bars minus 0.5 ATR, target the
4h SMA20, exit after 10 bars (the swing trade as Temur described it), 1 bp/side.
"""
from __future__ import annotations

import glob
from pathlib import Path

import numpy as np
import pandas as pd

from ten_cent_bot.tv_data import load_tv_csv

ROOT = Path(__file__).resolve().parent.parent
TZ = "America/New_York"


def rsi(x: pd.Series, n: int = 14) -> pd.Series:
    d = x.diff(); up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean(); dn = (-d).clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    return 100 - 100 / (1 + up / dn.replace(0, np.nan))


def tstat(x) -> float:
    x = pd.Series(x).dropna()
    return float(x.mean() / x.std() * np.sqrt(len(x))) if len(x) > 2 and x.std() > 0 else 0.0


def four_hour(path: str) -> pd.DataFrame:
    df = load_tv_csv(path); df.index = df.index.tz_convert(TZ)
    df = df.between_time("09:30", "15:59")
    return df.resample("4h", origin="start_day", offset="9h30min").agg({"open": "first", "high": "max", "low": "min", "close": "last"}).dropna()


def run(path: str) -> dict | None:
    f = four_hour(path)
    if len(f) < 400:
        return None
    daily = f.close.groupby(f.index.date).last()
    ema = daily.ewm(span=200, adjust=False).mean().shift(1)  # yesterday's EMA
    ema_on_bars = pd.Series([ema.get(d, np.nan) for d in f.index.date], index=f.index)
    c = f.close
    sma = c.rolling(20).mean(); sd = c.rolling(20).std(ddof=0); bb_l = sma - 2 * sd
    r = rsi(c)
    tr = pd.concat([f.high - f.low, (f.high - c.shift()).abs(), (f.low - c.shift()).abs()], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1 / 14, adjust=False).mean()
    oversold = (c < bb_l) & (r < 30)
    trend = c > ema_on_bars
    sig = oversold & trend
    sig_nt = oversold & ~trend
    o = f.open.to_numpy(); cl = c.to_numpy(); lo = f.low.to_numpy(); hi = f.high.to_numpy()
    n = len(f)
    out = {"file": Path(path).stem, "bars4h": n, "signals": int(sig.sum()), "signals_no_trend": int(sig_nt.sum())}
    for H in (2, 4, 6, 10):
        fwd = pd.Series([cl[min(i + 1 + H, n - 1)] / o[i + 1] - 1 if i + 1 < n else np.nan for i in range(n)], index=f.index)
        base = fwd.dropna(); s = fwd[sig].dropna(); snt = fwd[sig_nt].dropna()
        if len(s) >= 5:
            out[f"H{H}"] = f"signal {s.mean() * 1e4:+6.0f}bp (n {len(s)}, t {tstat(s):+.1f}, hit {(s > 0).mean():.2f}) | base {base.mean() * 1e4:+5.0f}bp | no-trend {snt.mean() * 1e4:+6.0f}bp (n {len(snt)})"
    # swing trade with stop/target
    trades = []
    idx = np.flatnonzero(sig.to_numpy())
    last_exit = -1
    for i in idx:
        if i + 1 >= n or i <= last_exit:
            continue
        entry = o[i + 1]; stop = lo[max(0, i - 9):i + 1].min() - 0.5 * atr.iloc[i]; target = sma.iloc[i]
        ex = cl[min(i + 10, n - 1)]; exit_i = min(i + 10, n - 1)
        for k in range(i + 1, min(i + 11, n)):
            if lo[k] <= stop:
                ex = stop; exit_i = k; break
            if hi[k] >= target:
                ex = target; exit_i = k; break
        trades.append(ex / entry - 1 - 2e-4); last_exit = exit_i
    if trades:
        tr_ = np.array(trades)
        out["swing_trade"] = f"n {len(tr_)} mean {tr_.mean() * 1e4:+.0f}bp win {(tr_ > 0).mean():.2f} t {tstat(tr_):+.1f} total {tr_.sum() * 100:+.1f}%"
    return out


def main() -> None:
    files = sorted(glob.glob(str(ROOT / "BATS_*, 60.csv"))) + sorted(glob.glob(str(ROOT / "BATS_*, 5.csv")))
    for fpath in files:
        res = run(fpath)
        if not res:
            continue
        print(f"\n{res['file']}: {res['bars4h']} 4h bars, {res['signals']} signals with trend, {res['signals_no_trend']} without")
        for k in ("H2", "H4", "H6", "H10", "swing_trade"):
            if k in res:
                print(f"  {k:12s} {res[k]}")


if __name__ == "__main__":
    main()
