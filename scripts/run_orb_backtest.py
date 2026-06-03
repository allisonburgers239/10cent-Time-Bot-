"""Smoke test: synthetic data -> ORB signals -> backtest -> summary stats.

Once real MNQ 5-min data lands in `data/`, swap `generate_synthetic_bars()`
for `load_bars(path)` and re-run.
"""
from __future__ import annotations

import pandas as pd

from ten_cent_bot.backtest import BacktestConfig, run
from ten_cent_bot.data import generate_synthetic_bars
from ten_cent_bot.metrics import summary
from ten_cent_bot.orb import ORBConfig, generate_signals


def main() -> None:
    bars = generate_synthetic_bars(days=120, seed=7)
    sessions = pd.Series(bars.index.tz_convert("America/New_York").date).nunique()
    print(f"Loaded {len(bars):,} bars across {sessions} sessions")

    signals = generate_signals(bars, ORBConfig())
    print(f"\n{len(signals)} trades generated")
    if signals.empty:
        print("No trades. Adjust vol filter or check data.")
        return

    results = run(signals, BacktestConfig())

    pd.set_option("display.width", 220)
    pd.set_option("display.max_columns", 20)
    print("\nLast 5 trades:")
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
        ].tail()
    )

    stats = summary(results)
    print("\nSummary:")
    for k, v in stats.items():
        if isinstance(v, float):
            print(f"  {k:>15}: {v:,.4f}")
        else:
            print(f"  {k:>15}: {v}")
    print(
        "\nNOTE: synthetic random-walk data. Real edge requires real MNQ bars and"
        " realistic execution costs."
    )


if __name__ == "__main__":
    main()
