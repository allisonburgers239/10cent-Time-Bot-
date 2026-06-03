from __future__ import annotations

import pandas as pd

from ten_cent_bot.orb import ORBConfig, generate_signals


def _bars(rows: list[tuple]) -> pd.DataFrame:
    """rows = list of (ts_str_ET, open, high, low, close)."""
    records = []
    for ts, o, h, l, c in rows:
        records.append(
            {
                "timestamp": pd.Timestamp(ts, tz="America/New_York").tz_convert("UTC"),
                "open": o,
                "high": h,
                "low": l,
                "close": c,
                "volume": 1_000,
            }
        )
    return pd.DataFrame(records).set_index("timestamp").sort_index()


def test_long_breakout_runs_to_session_close():
    bars = _bars(
        [
            ("2024-01-02 09:30", 100.0, 101.0, 99.0, 100.5),  # OR: high=101, low=99
            ("2024-01-02 09:35", 100.5, 102.0, 100.4, 101.8),  # breaks above 101
            ("2024-01-02 09:40", 101.8, 103.0, 101.5, 102.5),
            ("2024-01-02 15:55", 102.5, 103.0, 102.0, 102.7),  # session close bar
        ]
    )
    cfg = ORBConfig(vol_filter_lookback=0)
    signals = generate_signals(bars, cfg)

    assert len(signals) == 1
    row = signals.iloc[0]
    assert row["side"] == "long"
    assert row["or_high"] == 101.0
    assert row["or_low"] == 99.0
    assert row["entry_price"] == 101.0
    assert row["stop"] == 99.0
    assert row["exit_reason"] == "session_close"
    assert row["pnl_points"] == pytest_approx(row["exit_price"] - 101.0)


def test_short_breakout_stops_out():
    bars = _bars(
        [
            ("2024-01-03 09:30", 100.0, 101.0, 99.0, 99.5),   # OR: high=101, low=99
            ("2024-01-03 09:35", 99.5, 99.8, 98.5, 98.7),     # breaks below 99 -> short @ 99
            ("2024-01-03 09:40", 98.7, 101.2, 98.6, 101.0),   # high=101.2 hits stop @ 101
            ("2024-01-03 15:55", 101.0, 101.5, 100.5, 101.2),
        ]
    )
    cfg = ORBConfig(vol_filter_lookback=0)
    signals = generate_signals(bars, cfg)

    assert len(signals) == 1
    row = signals.iloc[0]
    assert row["side"] == "short"
    assert row["entry_price"] == 99.0
    assert row["stop"] == 101.0
    assert row["exit_reason"] == "stop"
    assert row["pnl_points"] == pytest_approx(99.0 - 101.0)


def test_no_breakout_no_trade():
    # Bars stay strictly inside the opening range -> no entry, no row emitted.
    bars = _bars(
        [
            ("2024-01-04 09:30", 100.0, 101.0, 99.0, 100.5),
            ("2024-01-04 09:35", 100.5, 100.9, 99.1, 100.0),
            ("2024-01-04 09:40", 100.0, 100.8, 99.2, 99.8),
            ("2024-01-04 15:55", 99.8, 100.5, 99.5, 100.1),
        ]
    )
    cfg = ORBConfig(vol_filter_lookback=0)
    signals = generate_signals(bars, cfg)
    assert signals.empty


def pytest_approx(value, tol: float = 1e-9):
    class _Approx:
        def __eq__(self, other):
            return abs(other - value) < tol
        def __repr__(self):
            return f"~{value}"
    return _Approx()
