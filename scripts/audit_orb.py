"""Robustness audit for Sleeve A (Opening Range Breakout).

Uses TradingView CSV exports (see issue #1) for QQQ + SPY + IWM 5-min
history. About 12.5 months of data per ticker.

Same seven-section format used for Sleeves B/C/D so results are comparable.
"""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd

from ten_cent_bot.backtest import BacktestConfig, run
from ten_cent_bot.metrics import max_drawdown, sharpe, sortino
from ten_cent_bot.orb import ORBConfig, generate_signals
from ten_cent_bot.tv_data import load_tv_csv

ROOT = Path(__file__).resolve().parent.parent

# Ali dropped the CSVs at repo root
CSV_PATHS: dict[str, Path] = {
    "QQQ": ROOT / "BATS_QQQ, 5.csv",
    "SPY": ROOT / "BATS_SPY, 5.csv",
    "IWM": ROOT / "BATS_IWM, 5.csv",
}


def default_bt_cfg() -> BacktestConfig:
    # Equity ETFs: 1 point = $1/share; ~2c round-trip retail cost.
    return BacktestConfig(
        starting_equity=25_000,
        risk_pct=0.01,
        point_value=1.0,
        cost_per_contract_rt=0.02,
    )


def run_orb(bars: pd.DataFrame, orb_cfg: ORBConfig, bt_cfg: BacktestConfig) -> pd.DataFrame:
    signals = generate_signals(bars, orb_cfg)
    if signals.empty:
        return pd.DataFrame()
    return run(signals, bt_cfg)


def stats_from_results(results: pd.DataFrame) -> dict:
    if results.empty:
        return {"trades": 0}
    pnl = results["net_pnl_dollars"]
    eq = results["equity_after"]
    starting = eq.iloc[0] - pnl.iloc[0]
    # daily returns (approx: 1 trade per session ≈ 1 return per session)
    ret = pnl / eq.shift(1).fillna(starting)
    return {
        "trades": int(len(results)),
        "net_pnl": float(pnl.sum()),
        "sharpe": sharpe(ret, 252),
        "sortino": sortino(ret, 252),
        "max_drawdown": max_drawdown(eq),
        "win_rate": float((pnl > 0).mean()),
        "profit_factor": (
            float(pnl[pnl > 0].sum() / -pnl[pnl < 0].sum())
            if (pnl < 0).any() and pnl[pnl < 0].sum() != 0
            else 0.0
        ),
        "final_equity": float(eq.iloc[-1]),
    }


def portfolio_stats(per_ticker_results: dict[str, pd.DataFrame], starting_equity: float) -> dict:
    """Combine per-ticker P&L to an equal-$-risk portfolio."""
    if not per_ticker_results:
        return {}
    all_dates = pd.Index([]).union_many(
        [pd.to_datetime(r["date"]).unique() for r in per_ticker_results.values() if not r.empty]
    ) if False else pd.Index(sorted({
        d for r in per_ticker_results.values() if not r.empty for d in pd.to_datetime(r["date"]).unique()
    }))
    if len(all_dates) == 0:
        return {}
    pnl_per_day = pd.Series(0.0, index=all_dates)
    for ticker, results in per_ticker_results.items():
        if results.empty:
            continue
        s = results.groupby(pd.to_datetime(results["date"]))["net_pnl_dollars"].sum()
        pnl_per_day = pnl_per_day.add(s, fill_value=0.0)
    equity = starting_equity * len(per_ticker_results) + pnl_per_day.cumsum()
    ret = pnl_per_day / equity.shift(1).fillna(equity.iloc[0])
    return {
        "sessions": int(len(pnl_per_day)),
        "net_pnl": float(pnl_per_day.sum()),
        "sharpe": sharpe(ret, 252),
        "sortino": sortino(ret, 252),
        "max_drawdown": max_drawdown(equity),
        "win_rate": float((pnl_per_day > 0).mean()),
        "final_equity": float(equity.iloc[-1]),
    }


# ---------------- sections ----------------


def section_baseline(data: dict[str, pd.DataFrame]) -> dict:
    print("\n=== 1. Baseline (default ORB config, 3 tickers) ===")
    orb_cfg = ORBConfig()
    bt_cfg = default_bt_cfg()
    per_ticker: dict[str, pd.DataFrame] = {}
    for tkr, bars in data.items():
        results = run_orb(bars, orb_cfg, bt_cfg)
        per_ticker[tkr] = results
        s = stats_from_results(results)
        print(
            f"  {tkr}: trades={s['trades']:>3}, sharpe={s['sharpe']:>6.3f}, "
            f"net_pnl=${s['net_pnl']:>+7.0f}, win={s.get('win_rate', 0):.1%}, "
            f"pf={s.get('profit_factor', 0):>4.2f}"
        )
    ps = portfolio_stats(per_ticker, bt_cfg.starting_equity)
    print(
        f"\n  Portfolio (equal-$-risk): sharpe={ps.get('sharpe', 0):>6.3f}, "
        f"net_pnl=${ps.get('net_pnl', 0):>+7.0f}, "
        f"MaxDD={ps.get('max_drawdown', 0):.3f}, "
        f"win={ps.get('win_rate', 0):.1%}"
    )
    return per_ticker


