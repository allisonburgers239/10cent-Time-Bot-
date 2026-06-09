"""Time-Series Momentum (Sleeve B) on a multi-asset ETF basket.

Daily bars are pulled from Yahoo Finance for each ETF's full available history,
resampled to month-end, and run through the TSMOM engine. The basket spans
US equity, international equity, bonds, gold, oil, and broad commodities so
the strategy can diversify across asset classes — the design that the
Moskowitz-Ooi-Pedersen and AQR studies measure.
"""
from __future__ import annotations

import pandas as pd
import yfinance as yf

from ten_cent_bot.tsmom import TSMOMConfig, backtest, summary

BASKET = [
    "SPY",  # US large-cap
    "QQQ",  # US tech
    "IWM",  # US small-cap
    "EFA",  # Developed intl
    "EEM",  # Emerging markets
    "TLT",  # Long bonds
    "IEF",  # Intermediate bonds
    "GLD",  # Gold
    "USO",  # Oil
    "DBC",  # Broad commodities
]


def fetch_basket_prices(tickers: list[str]) -> pd.DataFrame:
    data = yf.download(
        tickers,
        period="max",
        interval="1d",
        auto_adjust=True,
        progress=False,
    )
    if isinstance(data.columns, pd.MultiIndex):
        prices = data["Close"]
    else:
        prices = data[["Close"]].rename(columns={"Close": tickers[0]})
    return prices


def main() -> None:
    prices = fetch_basket_prices(BASKET)
    print(
        f"Daily prices: {prices.index.min().date()} -> {prices.index.max().date()}, "
        f"{prices.shape[1]} assets"
    )
    print("\nFirst valid date per asset:")
    for tkr in prices.columns:
        fv = prices[tkr].first_valid_index()
        print(f"  {tkr:>4}: {fv.date() if fv is not None else 'no data'}")

    monthly = prices.resample("ME").last()
    monthly_aligned = monthly.dropna()
    print(
        f"\nAligned monthly window: {monthly_aligned.index.min().date()} -> "
        f"{monthly_aligned.index.max().date()} ({len(monthly_aligned)} months)"
    )

    cfg = TSMOMConfig()
    result = backtest(monthly_aligned, cfg)
    stats = summary(result)

    print("\nTSMOM backtest summary (net of 10bps round-trip per rebalance):")
    for k, v in stats.items():
        if isinstance(v, float):
            print(f"  {k:>20}: {v:>12.4f}")
        else:
            print(f"  {k:>20}: {v}")

    eq = result["equity"]
    print(f"\nFinal equity multiple: {eq.iloc[-1]:.2f}x")
    print("\nEquity curve every 24 months:")
    print(eq.iloc[::24].round(3))

    print(
        "\nNOTE: ETF basket — futures version (AQR) typically shows somewhat higher "
        "Sharpe due to embedded leverage and lower drag. ETFs are the free-data variant."
    )


if __name__ == "__main__":
    main()
