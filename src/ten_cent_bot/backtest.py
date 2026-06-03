from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from .risk import position_size


@dataclass(frozen=True)
class BacktestConfig:
    starting_equity: float = 25_000.0
    risk_pct: float = 0.01
    point_value: float = 2.0  # MNQ = $2/point
    cost_per_contract_rt: float = 2.0  # commissions + 1-tick slippage, conservative


def run(signals: pd.DataFrame, config: BacktestConfig | None = None) -> pd.DataFrame:
    """Walk an ORB-style signals frame and produce a per-trade equity curve."""
    cfg = config or BacktestConfig()
    equity = cfg.starting_equity
    rows: list[dict] = []

    for _, trade in signals.iterrows():
        contracts = position_size(
            equity=equity,
            risk_pct=cfg.risk_pct,
            entry=trade["entry_price"],
            stop=trade["stop"],
            point_value=cfg.point_value,
        )
        gross_pnl = trade["pnl_points"] * cfg.point_value * contracts
        costs = cfg.cost_per_contract_rt * contracts
        net_pnl = gross_pnl - costs
        equity += net_pnl
        rows.append(
            {
                **trade.to_dict(),
                "contracts": contracts,
                "gross_pnl_dollars": float(gross_pnl),
                "costs": float(costs),
                "net_pnl_dollars": float(net_pnl),
                "equity_after": float(equity),
            }
        )

    return pd.DataFrame(rows)
