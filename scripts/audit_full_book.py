"""Full-book construction audit: B + E + H + FOMC overlay, plus vol-targeting.

Extends audit_combined_be.py to the four validated/candidate components:

  B - TSMOM 10-ETF basket, monthly (deployable, 7/7)
  E - Overnight drift SPY/QQQ/IWM, daily -> monthly (deployable, 7/7)
  H - Commodity hedger pressure, weekly -> monthly (weak-pass)
  O - Pre-FOMC drift overlay: long SPY intraday on the two full trading
      days before each scheduled announcement (screen-pass 2026-07-11,
      placebo p=0.012). Uses only the *intraday* sessions so it is
      strictly incremental to E (which already holds every overnight).
      Requires data/fomc_dates.json (scraped from federalreserve.gov).

Questions answered:
  1. Does adding H and/or O to the audited B70/E30 book improve
     Sharpe AND MaxDD after correlations?
  2. Does book-level vol-targeting (no return forecast, trailing
     realized vol only) improve the chosen book?

Usage: python scripts/audit_full_book.py
"""
from __future__ import annotations

import json
import os
import time

import numpy as np
import pandas as pd
import yfinance as yf

from ten_cent_bot import commodity_cot as cc
from ten_cent_bot import overnight, tsmom

B_BASKET = ["SPY", "QQQ", "IWM", "EFA", "EEM", "TLT", "IEF", "GLD", "USO", "DBC"]
E_BASKET = ["SPY", "QQQ", "IWM"]
OVERLAY_COST_PER_SIDE = 0.0001  # 1bp/side on SPY


def sharpe(r: pd.Series, ppy: int = 12) -> float:
    r = r.dropna()
    if len(r) < 12 or r.std() == 0:
        return float("nan")
    return float(r.mean() / r.std() * np.sqrt(ppy))


def cagr(r: pd.Series, ppy: int = 12) -> float:
    r = r.dropna()
    return float((1 + r).prod() ** (ppy / len(r)) - 1)


def maxdd(r: pd.Series) -> float:
    eq = (1 + r.fillna(0)).cumprod()
    return float((eq / eq.cummax() - 1).min())


def to_monthly(daily: pd.Series) -> pd.Series:
    return (1 + daily.fillna(0)).groupby(pd.Grouper(freq="ME")).apply(lambda x: x.prod() - 1)


def build_components() -> pd.DataFrame:
    syms = list(dict.fromkeys(B_BASKET + E_BASKET))
    data = yf.download(syms, period="max", interval="1d", auto_adjust=True, progress=False)
    close, open_ = data["Close"], data["Open"]

    # --- B ---
    monthly_px = close[B_BASKET].resample("ME").last().dropna()
    b = tsmom.backtest(monthly_px, tsmom.TSMOMConfig())["monthly_return_net"].dropna()

    # --- E ---
    e_ohlc = {t: pd.DataFrame({"open": open_[t], "close": close[t]}).dropna() for t in E_BASKET}
    e_daily = overnight.backtest_portfolio(e_ohlc, overnight.OvernightConfig())["portfolio_return"].dropna()
    e = to_monthly(e_daily)

    # --- H (cross-sectional hedger pressure, repo default top-3 LS) ---
    hp_frame = {}
    for sym, cftc_name in cc.COMMODITY_UNIVERSE.items():
        try:
            cot = cc.fetch_disaggregated(cftc_name)
            if not cot.empty:
                hp_frame[sym] = cc.compute_hedger_pressure(cot)
        except Exception as exc:  # noqa: BLE001 - fetch robustness
            print(f"  H fetch failed for {sym}: {exc}")
        time.sleep(0.15)
    hp_df = pd.DataFrame(hp_frame).sort_index()
    px = yf.download(list(hp_df.columns), period="max", interval="1wk",
                     auto_adjust=True, progress=False)["Close"][hp_df.columns]
    hp_friday = hp_df.copy()
    hp_friday.index = hp_friday.index + pd.Timedelta(days=3)
    hp_aligned = hp_friday.reindex(px.index, method="ffill", limit=6)
    weekly_returns = px.pct_change()
    h_cfg = cc.HPConfig(cs_top_n=3)
    h_sig = cc.cross_sectional_signal(hp_aligned, h_cfg)
    h_weekly = cc.backtest_cross_sectional(
        h_sig, weekly_returns, h_cfg)["portfolio_return_net"].dropna()
    h = to_monthly(h_weekly)

    # --- O (pre-FOMC intraday overlay) ---
    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    fomc = json.load(open(os.path.join(repo, "data", "fomc_dates.json")))
    ann = pd.DatetimeIndex([pd.Timestamp(y, m, d) for y, m, d in fomc])
    spy = pd.DataFrame({"open": open_["SPY"], "close": close["SPY"]}).dropna()
    intraday = (spy["close"] / spy["open"] - 1)
    pos = spy.index.searchsorted(ann)
    pos = np.array([p for p, f in zip(pos, ann) if p < len(spy.index) and spy.index[p] == f])
    pos = pos[pos > 2]
    hold = np.zeros(len(spy), bool)
    hold[pos - 1] = True
    hold[pos - 2] = True
    o_daily = intraday.where(pd.Series(hold, index=spy.index), 0.0)
    o_daily[hold] -= 2 * OVERLAY_COST_PER_SIDE
    o = to_monthly(o_daily)

    df = pd.concat([b.rename("B"), e.rename("E"), h.rename("H"), o.rename("O")], axis=1).dropna()
    return df


