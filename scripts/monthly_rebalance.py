"""Monthly rebalance for Sleeve B - manual or Tradovate-API mode.

Default mode is dry-run with a file-backed position store, so you can run
it today before Tradovate API credentials are issued. Outputs a trade
ticket you execute on the Tradovate UI; you then update the state file
with the fills.

Modes:
  --source file    (default) read positions from data/state.json
  --source tradovate    query Tradovate REST API (requires env vars set)
  --paper          use Tradovate demo host (with --source tradovate)
  --auto-fire      actually place orders (default: dry-run, print only)

Cron suggestion (1st trading day of month, after close):
  0 17 1 * 1-5  /path/to/.venv/bin/python /path/to/scripts/monthly_rebalance.py
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd
import yfinance as yf

from ten_cent_bot.contracts import CONTRACTS, DEPLOYMENT_BASKET
from ten_cent_bot.orchestrator import (
    load_state,
    plan_rebalance,
    save_state,
)

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_STATE_FILE = ROOT / "data" / "state.json"


def fetch_monthly_prices(basket: list[str]) -> tuple[pd.DataFrame, dict[str, float]]:
    """Fetch each contract's daily history; return (monthly_close, latest_daily_close)."""
    yf_symbols = [CONTRACTS[s].yf_symbol for s in basket]
    data = yf.download(
        yf_symbols, period="max", interval="1d", auto_adjust=True, progress=False
    )
    if isinstance(data.columns, pd.MultiIndex):
        daily = data["Close"]
    else:
        daily = data[["Close"]].rename(columns={"Close": yf_symbols[0]})

    # Map yfinance columns back to our basket symbols
    rename = {CONTRACTS[s].yf_symbol: s for s in basket}
    daily = daily.rename(columns=rename)[basket]

    monthly = daily.resample("ME").last().dropna()
    last_prices = {s: float(daily[s].dropna().iloc[-1]) for s in basket}
    return monthly, last_prices


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", choices=("file", "tradovate"), default="file")
    parser.add_argument("--paper", action="store_true", help="use Tradovate demo host")
    parser.add_argument("--auto-fire", action="store_true", help="actually place orders (default dry-run)")
    parser.add_argument("--state-file", type=Path, default=DEFAULT_STATE_FILE)
    parser.add_argument(
        "--equity-override",
        type=float,
        default=None,
        help="override account equity (file mode only)",
    )
    args = parser.parse_args()

    basket = DEPLOYMENT_BASKET
    print(f"Sleeve B monthly rebalance ({args.source} mode, basket: {basket})")

    print("\nFetching prices ...")
    monthly_prices, last_prices = fetch_monthly_prices(basket)
    print(
        f"  Monthly bars: {monthly_prices.index.min().date()} -> "
        f"{monthly_prices.index.max().date()} ({len(monthly_prices)} months)"
    )

    if args.source == "file":
        state = load_state(args.state_file)
        current_positions = {s: int(state["positions"].get(s, 0)) for s in basket}
        account_equity = (
            args.equity_override
            if args.equity_override is not None
            else state.get("account_equity")
        )
        if account_equity is None:
            print(
                f"\nNo account_equity in {args.state_file}. "
                "Pass --equity-override to set initial equity. "
                "Example: --equity-override 25000"
            )
            return 1
    else:  # tradovate
        from ten_cent_bot.tradovate import TradovateClient, TradovateConfig

        try:
            cfg = TradovateConfig.from_env(paper=args.paper)
            client = TradovateClient(cfg)
            current_positions = client.positions_by_symbol()
            account_equity = client.get_account_equity()
            current_positions = {s: int(current_positions.get(s, 0)) for s in basket}
            print(
                f"\nTradovate ({'PAPER' if args.paper else 'LIVE'}) account equity: "
                f"${account_equity:,.2f}"
            )
        except Exception as e:
            print(f"\nTradovate query failed: {e}")
            return 2

    plan = plan_rebalance(
        monthly_prices=monthly_prices,
        last_prices=last_prices,
        current_positions=current_positions,
        account_equity=float(account_equity),
        basket=basket,
    )

    print("\n" + plan.trade_ticket())

    if not plan.orders:
        return 0

    if args.auto_fire:
        if args.source != "tradovate":
            print("\n--auto-fire requires --source tradovate")
            return 3
        from ten_cent_bot.tradovate import TradovateClient, TradovateConfig

        cfg = TradovateConfig.from_env(paper=args.paper)
        client = TradovateClient(cfg)
        print("\nFiring orders ...")
        for order in plan.orders:
            side_tv = "Buy" if order.side == "BUY" else "Sell"
            result = client.place_order(
                symbol=order.symbol, qty=order.qty, side=side_tv, dry_run=False
            )
            print(f"  {order} -> {result}")
    else:
        print("\n(dry-run: no orders sent. Use --auto-fire with --source tradovate to actually trade.)")

    # Persist post-trade positions when running in file mode
    if args.source == "file":
        new_positions = dict(current_positions)
        for o in plan.orders:
            delta = o.qty if o.side == "BUY" else -o.qty
            new_positions[o.symbol] = new_positions.get(o.symbol, 0) + delta
        save_state(args.state_file, new_positions, float(account_equity))
        print(f"\nState updated: {args.state_file}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
