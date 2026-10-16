"""Sleeve E unit tests: signal lag, default behaviour, overlay wiring."""
import numpy as np
import pandas as pd
import pytest

from ten_cent_bot import overnight
from ten_cent_bot.overnight import OvernightConfig, down_streak, reversal_signal, rsi


def _ohlc(closes, opens=None):
    idx = pd.bdate_range("2024-01-01", periods=len(closes))
    closes = pd.Series(closes, index=idx, dtype=float)
    opens = closes.shift(1).fillna(closes.iloc[0]) if opens is None else pd.Series(opens, index=idx, dtype=float)
    return pd.DataFrame({"open": opens, "close": closes})


def test_default_config_is_unchanged_by_overlay_code():
    df = _ohlc([100, 99, 98, 97, 98, 99, 98, 97, 96, 97])
    r = overnight.backtest_single(df, OvernightConfig())
    assert (r["position"] == 1.0).all()


def test_down_streak_counts_consecutive_down_closes():
    s = down_streak(pd.Series([100, 99, 98, 97, 98, 97, 96], dtype=float))
    assert s.tolist() == [0, 1, 2, 3, 0, 1, 2]


def test_streak_signal_fires_on_entry_day_close_only():
    # closes: three down days end on day 3 -> overlay applies to the overnight
    # that STARTS at day 3's close, i.e. position[day3] is scaled.
    df = _ohlc([100, 99, 98, 97, 100, 101])
    cfg = OvernightConfig(reversal_signal="streak", reversal_streak_k=3, reversal_multiplier=2.0)
    r = overnight.backtest_single(df, cfg)
    pos = r["position"].tolist()
    assert pos[3] == 2.0
    assert pos[2] == 1.0 and pos[4] == 1.0


def test_signal_uses_no_future_data():
    df = _ohlc([100, 99, 98, 97, 96, 95, 94, 93])
    cfg = OvernightConfig(reversal_signal="either", reversal_multiplier=2.0)
    full = reversal_signal(df["close"], cfg)
    # recompute on a truncated series: earlier values must be identical
    trunc = reversal_signal(df["close"].iloc[:5], cfg)
    assert (full.iloc[:5].values == trunc.values).all()


def test_rsi2_signal_fires_after_sharp_drop():
    closes = [100] * 10 + [97, 94, 91]
    r = rsi(pd.Series(closes, dtype=float), 2)
    assert r.iloc[-1] < 10


def test_overlay_scales_cost_with_size():
    df = _ohlc([100, 99, 98, 97, 100])
    cfg = OvernightConfig(reversal_signal="streak", reversal_multiplier=2.0, cost_bps_per_side=1.0)
    r = overnight.backtest_single(df, cfg)
    gross = r["gross_return"].iloc[3]
    net = r["net_return"].iloc[3]
    assert pytest.approx(gross - net, rel=1e-9) == 2.0 * 2 * 1.0 / 10_000


def test_unknown_signal_rejected():
    with pytest.raises(ValueError):
        reversal_signal(pd.Series([1.0, 2.0]), OvernightConfig(reversal_signal="magic", reversal_multiplier=2.0))
