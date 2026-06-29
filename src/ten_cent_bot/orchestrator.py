"""Monthly rebalance orchestrator for Sleeve B (TSMOM on CME futures).

Universe-agnostic core: takes target portfolio weights, current positions,
and account equity; emits a clean list of orders to align them. Same code
serves both the dry-run trade-ticket mode (manual execution on Tradovate UI)
and the live auto-trade mode (Tradovate REST API).
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from .contracts import CONTRACTS, ContractSpec
from .tsmom import TSMOMConfig, backtest


@dataclass(frozen=True)
class Order:
    symbol: str
    side: str  # "BUY" or "SELL"
    qty: int

    def __str__(self) -> str:
        return f"{self.side:>4} {self.qty:>3}  {self.symbol}"


@dataclass(frozen=True)
class RebalancePlan:
    as_of: pd.Timestamp
    account_equity: float
    target_positions: dict[str, int]
    current_positions: dict[str, int]
    orders: list[Order]
    skipped_reason: str | None = None

    def trade_ticket(self) -> str:
        lines = [
            "Sleeve B monthly rebalance",
            f"As of:           {self.as_of.date()}",
            f"Account equity:  ${self.account_equity:,.2f}",
            "",
            f"{'Symbol':>6}  {'Current':>7}  {'Target':>6}  Action",
            "-" * 40,
        ]
        for symbol in sorted(set(self.target_positions) | set(self.current_positions)):
            cur = self.current_positions.get(symbol, 0)
            tgt = self.target_positions.get(symbol, 0)
            delta = tgt - cur
            action = "HOLD" if delta == 0 else (f"BUY {delta}" if delta > 0 else f"SELL {-delta}")
            lines.append(f"{symbol:>6}  {cur:>+7}  {tgt:>+6}  {action}")
        lines.append("-" * 40)
        lines.append(f"{len(self.orders)} order(s) to enter")
        if self.skipped_reason:
            lines.append(f"\n!! SKIPPED: {self.skipped_reason}")
        return "\n".join(lines)


def signal_to_target_contracts(
    target_weights: pd.Series,
    last_prices: dict[str, float],
    account_equity: float,
    basket: list[str],
    contracts: dict[str, ContractSpec] = CONTRACTS,
) -> dict[str, int]:
    """Convert a vol-targeted weight per asset (in pct of NAV) to integer contracts.

    For long positions: round(target_notional / contract_notional).
    For short positions: same with negative sign.
    Zero weight -> zero contracts.
    """
    target: dict[str, int] = {}
    for symbol in basket:
        if symbol not in contracts:
            raise KeyError(f"Unknown contract spec: {symbol}")
        spec = contracts[symbol]
        weight = float(target_weights.get(symbol, 0.0))
        if weight == 0.0 or np.isnan(weight):
            target[symbol] = 0
            continue
        price = last_prices[symbol]
        contract_notional = price * spec.point_value
        if contract_notional <= 0:
            target[symbol] = 0
            continue
        target[symbol] = int(round(weight * account_equity / contract_notional))
    return target


def compute_orders(
    target_positions: dict[str, int],
    current_positions: dict[str, int],
) -> list[Order]:
    """Diff target vs current, emit minimal orders to align."""
    orders: list[Order] = []
    symbols = sorted(set(target_positions) | set(current_positions))
    for symbol in symbols:
        target = target_positions.get(symbol, 0)
        current = current_positions.get(symbol, 0)
        delta = target - current
        if delta == 0:
            continue
        side = "BUY" if delta > 0 else "SELL"
        orders.append(Order(symbol=symbol, side=side, qty=abs(delta)))
    return orders


def risk_gate(
    portfolio_equity: pd.Series | None,
    cfg_rolling_window: int = 30,
    cfg_min_sharpe: float = 0.3,
    cfg_max_mtd_drawdown: float = 0.02,
) -> tuple[bool, str | None]:
    """Return (allowed, reason). If portfolio_equity history is missing, allow."""
    if portfolio_equity is None or len(portfolio_equity) < cfg_rolling_window + 1:
        return True, None

    recent = portfolio_equity.iloc[-(cfg_rolling_window + 1) :]
    returns = recent.pct_change().dropna()
    if returns.std(ddof=0) > 0:
        ann_sharpe = float(returns.mean() / returns.std(ddof=0) * np.sqrt(252))
        if ann_sharpe < cfg_min_sharpe:
            return False, f"30d rolling Sharpe {ann_sharpe:.2f} < {cfg_min_sharpe}"

    # MTD drawdown
    month_start = recent.index[-1].replace(day=1)
    mtd = recent[recent.index >= month_start]
    if len(mtd) > 1:
        mtd_dd = float(mtd.iloc[-1] / mtd.cummax().iloc[-1] - 1)
        if mtd_dd < -cfg_max_mtd_drawdown:
            return False, f"MTD drawdown {mtd_dd:.2%} > {cfg_max_mtd_drawdown:.0%}"

    return True, None


def plan_rebalance(
    monthly_prices: pd.DataFrame,
    last_prices: dict[str, float],
    current_positions: dict[str, int],
    account_equity: float,
    basket: list[str],
    portfolio_equity: pd.Series | None = None,
    tsmom_config: TSMOMConfig | None = None,
) -> RebalancePlan:
    """End-to-end: run TSMOM, compute target contracts, diff, emit plan."""
    cfg = tsmom_config or TSMOMConfig()
    result = backtest(monthly_prices, cfg)
    # Latest signal-driven weight per asset (after lagging, this is the
    # position to hold during the upcoming month).
    weights = result["position"].iloc[-1]

    target = signal_to_target_contracts(
        target_weights=weights,
        last_prices=last_prices,
        account_equity=account_equity,
        basket=basket,
    )
    orders = compute_orders(target, current_positions)
    allowed, reason = risk_gate(portfolio_equity)
    if not allowed:
        orders = []

    return RebalancePlan(
        as_of=monthly_prices.index[-1],
        account_equity=account_equity,
        target_positions=target,
        current_positions={s: current_positions.get(s, 0) for s in basket},
        orders=orders,
        skipped_reason=reason,
    )


# -------------------------------------------------------------------------
# State persistence for the manual-execution mode
# -------------------------------------------------------------------------


def load_state(path: Path) -> dict:
    """Load positions + equity from a JSON state file. Empty state if missing."""
    if not path.exists():
        return {"positions": {}, "account_equity": None}
    return json.loads(path.read_text())


def save_state(path: Path, positions: dict[str, int], account_equity: float) -> None:
    path.write_text(
        json.dumps(
            {"positions": positions, "account_equity": account_equity},
            indent=2,
        )
    )
