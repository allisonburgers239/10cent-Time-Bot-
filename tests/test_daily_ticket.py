import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import daily_overnight_ticket as dt  # noqa: E402


def _closes(tickers, last_three_down=False):
    idx = pd.bdate_range("2026-01-01", periods=40)
    out = {}
    for t in tickers:
        base = np.linspace(100, 110, 40)
        if last_three_down:
            base[-3:] = [104, 102, 100]
        out[t] = pd.Series(base, index=idx)
    return out


def test_no_overlay_sizes_equal_weight_etf_rail():
    closes = _closes(["SPY", "QQQ", "IWM"])
    legs = dt.plan_overnight(closes, {"SPY": 100.0, "QQQ": 100.0, "IWM": 100.0}, 30000, "e", "none", "etf")
    assert [L.qty for L in legs] == [100, 100, 100]
    assert all(L.multiplier == 1.0 for L in legs)


def test_v2_overlay_doubles_signal_leg():
    closes = _closes(["SPY", "QQQ", "IWM", "GLD"], last_three_down=True)
    last = {t: 98.0 for t in closes}   # another down print -> RSI2 ~ 0
    legs = dt.plan_overnight(closes, last, 40000, "e3", "v2", "etf")
    assert all(L.multiplier == 2.0 for L in legs)
    assert all(L.qty == int(40000 / 4 * 2 // 98.0) for L in legs)


def test_futures_rail_rounds_to_zero_for_small_account_and_flags_min_book():
    closes = _closes(["SPY", "QQQ", "IWM", "GLD"])
    last = {"SPY": 780.0, "QQQ": 750.0, "IWM": 250.0, "GLD": 400.0}
    futs = {"ES=F": 7800.0, "NQ=F": 30000.0, "RTY=F": 2500.0, "GC=F": 4000.0}
    legs = dt.plan_overnight(closes, last, 25000, "e3", "none", "futures", futs)
    assert [L.instrument for L in legs] == ["MES", "MNQ", "M2K", "MGC"]
    assert legs[0].unit_notional == 7800.0 * 5
    assert legs[0].qty == 0 and legs[0].min_viable_qty == 1
    txt = dt.ticket(legs, 25000, "e3", "none", "futures")
    assert "Minimum viable book" in txt


def test_signal_uses_provisional_close_not_history_only():
    tk = ["SPY", "QQQ", "IWM"]
    up = dt.plan_overnight(_closes(tk), {t: 120.0 for t in tk}, 10000, "e", "v2", "etf")[0]
    dn = dt.plan_overnight(_closes(tk, True), {t: 95.0 for t in tk}, 10000, "e", "v2", "etf")[0]
    assert up.multiplier == 1.0 and dn.multiplier == 2.0
