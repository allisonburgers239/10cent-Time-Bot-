"""Crypto cash-and-carry (Sleeve C) backtest.

Fetches multi-year funding-rate history from Binance for BTC and ETH
perpetuals, runs the long-only-when-positive variant, and reports
per-symbol and combined portfolio stats.
"""
from __future__ import annotations

import pandas as pd

from ten_cent_bot.basis import aggregate_to_8h, backtest, fetch_funding_history, summary
from ten_cent_bot.metrics import max_drawdown, sharpe

SYMBOLS = ["BTC-PERPETUAL", "ETH-PERPETUAL"]
START = "2020-01-01"
PERIODS_PER_YEAR = 365 * 3  # 8-hour funding intervals


def main() -> None:
    per_symbol_returns: dict[str, pd.Series] = {}
    per_symbol_stats: list[dict] = []

    for sym in SYMBOLS:
        print(f"Fetching {sym} hourly funding history from {START}...")
        hourly = fetch_funding_history(sym, START)
        if hourly.empty:
            print(f"  {sym}: no data returned")
            continue
        funding = aggregate_to_8h(hourly)
        print(
            f"  {sym}: {len(hourly):,} hourly records -> {len(funding):,} 8h bars, "
            f"{funding.index.min().date()} -> {funding.index.max().date()}"
        )
        print(
            f"  8h rate stats: mean={funding['rate'].mean():.4%} "
            f"median={funding['rate'].median():.4%} "
            f"pct_positive={(funding['rate'] > 0).mean():.1%}"
        )

        result = backtest(funding, cost_bps_per_change=5.0, two_sided=False)
        stats = summary(result, periods_per_year=PERIODS_PER_YEAR)
        per_symbol_stats.append({"symbol": sym, **stats})
        per_symbol_returns[sym] = result["per_period_return_net"]
        print(f"  final equity multiple: {result['equity'].iloc[-1]:.3f}x\n")

    if not per_symbol_returns:
        print("No data; aborting.")
        return

    df = pd.DataFrame(per_symbol_stats).set_index("symbol")
    pd.set_option("display.width", 220)
    pd.set_option("display.max_columns", 20)
    pd.set_option("display.float_format", "{:,.4f}".format)
    print("Per-symbol stats (long-only short-perp, net of 5bps per side):\n")
    print(
        df[
            [
                "periods",
                "years",
                "cagr",
                "annual_vol",
                "sharpe",
                "sortino",
                "max_drawdown",
                "pct_holding",
                "total_return",
            ]
        ]
    )

    panel = pd.concat(per_symbol_returns, axis=1, sort=False).fillna(0.0)
    portfolio_ret = panel.mean(axis=1)
    portfolio_eq = (1 + portfolio_ret).cumprod()

    print("\nEqual-weight portfolio (BTC + ETH):")
    print(f"  Sharpe:       {sharpe(portfolio_ret, PERIODS_PER_YEAR):.4f}")
    print(
        f"  CAGR:         "
        f"{((1 + portfolio_ret.mean()) ** PERIODS_PER_YEAR - 1):.4f}"
    )
    print(
        f"  Annual vol:   "
        f"{portfolio_ret.std(ddof=0) * (PERIODS_PER_YEAR ** 0.5):.4f}"
    )
    print(f"  Max DD:       {max_drawdown(portfolio_eq):.4f}")
    print(f"  Final equity: {portfolio_eq.iloc[-1]:.3f}x")

    print(
        "\nNOTE: assumes you can execute spot+perp in size at ~5bps each side. "
        "Real costs vary by exchange tier and trade size. Backtest excludes "
        "spot/perp basis variance (small over funding intervals)."
    )


if __name__ == "__main__":
    main()
