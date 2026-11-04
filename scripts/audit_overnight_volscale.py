"""Audit: VIX-scaled sizing for Sleeve E v2 (2026-11-04).

Rule: position = min(cap, 20 / VIX_close) x (2 on RSI(2)<10 nights, else 1),
total capped at 2x. Same harness as the other sleeves: baseline, walk-forward
halves, 5-year sub-periods, leave-one-ticker-out, cost sensitivity, placebo
(VIX series shuffled, 200 seeds -> p-value), parameter grid (ref, cap), and the
"why": overnight return and overnight volatility by VIX bucket.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import yfinance as yf

from ten_cent_bot import overnight as ov

TICKERS = ["SPY", "QQQ", "IWM", "GLD"]
E3 = ["SPY", "QQQ", "IWM", "GLD"]
E = ["SPY", "QQQ", "IWM"]


def load():
    raw = yf.download(TICKERS + ["^VIX"], period="max", interval="1d", auto_adjust=True, progress=False)
    data = {t: pd.DataFrame({"open": raw["Open"][t], "close": raw["Close"][t]}).dropna() for t in TICKERS}
    vix = raw["Close"]["^VIX"].dropna()
    return data, vix


def port(data, vix, cfg, tickers, start=None, end=None) -> pd.Series:
    rets = {}
    for t in tickers:
        df = data[t]
        if start is not None:
            df = df[df.index >= start]
        if end is not None:
            df = df[df.index < end]
        rets[t] = ov.backtest_single(df, cfg, vix=vix)["net_return"]
    return pd.DataFrame(rets).mean(axis=1).dropna()


def stats(r: pd.Series) -> str:
    s = ov.summary_from_returns(r)
    return f"Sharpe {s['sharpe']:5.2f}  CAGR {s['cagr']:6.1%}  MaxDD {s['max_drawdown']:6.1%}  n {s['days']}"


def main() -> None:
    data, vix = load()
    base = ov.E_V2_CONFIG
    vol = ov.E_V2_VOL_CONFIG
    print("=== 0. Why: SPY overnight return and vol by VIX bucket ===")
    df = data["SPY"]; on = ov.compute_overnight_returns(df); v = vix.reindex(df.index).ffill()
    for lo, hi in [(0, 13), (13, 16), (16, 20), (20, 25), (25, 35), (35, 100)]:
        m = (v >= lo) & (v < hi); x = on[m].dropna()
        print(f"  VIX {lo:>2}-{hi:<3} nights {len(x):5d}  mean {x.mean() * 1e4:+5.1f}bp  std {x.std() * 1e4:5.1f}bp  mean/std {x.mean() / x.std():+.3f}")
    print("  -> the premium per night grows with VIX but the variance grows faster; 20/VIX equalises risk per night.")

    print("\n=== 1. Baseline: E v2 vs E v2 + VIX scale (1993-, 1bp/side) ===")
    for name, tk in [("E (SPY/QQQ/IWM)", E), ("E3 (+GLD)", E3)]:
        print(f"  {name:18s} E v2: {stats(port(data, vix, base, tk))}")
        print(f"  {name:18s} +VIX: {stats(port(data, vix, vol, tk))}")
    for t in TICKERS:
        print(f"  {t:5s} E v2: {stats(port(data, vix, base, [t]))}   +VIX: {stats(port(data, vix, vol, [t]))}")

    print("\n=== 2. Walk-forward halves and 5-year sub-periods (E basket) ===")
    r0 = port(data, vix, base, E); r1 = port(data, vix, vol, E)
    h = len(r0) // 2
    print(f"  first half  E v2 {ov.sharpe(r0.iloc[:h]):.2f}  +VIX {ov.sharpe(r1.iloc[:h]):.2f}")
    print(f"  second half E v2 {ov.sharpe(r0.iloc[h:]):.2f}  +VIX {ov.sharpe(r1.iloc[h:]):.2f}")
    for y in range(1995, 2030, 5):
        a, b = r0[(r0.index.year >= y) & (r0.index.year < y + 5)], r1[(r1.index.year >= y) & (r1.index.year < y + 5)]
        if len(a) > 200:
            print(f"  {y}-{y + 4}: E v2 {ov.sharpe(a):5.2f}  +VIX {ov.sharpe(b):5.2f}  {'better' if ov.sharpe(b) > ov.sharpe(a) else 'worse'}")

    print("\n=== 3. Leave-one-ticker-out (E3) ===")
    for drop in E3:
        tk = [t for t in E3 if t != drop]
        print(f"  without {drop}: E v2 {ov.sharpe(port(data, vix, base, tk)):.2f}  +VIX {ov.sharpe(port(data, vix, vol, tk)):.2f}")

    print("\n=== 4. Cost sensitivity (bp per side) ===")
    for c in [0.5, 1.0, 2.0, 3.0, 5.0]:
        b = ov.OvernightConfig(reversal_signal="rsi2", reversal_multiplier=2.0, cost_bps_per_side=c)
        w = ov.OvernightConfig(reversal_signal="rsi2", reversal_multiplier=2.0, vol_scale="vix", cost_bps_per_side=c)
        print(f"  {c:3.1f}bp: E v2 {ov.sharpe(port(data, vix, b, E)):.2f}  +VIX {ov.sharpe(port(data, vix, w, E)):.2f}")

    print("\n=== 5. Parameter grid (ref, cap) on the E basket ===")
    for ref in [15, 20, 25, 30]:
        row = []
        for cap in [1.5, 2.0, 3.0]:
            w = ov.OvernightConfig(reversal_signal="rsi2", reversal_multiplier=2.0, vol_scale="vix", vol_scale_ref=ref, vol_scale_cap=cap)
            row.append(f"cap {cap}: {ov.sharpe(port(data, vix, w, E)):.2f}")
        print(f"  ref {ref}: " + "  ".join(row))

    print("\n=== 6. Placebo: VIX series shuffled (200 seeds) ===")
    real = ov.sharpe(r1)
    rng = np.random.default_rng(0)
    fake = []
    for _ in range(200):
        vs = pd.Series(rng.permutation(vix.to_numpy()), index=vix.index)
        fake.append(ov.sharpe(port(data, vs, vol, E)))
    fake = np.array(fake)
    print(f"  real {real:.3f}  placebo mean {fake.mean():.3f} sd {fake.std():.3f}  p(placebo >= real) = {(fake >= real).mean():.3f}")

    print("\n=== 7. Tail: worst nights and worst year, E basket ===")
    for name, r, cfg in [("E v2", r0, base), ("+VIX", r1, vol)]:
        yr = r.groupby(r.index.year).sum()
        size = pd.DataFrame({t: ov.backtest_single(data[t], cfg, vix=vix)["position"] for t in E}).mean(axis=1)
        print(f"  {name}: worst night {r.min():+.2%}  worst year {yr.idxmin()} {yr.min():+.1%}  avg position size {size.mean():.2f}x  (max {size.max():.1f}x)")


if __name__ == "__main__":
    main()
