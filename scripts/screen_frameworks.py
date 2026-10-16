"""Screens for three 'AI edge' frameworks, each reduced to a pre-registered,
daily-data, placebo-tested rule.  (The VWAP/liquidity-grab framework needs
years of intraday data we do not have; its closest cousin, the PDH/PDL sweep
test in audit_chronomatrix.py, was already dead.  The 'continuous screener'
framework is a live scan with no backtest and is excluded by design.)

F1  Multi-timeframe divergence, daily analogue: macro trend up (close >
    200d SMA) AND micro oversold (RSI(2) < 10) -> next-day / next-overnight.
    Compared with the unconditioned reversal (E v2's signal) to see whether
    the trend filter ADDS anything.
F2  Laggard catch-up: on days the group index (SPY) rises > 1%, the sector
    ETFs that lagged most (bottom 3 of 9 by that day's return) -> next-day
    return relative to the leaders.  Lo-MacKinlay (1990) lead-lag.
F4  Correlation breakdown pairs: rolling 60d beta of Y on X; residual
    z-score > 2 -> short Y / long X (and vice versa), 5-day horizon.
    Pairs fixed in advance: QQQ~SPY, IWM~SPY, GLD~TIP, XLE~USO, EFA~SPY,
    BTC-USD~QQQ, TLT~IEF, XLF~SPY.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import yfinance as yf


def rsi(c: pd.Series, n: int = 2) -> pd.Series:
    d = c.diff()
    up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    return 100 - 100 / (1 + up / dn.replace(0, np.nan))


def tstat(x: pd.Series, base: float = 0.0) -> float:
    x = x.dropna()
    return float((x.mean() - base) / (x.std(ddof=1) / np.sqrt(len(x)))) if len(x) > 10 else np.nan


def placebo_p(y: np.ndarray, m: np.ndarray, real: float, rng, n=400) -> float:
    k = int(m.sum())
    pl = np.array([y[rng.choice(len(y), k, replace=False)].mean() for _ in range(n)])
    return float((pl >= real).mean())


def f1(rng) -> None:
    print("=== F1. Trend-conditioned oversold: close > 200d SMA AND RSI(2) < 10 ===")
    data = yf.download(["SPY", "QQQ", "IWM", "EFA", "TLT", "GLD"], period="max", interval="1d", auto_adjust=True, progress=False)
    print(f"  {'tkr':<4} {'cond':<28} {'n':>5} {'next-day excess':>16} {'t':>6} {'p':>6}   {'next-ON excess':>15} {'t':>6}")
    for t in ["SPY", "QQQ", "IWM", "EFA", "TLT", "GLD"]:
        df = pd.DataFrame({"open": data["Open"][t], "close": data["Close"][t]}).dropna()
        nxt = df["close"].shift(-1) / df["close"] - 1
        on = df["open"].shift(-1) / df["close"] - 1
        os_ = rsi(df["close"]) < 10
        up = df["close"] > df["close"].rolling(200).mean()
        for label, m in [("RSI2<10 (any trend)", os_), ("RSI2<10 AND above 200d", os_ & up), ("RSI2<10 AND below 200d", os_ & ~up)]:
            j = pd.concat([m.rename("m"), nxt.rename("y"), on.rename("o")], axis=1).dropna()
            y = j.y.values; o = j.o.values; mm = j.m.values.astype(bool)
            if mm.sum() < 30:
                continue
            ex = y[mm].mean() - y.mean(); exo = o[mm].mean() - o.mean()
            p = placebo_p(y - y.mean(), mm, ex, rng)
            print(f"  {t:<4} {label:<28} {mm.sum():>5} {ex*1e4:>15.1f}bp {tstat(pd.Series(y[mm]), y.mean()):>6.2f} {p:>6.3f}   {exo*1e4:>14.1f}bp {tstat(pd.Series(o[mm]), o.mean()):>6.2f}")
    print("  Reading: if 'above 200d' is not clearly better than 'any trend', the macro filter adds nothing to E v2.")


def f2(rng) -> None:
    print("\n=== F2. Laggard catch-up in a correlated basket (9 sector ETFs vs SPY, 1999-2026) ===")
    secs = ["XLB", "XLE", "XLF", "XLI", "XLK", "XLP", "XLU", "XLV", "XLY"]
    px = yf.download(secs + ["SPY"], period="max", interval="1d", auto_adjust=True, progress=False)["Close"].dropna()
    r = px.pct_change().dropna()
    spy = r["SPY"]; sec = r[secs]
    rel = sec.sub(spy, axis=0)                       # same-day relative return
    nxt_rel = rel.shift(-1)                          # next-day relative return
    for thr in [0.01, 0.015, 0.02]:
        days = spy > thr
        rows = []
        for d in r.index[days]:
            rk = rel.loc[d].rank()
            lag = rk <= 3; lead = rk >= 7
            rows.append((nxt_rel.loc[d][lag].mean(), nxt_rel.loc[d][lead].mean()))
        a = pd.DataFrame(rows, columns=["laggards", "leaders"]).dropna()
        spread = a.laggards - a.leaders
        # placebo: random days, same count
        pl = []
        for _ in range(300):
            idx = r.index[rng.choice(len(r) - 1, len(a), replace=False)]
            s = []
            for d in idx:
                rk = rel.loc[d].rank(); s.append(nxt_rel.loc[d][rk <= 3].mean() - nxt_rel.loc[d][rk >= 7].mean())
            pl.append(np.nanmean(s))
        pl = np.array(pl)
        print(f"  SPY up > {thr:.1%} days: n={len(a)}  next-day laggards-minus-leaders {spread.mean()*1e4:+.1f}bp (t={tstat(spread):+.2f})  halves {spread.iloc[:len(a)//2].mean()*1e4:+.1f}/{spread.iloc[len(a)//2:].mean()*1e4:+.1f}  placebo(any day) {pl.mean()*1e4:+.1f}+/-{pl.std()*1e4:.1f}  p={float((pl>=spread.mean()).mean()):.3f}")
    print("  Reading: a positive spread on big-up days that random days do not show = catch-up; a positive spread on ANY day = plain daily reversal, already known.")


def f4(rng) -> None:
    print("\n=== F4. Correlation-breakdown pairs: residual z > 2 -> fade, 5-day horizon, 60d rolling beta ===")
    pairs = [("QQQ", "SPY"), ("IWM", "SPY"), ("EFA", "SPY"), ("XLF", "SPY"), ("GLD", "TIP"), ("XLE", "USO"), ("TLT", "IEF"), ("BTC-USD", "QQQ")]
    syms = sorted({s for p in pairs for s in p})
    px = yf.download(syms, period="max", interval="1d", auto_adjust=True, progress=False)["Close"]
    r = px.pct_change()
    print(f"  {'pair':<14} {'n sig':>6} {'5d spread ret':>14} {'t':>6} {'halves':>14} {'p':>6}  {'avg corr':>8}")
    for y_, x_ in pairs:
        j = r[[y_, x_]].dropna()
        if len(j) < 500:
            print(f"  {y_}~{x_:<8} too short"); continue
        ry, rx = j[y_], j[x_]
        cov = ry.rolling(60).cov(rx); var = rx.rolling(60).var()
        beta = cov / var
        resid = ry - beta * rx
        z = (resid - resid.rolling(60).mean()) / resid.rolling(60).std()
        # 5-day forward spread return of fading: short y long beta*x when z>2, reverse when z<-2
        fy = ry.rolling(5).sum().shift(-5); fx = rx.rolling(5).sum().shift(-5)
        spread_fwd = fy - beta * fx
        sig = pd.Series(np.where(z > 2, -1.0, np.where(z < -2, 1.0, 0.0)), index=z.index)
        pnl = (sig * spread_fwd)[sig != 0].dropna()
        pnl = pnl[~pnl.index.duplicated()]
        # de-overlap: take at most one signal per 5 days
        keep = []; last = None
        for d in pnl.index:
            if last is None or (d - last).days >= 7:
                keep.append(d); last = d
        pnl = pnl.loc[keep]
        if len(pnl) < 20:
            print(f"  {y_}~{x_:<8} n={len(pnl)} too few"); continue
        base = spread_fwd.dropna()
        pl = np.array([base.sample(len(pnl), random_state=int(rng.integers(1e9))).abs().mean() * 0 + (np.sign(rng.choice([-1, 1], len(pnl))) * base.sample(len(pnl), random_state=int(rng.integers(1e9))).values).mean() for _ in range(300)])
        h = len(pnl) // 2
        print(f"  {y_}~{x_:<8} {len(pnl):>6} {pnl.mean()*1e4:>13.1f}bp {tstat(pnl):>6.2f} {pnl.iloc[:h].mean()*1e4:>6.1f}/{pnl.iloc[h:].mean()*1e4:<6.1f} {float((pl>=pnl.mean()).mean()):>6.3f}  {ry.corr(rx):>8.2f}")
    print("  Reading: 5-day spread return per signal, before costs (two legs, ~4-6bp round trip on ETFs; far more on BTC).")


def main() -> None:
    rng = np.random.default_rng(77)
    f1(rng); f2(rng); f4(rng)


if __name__ == "__main__":
    main()
