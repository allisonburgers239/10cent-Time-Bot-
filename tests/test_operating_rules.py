import datetime as dt

import pandas as pd

from ten_cent_bot import calendar_nyse as cal
from ten_cent_bot import rolls
from ten_cent_bot.orchestrator import risk_gate
from ten_cent_bot.risk import daily_loss_cap_hit, price_is_fresh, price_is_plausible
from ten_cent_bot.state import append_equity, load_equity_history


def test_nyse_holidays_known_dates():
    assert not cal.is_trading_day(dt.date(2026, 1, 1))        # New Year's
    assert not cal.is_trading_day(dt.date(2026, 1, 19))       # MLK
    assert not cal.is_trading_day(dt.date(2026, 4, 3))        # Good Friday 2026
    assert not cal.is_trading_day(dt.date(2026, 11, 26))      # Thanksgiving
    assert not cal.is_trading_day(dt.date(2025, 1, 9))        # ad hoc closure
    assert cal.is_trading_day(dt.date(2026, 11, 3))
    assert not cal.is_trading_day(dt.date(2026, 11, 7))       # Saturday
    assert not cal.is_trading_day(dt.date(2026, 7, 3))        # July 4 2026 is Saturday -> observed Friday


def test_early_closes():
    assert cal.is_early_close(dt.date(2026, 11, 27))          # day after Thanksgiving
    assert cal.is_early_close(dt.date(2026, 12, 24))
    assert not cal.is_early_close(dt.date(2026, 11, 3))
    assert cal.session_close(dt.date(2026, 11, 27)) == dt.time(13, 0)


def test_next_trading_day_skips_weekend_and_holiday():
    assert cal.next_trading_day(dt.date(2026, 11, 25)) == dt.date(2026, 11, 27)   # over Thanksgiving
    assert cal.next_trading_day(dt.date(2026, 11, 6)) == dt.date(2026, 11, 9)     # Fri -> Mon


def test_roll_rules_equity_index():
    # Dec 2026 MES: third Friday is 2026-12-18; roll 8 days before -> 12-10
    assert rolls.last_trade_date("MES", 2026, 12) == dt.date(2026, 12, 18)
    assert rolls.roll_date("MES", 2026, 12) == dt.date(2026, 12, 10)
    assert rolls.active_contract("MES", dt.date(2026, 11, 3)) == (2026, 12)
    assert rolls.active_contract("MES", dt.date(2026, 12, 11)) == (2027, 3)
    assert rolls.contract_symbol("MES", 2026, 12) == "MESZ6"
    assert rolls.roll_due("MES", "MESZ6", dt.date(2026, 12, 10))
    assert not rolls.roll_due("MES", "MESZ6", dt.date(2026, 12, 9))


def test_roll_rules_gold_and_crude():
    assert rolls.active_contract("MGC", dt.date(2026, 11, 3)) == (2026, 12)   # Dec gold, roll ~Nov 27
    assert rolls.active_contract("MGC", dt.date(2026, 11, 28)) == (2027, 2)
    assert rolls.active_contract("MCL", dt.date(2026, 11, 3)) == (2026, 12)   # Dec CL expires ~Nov 20, roll Nov 17
    assert rolls.active_contract("MCL", dt.date(2026, 11, 18)) == (2027, 1)
    assert rolls.parse_symbol("MGCG7", "MGC", dt.date(2026, 11, 3)) == (2027, 2)


def test_daily_loss_cap_and_data_guards():
    eq = pd.Series([100.0, 97.0])
    hit, why = daily_loss_cap_hit(eq); assert hit and "skip" in why
    assert not daily_loss_cap_hit(pd.Series([100.0, 99.0]))[0]
    now = pd.Timestamp("2026-11-03 15:50")
    assert price_is_fresh(pd.Timestamp("2026-11-03 15:45"), now)[0]
    assert not price_is_fresh(pd.Timestamp("2026-11-03 15:20"), now)[0]
    assert price_is_plausible(101.0, 100.0)[0]
    assert not price_is_plausible(120.0, 100.0)[0]


def test_equity_history_feeds_kill_switch(tmp_path):
    p = tmp_path / "equity_history.csv"
    base = dt.date(2026, 9, 1)
    eq = 100.0
    for i in range(45):
        eq *= 0.995   # steady bleed -> rolling Sharpe << 0.3
        append_equity(p, eq, base + dt.timedelta(days=i))
    hist = load_equity_history(p)
    assert len(hist) == 45
    allowed, reason = risk_gate(hist)
    assert not allowed and "Sharpe" in reason
    allowed, _ = risk_gate(None)
    assert allowed   # documented: no history -> allow (this is why wiring matters)


def test_drawdown_gate_alert_then_stop():
    from ten_cent_bot.orchestrator import drawdown_gate
    eq = pd.Series([100.0, 110.0, 95.0])          # -13.6% from peak
    assert drawdown_gate(eq) == (True, None, None)
    eq = pd.Series([100.0, 110.0, 92.0])          # -16.4%: alert, still allowed
    ok, why, alert = drawdown_gate(eq); assert ok and why is None and "REVIEW" in alert
    eq = pd.Series([100.0, 110.0, 80.0])          # -27%: stop
    ok, why, _ = drawdown_gate(eq); assert not ok and "STOP" in why
    assert drawdown_gate(None) == (True, None, None)
