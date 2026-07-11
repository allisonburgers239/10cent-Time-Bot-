"""7-section robustness audit for the combined B + E portfolio.

Sleeve B (TSMOM on 10-ETF basket, monthly rebalance) and Sleeve E
(overnight drift on SPY/QQQ/IWM, daily hold-and-flip) are naturally
uncorrelated - different asset class, different frequency, different
signal type. If the theory holds, combining them should meaningfully
improve Sharpe over either alone.

Approach:
  - Sleeve B produces monthly net returns (via tsmom.backtest).
  - Sleeve E produces daily net returns (via overnight.backtest_portfolio).
  - Resample E's daily returns to monthly via compound aggregation.
  - Combine with a fixed weight w_b, w_e = (1 - w_b) at monthly frequency.
  - Run the standard 7-section audit on the combined monthly return stream.

Overlap window: both sleeves need to have data. B (ETFs) starts 2007
after all 10 have listed; E starts 1993 (SPY inception). Combined
analysis is on the intersection = 2007-2026 (~19 years).
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import yfinance as yf

from ten_cent_bot import overnight, tsmom

B_BASKET = ["SPY", "QQQ", "IWM", "EFA", "EEM", "TLT", "IEF", "GLD", "USO", "DBC"]
E_BASKET = ["SPY", "QQQ", "IWM"]


def fetch_data() -> tuple[pd.DataFrame, dict[str, pd.DataFrame]]:
    """Fetch both baskets in one yfinance call. Returns (monthly_b, daily_e_ohlc)."""
    all_syms = list(dict.fromkeys(B_BASKET + E_BASKET))  # dedupe preserving order
    data = yf.download(all_syms, period="max", interval="1d", auto_adjust=True, progress=False)

    close = data["Close"]
    open_ = data["Open"]

    # Sleeve B: monthly closes for the 10-ETF basket
    monthly_b = close[B_BASKET].resample("ME").last().dropna()

    # Sleeve E: daily open/close per ticker
    e_ohlc: dict[str, pd.DataFrame] = {}
    for tkr in E_BASKET:
        df = pd.DataFrame({"open": open_[tkr], "close": close[tkr]}).dropna()
        e_ohlc[tkr] = df

    return monthly_b, e_ohlc


def sleeve_b_monthly(monthly_prices: pd.DataFrame, cfg: tsmom.TSMOMConfig | None = None) -> pd.Series:
    result = tsmom.backtest(monthly_prices, cfg or tsmom.TSMOMConfig())
    return result["monthly_return_net"].dropna().rename("B")


def sleeve_e_daily(e_ohlc: dict[str, pd.DataFrame], cfg: overnight.OvernightConfig | None = None) -> pd.Series:
    result = overnight.backtest_portfolio(e_ohlc, cfg or overnight.OvernightConfig())
    return result["portfolio_return"].dropna().rename("E_daily")


def daily_to_monthly(daily_returns: pd.Series) -> pd.Series:
    """Compound daily returns into month-end monthly returns."""
    return (1 + daily_returns.fillna(0)).groupby(pd.Grouper(freq="ME")).apply(
        lambda x: x.prod() - 1
    )


def combine(b_ret: pd.Series, e_ret: pd.Series, w_b: float = 0.5) -> pd.DataFrame:
    """Align and combine two monthly return streams. Returns DataFrame [B, E, combined]."""
    w_e = 1.0 - w_b
    df = pd.concat(
        [b_ret.rename("B"), e_ret.rename("E")], axis=1, sort=False
    ).dropna()
    df["combined"] = w_b * df["B"] + w_e * df["E"]
    return df


def sharpe(ret: pd.Series, periods_per_year: int = 12) -> float:
    ret = ret.dropna()
    if len(ret) == 0 or ret.std(ddof=0) == 0:
        return 0.0
    return float(ret.mean() / ret.std(ddof=0) * np.sqrt(periods_per_year))


def annual_return(ret: pd.Series, periods_per_year: int = 12) -> float:
    ret = ret.dropna()
    if len(ret) == 0:
        return 0.0
    return float((1 + ret.mean()) ** periods_per_year - 1)


def annual_vol(ret: pd.Series, periods_per_year: int = 12) -> float:
    return float(ret.std(ddof=0) * np.sqrt(periods_per_year))


def max_dd(ret: pd.Series) -> float:
    eq = (1 + ret.fillna(0)).cumprod()
    if len(eq) == 0:
        return 0.0
    return float((eq / eq.cummax() - 1).min())


def summary(ret: pd.Series) -> dict:
    return {
        "months": int(len(ret.dropna())),
        "cagr": annual_return(ret),
        "annual_vol": annual_vol(ret),
        "sharpe": sharpe(ret),
        "max_drawdown": max_dd(ret),
    }


# -------------------- Section 0: individual + combined --------------------


def section_zero(b_ret: pd.Series, e_ret_monthly: pd.Series) -> None:
    print("\n=== 0. Individual Sleeves + Combined (baseline w_b=0.50) ===")
    df = combine(b_ret, e_ret_monthly, w_b=0.5)
    combined = df["combined"]

    print(f"  {'Series':>12}  {'Sharpe':>7}  {'CAGR':>8}  {'AnnVol':>7}  {'MaxDD':>7}")
    print("  " + "-" * 52)
    for name, series in [("Sleeve B", df["B"]), ("Sleeve E", df["E"]), ("Combined", combined)]:
        s = summary(series)
        print(
            f"  {name:>12}  {s['sharpe']:>7.3f}  {s['cagr']:>8.4f}  "
            f"{s['annual_vol']:>7.4f}  {s['max_drawdown']:>7.4f}"
        )

    corr = df["B"].corr(df["E"])
    print(f"\n  Correlation B <-> E:  {corr:+.3f}")
    print(f"  Period:              {df.index.min().date()} -> {df.index.max().date()}")
    print(f"  Overlapping months:  {len(df)}")


# -------------------- Sections 1-7 (audit on combined) --------------------


def section_baseline(b_ret: pd.Series, e_ret_monthly: pd.Series) -> None:
    print("\n=== 1. Baseline combined (w_b=0.50) ===")
    combined = combine(b_ret, e_ret_monthly, w_b=0.5)["combined"]
    s = summary(combined)
    for k, v in s.items():
        print(f"  {k:>15}: {v}")


def section_walk_forward(b_ret: pd.Series, e_ret_monthly: pd.Series) -> None:
    print("\n=== 2. Walk-Forward (train / test) ===")
    df = combine(b_ret, e_ret_monthly, w_b=0.5)
    combined = df["combined"]
    n = len(combined)
    split = n // 2
    tr = combined.iloc[:split]
    te = combined.iloc[split:]
    s_tr, s_te = summary(tr), summary(te)
    print(
        f"  Train ({tr.index.min().date()} -> {tr.index.max().date()}, {len(tr)}m): "
        f"Sharpe {s_tr['sharpe']:.3f}, MaxDD {s_tr['max_drawdown']:.3f}"
    )
    print(
        f"  Test  ({te.index.min().date()} -> {te.index.max().date()}, {len(te)}m): "
        f"Sharpe {s_te['sharpe']:.3f}, MaxDD {s_te['max_drawdown']:.3f}"
    )
    delta = abs(s_tr["sharpe"] - s_te["sharpe"])
    print(f"  delta = {delta:.3f}  =>  {'CONSISTENT' if delta < 0.35 else 'DIVERGENT'}")


def section_weight_sensitivity(b_ret: pd.Series, e_ret_monthly: pd.Series) -> None:
    print("\n=== 3. Weight Sensitivity (w_b, w_e = 1-w_b) ===")

    # Fixed grid
    print(f"  {'w_b':>6}  {'w_e':>6}  {'Sharpe':>7}  {'CAGR':>8}  {'AnnVol':>7}  {'MaxDD':>7}")
    print("  " + "-" * 54)
    best_sharpe, best_w = -np.inf, None
    for w_b in [0.0, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 1.0]:
        combined = combine(b_ret, e_ret_monthly, w_b=w_b)["combined"]
        s = summary(combined)
        marker = "  <-" if s["sharpe"] > best_sharpe else ""
        if s["sharpe"] > best_sharpe:
            best_sharpe, best_w = s["sharpe"], w_b
        print(
            f"  {w_b:>6.2f}  {1 - w_b:>6.2f}  {s['sharpe']:>7.3f}  "
            f"{s['cagr']:>8.4f}  {s['annual_vol']:>7.4f}  {s['max_drawdown']:>7.4f}"
        )
    print(f"\n  Sharpe-max weight:  w_b={best_w:.2f}")

    # Risk parity (inverse-vol on full sample)
    df = combine(b_ret, e_ret_monthly, w_b=0.5)
    b_vol = df["B"].std(ddof=0)
    e_vol = df["E"].std(ddof=0)
    rp_w_b = (1 / b_vol) / ((1 / b_vol) + (1 / e_vol))
    rp_combined = combine(b_ret, e_ret_monthly, w_b=rp_w_b)["combined"]
    rp_stats = summary(rp_combined)
    print(
        f"\n  Risk-parity (inverse-vol on full sample, w_b={rp_w_b:.3f}):  "
        f"Sharpe {rp_stats['sharpe']:.3f}, CAGR {rp_stats['cagr']:.4f}, "
        f"MaxDD {rp_stats['max_drawdown']:.4f}"
    )


def section_sub_periods(b_ret: pd.Series, e_ret_monthly: pd.Series) -> None:
    print("\n=== 4. Sub-Period Analysis (rolling 4y windows on combined 50/50) ===")
    combined = combine(b_ret, e_ret_monthly, w_b=0.5)["combined"]
    period = 48
    rows = []
    n = len(combined)
    for start in range(0, n - period + 1, 24):
        end = min(start + period, n)
        sub = combined.iloc[start:end]
        if len(sub) < 24:
            continue
        s = summary(sub)
        rows.append(
            {
                "from": sub.index[0].date(),
                "to": sub.index[-1].date(),
                "sharpe": s["sharpe"],
                "cagr": s["cagr"],
                "max_dd": s["max_drawdown"],
            }
        )
    df = pd.DataFrame(rows)
    print(df.to_string(index=False))
    print(f"\n  Sub-periods Sharpe > 0:    {(df['sharpe'] > 0).sum()}/{len(df)}")
    print(f"  Sub-periods Sharpe > 0.5:  {(df['sharpe'] > 0.5).sum()}/{len(df)}")
    print(f"  Sub-periods Sharpe > 1.0:  {(df['sharpe'] > 1.0).sum()}/{len(df)}")


def section_leave_one_out(b_ret: pd.Series, e_ret_monthly: pd.Series) -> None:
    print("\n=== 5. Leave-One-Sleeve-Out (does the combination beat each solo?) ===")
    df = combine(b_ret, e_ret_monthly, w_b=0.5)
    for name, series in [
        ("Sleeve B alone",  df["B"]),
        ("Sleeve E alone",  df["E"]),
        ("Combined 50/50",  df["combined"]),
    ]:
        s = summary(series)
        print(
            f"  {name:>18}: Sharpe {s['sharpe']:.3f}, CAGR {s['cagr']:.4f}, "
            f"MaxDD {s['max_drawdown']:.3f}"
        )


def section_cost_sensitivity(monthly_b: pd.DataFrame, e_ohlc: dict[str, pd.DataFrame]) -> None:
    print("\n=== 6. Cost Sensitivity (both sleeves scale up together) ===")
    print(f"  {'B cost bps':>10}  {'E bps/side':>10}  {'Sharpe':>7}  {'CAGR':>8}")
    print("  " + "-" * 42)
    for b_bps, e_bps in [(0, 0.0), (5, 0.5), (10, 1.0), (20, 2.0), (50, 5.0), (100, 10.0)]:
        b_r = sleeve_b_monthly(monthly_b, tsmom.TSMOMConfig(transaction_cost_bps=b_bps))
        e_r_daily = sleeve_e_daily(e_ohlc, overnight.OvernightConfig(cost_bps_per_side=e_bps))
        e_r_monthly = daily_to_monthly(e_r_daily)
        combined = combine(b_r, e_r_monthly, w_b=0.5)["combined"]
        s = summary(combined)
        print(f"  {b_bps:>10.0f}  {e_bps:>10.1f}  {s['sharpe']:>7.3f}  {s['cagr']:>8.4f}")


def section_placebo(
    monthly_b: pd.DataFrame,
    e_ohlc: dict[str, pd.DataFrame],
    n_seeds: int = 60,
) -> None:
    """Placebo: random signal in BOTH sleeves, then combine. If real combined
    beats the combined-random-placebo distribution, the joint edge is real."""
    print(f"\n=== 7. Combined Placebo (random signals in both sleeves, {n_seeds} seeds) ===")

    # Real combined
    b_r_real = sleeve_b_monthly(monthly_b, tsmom.TSMOMConfig())
    e_r_real_daily = sleeve_e_daily(e_ohlc, overnight.OvernightConfig())
    e_r_real = daily_to_monthly(e_r_real_daily)
    real_sharpe = summary(combine(b_r_real, e_r_real, w_b=0.5)["combined"])["sharpe"]

    # Precompute stuff for random B: use same vol scaling as real
    cfg_b = tsmom.TSMOMConfig()
    long_lb = cfg_b.lookback_months
    b_returns_full = monthly_b.pct_change()
    realized_vol = b_returns_full.rolling(long_lb).std() * np.sqrt(12)
    raw_weight = (cfg_b.target_vol / realized_vol).clip(upper=cfg_b.max_leverage)

    # Precompute per-ticker overnight returns for random E
    e_on_rets_frame = pd.DataFrame(
        {t: overnight.compute_overnight_returns(df) for t, df in e_ohlc.items()}
    ).dropna(how="all")

    rng = np.random.default_rng(42)
    placebo_sharpes = []
    cfg_e = overnight.OvernightConfig()
    for _ in range(n_seeds):
        # Random-signal Sleeve B
        signs_b = pd.DataFrame(
            rng.choice([-1.0, 1.0], size=monthly_b.shape),
            index=monthly_b.index,
            columns=monthly_b.columns,
        )
        pos_b = (raw_weight * signs_b).shift(1)
        asset_pnl = pos_b * b_returns_full
        port_gross = asset_pnl.mean(axis=1)
        cost_b = pos_b.diff().abs().mean(axis=1) * cfg_b.transaction_cost_bps / 10_000.0
        b_random_monthly = (port_gross - cost_b).dropna()

        # Random-direction Sleeve E
        signs_e = pd.DataFrame(
            rng.choice([-1.0, 1.0], size=e_on_rets_frame.shape),
            index=e_on_rets_frame.index,
            columns=e_on_rets_frame.columns,
        )
        e_random_daily_gross = (signs_e * e_on_rets_frame).mean(axis=1)
        # Same cost model as real E: 2bps per hold-day
        e_random_daily_cost = pd.Series(cfg_e.cost_bps_per_side * 2 / 10_000.0, index=e_random_daily_gross.index)
        e_random_daily = e_random_daily_gross - e_random_daily_cost
        e_random_monthly = daily_to_monthly(e_random_daily)

        combined_random = combine(b_random_monthly, e_random_monthly, w_b=0.5)["combined"]
        placebo_sharpes.append(sharpe(combined_random))

    arr = np.array(placebo_sharpes)
    p = float((arr >= real_sharpe).mean())
    print(f"  Real combined Sharpe:       {real_sharpe:.4f}")
    print(f"  Placebo mean +/- std:       {arr.mean():.4f} +/- {arr.std():.4f}")
    print(f"  Placebo p5 / p95:           {np.percentile(arr, 5):.3f} / {np.percentile(arr, 95):.3f}")
    print(f"  P(placebo >= real):         {p:.3f}")
    verdict = "REAL EDGE" if p < 0.05 else "WEAK EDGE" if p < 0.20 else "NO EDGE"
    print(f"  Verdict: {verdict}")


def main() -> None:
    print("Fetching data ...")
    monthly_b, e_ohlc = fetch_data()
    print(f"  Sleeve B monthly bars: {monthly_b.index.min().date()} -> "
          f"{monthly_b.index.max().date()} ({len(monthly_b)} months, {monthly_b.shape[1]} ETFs)")
    for t, df in e_ohlc.items():
        print(f"  Sleeve E {t} daily: {df.index.min().date()} -> "
              f"{df.index.max().date()} ({len(df):,} days)")

    b_r = sleeve_b_monthly(monthly_b)
    e_r_daily = sleeve_e_daily(e_ohlc)
    e_r_monthly = daily_to_monthly(e_r_daily)

    section_zero(b_r, e_r_monthly)
    section_baseline(b_r, e_r_monthly)
    section_walk_forward(b_r, e_r_monthly)
    section_weight_sensitivity(b_r, e_r_monthly)
    section_sub_periods(b_r, e_r_monthly)
    section_leave_one_out(b_r, e_r_monthly)
    section_cost_sensitivity(monthly_b, e_ohlc)
    section_placebo(monthly_b, e_ohlc, n_seeds=60)

    print("\n=== Audit complete ===")


if __name__ == "__main__":
    main()
