"""Audit: "daily uptrend + oversold 4-hour" as a 3-5 day reversal edge (2026-11-04).

Signal: 4h close < lower BB(20,2) AND 4h RSI(14) < 30 AND yesterday's daily close > daily EMA(200).
Entry at the next 4h bar's open, hold H four-hour bars (H = 2, 4, 6, 10 = 1-5 trading days).

Sections
  1. Pooled result on the 12 hourly ETF files (2015-): signal vs the RIGHT baseline (all bars in
     an uptrend, i.e. close > EMA200), vs a placebo (the same number of random uptrend bars, 200
     draws), with t-stats and hit rates.
  2. Decomposition: RSI<30 only, BB only, both - which part carries it.
  3. By year, pooled across the 12 ETFs (H=10).
  4. Portfolio simulation: every signal taken, equal dollar size, hold 10 bars, 1 bp/side,
     capital split across at most 5 concurrent positions. Sharpe, CAGR on the deployed capital,
     max drawdown, worst trade.
  5. Same rule on the actual target universe: the top-50 mid-cap tech names, 2 years of hourly
     bars from yfinance (the most it serves), pooled.
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
RNG = np.random.default_rng(5)


def rsi(x: pd.Series, n: int = 14) -> pd.Series:
    d = x.diff(); up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean(); dn = (-d).clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    return 100 - 100 / (1 + up / dn.replace(0, np.nan))


def tstat(x) -> float:
    x = pd.Series(x).dropna()
    return float(x.mean() / x.std() * np.sqrt(len(x))) if len(x) > 2 and x.std() > 0 else 0.0


def to4h(df: pd.DataFrame) -> pd.DataFrame:
    df = df.between_time("09:30", "15:59")
    return df.resample("4h", origin="start_day", offset="9h30min").agg({"open": "first", "high": "max", "low": "min", "close": "last"}).dropna()


def features(f: pd.DataFrame) -> pd.DataFrame:
    c = f.close
    daily = c.groupby(f.index.date).last()
    ema = daily.ewm(span=200, adjust=False).mean().shift(1)
    f = f.copy()
    f["ema200"] = [ema.get(d, np.nan) for d in f.index.date]
    sma = c.rolling(20).mean(); sd = c.rolling(20).std(ddof=0)
    f["bb_l"] = sma - 2 * sd; f["rsi"] = rsi(c); f["sma20"] = sma
    f["trend"] = c > f.ema200
    f["bb"] = c < f.bb_l; f["rs"] = f.rsi < 30
    f["sig"] = f.trend & f.bb & f.rs
    o = f.open.to_numpy(); cl = c.to_numpy(); n = len(f)
    for H in (2, 4, 6, 10):
        f[f"fwd{H}"] = [cl[min(i + 1 + H, n - 1)] / o[i + 1] - 1 if i + 1 < n and i + 1 + H < n else np.nan for i in range(n)]
    return f


def pooled(frames: dict[str, pd.DataFrame], label: str) -> None:
    allf = pd.concat([f.assign(sym=k) for k, f in frames.items()])
    allf = allf.dropna(subset=["ema200", "bb_l", "rsi"])
    up = allf[allf.trend]
    sig = allf[allf.sig]
    print(f"\n=== {label}: {len(frames)} instruments, {len(allf)} 4h bars, {len(up)} uptrend bars, {len(sig)} signals ===")
    print(f"  {'H':>3s} {'signal':>22s} {'uptrend base':>14s} {'all base':>10s} {'placebo mean (sd)':>20s} {'excess t':>9s}")
    for H in (2, 4, 6, 10):
        s = sig[f"fwd{H}"].dropna(); b = up[f"fwd{H}"].dropna(); a = allf[f"fwd{H}"].dropna()
        pl = np.array([b.sample(len(s), replace=False, random_state=int(RNG.integers(1e9))).mean() for _ in range(200)])
        t_ex = (s.mean() - b.mean()) / np.sqrt(s.var() / len(s) + b.var() / len(b))
        print(f"  {H:3d} {s.mean() * 1e4:+7.0f}bp hit {(s > 0).mean():.2f} n {len(s):4d} {b.mean() * 1e4:+9.0f}bp {a.mean() * 1e4:+9.0f}bp {pl.mean() * 1e4:+9.0f} ({pl.std() * 1e4:4.0f}) {t_ex:+8.1f}")
    # decomposition at H=10
    print("  decomposition (H=10, uptrend only): " + " | ".join(
        f"{name} {up[m][ 'fwd10'].mean() * 1e4:+.0f}bp n {int(m.sum())}" for name, m in [("RSI<30 only", up.rs & ~up.bb), ("BB only", up.bb & ~up.rs), ("both", up.rs & up.bb)]))
    yrs = sig.groupby(sig.index.year)["fwd10"].agg(["mean", "count"])
    print("  by year (H=10): " + " ".join(f"{y}:{r['mean'] * 1e4:+.0f}bp/n{int(r['count'])}" for y, r in yrs.iterrows()))
    return allf


def portfolio(allf: pd.DataFrame, H: int = 10, max_pos: int = 5, cost: float = 1e-4) -> None:
    sig = allf[allf.sig].sort_index()
    # 4h-bar timeline across all instruments
    timeline = sorted(set(allf.index))
    pos_until: dict[str, pd.Timestamp] = {}
    daily_ret = {}
    open_trades = []  # (sym, entry_time, exit_time, ret)
    trades = []
    idx_pos = {t: i for i, t in enumerate(timeline)}
    for t, row in sig.iterrows():
        open_trades = [x for x in open_trades if x[2] > t]
        if row.sym in [x[0] for x in open_trades] or len(open_trades) >= max_pos:
            continue
        i = idx_pos[t]
        if i + 1 + H >= len(timeline):
            continue
        exit_t = timeline[i + 1 + H]
        r = row[f"fwd{H}"] - 2 * cost
        if np.isnan(r):
            continue
        open_trades.append((row.sym, t, exit_t, r)); trades.append((t, exit_t, row.sym, r))
    tr = pd.DataFrame(trades, columns=["entry", "exit", "sym", "ret"])
    if tr.empty:
        print("  no trades"); return
    # equity: each trade gets 1/max_pos of capital
    eq_days = pd.Series(0.0, index=pd.to_datetime(sorted(set(d.date() for d in timeline))))
    for _, x in tr.iterrows():
        eq_days[pd.Timestamp(x.exit.date())] += x.ret / max_pos
    eq = (1 + eq_days).cumprod()
    yrs = len(eq_days) / 252
    print(f"  portfolio ({max_pos} slots, hold {H} bars, 1bp/side): trades {len(tr)}  win {(tr.ret > 0).mean():.2f}  mean {tr.ret.mean() * 1e4:+.0f}bp  worst {tr.ret.min() * 1e4:+.0f}bp  "
          f"CAGR {eq.iloc[-1] ** (1 / yrs) - 1:.1%}  Sharpe {eq_days.mean() / eq_days.std() * np.sqrt(252):.2f}  MaxDD {(eq / eq.cummax() - 1).min():.1%}  "
          f"avg slots used {tr.groupby(tr.entry.dt.date).size().mean():.1f}")


def main() -> None:
    frames = {}
    for p in sorted(glob.glob(str(ROOT / "BATS_*, 60.csv"))):
        df = load_tv_csv(p); df.index = df.index.tz_convert(TZ)
        frames[Path(p).stem.split(",")[0].replace("BATS_", "")] = features(to4h(df))
    allf = pooled(frames, "ETFs hourly 2015-")
    portfolio(allf)
    if "--no-universe" in sys.argv:
        return
    # mid-cap tech universe, 2y hourly from yfinance
    sys.path.insert(0, str(ROOT / "scripts"))
    from scan_trend_exhaustion import universe
    import yfinance as yf
    uni = universe(50)
    uf = {}
    for tk in uni["name"]:
        try:
            h = yf.Ticker(str(tk)).history(period="730d", interval="1h", prepost=False)
        except Exception:  # noqa: BLE001
            continue
        if h.empty or len(h) < 1500:
            continue
        h.index = h.index.tz_convert(TZ)
        h = h.rename(columns={"Open": "open", "High": "high", "Low": "low", "Close": "close"})
        uf[str(tk)] = features(to4h(h))
    if uf:
        allu = pooled(uf, "mid-cap tech universe, yfinance hourly 2y")
        portfolio(allu)


if __name__ == "__main__":
    main()
