"""Screen: do single stocks carry edges the index ETFs do not?

Universe: 40 US large/mid caps across sectors, deliberately including fallen
names (INTC, BA, PYPL, DIS, F, GE, T, VZ, PFE, NKE) alongside the winners
(TSLA, NVDA, PLTR, V, AAPL...) to limit survivorship bias.  Daily yfinance,
full history (PLTR 2020+, COIN 2021+, UBER 2019+ are short).

Tests per stock, pre-registered, same harness as the ETF batteries:
  D   overnight vs intraday decomposition (Lou-Polk-Skouras 2019: in stocks
      the overnight return is positive and intraday negative, strongest in
      high-retail-interest names)
  R   short-term reversal family: 3 down closes, RSI(2)<10, RSI(14)<30,
      Williams%R<-80 -> next day and next overnight
  M   3 up closes -> next day; 52w high -> next 20d
  G   gap up >1% fade intraday (short); gap down <-1% fade intraday (long)
Placebo per test (300 random day-sets), Bonferroni bar p<0.001 for ~12 tests
x 40 stocks.  Cost context: megacap spreads 1-3bp, mid caps 5-15bp.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import yfinance as yf

from ten_cent_bot.metrics import sharpe

STOCKS = ["TSLA", "NVDA", "PLTR", "V", "AAPL", "MSFT", "AMZN", "GOOGL", "META", "NFLX", "AMD", "AVGO", "CRM", "ORCL", "UBER", "COIN",
          "JPM", "BAC", "GS", "MA", "PYPL", "XOM", "CVX", "JNJ", "PFE", "UNH", "MRK", "WMT", "COST", "HD", "NKE", "DIS", "MCD", "KO",
          "BA", "GE", "CAT", "F", "T", "INTC"]
N_PL = 300; BONF = 0.001


def rsi(c, n):
    d = c.diff(); up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean(); dn = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    return 100 - 100 / (1 + up / dn.replace(0, np.nan))


def score(mask, target, rng):
    j = pd.concat([mask.rename("m"), target.rename("y")], axis=1).dropna()
    y = j.y.values.astype(float); m = j.m.values.astype(bool)
    if m.sum() < 40:
        return None
    sel = y[m]; unc = y.mean(); real = sel.mean() - unc
    t = real / (sel.std(ddof=1) / np.sqrt(len(sel)))
    half = len(y) // 2
    h1 = y[:half][m[:half]].mean() - y[:half].mean() if m[:half].sum() > 15 else np.nan
    h2 = y[half:][m[half:]].mean() - y[half:].mean() if m[half:].sum() > 15 else np.nan
    k = int(m.sum()); pl = np.array([y[rng.choice(len(y), k, replace=False)].mean() - unc for _ in range(N_PL)])
    return {"n": k, "edge_bp": real * 1e4, "t": t, "h1": h1 * 1e4, "h2": h2 * 1e4, "p": float((pl >= real).mean())}


def main():
    rng = np.random.default_rng(42)
    data = yf.download(STOCKS, period="max", interval="1d", auto_adjust=True, progress=False)
    dec_rows = []; rows = []
    for tk in STOCKS:
        df = pd.DataFrame({k.lower(): data[k][tk] for k in ["Open", "High", "Low", "Close"]}).dropna()
        df = df[(df > 0).all(axis=1)]
        # yfinance stale-open hygiene: drop years with >5% open==prevclose
        stale = (df["open"] == df["close"].shift(1)); by = stale.groupby(df.index.year).mean()
        df = df[df.index.year.isin(by[by < 0.05].index)]
        if len(df) < 750:
            continue
        o, h, l, c = df["open"], df["high"], df["low"], df["close"]
        on = o.shift(-1) / c - 1; idr = c / o - 1; cc = c.pct_change(); nxt = c.shift(-1) / c - 1; nxt20 = c.shift(-20) / c - 1
        dec_rows.append({"stock": tk, "from": df.index.min().year, "n": len(df), "ON Sharpe": sharpe(on.dropna(), 252), "ID Sharpe": sharpe(idr.dropna(), 252), "BH Sharpe": sharpe(cc.dropna(), 252),
                         "ON cagr": (1 + on.mean()) ** 252 - 1, "ID cagr": (1 + idr.mean()) ** 252 - 1})
        up = (cc > 0).astype(bool); u1 = up.shift(1, fill_value=False).astype(bool); u2 = up.shift(2, fill_value=False).astype(bool)
        gap = o / c.shift(1) - 1
        hh = h.rolling(14).max(); ll = l.rolling(14).min(); wr = -100 * (hh - c) / (hh - ll).replace(0, np.nan)
        tests = {
            "3 down -> next day": (~up & ~u1 & ~u2 & cc.notna(), nxt), "3 down -> next overnight": (~up & ~u1 & ~u2 & cc.notna(), on),
            "RSI2<10 -> next day": (rsi(c, 2) < 10, nxt), "RSI2<10 -> next overnight": (rsi(c, 2) < 10, on),
            "RSI14<30 -> next day": (rsi(c, 14) < 30, nxt), "RSI14<30 -> next 5d": (rsi(c, 14) < 30, c.shift(-5) / c - 1),
            "Williams<-80 -> next 5d": (wr < -80, c.shift(-5) / c - 1), "Williams>-20 -> next 5d (short)": (wr > -20, -(c.shift(-5) / c - 1)),
            "3 up -> next day": (up & u1 & u2, nxt), "52w high -> next 20d": (c >= c.rolling(252).max(), nxt20), "52w low -> next 20d": (c <= c.rolling(252).min(), nxt20),
            "gap up >1% -> fade intraday (short)": (gap > 0.01, -idr), "gap down <-1% -> fade intraday (long)": (gap < -0.01, idr),
        }
        for name, (mask, tgt) in tests.items():
            s = score(mask.astype(bool), tgt, rng)
            if s:
                rows.append({"stock": tk, "test": name, **s})
    dec = pd.DataFrame(dec_rows); res = pd.DataFrame(rows)
    pd.set_option("display.width", 220)
    print("=== D. Overnight vs intraday Sharpe per stock (clean-open years only) ===")
    print(dec.sort_values("ON Sharpe", ascending=False).to_string(index=False, float_format=lambda x: f"{x:6.2f}" if abs(x) < 10 else f"{x:.0f}"))
    print(f"\n  stocks with overnight Sharpe > intraday Sharpe: {(dec['ON Sharpe'] > dec['ID Sharpe']).sum()}/{len(dec)};  mean ON {dec['ON Sharpe'].mean():.2f}, mean ID {dec['ID Sharpe'].mean():.2f}, mean B&H {dec['BH Sharpe'].mean():.2f}")
    print(f"  stocks with NEGATIVE intraday Sharpe: {(dec['ID Sharpe'] < 0).sum()}/{len(dec)}")

    print("\n=== R/M/G. Per-test summary across stocks ===")
    print(f"{'test':<40} {'stocks':>6} {'p<.05&halves+':>13} {'p<bar':>6} {'median edge':>11} {'mean t':>7} {'edge>0':>7}")
    for name, g in res.groupby("test", sort=False):
        cons = int(((g.p < 0.05) & (g.h1 > 0) & (g.h2 > 0)).sum())
        print(f"{name:<40} {len(g):>6} {cons:>13} {int((g.p < BONF).sum()):>6} {g.edge_bp.median():>9.1f}bp {g.t.mean():>7.2f} {int((g.edge_bp > 0).sum()):>4}/{len(g)}")

    print("\n=== Per-stock hits at the bar (p<0.001, both halves positive) ===")
    hits = res[(res.p < BONF) & (res.h1 > 0) & (res.h2 > 0)].sort_values(["test", "edge_bp"], ascending=[True, False])
    for name, g in hits.groupby("test", sort=False):
        print(f"  {name}: " + ", ".join(f"{r.stock} {r.edge_bp:+.0f}bp(t{r.t:.1f})" for r in g.itertuples()))
    print("\n=== The user's four, every test ===")
    for tk in ["TSLA", "NVDA", "PLTR", "V"]:
        g = res[res.stock == tk]
        print(f"\n  {tk}:")
        for r in g.itertuples():
            flag = "**" if (r.p < BONF and r.h1 > 0 and r.h2 > 0) else "*" if r.p < 0.05 else ""
            print(f"    {r.test:<40} n={r.n:>5} edge {r.edge_bp:+7.1f}bp t={r.t:+5.2f} halves {r.h1:+6.1f}/{r.h2:+6.1f} p={r.p:.3f} {flag}")


if __name__ == "__main__":
    main()
