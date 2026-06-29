"""Cross-sectional sector momentum (Sleeve D) on the 9 long-history SPDR sectors.

Universe is the original 9 sector SPDR ETFs (XLB/XLE/XLF/XLI/XLK/XLP/XLU/
XLV/XLY), all with daily history back to 1998-12. XLRE (2015) and XLC
(2018) are excluded so the backtest spans the full 1998-2026 window.
"""
from __future__ import annotations

import pandas as pd
import yfinance as yf

from ten_cent_bot.xsmom import XSMOMConfig, backtest, summary

SECTORS = [
    "XLB",  # Materials
    "XLE",  # Energy
    "XLF",  # Financials
    "XLI",  # Industrials
    "XLK",  # Technology
    "XLP",  # Consumer Staples
    "XLU",  # Utilities
    "XLV",  # Health Care
    "XLY",  # Consumer Discretionary
]


def fetch_basket_prices(tickers: list[str]) -> pd.DataFrame:
    data = yf.download(
        tickers, period="max", interval="1d", auto_adjust=True, progress=False
    )
    if isinstance(data.columns, pd.MultiIndex):
        prices = data["Close"]
    else:
        prices = data[["Close"]].rename(columns={"Close": tickers[0]})
    return prices


def main() -> None:
    prices = fetch_basket_prices(SECTORS)
    monthly = prices.resample("ME").last().dropna()
    print(
        f"Daily prices: {prices.index.min().date()} -> {prices.index.max().date()}, "
        f"{prices.shape[1]} sectors"
    )
    print(
        f"Aligned monthly: {monthly.index.min().date()} -> "
        f"{monthly.index.max().date()} ({len(monthly)} months)"
    )

    cfg = XSMOMConfig()
    result = backtest(monthly, cfg)
    stats = summary(result)

    print(
        "\nCross-sectional sector momentum (long top 3, short bottom 3, "
        "12m lookback, 10bps/turnover):"
    )
    for k, v in stats.items():
        if isinstance(v, float):
            print(f"  {k:>20}: {v:>12.4f}")
        else:
            print(f"  {k:>20}: {v}")

    eq = result["equity"]
    print(f"\nFinal equity multiple: {eq.iloc[-1]:.2f}x")
    print("\nEquity curve every 24 months:")
    print(eq.iloc[::24].round(3))


if __name__ == "__main__":
    main()