def main() -> None:
    comp = build_components()
    print("=" * 70)
    print(f"FULL-BOOK AUDIT  {comp.index[0].date()} -> {comp.index[-1].date()}"
          f"  ({len(comp)} months)")
    print("=" * 70)

    print("\n[1] Components (overlap window, monthly):")
    for c in comp.columns:
        print(f"  {c}: Sharpe {sharpe(comp[c]):5.2f}  CAGR {cagr(comp[c])*100:5.2f}%"
              f"  AnnVol {comp[c].std()*np.sqrt(12)*100:5.2f}%  MaxDD {maxdd(comp[c])*100:6.1f}%")

    print("\n[2] Correlation matrix:")
    print(comp.corr().round(3).to_string())

    # --- weight grid: keep B:E at 70:30 of the residual, sweep H and O ---
    print("\n[3] Weight grid (B:E fixed 70:30 of residual; sweep w_H, w_O):")
    print(f"  {'w_H':>5} {'w_O':>5} {'Sharpe':>7} {'CAGR%':>7} {'MaxDD%':>7}")
    results = {}
    for w_h in [0.0, 0.05, 0.10, 0.15, 0.20]:
        for w_o in [0.0, 0.05, 0.10, 0.15]:
            resid = 1 - w_h - w_o
            w = {"B": 0.7 * resid, "E": 0.3 * resid, "H": w_h, "O": w_o}
            r = sum(comp[k] * v for k, v in w.items())
            results[(w_h, w_o)] = r
            print(f"  {w_h:5.2f} {w_o:5.2f} {sharpe(r):7.2f} {cagr(r)*100:7.2f} {maxdd(r)*100:7.1f}")

    base = results[(0.0, 0.0)]
    best_key = max(results, key=lambda k: sharpe(results[k]))
    best = results[best_key]
    print(f"\n  Baseline B70/E30:      Sharpe {sharpe(base):.2f}  MaxDD {maxdd(base)*100:.1f}%")
    print(f"  Best grid point {best_key}: Sharpe {sharpe(best):.2f}  MaxDD {maxdd(best)*100:.1f}%")

    print("\n[4] Best-point robustness:")
    half = len(best) // 2
    print(f"  Walk-forward halves: {sharpe(best.iloc[:half]):.2f} -> {sharpe(best.iloc[half:]):.2f}"
          f"   (baseline: {sharpe(base.iloc[:half]):.2f} -> {sharpe(base.iloc[half:]):.2f})")
    print("  4y sub-periods (best vs baseline):")
    y0s = range(comp.index[0].year, comp.index[-1].year, 4)
    for y0 in y0s:
        m = (best.index.year >= y0) & (best.index.year < y0 + 4)
        print(f"    {y0}-{y0+3}: {sharpe(best[m]):5.2f}  vs  {sharpe(base[m]):5.2f}")

    # --- [5] Vol targeting (book level) ---
    print("\n[5] Vol-targeting the book (trailing realized vol, no forecast):")
    target = 0.10
    for name, r in [("baseline B70/E30", base), (f"best {best_key}", best)]:
        for lb in (6, 12):
            vol = r.rolling(lb).std() * np.sqrt(12)
            lev = (target / vol).shift(1).clip(upper=2.0)
            rv = (r * lev).dropna()
            print(f"  {name:<20} lb={lb:>2}m: Sharpe {sharpe(rv):5.2f}  CAGR {cagr(rv)*100:5.2f}%"
                  f"  MaxDD {maxdd(rv)*100:6.1f}%   (static: {sharpe(r):.2f} / {maxdd(r)*100:.1f}%)")

    # --- [6] Placebo on the H+O addition ---
    print("\n[6] Placebo: does adding random noise sleeves 'improve' the book too?")
    rng = np.random.default_rng(0)
    w_h, w_o = best_key
    gains = []
    for _ in range(200):
        fake_h = pd.Series(rng.normal(comp["H"].mean(), comp["H"].std(), len(comp)), index=comp.index)
        fake_o = pd.Series(rng.normal(comp["O"].mean(), comp["O"].std(), len(comp)), index=comp.index)
        resid = 1 - w_h - w_o
        r = 0.7 * resid * comp["B"] + 0.3 * resid * comp["E"] + w_h * fake_h + w_o * fake_o
        gains.append(sharpe(r) - sharpe(base))
    gains = np.array(gains)
    real_gain = sharpe(best) - sharpe(base)
    print(f"  Real Sharpe gain {real_gain:+.3f} vs same-moment noise sleeves "
          f"{gains.mean():+.3f} +/- {gains.std():.3f},  P(noise >= real) = {(gains >= real_gain).mean():.3f}")


if __name__ == "__main__":
    main()
