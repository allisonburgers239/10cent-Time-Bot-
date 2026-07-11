"""Audit of Hong-Yogo hedger-pressure strategy on 12 commodity futures.

Sections:
  0. Hedger-pressure vs future returns per commodity (naked-eye correlation)
  1. Time-series long-only per commodity + equal-weight portfolio
  2. Walk-forward on the equal-weight time-series portfolio
  3. Cross-sectional long-short portfolio (Basu-Miffre variant)
  4. Sub-period analysis on the winning variant
  5. Parameter sensitivity grid
  6. Cost sensitivity
  7. Placebo (random HP ranks)
"""
from __future__ import annotations

import time

import numpy as np
import pandas as pd
import yfinance as yf

from ten_cent_bot import commodity_cot as cc


def fetch_all() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    print("Fetching Disaggregated COT for 12 commodities ...")
    hp_frame = {}
    for sym, cftc_name in cc.COMMODITY_UNIVERSE.items():
        try:
            cot = cc.fetch_disaggregated(cftc_name)
            if not cot.empty:
                hp = cc.compute_hedger_pressure(cot)
                hp_frame[sym] = hp
                print(f"  {sym:>4}  {len(hp):>4} weekly obs, "
                      f"{hp.index.min().date()} -> {hp.index.max().date()}")
            else:
                print(f"  {sym:>4}  no COT data")
        except Exception as e:
            print(f"  {sym:>4}  fetch failed: {e}")
        time.sleep(0.15)

    hp_df = pd.DataFrame(hp_frame).sort_index()

    print("\nFetching weekly prices ...")
    yf_syms = list(hp_df.columns)
    px = yf.download(yf_syms, period="max", interval="1wk", auto_adjust=True, progress=False)
    if isinstance(px.columns, pd.MultiIndex):
        close = px["Close"]
    else:
        close = px[["Close"]].rename(columns={"Close": yf_syms[0]})
    close = close[hp_df.columns]  # order-match
    print(f"  Weekly closes: {close.index.min().date()} -> {close.index.max().date()}, "
          f"{close.shape[0]} bars, {close.shape[1]} contracts")

    # Align HP to weekly Friday dates
    hp_friday = hp_df.copy()
    hp_friday.index = hp_friday.index + pd.Timedelta(days=3)
    hp_aligned = hp_friday.reindex(close.index, method="ffill", limit=6)
    weekly_returns = close.pct_change()
    return hp_aligned, close, weekly_returns


def _s(ret):
    return cc.summary_from_returns(ret)


# ---------- Section 0 ----------


def section_hp_predictive_check(hp_aligned: pd.DataFrame, weekly_returns: pd.DataFrame) -> None:
    print("\n=== 0. HP -> future return correlation per commodity ===")
    print("  Positive coef = higher HP => higher next-week return (Hong-Yogo direction)")
    print(f"  {'sym':>5}  {'obs':>5}  {'corr(HP_t, ret_t+1)':>22}  {'mean HP':>7}")
    print("  " + "-" * 52)
    rows = []
    for sym in hp_aligned.columns:
        hp = hp_aligned[sym]
        ret_next = weekly_returns[sym].shift(-1)
        both = pd.concat([hp, ret_next], axis=1).dropna()
        if len(both) < 100:
            continue
        corr = both.corr().iloc[0, 1]
        rows.append((sym, len(both), corr, hp.mean()))
        print(f"  {sym:>5}  {len(both):>5}  {corr:>+22.4f}  {hp.mean():>+7.3f}")
    if rows:
        avg = np.mean([r[2] for r in rows])
        pos = sum(1 for r in rows if r[2] > 0)
        print(f"\n  Mean corr across commodities: {avg:+.4f}")
        print(f"  Commodities with positive HP->return correlation: {pos}/{len(rows)}")


# ---------- Section 1 ----------


