from __future__ import annotations

import numpy as np
import pandas as pd

from ten_cent_bot import swing_reversal as sw


def _hourly(n_days: int = 300, seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    idx = []
    for d in pd.bdate_range("2024-01-02", periods=n_days):
        for h in range(9, 16):
            idx.append(pd.Timestamp(d.date()).replace(hour=h, minute=30 if h == 9 else 0))
    idx = pd.DatetimeIndex(idx).tz_localize("America/New_York")
    px = 100 * np.exp(np.cumsum(rng.normal(0.0002, 0.004, len(idx))))
    df = pd.DataFrame({"open": px, "high": px * 1.002, "low": px * 0.998, "close": px}, index=idx)
    return df


def test_to_4h_gives_two_bars_per_day():
    f = sw.to_4h(_hourly(20))
    per_day = f.groupby(f.index.date).size()
    assert (per_day == 2).all()
    assert str(f.index[0].time()) == "09:30:00" and str(f.index[1].time()) == "13:30:00"


def test_signal_uses_only_past_information():
    cfg = sw.SwingConfig(trend_ema=50)
    f = sw.signals(sw.to_4h(_hourly(300)), cfg)
    cut = len(f) // 2
    g = sw.signals(sw.to_4h(_hourly(300)).iloc[:cut], cfg)
    assert (f.sig.iloc[:cut].to_numpy() == g.sig.to_numpy()).all()  # truncating the future changes nothing in the past
    assert f.ema.isna().sum() >= 1  # the first day has no yesterday-EMA


def test_trade_returns_match_manual_fill():
    cfg = sw.SwingConfig(trend_ema=50, hold_bars=3, cost_bps_per_side=0.0)
    f = sw.signals(sw.to_4h(_hourly(300, seed=3)), cfg)
    tr = sw.trade_returns(f, cfg)
    if len(tr):
        t0 = tr.index[0]; i = list(f.index).index(t0)
        expected = f.close.iloc[i + 1 + 3] / f.open.iloc[i + 1] - 1
        assert abs(tr.iloc[0] - expected) < 1e-12


def test_backtest_respects_slots_and_one_position_per_symbol():
    cfg = sw.SwingConfig(trend_ema=50, max_slots=1)
    bars = {"A": sw.to_4h(_hourly(300, seed=1)), "B": sw.to_4h(_hourly(300, seed=2))}
    res = sw.backtest(bars, cfg)
    t = res["trades"]
    for k in range(1, len(t)):
        assert t.entry_signal.iloc[k] >= t.exit.iloc[k - 1]  # with one slot, trades never overlap
    assert abs(res["daily"].sum() - t.ret.sum() / cfg.max_slots) < 1e-9


def test_cost_scales_per_trade():
    bars = {"A": sw.to_4h(_hourly(300, seed=4))}
    r0 = sw.backtest(bars, sw.SwingConfig(trend_ema=50, cost_bps_per_side=0.0))["trades"].ret
    r1 = sw.backtest(bars, sw.SwingConfig(trend_ema=50, cost_bps_per_side=5.0))["trades"].ret
    if len(r0):
        assert np.allclose(r0.to_numpy() - r1.to_numpy(), 10 / 1e4)
