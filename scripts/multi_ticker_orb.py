"""Multi-ticker ORB cross-sectional robustness check.

Same strategy, same 60-day window, applied across a basket of liquid US ETFs
(broad indexes + sectors). If the edge is real, it should show up in more
than one place. If only one ticker works, the edge is likely a quirk.
"""
from __future__ import annotations

import sys
import time

import pandas as pd
import yfinance as yf

from ten_cent_bot.backtest import BacktestConfig, run
from ten_cent_bot.metrics import summary
from ten_cent_bot.orb import ORBConfig, generate_signals

TICKERS = ["QQQ", "SPY", "IWM", "DIA", "XLF", "XLE", "XLK", "XBI"]


def fetch_one(ticker: str) -> pd.DataFrame:
    df = yf.download(
        ticker, period="60d", interval="5m", progress=False, auto_adjust=False
    )
    if df is None or df.empty:
        raise RuntimeError(f"yfinance returned no data for {ticker}")
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df = df.rename(columns=str.lower)[
        ["open", "high", "low", "close", "volume"]
    ].dropna()
    if df.index.tz is None:
        df.index = df.index.tz_localize("America/New_York")
    df.index.name = "timestamp"
    return df


def main() -> None:
    rows: list[dict] = []
    combined_pnl: list[pd.Series] = []

    cfg = BacktestConfig(
        starting_equity=25_000,
        risk_pct=0.01,
        point_value=1.0,
        cost_per_contract_rt=0.02,
    )

    for tkr in TICKERS:
        try:
            bars = fetch_one(tkr)
        except Exception as e:
            print(f"  {tkr}: fetch failed ({e})")
            continue

        signals = generate_signals(bars, ORBConfig())
        if signals.empty:
            print(f"  {tkr}: no trades")
            continue

        results = run(signals, cfg)
        stats = summary(results)
        rows.append({"ticker": tkr, **stats})

        ts = pd.to_datetime(results["date"])
        combined_pnl.append(pd.Series(results["net_pnl_dollars"].values, index=ts, name=tkr))

        time.sleep(0.5)  # be polite to Yahoo

    if not rows:
        print("No tickers produced results.")
        sys.exit(1)

    df = pd.DataFrame(rows).set_index("ticker")
    pd.set_option("display.width", 220)
    pd.set_option("display.max_columns", 20)
    pd.set_option("display.float_format", "{:,.4f}".format)
    print("\nPer-ticker stats (60-day window, $25k each, ORB v0):\n")
    print(df[["trades", "net_pnl", "sharpe", "sortino", "max_drawdown", "win_rate", "profit_factor"]])

    profitable = (df["net_pnl"] > 0).sum()
    print(f"\nProfitable tickers: {profitable} / {len(df)}")
    print(f"Mean Sharpe across tickers: {df['sharpe'].mean():.3f}")
    print(f"Median Sharpe across tickers: {df['sharpe'].median():.3f}")

    # Naive equal-$-risk portfolio: sum daily pnl across tickers.
    pnl_panel = pd.concat(combined_pnl, axis=1, sort=False).fillna(0.0)
    daily_total = pnl_panel.sum(axis=1)
    cumulative = daily_total.cumsum() + cfg.starting_equity * len(TICKERS)
    daily_ret = daily_total / cumulative.shift(1).fillna(cumulative.iloc[0])

    from ten_cent_bot.metrics import (
        max_drawdown,
        sharpe,
        sortino,
    )

    print("\nEqual-$-risk portfolio across all tickers:")
    print(f"  total net pnl:     ${daily_total.sum():>12,.2f}")
    print(f"  portfolio sharpe:  {sharpe(daily_ret):>12.4f}")
    print(f"  portfolio sortino: {sortino(daily_ret):>12.4f}")
    print(f"  portfolio max DD:  {max_drawdown(cumulative):>12.4f}")

    print(
        "\nNOTE: 60d is still too small for any honest Sharpe estimate. "
        "Multi-ticker shows whether the edge appears in more than one place "
        "during the same period."
    )


if __name__ == "__main__":
    main()
