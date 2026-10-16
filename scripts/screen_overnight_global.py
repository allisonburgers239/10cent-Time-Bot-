"""Screen: is the overnight-vs-intraday return split (Sleeve E's edge) a
global phenomenon?  Decomposes daily index returns into overnight
(prev close -> open) and intraday (open -> close) for every major index
whose yfinance OPEN prints are real.

Open-price hygiene: many yfinance index histories have fake opens
(open == prior close, or open == close) in early years.  Each year is
kept only if < 5% of its days show either signature.  Indices that never
clear the bar (SPX, FTSE, Nikkei, ASX, Bovespa) are reported as unusable.

Reference: Lou, Polk, Skouras (2019) "A tug of war: Overnight versus
intraday expected returns", JFE; Kelly & Clark (2011).
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import yfinance as yf

from ten_cent_bot.metrics import max_drawdown, sharpe

UNIVERSE = {
    "SPY": "US (SPY, reference)",
    "^GSPC": "US S&P 500 index",
    "^GDAXI": "Germany DAX",
    "^STOXX50E": "Euro Stoxx 50",
    "^FTSE": "UK FTSE 100",
    "^N225": "Japan Nikkei 225",
    "^HSI": "Hong Kong Hang Seng",
    "^KS11": "Korea KOSPI",
    "^AXJO": "Australia ASX 200",
    "^NSEI": "India Nifty 50",
    "^BVSP": "Brazil Bovespa",
}
STALE_MAX = 0.05


def fetch(sym: str) -> pd.DataFrame:
    d = yf.download(sym, period="max", interval="1d", auto_adjust=True, progress=False)
    if d.empty:
        return d
    df = pd.DataFrame({"open": d["Open"].squeeze(), "close": d["Close"].squeeze()}).dropna()
    df = df[(df["open"] > 0) & (df["close"] > 0)]
    return df


def clean_years(df: pd.DataFrame) -> tuple[pd.DataFrame, list[int]]:
    stale = (df["open"] == df["close"].shift(1)) | (df["open"] == df["close"])
    by_year = stale.groupby(df.index.year).mean()
    ok_years = by_year[by_year < STALE_MAX].index.tolist()
    # require a contiguous recent run: drop everything before the last bad year
    bad = by_year[by_year >= STALE_MAX].index.tolist()
    if bad:
        cutoff = max(bad) + 1
        ok_years = [y for y in ok_years if y >= cutoff]
    return df[df.index.year.isin(ok_years)], ok_years


def stats(r: pd.Series) -> dict:
    r = r.dropna()
    if len(r) < 250:
        return {}
    eq = (1 + r).cumprod()
    return {
        "n": len(r),
        "cagr": (1 + r.mean()) ** 252 - 1,
        "vol": r.std(ddof=0) * np.sqrt(252),
        "sharpe": sharpe(r, 252),
        "mdd": max_drawdown(eq),
    }


def main() -> None:
    print("=== GLOBAL OVERNIGHT vs INTRADAY SCREEN ===\n")
    hdr = f"{'index':<28} {'years':<11} {'n':>6}  {'ON Sharpe':>9} {'ID Sharpe':>9} {'BH Sharpe':>9}  {'ON CAGR':>8} {'ID CAGR':>8}  {'ON MaxDD':>8}"
    print(hdr)
    print("-" * len(hdr))
    rows = []
    for sym, name in UNIVERSE.items():
        raw = fetch(sym)
        if raw.empty:
            print(f"{name:<28} no data")
            continue
        df, yrs = clean_years(raw)
        if len(df) < 750:
            print(f"{name:<28} UNUSABLE: fake opens in {len(raw)} days, only {len(df)} clean")
            continue
        on = df["open"] / df["close"].shift(1) - 1
        idr = df["close"] / df["open"] - 1
        bh = df["close"].pct_change()
        so, si, sb = stats(on), stats(idr), stats(bh)
        print(
            f"{name:<28} {min(yrs)}-{max(yrs)}  {so['n']:>6}  {so['sharpe']:>9.2f} {si['sharpe']:>9.2f} {sb['sharpe']:>9.2f}  "
            f"{so['cagr']:>8.1%} {si['cagr']:>8.1%}  {so['mdd']:>8.1%}"
        )
        rows.append((sym, name, df, on, idr))

    print("\n=== 5-year sub-periods: overnight Sharpe (intraday Sharpe in brackets) ===")
    for sym, name, df, on, idr in rows:
        parts = []
        for start in range(int(df.index.year.min()) // 5 * 5, int(df.index.year.max()) + 1, 5):
            m = (df.index.year >= start) & (df.index.year < start + 5)
            if m.sum() < 500:
                continue
            parts.append(f"{start}: {sharpe(on[m].dropna(), 252):+.2f} [{sharpe(idr[m].dropna(), 252):+.2f}]")
        print(f"  {name:<26} " + "  ".join(parts))

    print("\n=== Placebo: random nightly sign, 200 seeds, P(placebo Sharpe >= real) ===")
    rng = np.random.default_rng(7)
    for sym, name, df, on, idr in rows:
        r = on.dropna()
        real = sharpe(r, 252)
        pl = np.array([sharpe(r * rng.choice([-1.0, 1.0], size=len(r)), 252) for _ in range(200)])
        p = float((pl >= real).mean())
        print(f"  {name:<26} real {real:+.2f}  placebo {pl.mean():+.2f} +/- {pl.std():.2f}  p={p:.3f}  {'REAL' if p < 0.05 else 'WEAK' if p < 0.2 else 'NONE'}")

    print("\n=== Overnight-minus-intraday spread Sharpe (long overnight, short intraday, zero net beta) ===")
    for sym, name, df, on, idr in rows:
        spread = (on - idr).dropna()
        print(f"  {name:<26} {sharpe(spread, 252):+.2f}")


if __name__ == "__main__":
    main()
