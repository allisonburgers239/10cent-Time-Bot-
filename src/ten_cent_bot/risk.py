from __future__ import annotations


def position_size(
    equity: float,
    risk_pct: float,
    entry: float,
    stop: float,
    point_value: float,
) -> int:
    """Number of contracts whose dollar risk to `stop` <= equity * risk_pct.

    Returns 0 if the stop distance is zero (degenerate) or if even one
    contract exceeds the risk budget.
    """
    stop_distance = abs(entry - stop)
    if stop_distance == 0:
        return 0
    risk_budget = equity * risk_pct
    risk_per_contract = stop_distance * point_value
    return max(0, int(risk_budget // risk_per_contract))
