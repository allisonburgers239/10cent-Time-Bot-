"""7-section robustness audit for overnight drift on SPY/QQQ/IWM.

Includes a special "Section 0" that decomposes total return into
overnight vs intraday — the direct empirical test of the anomaly.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import yfinance as yf

from ten_cent_bot import overnight

TICKERS = ["SPY", "QQQ", "IWM"]


def fetch_daily_ohlc() -> dict[str, pd.DataFrame]:
    data = yf.download(
        TICKERS, period="max", interval="1d", auto_adjust=True, progress=False
    )
    per: dict[str, pd.DataFrame] = {}
    for t in TICKERS:
        df = pd.DataFrame({"open": data["Open"][t], "close": data["Close"][t]}).dropna()
        per[t] = df
    return per


def _s(ret: pd.Series) -> dict:
    return overnight.summary_from_returns(ret)


# ---------- Section 0: overnight vs intraday decomposition ----------


def section_decomposition(data: dict[str, pd.DataFrame]) -> None:
    print("\n=== 0. Anomaly Check: Overnight vs Intraday vs Buy-and-Hold ===")
    print(f"  {'':6}  {'Series':>10}  {'CAGR':>8}  {'Vol':>7}  {'Sharpe':>7}  {'MaxDD':>7}")
    print("  " + "-" * 62)
    for ticker, df in data.items():
        on = overnight.compute_overnight_returns(df)
        intra = overnight.compute_intraday_returns(df)
        buy = df["close"].pct_change()
        for name, series in [("Overnight", on), ("Intraday", intra), ("Buy-Hold", buy)]:
            s = _s(series)
            print(
                f"  {ticker:>6}  {name:>10}  {s.get('cagr', 0):>8.4f}  "
                f"{s.get('annual_vol', 0):>7.4f}  {s.get('sharpe', 0):>7.3f}  "
                f"{s.get('max_drawdown', 0):>7.3f}"
            )
        print()


# ---------- Sections 1-7 (standard harness) ----------


def section_baseline(data: dict[str, pd.DataFrame]) -> None:
    print("\n=== 1. Baseline (long overnight, all 3 tickers, 1bp/side cost) ===")
    cfg = overnight.OvernightConfig()
    for ticker, df in data.items():
        r = overnight.backtest_single(df, cfg)
        s = _s(r["net_return"])
        print(
            f"  {ticker}: Sharpe {s.get('sharpe', 0):>6.3f}, CAGR {s.get('cagr', 0):.4f}, "
            f"MaxDD {s.get('max_drawdown', 0):.3f}, win {s.get('win_rate', 0):.1%}, "
            f"days {s.get('days', 0)}"
        )
    port = overnight.backtest_portfolio(data, cfg)
    ps = _s(port["portfolio_return"])
    print(
        f"\n  Portfolio equal-weight: Sharpe {ps.get('sharpe', 0):>6.3f}, "
        f"CAGR {ps.get('cagr', 0):.4f}, MaxDD {ps.get('max_drawdown', 0):.3f}"
    )


def section_walk_forward(data: dict[str, pd.DataFrame]) -> None:
    print("\n=== 2. Walk-Forward (train / test) ===")
    cfg = overnight.OvernightConfig()
    for ticker, df in data.items():
        n = len(df)
        split = n // 2
        tr = df.iloc[:split]
        te = df.iloc[split:]
        st = _s(overnight.backtest_single(tr, cfg)["net_return"])
        se = _s(overnight.backtest_single(te, cfg)["net_return"])
        delta = abs(st.get("sharpe", 0) - se.get("sharpe", 0))
        print(
            f"  {ticker}: train Sharpe={st.get('sharpe', 0):>6.3f} "
            f"({tr.index.min().date()} -> {tr.index.max().date()}), "
            f"test Sharpe={se.get('sharpe', 0):>6.3f} "
            f"({te.index.min().date()} -> {te.index.max().date()}), delta={delta:.3f}"
        )


def section_parameter_sensitivity(data: dict[str, pd.DataFrame]) -> None:
    print("\n=== 3. Parameter Sensitivity ===")
    rows = []
    for cost_bps in [0.5, 1.0, 2.0, 5.0]:
        for use_trend in [False, True]:
            for exclude in [(), (4,), (0,), (0, 4)]:
                cfg = overnight.OvernightConfig(
                    cost_bps_per_side=cost_bps,
                    use_trend_filter=use_trend,
                    exclude_days_of_week=exclude,
                )
                port = overnight.backtest_portfolio(data, cfg)
                s = _s(port["portfolio_return"])
                rows.append(
                    {
                        "cost_bps": cost_bps,
                        "trend_filter": use_trend,
                        "exclude_dow": str(exclude),
                        "sharpe": s.get("sharpe", 0),
                        "cagr": s.get("cagr", 0),
                    }
                )
    df = pd.DataFrame(rows)
    print(f"  Configs tested:            {len(df)}")
    print(f"  Sharpe mean +/- std:       {df['sharpe'].mean():.3f} +/- {df['sharpe'].std():.3f}")
    print(f"  Sharpe min / median / max: {df['sharpe'].min():.3f} / {df['sharpe'].median():.3f} / {df['sharpe'].max():.3f}")
    print(f"  % configs Sharpe > 0.5:    {(df['sharpe'] > 0.5).mean():.1%}")
    best = df.iloc[df["sharpe"].idxmax()]
    worst = df.iloc[df["sharpe"].idxmin()]
    print(f"  Best:  {best.to_dict()}")
    print(f"  Worst: {worst.to_dict()}")


def section_sub_periods(data: dict[str, pd.DataFrame]) -> None:
    print("\n=== 4. Sub-Period Analysis (5-year windows on portfolio) ===")
    cfg = overnight.OvernightConfig()
    port = overnight.backtest_portfolio(data, cfg)
    port_ret = port["portfolio_return"].dropna()
    years = pd.Series(port_ret.index.year)
    rows = []
    for start in range(int(years.min()), int(years.max()) + 1, 5):
        end = start + 5
        sub = port_ret[(port_ret.index.year >= start) & (port_ret.index.year < end)]
        if len(sub) < 100:
            continue
        s = _s(sub)
        rows.append(
            {
                "start_year": start,
                "end_year": end - 1,
                "days": s.get("days", 0),
                "sharpe": s.get("sharpe", 0),
                "cagr": s.get("cagr", 0),
                "max_dd": s.get("max_drawdown", 0),
            }
        )
    df = pd.DataFrame(rows)
    print(df.to_string(index=False))
    print(f"\n  Sub-periods Sharpe > 0:    {(df['sharpe'] > 0).sum()}/{len(df)}")
    print(f"  Sub-periods Sharpe > 0.5:  {(df['sharpe'] > 0.5).sum()}/{len(df)}")


def section_leave_one_out(data: dict[str, pd.DataFrame]) -> None:
    print("\n=== 5. Leave-One-Out Ticker Drop ===")
    cfg = overnight.OvernightConfig()
    base = _s(overnight.backtest_portfolio(data, cfg)["portfolio_return"]).get("sharpe", 0)
    print(f"  Baseline (all {len(data)}): Sharpe {base:.4f}\n")
    for drop in data:
        reduced = {t: v for t, v in data.items() if t != drop}
        s = _s(overnight.backtest_portfolio(reduced, cfg)["portfolio_return"]).get("sharpe", 0)
        print(f"  drop {drop}: Sharpe {s:>6.3f}, delta {s - base:+.3f}")


def section_cost_sensitivity(data: dict[str, pd.DataFrame]) -> None:
    print("\n=== 6. Cost Sensitivity (bps per side) ===")
    rows = []
    for cost in [0.0, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0]:
        cfg = overnight.OvernightConfig(cost_bps_per_side=cost)
        s = _s(overnight.backtest_portfolio(data, cfg)["portfolio_return"])
        rows.append(
            {
                "cost_bps_per_side": cost,
                "roundtrip_bps": cost * 2,
                "sharpe": s.get("sharpe", 0),
                "cagr": s.get("cagr", 0),
            }
        )
    print(pd.DataFrame(rows).to_string(index=False))


def section_placebo(data: dict[str, pd.DataFrame], n_seeds: int = 100) -> None:
    print(f"\n=== 7. Direction Placebo (random long/short each night, {n_seeds} seeds) ===")
    cfg = overnight.OvernightConfig()
    real = _s(overnight.backtest_portfolio(data, cfg)["portfolio_return"]).get("sharpe", 0)

    # Get per-ticker overnight returns
    on_rets = {t: overnight.compute_overnight_returns(df) for t, df in data.items()}
    on_frame = pd.DataFrame(on_rets).dropna(how="all")

    rng = np.random.default_rng(42)
    placebo_sharpes = []
    for _ in range(n_seeds):
        # Random +/-1 direction per ticker per day
        signs = pd.DataFrame(
            rng.choice([-1.0, 1.0], size=on_frame.shape),
            index=on_frame.index,
            columns=on_frame.columns,
        )
        placebo_returns = (signs * on_frame).mean(axis=1)
        placebo_sharpes.append(overnight.sharpe(placebo_returns.dropna(), 252))

    arr = np.array(placebo_sharpes)
    p = float((arr >= real).mean())
    print(f"  Real (long-only overnight) Sharpe: {real:.4f}")
    print(f"  Placebo mean +/-:                   {arr.mean():.4f} +/- {arr.std():.4f}")
    print(f"  Placebo p5 / p95:                   {np.percentile(arr, 5):.3f} / {np.percentile(arr, 95):.3f}")
    print(f"  P(placebo >= real):                 {p:.3f}")
    verdict = "REAL EDGE" if p < 0.05 else "WEAK EDGE" if p < 0.20 else "NO EDGE"
    print(f"  Verdict: {verdict}")


def main() -> None:
    print("Fetching daily OHLC ...")
    data = fetch_daily_ohlc()
    for t, df in data.items():
        print(f"  {t}: {df.index.min().date()} -> {df.index.max().date()} ({len(df):,} days)")

    section_decomposition(data)
    section_baseline(data)
    section_walk_forward(data)
    section_parameter_sensitivity(data)
    section_sub_periods(data)
    section_leave_one_out(data)
    section_cost_sensitivity(data)
    section_placebo(data)

    print("\n=== Audit complete ===")


if __name__ == "__main__":
    main()
