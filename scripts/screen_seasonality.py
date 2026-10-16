"""Screen: calendar seasonality with literature behind it.

S1  Halloween / sell-in-May (Bouman-Jacobsen 2002; Jacobsen-Zhang 2018 find
    it in 114 of 114 markets): Nov-Apr vs May-Oct, ten world indices,
    close-to-close monthly so stale opens do not matter.
S2  Faber (2007) 10-month SMA timing on the Sleeve B ETF basket, long-only,
    equal weight, vs buy-and-hold.
S3  Commodity seasonals on roll-adjusted TradingView monthly pairs
    (grains: weather premium Apr-Jun, harvest low Sep-Oct; gold: Aug-Jan
    jewellery season).  Windows fixed from folklore before looking.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from audit_carry import adjusted_returns, load_all  # noqa: E402

from ten_cent_bot.metrics import max_drawdown, sharpe  # noqa: E402

INDICES = {"SPY": "US SPY", "^GSPC": "US S&P 500 (1950+)", "^GDAXI": "Germany DAX", "^FTSE": "UK FTSE", "^N225": "Japan Nikkei",
           "^HSI": "Hong Kong HSI", "^KS11": "Korea KOSPI", "^AXJO": "Australia ASX", "^BVSP": "Brazil Bovespa", "^NSEI": "India Nifty", "^STOXX50E": "Euro Stoxx"}


def monthly(sym: str) -> pd.Series:
    d = yf.download(sym, period="max", interval="1d", auto_adjust=True, progress=False)["Close"].squeeze().dropna()
    d.index = pd.to_datetime(d.index).tz_localize(None)
    m = d.resample("ME").last().pct_change().dropna()
    return m[m.index >= "1950-01-01"]


def window_test(r: pd.Series, months: set, label: str, rng: np.random.Generator, n_pl: int = 500) -> None:
    inw = r[r.index.month.isin(months)]; out = r[~r.index.month.isin(months)]
    if len(inw) < 24:
        print(f"  {label:<28} too short"); return
    diff = inw.mean() - out.mean()
    se = np.sqrt(inw.var(ddof=1) / len(inw) + out.var(ddof=1) / len(out))
    yrs = sorted(set(r.index.year))
    # placebo: random contiguous window of the same length (same start month each year)
    L = len(months)
    pl = []
    for _ in range(n_pl):
        s = int(rng.integers(1, 13)); ms = {((s - 1 + k) % 12) + 1 for k in range(L)}
        a = r[r.index.month.isin(ms)]; b = r[~r.index.month.isin(ms)]
        pl.append(a.mean() - b.mean())
    pl = np.array(pl); p = float((pl >= diff).mean())
    h = len(r) // 2
    d1 = r.iloc[:h]; d2 = r.iloc[h:]
    f = lambda x: x[x.index.month.isin(months)].mean() - x[~x.index.month.isin(months)].mean()
    print(f"  {label:<28} in {inw.mean()*100:+5.2f}%/m  out {out.mean()*100:+5.2f}%/m  diff t={diff/se:+5.2f}  halves {f(d1)*100:+.2f}/{f(d2)*100:+.2f}  placebo p={p:.3f}  {yrs[0]}-{yrs[-1]}")


def main() -> None:
    rng = np.random.default_rng(23)
    print("=== S1. Halloween: Nov-Apr vs May-Oct, monthly close-to-close ===")
    for sym, name in INDICES.items():
        try:
            window_test(monthly(sym), {11, 12, 1, 2, 3, 4}, name, rng)
        except Exception as e:
            print(f"  {name:<28} error {e}")

    print("\n=== S2. Faber 10-month SMA timing, Sleeve B ETF basket (SPY QQQ IWM EFA EEM TLT IEF GLD USO DBC), long-only EW ===")
    etfs = ["SPY", "QQQ", "IWM", "EFA", "EEM", "TLT", "IEF", "GLD", "USO", "DBC"]
    px = yf.download(etfs, period="max", interval="1d", auto_adjust=True, progress=False)["Close"]
    px.index = pd.to_datetime(px.index).tz_localize(None)
    m = px.resample("ME").last().loc["2007-01-01":]
    ret = m.pct_change()
    sig = (m > m.rolling(10).mean()).shift(1).astype(float)
    timed = (sig * ret).mean(axis=1) - sig.diff().abs().mean(axis=1) * 10 / 1e4
    bh = ret.mean(axis=1)
    for label, s in [("10m SMA timed", timed), ("buy-and-hold EW", bh)]:
        s = s.dropna(); eq = (1 + s).cumprod()
        print(f"  {label:<18} Sharpe {sharpe(s, 12):5.2f}  CAGR {((1+s.mean())**12-1):6.2%}  Vol {s.std(ddof=0)*np.sqrt(12):5.1%}  MaxDD {max_drawdown(eq):6.1%}  n={len(s)}")
    for start in range(2008, 2027, 4):
        a = timed[(timed.index.year >= start) & (timed.index.year < start + 4)].dropna(); b = bh[(bh.index.year >= start) & (bh.index.year < start + 4)].dropna()
        if len(a) >= 24:
            print(f"    {start}-{start+3}: timed {sharpe(a,12):+.2f} vs b&h {sharpe(b,12):+.2f}")
    rng2 = np.random.default_rng(5); real = sharpe(timed.dropna(), 12)
    pl = []
    for _ in range(200):
        rs = pd.DataFrame(rng2.choice([0.0, 1.0], size=sig.shape, p=[0.3, 0.7]), index=sig.index, columns=sig.columns)
        pl.append(sharpe(((rs * ret).mean(axis=1) - rs.diff().abs().mean(axis=1) * 10 / 1e4).dropna(), 12))
    pl = np.array(pl); print(f"  placebo (random 70%-invested masks): real {real:.2f}, placebo {pl.mean():.2f} +/- {pl.std():.2f}, P(rand>=real)={float((pl>=real).mean()):.3f}")

    print("\n=== S3. Commodity seasonal windows on roll-adjusted TradingView monthly returns ===")
    f1, f2 = load_all()
    f1 = f1.loc["1990-01-01":]; f2 = f2.reindex(f1.index)
    r_adj = adjusted_returns(f1, f2, verbose=False)
    tests = [
        ("ZC", {4, 5, 6}, "corn long Apr-Jun (weather premium)"), ("ZC", {7, 8, 9}, "corn SHORT Jul-Sep (harvest pressure)"),
        ("ZS", {4, 5, 6}, "soy long Apr-Jun"), ("ZS", {7, 8, 9}, "soy SHORT Jul-Sep"),
        ("ZW", {4, 5, 6}, "wheat long Apr-Jun"), ("ZW", {6, 7, 8}, "wheat SHORT Jun-Aug (N. hemisphere harvest)"),
        ("GC", {8, 9, 10, 11, 12, 1}, "gold long Aug-Jan (jewellery season)"), ("SI", {8, 9, 10, 11, 12, 1}, "silver long Aug-Jan"),
        ("KC", {5, 6, 7}, "coffee long May-Jul (Brazil frost season)"), ("LE", {2, 3, 4}, "cattle long Feb-Apr (grilling-season build)"),
        ("CT", {3, 4, 5}, "cotton long Mar-May (planting)"),
    ]
    for mkt, months, label in tests:
        if mkt not in r_adj.columns:
            print(f"  {label:<44} no data"); continue
        r = r_adj[mkt].dropna()
        if "SHORT" in label:
            r = -r
        window_test(r, months, label, rng)
    print("\n  (11 pre-registered windows; Bonferroni bar p<0.005)")


if __name__ == "__main__":
    main()


def halloween_overlay_on_e() -> None:
    """S1b. Does the Halloween tilt improve Sleeve E (overnight SPY/QQQ/IWM)?
    Pre-registered variants: full size Nov-Apr, half or zero size May-Oct."""
    print("\n=== S1b. Halloween tilt on Sleeve E overnight returns (SPY/QQQ/IWM, 1bp/side) ===")
    data = yf.download(["SPY", "QQQ", "IWM"], period="max", interval="1d", auto_adjust=True, progress=False)
    rets = {}
    for t in ["SPY", "QQQ", "IWM"]:
        df = pd.DataFrame({"open": data["Open"][t], "close": data["Close"][t]}).dropna()
        rets[t] = (df["open"].shift(-1) - df["close"]) / df["close"]
    on = pd.DataFrame(rets).dropna()
    winter = on.index.month.isin([11, 12, 1, 2, 3, 4])
    print(f"  E overnight mean/day: Nov-Apr {on[winter].mean().mean()*1e4:+.1f}bp  May-Oct {on[~winter].mean().mean()*1e4:+.1f}bp  (t of diff {((on[winter].mean(axis=1).mean()-on[~winter].mean(axis=1).mean())/np.sqrt(on[winter].mean(axis=1).var()/winter.sum()+on[~winter].mean(axis=1).var()/(~winter).sum())):+.2f})")
    for label, w_summer in [("E baseline (x1 all year)", 1.0), ("x0.5 May-Oct", 0.5), ("x0 May-Oct (flat all summer)", 0.0), ("x1.5 Nov-Apr, x0.5 May-Oct", None)]:
        if w_summer is None:
            mult = pd.Series(np.where(winter, 1.5, 0.5), index=on.index)
        else:
            mult = pd.Series(np.where(winter, 1.0, w_summer), index=on.index)
        port = (on.mul(mult, axis=0) - mult.abs().values[:, None] * 2 / 1e4).mean(axis=1)
        eq = (1 + port).cumprod()
        print(f"  {label:<32} Sharpe {sharpe(port, 252):5.2f}  CAGR {((1+port.mean())**252-1):6.2%}  MaxDD {max_drawdown(eq):6.1%}  avg gross {mult.mean():.2f}x")


if __name__ == "__main__":
    halloween_overlay_on_e()
