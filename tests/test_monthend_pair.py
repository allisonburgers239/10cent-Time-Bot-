from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd

from ten_cent_bot import monthend_pair as mp


def _prices(n_days=400, seed=0):
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2023-01-02", periods=n_days)
    s = pd.Series(100 * np.exp(np.cumsum(rng.normal(0.0004, 0.01, n_days))), index=idx)
    b = pd.Series(100 * np.exp(np.cumsum(rng.normal(0.0001, 0.006, n_days))), index=idx)
    return s, b


def test_decision_thresholds():
    cfg = mp.MonthEndConfig(threshold=0.03)
    assert mp.decision(0.05, 0.01, cfg) == -1     # stocks beat bonds by 4% -> short stock / long bond
    assert mp.decision(-0.02, 0.02, cfg) == 1     # stocks lag by 4% -> long stock / short bond
    assert mp.decision(0.02, 0.0, cfg) == 0       # inside the band
    assert mp.decision(0.03, 0.0, cfg) == 0       # exactly at the band is not a trade


def test_sessions_left_in_month_known_dates():
    assert mp.sessions_left_in_month(dt.date(2026, 11, 30)) == 1      # Monday, last session of Nov 2026
    assert mp.sessions_left_in_month(dt.date(2026, 11, 23)) == 5      # Mon 23, Tue 24, Wed 25, Fri 27 (Thu = Thanksgiving), Mon 30
    assert mp.sessions_left_in_month(dt.date(2026, 11, 28)) == 1      # Saturday: only Mon 30 remains


def test_events_match_manual_computation():
    s, b = _prices()
    cfg = mp.MonthEndConfig(threshold=0.0, last_sessions=5, cost_bps_per_side=0.0)   # threshold 0 -> a trade every month
    ev = mp.events(s, b, cfg)
    assert (ev.side != 0).all()
    row = ev.iloc[3]
    m = pd.Timestamp(row.end_date).to_period("M")
    month = s[s.index.to_period("M") == m]
    sig_date = month.index[-1 - 5]
    assert row.signal_date == sig_date
    prev_close = s.index[s.index.get_loc(month.index[0]) - 1]
    spread = (s[sig_date] / s[prev_close] - 1) - (b[sig_date] / b[prev_close] - 1)
    assert abs(row.spread - spread) < 1e-12
    side = -1 if spread > 0 else 1
    manual = side * ((s[row.end_date] / s[sig_date] - 1) - (b[row.end_date] / b[sig_date] - 1))
    assert abs(row.net - manual) < 1e-12


def test_events_use_only_information_through_the_signal_close():
    s, b = _prices()
    cfg = mp.MonthEndConfig(threshold=0.0)
    full = mp.events(s, b, cfg)
    row = full.iloc[5]
    cut = s.index.get_loc(row.signal_date) + 1
    s2, b2 = s.copy(), b.copy()
    s2.iloc[cut:] *= 1.5          # scramble everything after the signal close
    part = mp.events(s2, b2, cfg)
    assert part.iloc[5].side == row.side and abs(part.iloc[5].spread - row.spread) < 1e-12


def test_daily_returns_compound_to_event_returns_and_cost_is_charged_once():
    s, b = _prices(seed=2)
    cfg = mp.MonthEndConfig(threshold=0.0, cost_bps_per_side=1.0)
    ev = mp.events(s, b, cfg); r = mp.daily_returns(s, b, cfg)
    row = ev.iloc[2]
    window = r[(r.index > row.signal_date) & (r.index <= row.end_date)]
    assert len(window) == 5
    # sum of daily pair returns (not compounded) is within rounding of the event's gross minus 4 bp
    assert abs(window.sum() - (row.side * ((s[row.end_date] / s[row.signal_date] - 1) - (b[row.end_date] / b[row.signal_date] - 1)) - 4e-4)) < 5e-4
    assert (r[(r.index <= row.signal_date) & (r.index > ev.iloc[1].end_date)] == 0).all()   # flat between windows
