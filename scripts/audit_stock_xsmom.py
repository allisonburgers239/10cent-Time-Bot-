"""7-section robustness audit for stock-level cross-sectional momentum.

Universe: 25 continuously-listed large-cap US stocks (all with data
from 2000+). Compares vanilla momentum vs residual momentum
(Blitz-Hanauer-Vidojevic 2020) as the primary "does it help" question.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import yfinance as yf

from ten_cent_bot import stock_xsmom

# Long-history large-cap US names. All have monthly prices from 2000+.
UNIVERSE = [
    "AAPL", "MSFT", "JNJ", "XOM", "JPM",
    "PG", "WMT", "KO", "PEP", "DIS",
    "MCD", "IBM", "CSCO", "INTC", "VZ",
    "T", "MRK", "PFE", "ABT", "TXN",
    "HON", "MMM", "CAT", "BA", "WFC",
]
MARKET = "SPY"


def fetch_monthly() -> tuple[pd.DataFrame, pd.Series]:
    tickers = UNIVERSE + [MARKET]
    data = yf.download(
        tickers, period="max", interval="1d", auto_adjust=True, progress=False
    )
    prices = data["Close"]
    monthly = prices.resample("ME").last().dropna()
    market = monthly[MARKET]
    stocks = monthly[UNIVERSE]
    return stocks, market


def _s(result):
    return stock_xsmom.summary(result)


# ---------- Section 0: variant comparison ----------


def section_variants(monthly: pd.DataFrame, market: pd.Series) -> None:
    print("\n=== 0. Variant Comparison (vanilla vs residual, long/short vs long-only) ===")
    variants = {
        "vanilla long-short":  stock_xsmom.StockXSMOMConfig(),
        "vanilla long-only":   stock_xsmom.StockXSMOMConfig(long_only=True),
        "residual long-short": stock_xsmom.StockXSMOMConfig(residual=True),
        "residual long-only":  stock_xsmom.StockXSMOMConfig(residual=True, long_only=True),
    }
    print(f"  {'variant':>22}  {'Sharpe':>7}  {'CAGR':>8}  {'Vol':>7}  {'MaxDD':>7}")
    print("  " + "-" * 60)
    for name, cfg in variants.items():
        s = _s(stock_xsmom.backtest(monthly, market, cfg))
        print(
            f"  {name:>22}  {s.get('sharpe', 0):>7.3f}  "
            f"{s.get('cagr', 0):>8.4f}  {s.get('annual_vol', 0):>7.4f}  "
            f"{s.get('max_drawdown', 0):>7.4f}"
        )


# ---------- Sections 1-7 (standard harness on default = vanilla long-short) ----------


def section_baseline(monthly, market):
    print("\n=== 1. Baseline (vanilla long-short, top 5) ===")
    cfg = stock_xsmom.StockXSMOMConfig(long_only=True)
    s = _s(stock_xsmom.backtest(monthly, market, cfg))
    print(
        f"Period: {monthly.index.min().date()} -> {monthly.index.max().date()} "
        f"({len(monthly)} months, {len(monthly.columns)} stocks)"
    )
    print(f"  Sharpe:        {s['sharpe']:.4f}")
    print(f"  CAGR:          {s['cagr']:.4f}")
    print(f"  Max DD:        {s['max_drawdown']:.4f}")
    print(f"  Monthly win %: {s['monthly_win_rate']:.4f}")


def section_walk_forward(monthly, market):
    print("\n=== 2. Walk-Forward (train / test) ===")
    cfg = stock_xsmom.StockXSMOMConfig(long_only=True)
    n = len(monthly)
    split = n // 2
    tr = monthly.iloc[:split]
    te = monthly.iloc[split - 12:]
    st = _s(stock_xsmom.backtest(tr, market.reindex(tr.index), cfg))
    se = _s(stock_xsmom.backtest(te, market.reindex(te.index), cfg))
    print(
        f"Train ({tr.index.min().date()} -> {tr.index.max().date()}): "
        f"Sharpe {st['sharpe']:.3f}, MaxDD {st['max_drawdown']:.3f}"
    )
    print(
        f"Test  ({te.index.min().date()} -> {te.index.max().date()}): "
        f"Sharpe {se['sharpe']:.3f}, MaxDD {se['max_drawdown']:.3f}"
    )
    delta = abs(st["sharpe"] - se["sharpe"])
    print(f"  delta = {delta:.3f}  =>  {'CONSISTENT' if delta < 0.35 else 'DIVERGENT'}")


def section_parameter_sensitivity(monthly, market):
    print("\n=== 3. Parameter Sensitivity ===")
    rows = []
    for lb in [3, 6, 9, 12, 15, 18]:
        for top_n in [3, 5, 7]:
            for long_only in [False, True]:
                for resid in [False, True]:
                    cfg = stock_xsmom.StockXSMOMConfig(
                        lookback_months=lb, top_n=top_n,
                        long_only=long_only, residual=resid,
                    )
                    s = _s(stock_xsmom.backtest(monthly, market, cfg))
                    rows.append({
                        "lookback": lb, "top_n": top_n,
                        "long_only": long_only, "residual": resid,
                        "sharpe": s.get("sharpe", 0),
                        "cagr": s.get("cagr", 0),
                    })
    df = pd.DataFrame(rows)
    print(f"  Configs tested:            {len(df)}")
    print(f"  Sharpe mean +/- std:       {df['sharpe'].mean():.3f} +/- {df['sharpe'].std():.3f}")
    print(f"  Sharpe min / median / max: {df['sharpe'].min():.3f} / {df['sharpe'].median():.3f} / {df['sharpe'].max():.3f}")
    print(f"  % configs Sharpe > 0:      {(df['sharpe'] > 0).mean():.1%}")
    print(f"  % configs Sharpe > 0.3:    {(df['sharpe'] > 0.3).mean():.1%}")
    best = df.iloc[df["sharpe"].idxmax()]
    worst = df.iloc[df["sharpe"].idxmin()]
    print(f"  Best:  {best.to_dict()}")
    print(f"  Worst: {worst.to_dict()}")


def section_sub_periods(monthly, market):
    print("\n=== 4. Sub-Period Analysis (rolling 4y windows) ===")
    cfg = stock_xsmom.StockXSMOMConfig(long_only=True)
    period = 48
    rows = []
    n = len(monthly)
    for start in range(0, n - period + 1, 24):
        end = min(start + period + 12, n)
        sub_p = monthly.iloc[start:end]
        sub_m = market.reindex(sub_p.index)
        if len(sub_p) < 24:
            continue
        s = _s(stock_xsmom.backtest(sub_p, sub_m, cfg))
        rows.append({
            "from": sub_p.index[12].date() if len(sub_p) > 12 else sub_p.index[0].date(),
            "to": sub_p.index[-1].date(),
            "sharpe": s.get("sharpe", 0),
            "cagr": s.get("cagr", 0),
            "max_dd": s.get("max_drawdown", 0),
        })
    df = pd.DataFrame(rows)
    print(df.to_string(index=False))
    print(f"\n  Sub-periods Sharpe > 0:    {(df['sharpe'] > 0).sum()}/{len(df)}")
    print(f"  Sub-periods Sharpe > 0.3:  {(df['sharpe'] > 0.3).sum()}/{len(df)}")


def section_leave_one_out(monthly, market):
    print("\n=== 5. Leave-One-Out Stock Drop ===")
    cfg = stock_xsmom.StockXSMOMConfig(long_only=True)
    base = _s(stock_xsmom.backtest(monthly, market, cfg))["sharpe"]
    rows = []
    for col in monthly.columns:
        reduced = monthly.drop(columns=[col])
        s = _s(stock_xsmom.backtest(reduced, market, cfg))
        rows.append({
            "dropped": col,
            "sharpe": s.get("sharpe", 0),
            "delta": s.get("sharpe", 0) - base,
        })
    df = pd.DataFrame(rows).sort_values("delta")
    print(f"  Baseline (all {len(monthly.columns)}): Sharpe {base:.4f}\n")
    print(df.to_string(index=False))
    max_delta = df["delta"].abs().max()
    print(f"\n  Max single-stock delta: {max_delta:.3f}  "
          f"=> {'NOT DOMINATED' if max_delta < 0.20 else 'CONCENTRATED'}")


def section_cost_sensitivity(monthly, market):
    print("\n=== 6. Cost Sensitivity (bps per turnover unit, long-only variant) ===")
    rows = []
    for bps in [0, 10, 20, 50, 100, 200, 500]:
        cfg = stock_xsmom.StockXSMOMConfig(transaction_cost_bps=bps, long_only=True)
        s = _s(stock_xsmom.backtest(monthly, market, cfg))
        rows.append({"cost_bps": bps, "sharpe": s.get("sharpe", 0), "cagr": s.get("cagr", 0)})
    print(pd.DataFrame(rows).to_string(index=False))

    # Compare vs SPY buy-and-hold for the same period
    spy_ret = market.pct_change().dropna()
    spy_annual = (1 + spy_ret.mean()) ** 12 - 1
    spy_vol = spy_ret.std(ddof=0) * np.sqrt(12)
    spy_sharpe = spy_annual / spy_vol if spy_vol > 0 else 0
    print(f"\n  SPY buy-and-hold benchmark: Sharpe {spy_sharpe:.3f}, CAGR {spy_annual:.4f}")


def section_placebo(monthly, market, n_seeds=100):
    print(f"\n=== 7. Random-Rank Placebo ({n_seeds} seeds) ===")
    cfg = stock_xsmom.StockXSMOMConfig(long_only=True)
    real = _s(stock_xsmom.backtest(monthly, market, cfg))["sharpe"]

    monthly_returns = monthly.pct_change()
    n_stocks = monthly.shape[1]
    weight = 1.0 / cfg.top_n

    rng = np.random.default_rng(42)
    placebo_sharpes = []
    for _ in range(n_seeds):
        random_ranks = pd.DataFrame(
            np.array([rng.permutation(np.arange(1, n_stocks + 1)) for _ in range(len(monthly))]),
            index=monthly.index,
            columns=monthly.columns,
        )
        signal = pd.DataFrame(0.0, index=monthly.index, columns=monthly.columns)
        signal[random_ranks <= cfg.top_n] = weight
        if not cfg.long_only:
            signal[random_ranks > (n_stocks - cfg.top_n)] = -weight
        position = signal.shift(1)
        asset_pnl = position * monthly_returns
        port_ret = asset_pnl.sum(axis=1)
        turnover = position.diff().abs().sum(axis=1)
        cost = turnover * cfg.transaction_cost_bps / 10_000.0
        net = (port_ret - cost).dropna()
        if len(net) == 0 or net.std(ddof=0) == 0:
            continue
        placebo_sharpes.append(
            float(net.mean() * 12 / (net.std(ddof=0) * np.sqrt(12)))
        )

    arr = np.array(placebo_sharpes)
    p = float((arr >= real).mean())
    print(f"  Real Sharpe:             {real:.4f}")
    print(f"  Placebo mean +/-:        {arr.mean():.4f} +/- {arr.std():.4f}")
    print(f"  Placebo p5 / p95:        {np.percentile(arr, 5):.3f} / {np.percentile(arr, 95):.3f}")
    print(f"  P(placebo >= real):      {p:.3f}")
    verdict = "REAL EDGE" if p < 0.05 else "WEAK EDGE" if p < 0.20 else "NO EDGE"
    print(f"  Verdict: {verdict}")


def main() -> None:
    print("Fetching prices ...")
    monthly, market = fetch_monthly()
    print(f"Universe: {list(monthly.columns)}")
    print(f"Period:   {monthly.index.min().date()} -> {monthly.index.max().date()} "
          f"({len(monthly)} months)")

    section_variants(monthly, market)
    section_baseline(monthly, market)
    section_walk_forward(monthly, market)
    section_parameter_sensitivity(monthly, market)
    section_sub_periods(monthly, market)
    section_leave_one_out(monthly, market)
    section_cost_sensitivity(monthly, market)
    section_placebo(monthly, market)

    print("\n=== Audit complete ===")


if __name__ == "__main__":
    main()
