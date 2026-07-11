"""7-section audit of the systematic AMDX/COT weekly bias on NQ.

Validates Ali's framework rigorously:
  - 16-year OOS window (Jun 2010 - Jul 2026)
  - Benchmarks vs buy-and-hold NQ (critical - NQ was mostly up in this window)
  - Placebo test with random weekly bias
  - Per-phase accuracy check (MD claimed Manipulation=28%, X=71%, etc.)
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import yfinance as yf

from ten_cent_bot import cot


def fetch_data() -> tuple[pd.DataFrame, pd.DataFrame]:
    print("Fetching CFTC TFF history for NASDAQ-100 Consolidated ...")
    tff = cot.fetch_tff_history()
    print(f"  {len(tff):,} weekly reports, {tff.index.min().date()} -> {tff.index.max().date()}")

    print("Fetching NQ=F weekly prices ...")
    nq = yf.download("NQ=F", period="max", interval="1wk", auto_adjust=True, progress=False)
    if isinstance(nq.columns, pd.MultiIndex):
        nq.columns = nq.columns.get_level_values(0)
    print(f"  {len(nq):,} weekly bars, {nq.index.min().date()} -> {nq.index.max().date()}")
    return tff, nq


def _s(ret):
    return cot.summary_from_returns(ret)


# ---------- Section 0: reproduce MD's per-phase accuracy claim ----------


def section_zero(combined: pd.DataFrame) -> None:
    """The MD claims per-phase directional accuracy. Reproduce it."""
    print("\n=== 0. Per-Phase Directional Accuracy (MD's central claim) ===")
    print("  MD claim: X=71%, A=67%, X_reversal=56%, D=50-83%, M=28%")

    # Signal(t-1) direction vs realized return(t) direction
    aligned = combined.copy()
    aligned["signal_lag"] = aligned["signal"].shift(1)
    aligned["phase_lag"] = aligned["phase"].shift(1)
    aligned = aligned.dropna(subset=["signal_lag", "weekly_return"])

    active = aligned[aligned["signal_lag"] != 0].copy()
    if len(active) == 0:
        print("  No active signals")
        return
    active["hit"] = np.sign(active["signal_lag"]) == np.sign(active["weekly_return"])

    print(f"\n  Overall active-signal accuracy: {active['hit'].mean():.1%} "
          f"across {len(active)} weeks (of {len(aligned)} total = "
          f"{len(active) / len(aligned):.1%} signal frequency)")

    print("\n  Per-phase directional accuracy:")
    for phase in sorted(active["phase_lag"].unique()):
        sub = active[active["phase_lag"] == phase]
        if len(sub) < 10:
            continue
        print(
            f"    {phase:>16}  n={len(sub):>4}  hit={sub['hit'].mean():>5.1%}  "
            f"avg_ret={sub['weekly_return'].mean():>+.4f}"
        )


# ---------- Sections 1-7 (standard harness) ----------


def section_baseline(combined: pd.DataFrame) -> None:
    print("\n=== 1. Baseline vs Buy-and-Hold NQ ===")
    result = cot.backtest(combined)
    strategy = _s(result["net_return"])
    buyhold = _s(combined["weekly_return"])

    print(
        f"  {'':>18}  {'Sharpe':>7}  {'CAGR':>7}  {'Vol':>7}  {'MaxDD':>7}  {'Weeks':>6}"
    )
    print("  " + "-" * 62)
    for name, s in [("AMDX strategy", strategy), ("Buy-and-hold NQ", buyhold)]:
        print(
            f"  {name:>18}  {s['sharpe']:>7.3f}  {s['cagr']:>7.4f}  "
            f"{s['annual_vol']:>7.4f}  {s['max_drawdown']:>7.4f}  {s['weeks']:>6}"
        )


def section_walk_forward(combined: pd.DataFrame) -> None:
    print("\n=== 2. Walk-Forward (train / test) ===")
    n = len(combined)
    split = n // 2
    tr = combined.iloc[:split]
    te = combined.iloc[split:]
    st = _s(cot.backtest(tr)["net_return"])
    se = _s(cot.backtest(te)["net_return"])
    delta = abs(st.get("sharpe", 0) - se.get("sharpe", 0))
    print(f"  Train ({tr.index.min().date()} -> {tr.index.max().date()}): Sharpe {st['sharpe']:.3f}")
    print(f"  Test  ({te.index.min().date()} -> {te.index.max().date()}): Sharpe {se['sharpe']:.3f}")
    print(f"  Delta {delta:.3f}  =>  {'CONSISTENT' if delta < 0.35 else 'DIVERGENT'}")


def section_parameter_sensitivity(tff: pd.DataFrame, nq: pd.DataFrame) -> None:
    print("\n=== 3. Parameter Sensitivity ===")
    rows = []
    for hf_low in [0.10, 0.20, 0.30]:
        for hf_mid in [0.40, 0.50, 0.60]:
            for am_win in [1, 2, 4]:
                for pctl_win in [26, 52, 104]:
                    cfg = cot.AMDXConfig(
                        hf_pctl_window=pctl_win,
                        hf_extreme_low_pct=hf_low,
                        hf_mid_pct=hf_mid,
                        am_delta_window=am_win,
                    )
                    sig = cot.compute_amdx_signals(tff, cfg)
                    c = cot.align_to_weekly_price(sig, nq)
                    r = cot.backtest(c, cfg)
                    s = _s(r["net_return"])
                    rows.append(
                        {
                            "hf_low": hf_low, "hf_mid": hf_mid,
                            "am_win": am_win, "pctl_win": pctl_win,
                            "sharpe": s.get("sharpe", 0),
                            "cagr": s.get("cagr", 0),
                        }
                    )
    df = pd.DataFrame(rows)
    print(f"  Configs tested:            {len(df)}")
    print(f"  Sharpe mean +/- std:       {df['sharpe'].mean():.3f} +/- {df['sharpe'].std():.3f}")
    print(f"  Sharpe min / median / max: {df['sharpe'].min():.3f} / {df['sharpe'].median():.3f} / {df['sharpe'].max():.3f}")
    print(f"  % configs > 0:             {(df['sharpe'] > 0).mean():.1%}")
    print(f"  % configs > buy-hold:      (buy-hold Sharpe reported in section 1)")


def section_sub_periods(combined: pd.DataFrame) -> None:
    print("\n=== 4. Sub-Period Analysis (annual buckets) ===")
    result = cot.backtest(combined)
    net = result["net_return"]
    rows = []
    for year in sorted(set(net.index.year)):
        sub = net[net.index.year == year]
        if len(sub) < 20:
            continue
        s = _s(sub)
        buy = _s(combined.loc[sub.index, "weekly_return"])
        rows.append({
            "year": year,
            "amdx_sharpe": s.get("sharpe", 0),
            "amdx_ret": s.get("cagr", 0),
            "buy_hold_ret": buy.get("cagr", 0),
        })
    df = pd.DataFrame(rows)
    print(df.to_string(index=False))
    print(f"\n  Years AMDX beats buy-hold: "
          f"{(df['amdx_ret'] > df['buy_hold_ret']).sum()}/{len(df)}")


def section_direction_check(combined: pd.DataFrame) -> None:
    """Section 5: how much does the short leg hurt vs long-only?"""
    print("\n=== 5. Direction Ablation (long-only vs short-only vs both) ===")
    for name, mask in [
        ("both directions", np.abs(combined["signal"]) > 0),
        ("long-only",       combined["signal"] > 0),
        ("short-only",      combined["signal"] < 0),
    ]:
        cfg = cot.AMDXConfig()
        pos = combined["signal"].copy()
        pos[~mask] = 0
        c = combined.copy()
        c["signal"] = pos
        r = cot.backtest(c, cfg)
        s = _s(r["net_return"])
        n_active = int(mask.sum())
        print(
            f"  {name:>18}: Sharpe {s['sharpe']:>6.3f}, CAGR {s['cagr']:>+.4f}, "
            f"MaxDD {s['max_drawdown']:>+.3f}, active weeks {n_active}"
        )


def section_cost_sensitivity(combined: pd.DataFrame) -> None:
    print("\n=== 6. Cost Sensitivity (bps per position change) ===")
    rows = []
    for bps in [0, 1, 2, 5, 10, 20]:
        cfg = cot.AMDXConfig(cost_bps_per_change=bps)
        r = cot.backtest(combined, cfg)
        s = _s(r["net_return"])
        rows.append({"cost_bps": bps, "sharpe": s.get("sharpe", 0), "cagr": s.get("cagr", 0)})
    print(pd.DataFrame(rows).to_string(index=False))


def section_placebo(combined: pd.DataFrame, n_seeds: int = 100) -> None:
    print(f"\n=== 7. Random-Bias Placebo ({n_seeds} seeds) ===")
    real = _s(cot.backtest(combined)["net_return"]).get("sharpe", 0)

    # Match the fraction of active signals in the real strategy
    active_frac = float((combined["signal"] != 0).mean())
    p_pos = float((combined["signal"] > 0).mean()) / active_frac if active_frac > 0 else 0.5

    rng = np.random.default_rng(42)
    placebo_sharpes = []
    for _ in range(n_seeds):
        random_active = rng.random(len(combined)) < active_frac
        random_dir = rng.choice([1.0, -1.0], size=len(combined), p=[p_pos, 1 - p_pos])
        random_signal = pd.Series(random_active * random_dir, index=combined.index)

        c = combined.copy()
        c["signal"] = random_signal
        s = _s(cot.backtest(c)["net_return"]).get("sharpe", 0)
        placebo_sharpes.append(s)

    arr = np.array(placebo_sharpes)
    p_value = float((arr >= real).mean())
    print(f"  Real strategy Sharpe:      {real:.4f}")
    print(f"  Placebo mean +/- std:      {arr.mean():.4f} +/- {arr.std():.4f}")
    print(f"  Placebo p5 / p95:          {np.percentile(arr, 5):.3f} / {np.percentile(arr, 95):.3f}")
    print(f"  P(placebo >= real):        {p_value:.3f}")
    verdict = "REAL EDGE" if p_value < 0.05 else "WEAK EDGE" if p_value < 0.20 else "NO EDGE"
    print(f"  Verdict: {verdict}")


def main() -> None:
    tff, nq = fetch_data()
    signals = cot.compute_amdx_signals(tff)
    combined = cot.align_to_weekly_price(signals, nq)
    print(f"\nAligned working data: {len(combined)} weeks, "
          f"{combined.index.min().date()} -> {combined.index.max().date()}")
    print(f"Active signal weeks:  {int((combined['signal'] != 0).sum())} "
          f"({(combined['signal'] != 0).mean():.1%} of total)")

    section_zero(combined)
    section_baseline(combined)
    section_walk_forward(combined)
    section_parameter_sensitivity(tff, nq)
    section_sub_periods(combined)
    section_direction_check(combined)
    section_cost_sensitivity(combined)
    section_placebo(combined)

    print("\n=== Audit complete ===")


if __name__ == "__main__":
    main()
