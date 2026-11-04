from __future__ import annotations

import pandas as pd
import pytest

from ten_cent_bot.contracts import CONTRACTS
from ten_cent_bot.orchestrator import (
    Order,
    compute_orders,
    risk_gate,
    signal_to_target_contracts,
)


def test_compute_orders_basic_diff():
    target = {"MES": 3, "MNQ": 1, "ZN": 2}
    current = {"MES": 0, "MNQ": 1, "ZN": -1}
    orders = compute_orders(target, current)
    by_symbol = {o.symbol: o for o in orders}
    assert by_symbol["MES"] == Order("MES", "BUY", 3)
    assert "MNQ" not in by_symbol  # already at target
    assert by_symbol["ZN"] == Order("ZN", "BUY", 3)  # from -1 to +2 = +3


def test_compute_orders_no_change():
    assert compute_orders({"MES": 2}, {"MES": 2}) == []


def test_compute_orders_close_position():
    orders = compute_orders({"MES": 0}, {"MES": 2})
    assert orders == [Order("MES", "SELL", 2)]


def test_compute_orders_flip_sign():
    orders = compute_orders({"MES": 2}, {"MES": -1})
    assert orders == [Order("MES", "BUY", 3)]


def test_signal_to_target_contracts_basic():
    # MES point_value=5, price=6000 -> $30k notional/contract.
    # weight=1.0, equity=30k -> exactly 1 contract.
    weights = pd.Series({"MES": 1.0})
    target = signal_to_target_contracts(
        target_weights=weights,
        last_prices={"MES": 6000.0},
        account_equity=30_000.0,
        basket=["MES"],
    )
    assert target["MES"] == 1


def test_signal_to_target_contracts_scales_with_equity():
    # Same weight=1.0 but 3x the equity -> 3 contracts.
    target = signal_to_target_contracts(
        target_weights=pd.Series({"MES": 1.0}),
        last_prices={"MES": 6000.0},
        account_equity=90_000.0,
        basket=["MES"],
    )
    assert target["MES"] == 3


def test_signal_to_target_contracts_short():
    weights = pd.Series({"MES": -1.0})  # short, full NAV
    target = signal_to_target_contracts(
        target_weights=weights,
        last_prices={"MES": 6000.0},
        account_equity=60_000.0,
        basket=["MES"],
    )
    # -1.0 * 60000 / (6000*5) = -2.0 -> rounds to -2
    assert target["MES"] == -2


def test_signal_to_target_contracts_zero_weight():
    weights = pd.Series({"MES": 0.0, "MNQ": 0.0})
    target = signal_to_target_contracts(
        target_weights=weights,
        last_prices={"MES": 6000.0, "MNQ": 22000.0},
        account_equity=25_000.0,
        basket=["MES", "MNQ"],
    )
    assert target == {"MES": 0, "MNQ": 0}


def test_risk_gate_allows_with_no_history():
    allowed, reason = risk_gate(None)
    assert allowed
    assert reason is None


def test_risk_gate_blocks_on_low_sharpe():
    # 30 days of negative returns
    dates = pd.date_range("2026-05-01", periods=40, freq="B")
    equity = pd.Series([100 - 0.5 * i for i in range(len(dates))], index=dates)
    allowed, reason = risk_gate(equity, cfg_min_sharpe=0.3)
    assert not allowed
    assert "Sharpe" in (reason or "")


def test_contracts_basket_resolves():
    # Every symbol in the deployment basket has a contract spec
    from ten_cent_bot.contracts import DEPLOYMENT_BASKET
    for sym in DEPLOYMENT_BASKET:
        assert sym in CONTRACTS, f"Missing contract spec: {sym}"
        assert CONTRACTS[sym].point_value > 0


def test_thin_basket_warning_and_pending_flow(tmp_path):
    import json
    import numpy as np
    import pandas as pd
    from ten_cent_bot.orchestrator import RebalancePlan, apply_pending, load_state, write_pending

    plan = RebalancePlan(
        as_of=pd.Timestamp("2026-11-30"), account_equity=25000.0,
        target_positions={"MES": 1, "SI": 0}, current_positions={"MES": 0, "SI": 0},
        orders=[Order("MES", "BUY", 1)], unfunded=("SI",), min_equity_full_basket=90000.0,
    )
    txt = plan.trade_ticket()
    assert "WARNING" in txt and "SI" in txt and "$90,000" in txt
    pending = tmp_path / "pending.json"; state = tmp_path / "state.json"
    write_pending(pending, plan, {"MES": "MESZ6", "SI": "SIZ6"})
    assert load_state(state)["positions"] == {}          # a dry run changes nothing
    st = apply_pending(pending, state)
    assert st["positions"] == {"MES": 1, "SI": 0} and st["contracts"]["MES"] == "MESZ6"
    assert not pending.exists()


def test_plan_rebalance_flags_unfunded_markets():
    import numpy as np
    import pandas as pd
    from ten_cent_bot.orchestrator import plan_rebalance

    idx = pd.date_range("2015-01-31", periods=60, freq="ME")
    prices = pd.DataFrame({"MES": np.linspace(100, 300, 60), "SI": np.linspace(10, 40, 60)}, index=idx)
    plan = plan_rebalance(prices, {"MES": 300.0, "SI": 40.0}, {"MES": 0, "SI": 0}, 2000.0, ["MES", "SI"])
    # at $2k a silver contract (5000 oz x $40 = $200k) can never be funded
    assert "SI" in plan.unfunded
    assert plan.min_equity_full_basket is not None and plan.min_equity_full_basket > 2000
