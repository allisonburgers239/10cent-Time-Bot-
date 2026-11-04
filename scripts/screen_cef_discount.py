"""Forced-flow idea #3: closed-end funds trading far below their own net asset value (2026-11-04).

Premise: CEF shares trade at a discount to NAV; when the discount is unusually wide versus the
fund's own history it tends to narrow. Too small for institutions; retail sells them in panics.

Data: Yahoo price (ticker) and NAV (X<ticker>X) daily series, as far back as both exist.
Signal, computed at each month-end: discount = price / NAV - 1; z = (discount - 2y rolling mean)
/ 2y rolling sd. Buy the funds with z <= -1.5 (or the widest-5 cross-sectionally), hold one
month, equal weight, 5 bp per side (CEF spreads are wider than ETFs).
Baseline: equal-weight buy-and-hold of the same funds (the discount edge must beat the funds
themselves, not cash). Also the price-only version (just the fund's return) vs the "NAV
return" to show where the money comes from (discount narrowing vs the assets).
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import yfinance as yf

FUNDS = ["PEO", "GAM", "USA", "UTG", "UTF", "PDI", "PTY", "GOF", "DNP", "GAB", "BDJ", "HQH", "RQI", "JPC", "EOS", "ETY", "CII", "STK", "BST", "BME",
         "ETG", "EVT", "NFJ", "RNP", "EOI", "ETV", "THQ", "NIE", "BGY", "AWF", "HYT", "BLW", "EMD", "KYN", "NML"]


def tstat(x) -> float:
    x = pd.Series(x).dropna()
    return float(x.mean() / x.std() * np.sqrt(len(x))) if len(x) > 2 and x.std() > 0 else 0.0


def sh(x, ppy=12) -> float:
    x = pd.Series(x).dropna()
    return float(x.mean() / x.std() * np.sqrt(ppy)) if len(x) > 2 and x.std() > 0 else 0.0


def load() -> tuple[pd.DataFrame, pd.DataFrame]:
    px, nav = {}, {}
    for t in FUNDS:
        p = yf.Ticker(t).history(period="max", auto_adjust=False)
        n = yf.Ticker(f"X{t}X").history(period="max", auto_adjust=False)
        if len(p) < 500 or len(n) < 500:
            continue
        px[t] = p.Close.tz_localize(None); nav[t] = n.Close.tz_localize(None)
    P = pd.DataFrame(px); N = pd.DataFrame(nav)
    idx = P.index.union(N.index)
    return P.reindex(idx).ffill(), N.reindex(idx).ffill()


def main() -> None:
    P, N = load()
    P, N = P.dropna(how="all"), N.reindex(P.index)
    print(f"funds with price + NAV: {P.shape[1]}; {P.index[0].date()} -> {P.index[-1].date()}")
    disc = P / N - 1
    # total return needs dividends: use adjusted close ratio for returns
    adj = {}
    for t in P.columns:
        a = yf.Ticker(t).history(period="max", auto_adjust=True).Close.tz_localize(None)
        adj[t] = a
    A = pd.DataFrame(adj).reindex(P.index).ffill()
    me = P.resample("ME").last().index
    discm = disc.reindex(me, method="ffill")
    z = (discm - discm.rolling(24).mean()) / discm.rolling(24).std()
    retm = A.resample("ME").last().pct_change().shift(-1)  # next month's total return
    navm = N.resample("ME").last().pct_change().shift(-1)
    cost = 2 * 5e-4
    rows = []
    for d in me:
        zz = z.loc[d].dropna(); r = retm.loc[d]; nr = navm.loc[d]
        if len(zz) < 8 or r.isna().all():
            continue
        wide = zz[zz <= -1.5].index; narrow = zz[zz >= 1.5].index
        widest5 = zz.nsmallest(5).index
        rows.append({
            "date": d, "n": len(zz),
            "wide_z": r[wide].mean() - cost if len(wide) else np.nan, "n_wide": len(wide),
            "widest5": r[widest5].mean() - cost, "narrow_z": r[narrow].mean() - cost if len(narrow) else np.nan,
            "all_funds": r[zz.index].mean(), "all_nav": nr[zz.index].mean(),
            "widest5_nav": nr[widest5].mean(),
        })
    t = pd.DataFrame(rows).set_index("date")
    print(f"months {len(t)}, avg funds per month {t.n.mean():.0f}, months with a z<=-1.5 fund {t.n_wide.gt(0).mean():.0%}")
    for col, name in [("all_funds", "all funds equal-weight (benchmark)"), ("all_nav", "NAV return of all funds"), ("widest5", "widest-5 discounts vs own history, 1-month hold"), ("widest5_nav", "  ...their NAV return (asset part)"), ("wide_z", "funds with z <= -1.5"), ("narrow_z", "funds with z >= +1.5 (should be worse)")]:
        x = t[col].dropna()
        print(f"  {name:48s} n {len(x):3d}  mean {x.mean() * 100:+5.2f}%/mo  Sharpe {sh(x):+5.2f}  t {tstat(x):+4.1f}  halves {x.iloc[:len(x) // 2].mean() * 100:+.2f}/{x.iloc[len(x) // 2:].mean() * 100:+.2f}")
    ex = (t.widest5 - t.all_funds).dropna()
    print(f"  widest-5 minus all-funds: {ex.mean() * 100:+.2f}%/mo t {tstat(ex):+.1f} | by year: " + " ".join(f"{y}:{v * 100:+.1f}" for y, v in ex.groupby(ex.index.year).sum().items()))
    # placebo: random 5 funds each month
    rng = np.random.default_rng(1); pl = []
    for _ in range(200):
        vals = []
        for d in t.index:
            zz = z.loc[d].dropna(); r = retm.loc[d]
            pick = rng.choice(zz.index, size=min(5, len(zz)), replace=False)
            vals.append(r[pick].mean() - cost)
        pl.append(np.nanmean(vals))
    pl = np.array(pl)
    print(f"  placebo random-5: mean {pl.mean() * 100:+.2f}%/mo sd {pl.std() * 100:.2f} | p(placebo >= widest5) = {(pl >= t.widest5.mean()).mean():.3f}")


if __name__ == "__main__":
    main()
