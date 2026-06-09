"""Fetch QQQ 5-min bars from Yahoo Finance and run the ORB backtest.

QQQ is the instrument the canonical Zarattini/Aziz ORB paper used, which
makes it the right first-real-data validation target. Yahoo only serves
the last ~60 calendar days at 5-min granularity, so this is a smoke
check against real prices, not a full backtest.
"""
from __future__ import annotations

import sys

import pandas as pd
import yfinance as yf

from ten_cent_bot.backtest import BacktestConfig, run
from ten_cent_bot.metrics import summary
from ten_cent_bot.orb import ORBConfig, generate_signals


def fetch_qqq_5m() -> pd.DataFrame:
    df = yf.download("QQQ", period="60d", interval="5m", progress=False, auto_adjust=False)
    if df is None or df.empty:
        raise RuntimeError("yfinance returned no data for QQQ")
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df = df.rename(columns=str.lower)[["open", "high", "low", "close", "volume"]].dropna()
    if df.index.tz is None:
        df.index = df.index.tz_localize("America/New_York")
    df.index.name = "timestamp"
    return df


def main() -> None:
    bars = fetch_qqq_5m()
    print(
        f"Fetched {len(bars):,} QQQ 5-min bars: "
        f"{bars.index.min()} -> {bars.index.max()}"
    )
    bars.to_csv("data/QQQ_5m.csv")

    signals = generate_signals(bars, ORBConfig())
    print(f"\n{len(signals)} trades generated")
    if signals.empty:
        sys.exit(0)

    # QQQ-specific config: $1 per point (per share), cheap retail costs.
    cfg = BacktestConfig(
        starting_equity=25_000,
        risk_pct=0.01,
        point_value=1.0,
        cost_per_contract_rt=0.02,  # ~1c slippage round-trip per share
    )
    results = run(signals, cfg)

    pd.set_option("display.width", 220)
    pd.set_option("display.max_columns", 20)
    print("\nLast 10 trades:")
    print(
        results[
            [
                "date",
                "side",
                "entry_price",
                "stop",
                "exit_price",
                "exit_reason",
                "contracts",
                "net_pnl_dollars",
                "equity_after",
            ]
        ].tail(10)
    )

    stats = summary(results)
    print("\nSummary (QQQ 5-min ORB, real data, last ~60d):")
    for k, v in stats.items():
        if isinstance(v, float):
            print(f"  {k:>15}: {v:,.4f}")
        else:
            print(f"  {k:>15}: {v}")
    print(
        "\nNOTE: ~42 trading days is too small for a real Sharpe estimate."
        "\nUse this only to confirm the pipeline runs against real prices."
    )


if __name__ == "__main__":
    main()