def section_walk_forward(data: dict[str, pd.DataFrame]) -> None:
    print("\n=== 2. Walk-Forward (train first half, test second half) ===")
    orb_cfg = ORBConfig()
    bt_cfg = default_bt_cfg()
    for tkr, bars in data.items():
        n = len(bars)
        train = bars.iloc[: n // 2]
        test = bars.iloc[n // 2 :]
        st = stats_from_results(run_orb(train, orb_cfg, bt_cfg))
        se = stats_from_results(run_orb(test, orb_cfg, bt_cfg))
        delta = abs(st.get("sharpe", 0) - se.get("sharpe", 0))
        print(
            f"  {tkr}: train sharpe={st.get('sharpe', 0):>6.3f} (n={st['trades']})  "
            f"test sharpe={se.get('sharpe', 0):>6.3f} (n={se['trades']})  "
            f"delta={delta:.3f}"
        )


def section_parameter_sensitivity(data: dict[str, pd.DataFrame]) -> None:
    print("\n=== 3. Parameter Sensitivity ===")
    rows = []
    bt_cfg = default_bt_cfg()
    for or_bars in [1, 2, 3]:
        for vol_lb in [0, 7, 14, 21]:
            for vol_ratio in [0.3, 0.5, 0.7]:
                orb_cfg = ORBConfig(
                    opening_range_bars=or_bars,
                    vol_filter_lookback=vol_lb,
                    vol_filter_min_ratio=vol_ratio,
                )
                per_ticker = {
                    tkr: run_orb(bars, orb_cfg, bt_cfg) for tkr, bars in data.items()
                }
                ps = portfolio_stats(per_ticker, bt_cfg.starting_equity)
                if not ps:
                    continue
                rows.append(
                    {
                        "or_bars": or_bars,
                        "vol_lb": vol_lb,
                        "vol_ratio": vol_ratio,
                        "sharpe": ps.get("sharpe", 0),
                        "net_pnl": ps.get("net_pnl", 0),
                        "max_dd": ps.get("max_drawdown", 0),
                    }
                )
    df = pd.DataFrame(rows)
    print(f"  Configs tested:              {len(df)}")
    print(f"  Sharpe mean +/- std:         {df['sharpe'].mean():.3f} +/- {df['sharpe'].std():.3f}")
    print(f"  Sharpe min / median / max:   {df['sharpe'].min():.3f} / {df['sharpe'].median():.3f} / {df['sharpe'].max():.3f}")
    print(f"  % configs with Sharpe > 0:   {(df['sharpe'] > 0).mean():.1%}")
    print(f"  % configs with Sharpe > 0.5: {(df['sharpe'] > 0.5).mean():.1%}")
    best = df.iloc[df["sharpe"].idxmax()]
    worst = df.iloc[df["sharpe"].idxmin()]
    print(
        f"  Best:  or_bars={int(best.or_bars)}, vol_lb={int(best.vol_lb)}, ratio={best.vol_ratio} -> Sharpe {best.sharpe:.3f}"
    )
    print(
        f"  Worst: or_bars={int(worst.or_bars)}, vol_lb={int(worst.vol_lb)}, ratio={worst.vol_ratio} -> Sharpe {worst.sharpe:.3f}"
    )


def section_sub_periods(data: dict[str, pd.DataFrame]) -> None:
    print("\n=== 4. Sub-Period Analysis (quarterly windows) ===")
    orb_cfg = ORBConfig()
    bt_cfg = default_bt_cfg()
    for tkr, bars in data.items():
        et = bars.index.tz_convert("America/New_York")
        by_q = pd.Series(et.date, index=bars.index)
        quarters = pd.Series(by_q.map(lambda d: f"{d.year}Q{(d.month - 1) // 3 + 1}"))
        unique_q = list(sorted(set(quarters)))
        rows = []
        for q in unique_q:
            sub = bars[quarters.values == q]
            if len(sub) < 100:
                continue
            s = stats_from_results(run_orb(sub, orb_cfg, bt_cfg))
            rows.append(
                {
                    "quarter": q,
                    "trades": s.get("trades", 0),
                    "sharpe": s.get("sharpe", 0),
                    "net_pnl": s.get("net_pnl", 0),
                }
            )
        df = pd.DataFrame(rows)
        print(f"\n  {tkr}:")
        print(df.to_string(index=False))


def section_leave_one_out(data: dict[str, pd.DataFrame]) -> None:
    print("\n=== 5. Leave-One-Out Ticker Drop ===")
    orb_cfg = ORBConfig()
    bt_cfg = default_bt_cfg()
    base = portfolio_stats(
        {tkr: run_orb(bars, orb_cfg, bt_cfg) for tkr, bars in data.items()},
        bt_cfg.starting_equity,
    )
    base_sharpe = base.get("sharpe", 0)
    print(f"  Baseline portfolio Sharpe: {base_sharpe:.4f}\n")
    for drop in data:
        reduced = {t: b for t, b in data.items() if t != drop}
        per = {tkr: run_orb(bars, orb_cfg, bt_cfg) for tkr, bars in reduced.items()}
        ps = portfolio_stats(per, bt_cfg.starting_equity)
        delta = ps.get("sharpe", 0) - base_sharpe
        print(
            f"  drop {drop}: sharpe={ps.get('sharpe', 0):>6.3f} (delta {delta:+.3f}), "
            f"net_pnl=${ps.get('net_pnl', 0):>+7.0f}"
        )


def section_cost_sensitivity(data: dict[str, pd.DataFrame]) -> None:
    print("\n=== 6. Cost Sensitivity (cents per share round-trip) ===")
    orb_cfg = ORBConfig()
    for cost_cents in [0.0, 0.5, 1.0, 2.0, 5.0, 10.0]:
        bt_cfg = replace(default_bt_cfg(), cost_per_contract_rt=cost_cents / 100.0)
        per = {tkr: run_orb(bars, orb_cfg, bt_cfg) for tkr, bars in data.items()}
        ps = portfolio_stats(per, bt_cfg.starting_equity)
        print(
            f"  {cost_cents:>5.1f} cents: sharpe={ps.get('sharpe', 0):>6.3f}, "
            f"net_pnl=${ps.get('net_pnl', 0):>+7.0f}"
        )


def section_placebo(data: dict[str, pd.DataFrame], n_seeds: int = 100) -> None:
    print(f"\n=== 7. Direction Placebo ({n_seeds} seeds) ===")
    orb_cfg = ORBConfig()
    bt_cfg = default_bt_cfg()
    # Real signals
    real_per_ticker = {tkr: run_orb(bars, orb_cfg, bt_cfg) for tkr, bars in data.items()}
    real_sharpe = portfolio_stats(real_per_ticker, bt_cfg.starting_equity).get("sharpe", 0)

    # Generate raw signals per ticker (no backtest) so we can flip direction
    from ten_cent_bot.orb import generate_signals as gen_signals

    rng = np.random.default_rng(42)
    placebo_sharpes = []
    raw_signals = {tkr: gen_signals(bars, orb_cfg) for tkr, bars in data.items()}

    for _ in range(n_seeds):
        per_ticker: dict[str, pd.DataFrame] = {}
        for tkr, sig in raw_signals.items():
            if sig.empty:
                per_ticker[tkr] = sig
                continue
            flipped = sig.copy()
            # 50/50 flip direction for each trade
            for i in range(len(flipped)):
                if rng.random() < 0.5:
                    row = flipped.iloc[i]
                    new_side = "short" if row["side"] == "long" else "long"
                    flipped.at[flipped.index[i], "side"] = new_side
                    flipped.at[flipped.index[i], "pnl_points"] = -row["pnl_points"]
                    # entry/stop swap
                    entry, stop = row["entry_price"], row["stop"]
                    flipped.at[flipped.index[i], "entry_price"] = entry
                    flipped.at[flipped.index[i], "stop"] = stop
            per_ticker[tkr] = run(flipped, bt_cfg)
        ps = portfolio_stats(per_ticker, bt_cfg.starting_equity)
        placebo_sharpes.append(ps.get("sharpe", 0))

    arr = np.array(placebo_sharpes)
    p_value = float((arr >= real_sharpe).mean())
    print(f"  Real portfolio Sharpe:  {real_sharpe:.4f}")
    print(f"  Placebo mean +/- std:   {arr.mean():.4f} +/- {arr.std():.4f}")
    print(f"  Placebo p5 / p95:       {np.percentile(arr, 5):.3f} / {np.percentile(arr, 95):.3f}")
    print(f"  P(placebo >= real):     {p_value:.3f}")
    if p_value < 0.05:
        verdict = "REAL EDGE (real signal beats random-direction at p<0.05)"
    elif p_value < 0.20:
        verdict = "WEAK EDGE"
    else:
        verdict = "NO DETECTABLE EDGE (breakout direction doesn't predict)"
    print(f"  Verdict: {verdict}")


def main() -> None:
    print("Loading TradingView CSV exports ...")
    data: dict[str, pd.DataFrame] = {}
    for tkr, path in CSV_PATHS.items():
        if not path.exists():
            print(f"  ! missing: {path}")
            continue
        bars = load_tv_csv(path)
        et = bars.index.tz_convert("America/New_York")
        print(
            f"  {tkr}: {len(bars):,} bars, {et.min().date()} -> {et.max().date()} "
            f"({len(set(et.date))} sessions)"
        )
        data[tkr] = bars

    if not data:
        print("No data loaded. Are the CSVs at the repo root?")
        return

    section_baseline(data)
    section_walk_forward(data)
    section_parameter_sensitivity(data)
    section_sub_periods(data)
    section_leave_one_out(data)
    section_cost_sensitivity(data)
    section_placebo(data, n_seeds=100)

    print("\n=== Audit complete ===")


if __name__ == "__main__":
    main()
