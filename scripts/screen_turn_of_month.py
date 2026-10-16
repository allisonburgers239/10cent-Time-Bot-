"""Screen: turn-of-the-month (TOM) and pre-month-end dip, stocks and bonds.

Windows are FIXED from the literature before looking at the data:
  TOM = {-1, +1, +2, +3}   last trading day + first three   (McConnell & Xu 2008)
  DIP = {-8 .. -4}         pre-month-end institutional selling (Etula et al. 2020, JF)

Series:
  SPY   close->close and overnight-only (1993+, yfinance)
  ^GSPC close->close (1950+, yfinance; opens are fake so no overnight split)
  ZB    30y T-bond futures, close->close (TradingView export 1977+ if present,
        else ZN=F / ZB=F from yfinance 2000+)

For each: mean return by trading-day-of-month index with t-stats, TOM vs
rest, DIP vs rest, by decade, and a placebo that draws random 4-day
windows with the same count.  Then the Sleeve E overlay test: E's
overnight position x multiplier in TOM/DIP, vs plain E, on SPY/QQQ/IWM.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

from ten_cent_bot.metrics import max_drawdown, sharpe

ROOT = Path(__file__).resolve().parents[1]
TOM = {-1, 1, 2, 3}
DIP = {-8, -7, -6, -5, -4}


def tdom_index(idx: pd.DatetimeIndex) -> pd.Series:
    """Signed trading-day-of-month: +1 = first trading day, -1 = last."""
    s = pd.Series(idx, index=idx)
    ym = s.dt.to_period("M")
    pos = s.groupby(ym).cumcount() + 1
    cnt = s.groupby(ym).transform("count")
    neg = pos - cnt - 1
    return pd.Series(np.where(pos <= 10, pos, neg), index=idx)


def load_tv_daily(name: str) -> pd.Series | None:
    p = ROOT / name
    if not p.exists():
        return None
    df = pd.read_csv(p)
    df["time"] = pd.to_datetime(df["time"], unit="s", utc=True).dt.tz_convert(None).dt.normalize()
    return df.set_index("time")["close"].astype(float)


def yf_ohlc(sym: str) -> pd.DataFrame:
    d = yf.download(sym, period="max", interval="1d", auto_adjust=True, progress=False)
    return pd.DataFrame({"open": d["Open"].squeeze(), "close": d["Close"].squeeze()}).dropna()


def analyse(name: str, r: pd.Series, n_placebo: int = 500) -> None:
    r = r.dropna()
    d = tdom_index(r.index)
    print(f"\n--- {name}: {r.index.min().date()} -> {r.index.max().date()}, {len(r)} days, uncond mean {r.mean()*1e4:+.1f}bp/day")
    print("  day   mean(bp)   t     n")
    for k in [-10, -9, -8, -7, -6, -5, -4, -3, -2, -1, 1, 2, 3, 4, 5]:
        x = r[d == k]
        t = x.mean() / (x.std(ddof=1) / np.sqrt(len(x)))
        flag = "  <TOM" if k in TOM else "  <DIP" if k in DIP else ""
        print(f"  {k:>3}  {x.mean()*1e4:+8.1f}  {t:+5.2f}  {len(x):>5}{flag}")
    tom = r[d.isin(TOM)]; dip = r[d.isin(DIP)]; rest = r[~d.isin(TOM | DIP)]
    def tt(a, b):
        return (a.mean() - b.mean()) / np.sqrt(a.var(ddof=1) / len(a) + b.var(ddof=1) / len(b))
    print(f"  TOM  mean {tom.mean()*1e4:+.1f}bp vs rest {rest.mean()*1e4:+.1f}bp  diff t={tt(tom, rest):+.2f}   share of total return in TOM: {tom.sum()/r.sum():.0%} of days: {len(tom)/len(r):.0%}")
    print(f"  DIP  mean {dip.mean()*1e4:+.1f}bp vs rest {rest.mean()*1e4:+.1f}bp  diff t={tt(dip, rest):+.2f}")
    print("  by decade (TOM mean bp / DIP mean bp / rest mean bp):")
    for dec in sorted(set(r.index.year // 10 * 10)):
        m = (r.index.year // 10 * 10) == dec
        rr, dd = r[m], d[m]
        if m.sum() < 500:
            continue
        print(f"    {dec}s  {rr[dd.isin(TOM)].mean()*1e4:+6.1f} / {rr[dd.isin(DIP)].mean()*1e4:+6.1f} / {rr[~dd.isin(TOM|DIP)].mean()*1e4:+6.1f}   (n={m.sum()})")
    # placebo: random contiguous 4-day windows each month
    rng = np.random.default_rng(11)
    real = tom.mean() - rest.mean()
    months = r.groupby(r.index.to_period("M"))
    arr = []
    for _ in range(n_placebo):
        picks = []
        for _, g in months:
            if len(g) < 8:
                continue
            s = rng.integers(0, len(g) - 3)
            picks.append(g.iloc[s : s + 4])
        w = pd.concat(picks)
        arr.append(w.mean() - r.drop(w.index).mean())
    arr = np.array(arr)
    p = float((arr >= real).mean())
    print(f"  placebo (random 4-day window/month, {n_placebo}x): real diff {real*1e4:+.1f}bp, placebo {arr.mean()*1e4:+.1f} +/- {arr.std()*1e4:.1f}bp, P(rand >= real) = {p:.3f}  {'REAL' if p < 0.05 else 'WEAK' if p < 0.2 else 'NONE'}")


def overlay_test() -> None:
    print("\n=== Sleeve E overlay: overnight SPY/QQQ/IWM x calendar multiplier (1bp/side cost) ===")
    data = {s: yf_ohlc(s) for s in ["SPY", "QQQ", "IWM"]}
    variants = {
        "E baseline (x1 every night)": lambda k: 1.0,
        "A: x2 in TOM": lambda k: 2.0 if k in TOM else 1.0,
        "B: x2 in TOM, x0.5 in DIP": lambda k: 2.0 if k in TOM else 0.5 if k in DIP else 1.0,
        "C: x1.5 in TOM, x0 in DIP": lambda k: 1.5 if k in TOM else 0.0 if k in DIP else 1.0,
        "D: TOM only (x1 in TOM, flat else)": lambda k: 1.0 if k in TOM else 0.0,
    }
    for label, f in variants.items():
        rets = []
        for s, df in data.items():
            on = (df["open"].shift(-1) - df["close"]) / df["close"]
            d = tdom_index(df.index)
            mult = d.map(f).astype(float)
            net = mult * on - mult.abs() * 2 / 10_000
            rets.append(net)
        port = pd.concat(rets, axis=1).mean(axis=1).dropna()
        eq = (1 + port).cumprod()
        print(f"  {label:<38} Sharpe {sharpe(port, 252):5.2f}  CAGR {((1+port.mean())**252-1):6.2%}  MaxDD {max_drawdown(eq):7.1%}  avg gross {pd.concat([d.map(f) for d in [tdom_index(data['SPY'].index)]],axis=1).mean().mean():.2f}x")


def main() -> None:
    print("=== TURN-OF-MONTH / PRE-MONTH-END DIP SCREEN ===")
    spy = yf_ohlc("SPY")
    analyse("SPY close->close", spy["close"].pct_change())
    analyse("SPY overnight only (close->next open)", ((spy["open"].shift(-1) - spy["close"]) / spy["close"]))
    analyse("SPY intraday only (open->close)", spy["close"] / spy["open"] - 1)
    gspc = yf_ohlc("^GSPC")
    analyse("S&P 500 index close->close (1950+)", gspc["close"].pct_change().loc["1950":])
    zb = load_tv_daily("CBOT_ZB1!, 1D.csv")
    if zb is not None:
        analyse("ZB 30y T-bond futures close->close (TradingView 1!, 1977+)", zb.pct_change())
    zn = yf_ohlc("ZN=F")
    analyse("ZN 10y T-note futures close->close (yfinance, 2000+)", zn["close"].pct_change())
    overlay_test()


if __name__ == "__main__":
    main()