def section_time_series_per_commodity(hp_aligned: pd.DataFrame, weekly_returns: pd.DataFrame) -> None:
    print("\n=== 1. Time-series long-only per commodity (HP > median => long) ===")
    cfg = cc.HPConfig(signal_mode="time_series")
    rows = []
    equity_curves = {}
    print(f"  {'sym':>5}  {'Strat Sharpe':>13}  {'B&H Sharpe':>11}  {'Strat CAGR':>11}  {'B&H CAGR':>10}")
    print("  " + "-" * 58)
    for sym in hp_aligned.columns:
        hp = hp_aligned[sym]
        sig = cc.time_series_signal(hp, cfg)
        combined = pd.DataFrame({
            "signal": sig,
            "weekly_return": weekly_returns[sym],
        }).dropna()
        if len(combined) < 100:
            continue
        result = cc.backtest_time_series(combined, cfg)
        st = _s(result["net_return"])
        bh = _s(combined["weekly_return"])
        rows.append({
            "sym": sym,
            "strat_sharpe": st.get("sharpe", 0),
            "strat_cagr": st.get("cagr", 0),
            "bh_sharpe": bh.get("sharpe", 0),
            "bh_cagr": bh.get("cagr", 0),
        })
        equity_curves[sym] = result["net_return"]
        print(f"  {sym:>5}  {st.get('sharpe', 0):>13.3f}  {bh.get('sharpe', 0):>11.3f}  "
              f"{st.get('cagr', 0):>11.4f}  {bh.get('cagr', 0):>10.4f}")

    # Equal-weight portfolio across commodities
    if equity_curves:
        panel = pd.DataFrame(equity_curves)
        port = panel.mean(axis=1)
        s = _s(port)
        # Buy-and-hold equal-weight benchmark
        bh_panel = weekly_returns[list(equity_curves.keys())].dropna(how="all")
        bh_port = bh_panel.mean(axis=1)
        bh_s = _s(bh_port)
        print(f"\n  {'Equal-weight portfolio':>28}: Sharpe {s.get('sharpe', 0):>6.3f}  "
              f"CAGR {s.get('cagr', 0):>+.4f}  MaxDD {s.get('max_drawdown', 0):>+.3f}")
        print(f"  {'B&H equal-weight benchmark':>28}: Sharpe {bh_s.get('sharpe', 0):>6.3f}  "
              f"CAGR {bh_s.get('cagr', 0):>+.4f}  MaxDD {bh_s.get('max_drawdown', 0):>+.3f}")


# ---------- Section 3 (cross-sectional) ----------


def section_cross_sectional(hp_aligned: pd.DataFrame, weekly_returns: pd.DataFrame) -> pd.Series:
    print("\n=== 3. Cross-Sectional Long-Short (Basu-Miffre variant) ===")
    for top_n in [2, 3, 4]:
        for long_only in [False, True]:
            cfg = cc.HPConfig(cs_top_n=top_n, cs_long_only=long_only)
            sig = cc.cross_sectional_signal(hp_aligned, cfg)
            r = cc.backtest_cross_sectional(sig, weekly_returns, cfg)
            s = _s(r["portfolio_return_net"])
            side = "long-only" if long_only else "long-short"
            print(f"  top_n={top_n}, {side:>10}: "
                  f"Sharpe {s.get('sharpe', 0):>6.3f}, "
                  f"CAGR {s.get('cagr', 0):>+.4f}, "
                  f"MaxDD {s.get('max_drawdown', 0):>+.3f}")
    # Return the default (top_n=3, long-short) for downstream use
    cfg = cc.HPConfig(cs_top_n=3, cs_long_only=False)
    sig = cc.cross_sectional_signal(hp_aligned, cfg)
    return cc.backtest_cross_sectional(sig, weekly_returns, cfg)["portfolio_return_net"]


def section_walk_forward(portfolio_ret: pd.Series) -> None:
    print("\n=== 2. Walk-Forward on cross-sectional portfolio (top-3 long-short) ===")
    ret = portfolio_ret.dropna()
    n = len(ret)
    split = n // 2
    tr = ret.iloc[:split]
    te = ret.iloc[split:]
    st = _s(tr)
    se = _s(te)
    delta = abs(st.get("sharpe", 0) - se.get("sharpe", 0))
    print(f"  Train ({tr.index.min().date()} -> {tr.index.max().date()}): Sharpe {st['sharpe']:.3f}")
    print(f"  Test  ({te.index.min().date()} -> {te.index.max().date()}): Sharpe {se['sharpe']:.3f}")
    print(f"  Delta {delta:.3f}  =>  {'CONSISTENT' if delta < 0.35 else 'DIVERGENT'}")


def section_sub_periods(portfolio_ret: pd.Series) -> None:
    print("\n=== 4. Sub-Period Analysis (annual buckets) on cross-sectional portfolio ===")
    ret = portfolio_ret.dropna()
    rows = []
    for year in sorted(set(ret.index.year)):
        sub = ret[ret.index.year == year]
        if len(sub) < 20:
            continue
        s = _s(sub)
        rows.append({"year": year, "sharpe": s["sharpe"], "cagr": s["cagr"]})
    df = pd.DataFrame(rows)
    print(df.to_string(index=False))
    print(f"\n  Years positive Sharpe: {(df['sharpe'] > 0).sum()}/{len(df)}")


