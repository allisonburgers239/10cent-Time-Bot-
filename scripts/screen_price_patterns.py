"""Screen: classic daily price patterns, pre-registered and placebo-tested.

Every pattern is computed from data available at the close of day t (or the
open of day t for gap patterns) and scored on the return it claims to
predict.  Each is compared with the unconditional mean over the same
sample and with a placebo of random day-sets of the same size.  With ~17
patterns per ticker the Bonferroni bar is p < 0.003; anything above that
and below 0.05 is 'suggestive', not an edge.

Markets: SPY QQQ IWM EFA TLT GLD (yfinance daily, 1993+/2003+/2004+).
Literature anchors: Lo-Mamaysky-Wang (2000) chart patterns; Marshall-Young-
Rose (2006) candlesticks; George-Hwang (2004) 52-week high; Connors RSI(2);
Faber (2007) 10-month SMA; Ariel (1990) pre-holiday; Brock-Lakonishok-
LeBaron (1992) vs Sullivan-Timmermann-White (1999) on MA rules.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import yfinance as yf

TICKERS = ["SPY", "QQQ", "IWM", "EFA", "TLT", "GLD"]
N_PLACEBO = 400
BONF = 0.003


def rsi(c: pd.Series, n: int) -> pd.Series:
    d = c.diff()
    up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    return 100 - 100 / (1 + up / dn.replace(0, np.nan))


def patterns(df: pd.DataFrame) -> dict[str, tuple[pd.Series, pd.Series, str]]:
    """name -> (mask of signal days, target return series, note). Target is
    the return the pattern claims to predict; sign convention: positive mean
    = pattern is right."""
    o, h, l, c = df["open"], df["high"], df["low"], df["close"]
    r = c.pct_change()                    # close->close day t
    nxt = r.shift(-1)                     # next day close->close
    nxt20 = c.shift(-20) / c - 1          # next 20 days
    intra = c / o - 1                     # open->close day t
    up = (r > 0).astype(bool)
    up1 = up.shift(1, fill_value=False).astype(bool); up2 = up.shift(2, fill_value=False).astype(bool)
    body = (c - o)
    rng = (h - l).replace(0, np.nan)
    out = {}
    out["3 up closes -> next day (momentum)"] = (up & up1 & up2, nxt, "")
    out["3 down closes -> next day (reversal, long)"] = (~up & ~up1 & ~up2 & r.notna(), nxt, "")
    out["inside day -> next day"] = ((h < h.shift(1)) & (l > l.shift(1)), nxt, "")
    out["NR7 (narrowest range of 7) -> next day"] = (rng == rng.rolling(7).min(), nxt, "")
    out["new 52w closing high -> next day"] = (c >= c.rolling(252).max(), nxt, "")
    out["new 52w closing high -> next 20d"] = (c >= c.rolling(252).max(), nxt20, "")
    out["new 52w closing low -> next 20d (reversal, long)"] = (c <= c.rolling(252).min(), nxt20, "")
    eng_bull = (body > 0) & (body.shift(1) < 0) & (c > o.shift(1)) & (o < c.shift(1))
    eng_bear = (body < 0) & (body.shift(1) > 0) & (c < o.shift(1)) & (o > c.shift(1))
    out["bullish engulfing -> next day"] = (eng_bull, nxt, "")
    out["bearish engulfing -> next day (short)"] = (eng_bear, -nxt, "")
    gap = o / c.shift(1) - 1
    out["gap up > 0.5% -> fade intraday (short)"] = (gap > 0.005, -intra, "")
    out["gap down < -0.5% -> fade intraday (long)"] = (gap < -0.005, intra, "")
    out["gap |>1%| -> continue intraday"] = (gap.abs() > 0.01, np.sign(gap) * intra, "")
    r2 = rsi(c, 2)
    out["RSI(2) < 10 -> next day (long)"] = (r2 < 10, nxt, "")
    out["RSI(2) > 90 -> next day (short)"] = (r2 > 90, -nxt, "")
    out["close > 200d SMA -> next day"] = (c > c.rolling(200).mean(), nxt, "")
    out["close > 10m (210d) SMA -> next 20d"] = (c > c.rolling(210).mean(), nxt20, "")
    idx = pd.Series(df.index, index=df.index)
    bdays_to_next = pd.Series(np.busday_count(idx.dt.date.values[:-1].astype("datetime64[D]"), idx.dt.date.values[1:].astype("datetime64[D]")), index=df.index[:-1])
    pre_holiday = bdays_to_next.reindex(df.index) > 1
    out["pre-holiday day (Ariel) -> that day"] = (pre_holiday, r, "")
    out["Monday -> that day"] = (pd.Series(df.index.dayofweek == 0, index=df.index), r, "")
    out["Friday -> that day"] = (pd.Series(df.index.dayofweek == 4, index=df.index), r, "")
    return out


def score(mask: pd.Series, target: pd.Series, rng: np.random.Generator) -> dict:
    j = pd.concat([mask.rename("m"), target.rename("y")], axis=1).dropna()
    j = j[j.m.notna()]
    y = j.y.values.astype(float); m = j.m.values.astype(bool)
    if m.sum() < 30:
        return {}
    sel = y[m]; unc = y.mean()
    t = (sel.mean() - unc) / (sel.std(ddof=1) / np.sqrt(len(sel)))
    half = len(y) // 2
    h1 = y[:half][m[:half]].mean() - y[:half].mean() if m[:half].sum() > 10 else np.nan
    h2 = y[half:][m[half:]].mean() - y[half:].mean() if m[half:].sum() > 10 else np.nan
    k = int(m.sum())
    pl = np.array([y[rng.choice(len(y), k, replace=False)].mean() - unc for _ in range(N_PLACEBO)])
    real = sel.mean() - unc
    p = float((pl >= real).mean())
    return {"n": k, "mean_bp": sel.mean() * 1e4, "edge_bp": real * 1e4, "t": t, "h1_bp": h1 * 1e4, "h2_bp": h2 * 1e4, "p": p}


def main() -> None:
    rng = np.random.default_rng(17)
    data = yf.download(TICKERS, period="max", interval="1d", auto_adjust=True, progress=False)
    rows = []
    for tk in TICKERS:
        df = pd.DataFrame({k.lower(): data[k][tk] for k in ["Open", "High", "Low", "Close"]}).dropna()
        df = df[(df > 0).all(axis=1)]
        for name, (mask, target, _) in patterns(df).items():
            s = score(mask, target, rng)
            if s:
                rows.append({"ticker": tk, "pattern": name, **s})
    res = pd.DataFrame(rows)
    pd.set_option("display.width", 200)
    print(f"=== PRICE-PATTERN BATTERY: {len(res)} tests, Bonferroni bar p<{BONF} ===")
    print("edge_bp = pattern-day mean minus unconditional mean of the same target; h1/h2 = same in first/second half of sample\n")
    for tk in TICKERS:
        sub = res[res.ticker == tk].sort_values("p")
        print(f"--- {tk}")
        print(sub[["pattern", "n", "mean_bp", "edge_bp", "t", "h1_bp", "h2_bp", "p"]].to_string(index=False, float_format=lambda x: f"{x:7.1f}" if abs(x) >= 1 or x == 0 else f"{x:7.3f}"))
    print("\n=== Cross-market summary: patterns ranked by how many of the 6 tickers show p<0.05 with the SAME sign in both halves ===")
    agg = []
    for name, g in res.groupby("pattern"):
        consistent = int(((g.p < 0.05) & (np.sign(g.h1_bp) == np.sign(g.h2_bp)) & (g.edge_bp > 0)).sum())
        agg.append((name, consistent, int((g.p < BONF).sum()), g.edge_bp.mean(), g.t.mean()))
    agg.sort(key=lambda x: (-x[1], -x[2]))
    print(f"{'pattern':<48} {'p<.05&consistent':>16} {'p<Bonf':>7} {'avg edge bp':>12} {'avg t':>6}")
    for a in agg:
        print(f"{a[0]:<48} {a[1]:>16} {a[2]:>7} {a[3]:>12.1f} {a[4]:>6.2f}")
    print("\nVerdict rule: an edge needs p<0.003 on at least 2 tickers AND the same sign in both halves. Anything else is noise or beta.")


if __name__ == "__main__":
    main()
