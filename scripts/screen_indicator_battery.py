"""Screen: TradingView's standard indicators (default settings) and mechanical
support / resistance / trendline rules, pre-registered and placebo-tested on
daily ETF data.  Same harness and bar as screen_price_patterns.py.

Indicators (TV defaults): MACD(12,26,9) cross, RSI(14) 30/70, Bollinger(20,2)
band breach, Stochastic(14,3) 20/80, ADX(14)>25 with DI direction,
SuperTrend(10,3) flip, Donchian(20) breakout/breakdown, EMA 50/200 cross,
CCI(20) +/-100, Williams %R(14).
Mechanical levels (no look-ahead: a pivot is confirmed 5 bars after it
forms and only used from then on):
  support bounce   : close within 0.5% above a prior pivot low      -> long
  resistance reject: close within 0.5% below a prior pivot high     -> short
  resistance break : close > prior pivot high (first day through)   -> long
  support break    : close < prior pivot low (first day through)    -> short
  uptrend-line touch  : line through the last two rising pivot lows, close within 0.5% above it -> long
  downtrend-line touch: line through the last two falling pivot highs, close within 0.5% below -> short
Targets: next day (cc) and next 5 days.  Bonferroni bar p < 0.0015 (~34 tests x 8 tickers / 2 horizons is
too strict to apply literally; we use 0.0015 and also report the count at 0.05 with same-sign halves).
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import yfinance as yf

TICKERS = ["SPY", "QQQ", "IWM", "EFA", "EEM", "TLT", "GLD", "USO"]
N_PLACEBO = 300
BONF = 0.0015


def ema(x, n): return x.ewm(span=n, adjust=False).mean()


def rsi(c, n=14):
    d = c.diff(); up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean(); dn = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    return 100 - 100 / (1 + up / dn.replace(0, np.nan))


def atr(h, l, c, n=14):
    tr = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / n, adjust=False).mean()


def adx(h, l, c, n=14):
    up = h.diff(); dn = -l.diff()
    plus = np.where((up > dn) & (up > 0), up, 0.0); minus = np.where((dn > up) & (dn > 0), dn, 0.0)
    a = atr(h, l, c, n)
    pdi = 100 * pd.Series(plus, index=h.index).ewm(alpha=1 / n, adjust=False).mean() / a
    mdi = 100 * pd.Series(minus, index=h.index).ewm(alpha=1 / n, adjust=False).mean() / a
    dx = 100 * (pdi - mdi).abs() / (pdi + mdi).replace(0, np.nan)
    return dx.ewm(alpha=1 / n, adjust=False).mean(), pdi, mdi


def supertrend(h, l, c, n=10, mult=3.0):
    a = atr(h, l, c, n); hl2 = (h + l) / 2
    upper = hl2 + mult * a; lower = hl2 - mult * a
    trend = pd.Series(1, index=c.index); fu = upper.copy(); fl = lower.copy()
    for i in range(1, len(c)):
        fu.iloc[i] = min(upper.iloc[i], fu.iloc[i - 1]) if c.iloc[i - 1] <= fu.iloc[i - 1] else upper.iloc[i]
        fl.iloc[i] = max(lower.iloc[i], fl.iloc[i - 1]) if c.iloc[i - 1] >= fl.iloc[i - 1] else lower.iloc[i]
        if trend.iloc[i - 1] == 1:
            trend.iloc[i] = -1 if c.iloc[i] < fl.iloc[i] else 1
        else:
            trend.iloc[i] = 1 if c.iloc[i] > fu.iloc[i] else -1
    return trend


def pivots(h, l, k=5):
    """Confirmed pivot highs/lows: the bar is an extreme of +/-k bars; usable from bar+k."""
    ph = pd.Series(np.nan, index=h.index); pl = pd.Series(np.nan, index=l.index)
    hv, lv = h.values, l.values
    for i in range(k, len(h) - k):
        if hv[i] == hv[i - k:i + k + 1].max():
            ph.iloc[i + k] = hv[i]      # known k bars later
        if lv[i] == lv[i - k:i + k + 1].min():
            pl.iloc[i + k] = lv[i]
    return ph, pl


def level_rules(o, h, l, c, k=5, tol=0.005):
    ph, pl = pivots(h, l, k)
    last_ph = ph.ffill(); last_pl = pl.ffill()
    prev_c = c.shift(1)
    sup_bounce = (c > last_pl) & (c <= last_pl * (1 + tol)) & (prev_c > last_pl * (1 + tol))
    res_reject = (c < last_ph) & (c >= last_ph * (1 - tol)) & (prev_c < last_ph * (1 - tol))
    res_break = (c > last_ph) & (prev_c <= last_ph.shift(1))
    sup_break = (c < last_pl) & (prev_c >= last_pl.shift(1))
    # trendlines through the last two pivots
    up_touch = pd.Series(False, index=c.index); dn_touch = pd.Series(False, index=c.index)
    pl_pts = [(i, v) for i, v in enumerate(pl.values) if not np.isnan(v)]
    ph_pts = [(i, v) for i, v in enumerate(ph.values) if not np.isnan(v)]
    cv = c.values
    def touches(pts, rising, out, below):
        for j in range(1, len(pts)):
            (i1, v1), (i2, v2) = pts[j - 1], pts[j]
            if (v2 > v1) != rising or i2 == i1:
                continue
            slope = (v2 - v1) / (i2 - i1)
            end = pts[j + 1][0] if j + 1 < len(pts) else len(cv)
            for t in range(i2 + 1, min(end, len(cv))):
                line = v2 + slope * (t - i2)
                if line <= 0:
                    continue
                if below and 0 <= (cv[t] - line) / line <= tol:
                    out.iloc[t] = True
                if (not below) and 0 <= (line - cv[t]) / line <= tol:
                    out.iloc[t] = True
    touches(pl_pts, True, up_touch, True)      # rising support line, price just above it
    touches(ph_pts, False, dn_touch, False)    # falling resistance line, price just below it
    return {"support bounce (pivot low +0.5%) -> long": sup_bounce, "resistance reject (pivot high -0.5%) -> short": res_reject,
            "resistance BREAK (close > pivot high) -> long": res_break, "support BREAK (close < pivot low) -> short": sup_break,
            "uptrend-line touch -> long": up_touch, "downtrend-line touch -> short": dn_touch}


def indicator_rules(o, h, l, c):
    out = {}
    macd = ema(c, 12) - ema(c, 26); sig = ema(macd, 9)
    out["MACD cross up -> long"] = (macd > sig) & (macd.shift(1) <= sig.shift(1))
    out["MACD cross down -> short"] = (macd < sig) & (macd.shift(1) >= sig.shift(1))
    r = rsi(c, 14)
    out["RSI14 < 30 -> long"] = r < 30; out["RSI14 > 70 -> short"] = r > 70
    ma = c.rolling(20).mean(); sd = c.rolling(20).std()
    out["Bollinger lower breach -> long"] = c < ma - 2 * sd; out["Bollinger upper breach -> short"] = c > ma + 2 * sd
    lo = l.rolling(14).min(); hi = h.rolling(14).max(); kfast = 100 * (c - lo) / (hi - lo).replace(0, np.nan); kslow = kfast.rolling(3).mean()
    out["Stochastic < 20 -> long"] = kslow < 20; out["Stochastic > 80 -> short"] = kslow > 80
    a, pdi, mdi = adx(h, l, c, 14)
    out["ADX>25 & +DI>-DI -> long"] = (a > 25) & (pdi > mdi); out["ADX>25 & -DI>+DI -> short"] = (a > 25) & (mdi > pdi)
    st = supertrend(h, l, c)
    out["SuperTrend flip up -> long"] = (st == 1) & (st.shift(1) == -1); out["SuperTrend flip down -> short"] = (st == -1) & (st.shift(1) == 1)
    out["Donchian20 breakout -> long"] = c > h.shift(1).rolling(20).max(); out["Donchian20 breakdown -> short"] = c < l.shift(1).rolling(20).min()
    e50, e200 = ema(c, 50), ema(c, 200)
    out["EMA50 > EMA200 (regime) -> long"] = e50 > e200; out["EMA50 < EMA200 (regime) -> short"] = e50 < e200
    tp = (h + l + c) / 3; cci = (tp - tp.rolling(20).mean()) / (0.015 * tp.rolling(20).apply(lambda x: np.mean(np.abs(x - x.mean())), raw=True))
    out["CCI20 < -100 -> long"] = cci < -100; out["CCI20 > 100 -> short"] = cci > 100
    wr = -100 * (hi - c) / (hi - lo).replace(0, np.nan)
    out["Williams%R < -80 -> long"] = wr < -80; out["Williams%R > -20 -> short"] = wr > -20
    return out


def score(mask, target, rng):
    j = pd.concat([mask.rename("m"), target.rename("y")], axis=1).dropna()
    y = j.y.values.astype(float); m = j.m.values.astype(bool)
    if m.sum() < 30:
        return None
    sel = y[m]; unc = y.mean(); real = sel.mean() - unc
    t = real / (sel.std(ddof=1) / np.sqrt(len(sel)))
    half = len(y) // 2
    h1 = y[:half][m[:half]].mean() - y[:half].mean() if m[:half].sum() > 10 else np.nan
    h2 = y[half:][m[half:]].mean() - y[half:].mean() if m[half:].sum() > 10 else np.nan
    k = int(m.sum()); pl = np.array([y[rng.choice(len(y), k, replace=False)].mean() - unc for _ in range(N_PLACEBO)])
    return {"n": k, "edge_bp": real * 1e4, "t": t, "h1": h1 * 1e4, "h2": h2 * 1e4, "p": float((pl >= real).mean())}


def main():
    rng = np.random.default_rng(5)
    data = yf.download(TICKERS, period="max", interval="1d", auto_adjust=True, progress=False)
    rows = []
    for tk in TICKERS:
        df = pd.DataFrame({k.lower(): data[k][tk] for k in ["Open", "High", "Low", "Close"]}).dropna()
        df = df[(df > 0).all(axis=1)]
        o, h, l, c = df["open"], df["high"], df["low"], df["close"]
        nxt1 = c.shift(-1) / c - 1; nxt5 = c.shift(-5) / c - 1
        rules = {**indicator_rules(o, h, l, c), **level_rules(o, h, l, c)}
        for name, mask in rules.items():
            sign = -1.0 if "short" in name else 1.0
            for hz, tgt in [("1d", nxt1), ("5d", nxt5)]:
                s = score(mask.astype(bool), sign * tgt, rng)
                if s:
                    rows.append({"ticker": tk, "rule": name, "hz": hz, **s})
    res = pd.DataFrame(rows)
    print(f"=== INDICATOR + LEVEL BATTERY: {len(res)} tests on {len(TICKERS)} ETFs; bar p<{BONF} ===")
    print("edge_bp = signal-day mean of the SIGNED target minus unconditional; h1/h2 = first/second half\n")
    agg = []
    for (name, hz), g in res.groupby(["rule", "hz"]):
        cons = int(((g.p < 0.05) & (g.h1 > 0) & (g.h2 > 0)).sum())
        agg.append((name, hz, cons, int((g.p < BONF).sum()), g.edge_bp.mean(), g.t.mean(), int((g.edge_bp > 0).sum()), len(g)))
    agg.sort(key=lambda x: (-x[2], -x[3], -x[5]))
    print(f"{'rule':<48} {'hz':>3} {'p<.05&both halves+':>18} {'p<bar':>5} {'avg edge':>9} {'avg t':>6} {'tickers +':>9}")
    for a in agg:
        print(f"{a[0]:<48} {a[1]:>3} {a[2]:>18} {a[3]:>5} {a[4]:>8.1f}bp {a[5]:>6.2f} {a[6]:>5}/{a[7]}")
    print("\n--- Any rule clearing the bar on >=2 tickers with both halves positive:")
    hits = res[(res.p < BONF) & (res.h1 > 0) & (res.h2 > 0)]
    for (name, hz), g in hits.groupby(["rule", "hz"]):
        if len(g) >= 2:
            print(f"  {name} [{hz}]: " + ", ".join(f"{r.ticker} {r.edge_bp:+.0f}bp t={r.t:.1f}" for r in g.itertuples()))
    if hits.groupby(["rule", "hz"]).size().max() < 2 if len(hits) else True:
        print("  none")


if __name__ == "__main__":
    main()
