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


# --- operating guards (2026-11-03) -----------------------------------------
import pandas as pd  # noqa: E402


def daily_loss_cap_hit(equity: pd.Series, cap: float = 0.02) -> tuple[bool, str | None]:
    """README rule: 2% daily loss -> flatten and stop. For an overnight sleeve
    the stop is applied to the NEXT entry: if the last recorded day lost more
    than `cap` of equity, skip tonight.  Needs >= 2 equity points."""
    if equity is None or len(equity) < 2:
        return False, None
    last = float(equity.iloc[-1] / equity.iloc[-2] - 1)
    if last < -cap:
        return True, f"last session {last:.2%} < -{cap:.0%} daily loss cap: skip tonight"
    return False, None


def price_is_fresh(last_bar_time: pd.Timestamp, now: pd.Timestamp, max_age_min: int = 10) -> tuple[bool, str | None]:
    """Fail closed if the quote used for the signal is older than max_age_min."""
    age = (now - last_bar_time).total_seconds() / 60
    if age > max_age_min:
        return False, f"last quote is {age:.0f} min old (> {max_age_min}): data stale, NO TRADE"
    return True, None


def price_is_plausible(last_price: float, prev_close: float, max_move: float = 0.08) -> tuple[bool, str | None]:
    """Fail closed on a quote that moved more than max_move from the prior
    close (a bad print or a wrong symbol, far more often than a real crash)."""
    mv = last_price / prev_close - 1
    if abs(mv) > max_move:
        return False, f"quote moved {mv:+.1%} vs prior close (> {max_move:.0%}): suspect data, NO TRADE"
    return True, None