def section_parameter_sensitivity(hp_aligned: pd.DataFrame, weekly_returns: pd.DataFrame) -> None:
    print("\n=== 5. Parameter Sensitivity (cross-sectional grid) ===")
    rows = []
    for lb in [26, 52, 104]:
        for top_n in [2, 3, 4]:
            for long_only in [False, True]:
                cfg = cc.HPConfig(lookback_weeks=lb, cs_top_n=top_n, cs_long_only=long_only)
                sig = cc.cross_sectional_signal(hp_aligned, cfg)
                r = cc.backtest_cross_sectional(sig, weekly_returns, cfg)
                s = _s(r["portfolio_return_net"])
                rows.append({
                    "lb": lb, "top_n": top_n, "long_only": long_only,
                    "sharpe": s.get("sharpe", 0),
                    "cagr": s.get("cagr", 0),
                })
    df = pd.DataFrame(rows)
    print(f"  Configs tested: {len(df)}")
    print(f"  Sharpe mean +/- std: {df['sharpe'].mean():.3f} +/- {df['sharpe'].std():.3f}")
    print(f"  Sharpe min / median / max: "
          f"{df['sharpe'].min():.3f} / {df['sharpe'].median():.3f} / {df['sharpe'].max():.3f}")
    print(f"  % configs positive: {(df['sharpe'] > 0).mean():.1%}")
    print(f"  % configs > 0.3:    {(df['sharpe'] > 0.3).mean():.1%}")


def section_cost_sensitivity(hp_aligned: pd.DataFrame, weekly_returns: pd.DataFrame) -> None:
    print("\n=== 6. Cost Sensitivity ===")
    rows = []
    for bps in [0, 5, 10, 20, 50]:
        cfg = cc.HPConfig(cost_bps_per_change=bps)
        sig = cc.cross_sectional_signal(hp_aligned, cfg)
        r = cc.backtest_cross_sectional(sig, weekly_returns, cfg)
        s = _s(r["portfolio_return_net"])
        rows.append({"cost_bps": bps, "sharpe": s.get("sharpe", 0), "cagr": s.get("cagr", 0)})
    print(pd.DataFrame(rows).to_string(index=False))


def section_placebo(hp_aligned: pd.DataFrame, weekly_returns: pd.DataFrame, n_seeds: int = 100) -> None:
    print(f"\n=== 7. Random-Rank Placebo ({n_seeds} seeds) ===")
    cfg = cc.HPConfig()
    real_sig = cc.cross_sectional_signal(hp_aligned, cfg)
    real_stats = _s(
        cc.backtest_cross_sectional(real_sig, weekly_returns, cfg)["portfolio_return_net"]
    )
    real = real_stats.get("sharpe", 0)

    rng = np.random.default_rng(42)
    n_stocks = hp_aligned.shape[1]
    weight = 1.0 / cfg.cs_top_n
    placebo_sharpes = []
    for _ in range(n_seeds):
        random_ranks = pd.DataFrame(
            np.array([rng.permutation(np.arange(1, n_stocks + 1)) for _ in range(len(hp_aligned))]),
            index=hp_aligned.index,
            columns=hp_aligned.columns,
        )
        placebo_sig = pd.DataFrame(0.0, index=hp_aligned.index, columns=hp_aligned.columns)
        placebo_sig[random_ranks <= cfg.cs_top_n] = weight
        placebo_sig[random_ranks > (n_stocks - cfg.cs_top_n)] = -weight
        r = cc.backtest_cross_sectional(placebo_sig, weekly_returns, cfg)
        s = _s(r["portfolio_return_net"])
        placebo_sharpes.append(s.get("sharpe", 0))

    arr = np.array(placebo_sharpes)
    p = float((arr >= real).mean())
    print(f"  Real HP-signal Sharpe:  {real:.4f}")
    print(f"  Placebo mean +/- std:   {arr.mean():.4f} +/- {arr.std():.4f}")
    print(f"  Placebo p5 / p95:       {np.percentile(arr, 5):.3f} / {np.percentile(arr, 95):.3f}")
    print(f"  P(placebo >= real):     {p:.3f}")
    verdict = "REAL EDGE" if p < 0.05 else "WEAK EDGE" if p < 0.20 else "NO EDGE"
    print(f"  Verdict: {verdict}")


def main() -> None:
    hp_aligned, close, weekly_returns = fetch_all()
    print(f"\nAligned HP frame: {hp_aligned.shape[0]} weeks x {hp_aligned.shape[1]} commodities")

    section_hp_predictive_check(hp_aligned, weekly_returns)
    section_time_series_per_commodity(hp_aligned, weekly_returns)
    portfolio_ret = section_cross_sectional(hp_aligned, weekly_returns)
    section_walk_forward(portfolio_ret)
    section_sub_periods(portfolio_ret)
    section_parameter_sensitivity(hp_aligned, weekly_returns)
    section_cost_sensitivity(hp_aligned, weekly_returns)
    section_placebo(hp_aligned, weekly_returns)

    print("\n=== Audit complete ===")


if __name__ == "__main__":
    main()
