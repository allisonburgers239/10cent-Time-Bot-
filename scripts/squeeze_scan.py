"""Volatility-squeeze scanner on 1-minute and 5-minute bars (2026-11-04).

Definitions (fixed, nothing eyeballed):
  Bollinger Bands  BB(20, 2.0 sd) on close
  Keltner Channel  KC(20 EMA, 1.5 x ATR(20))
  Squeeze ON       BB upper < KC upper AND BB lower > KC lower   (John Carter's TTM squeeze)
  Squeeze range    highest high / lowest low over the current run of consecutive squeeze bars
  HV100            annualised std of 1-bar log returns over the last 100 bars
                   (1-min: sqrt(390*252), 5-min: sqrt(78*252); futures/crypto use their own bar counts)
  HV percentile    where the current HV100 sits in the distribution of HV100 over the whole sample
  Volume lean      last 10 bars: share of volume on up bars (close > open). >= 0.60 buyers lean,
                   <= 0.40 sellers lean, else balanced. Also the OBV change over the squeeze run.
  Trigger levels   up = squeeze range high, down = squeeze range low
  Alert levels     up x 1.0005, down x 0.9995 (0.05% beyond the range)

Data: yfinance, 1m (7 days, pre/post market) and 5m (60 days). Stocks only
print bars up to the last session; futures and crypto are live.

Usage: python scripts/squeeze_scan.py [--symbols SPY,QQQ,...] [--json out.json]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent

# (yfinance symbol, TradingView symbol, bars per day for annualising 1m/5m)
WATCHLIST = [
    ("SPY", "AMEX:SPY", 390), ("QQQ", "NASDAQ:QQQ", 390), ("IWM", "AMEX:IWM", 390),
    ("NVDA", "NASDAQ:NVDA", 390), ("TSLA", "NASDAQ:TSLA", 390), ("AAPL", "NASDAQ:AAPL", 390),
    ("AMD", "NASDAQ:AMD", 390), ("AMZN", "NASDAQ:AMZN", 390), ("MSFT", "NASDAQ:MSFT", 390), ("META", "NASDAQ:META", 390),
    ("MNQ=F", "CME_MINI:MNQ1!", 1380), ("MES=F", "CME_MINI:MES1!", 1380), ("M2K=F", "CME_MINI:M2K1!", 1380), ("MGC=F", "COMEX_MINI:MGC1!", 1380),
    ("BTC-USD", "BINANCE:BTCUSDT", 1440),
]


def squeeze_frame(df: pd.DataFrame, bars_per_day: int, minutes: int) -> pd.DataFrame:
    c, h, l = df.Close, df.High, df.Low
    mid = c.rolling(20).mean(); sd = c.rolling(20).std(ddof=0)
    bb_u, bb_l = mid + 2 * sd, mid - 2 * sd
    ema = c.ewm(span=20, adjust=False).mean()
    tr = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1 / 20, adjust=False).mean()
    kc_u, kc_l = ema + 1.5 * atr, ema - 1.5 * atr
    out = df.copy()
    out["bb_u"], out["bb_l"], out["kc_u"], out["kc_l"] = bb_u, bb_l, kc_u, kc_l
    out["sq"] = (bb_u < kc_u) & (bb_l > kc_l)
    out["bb_width_pct"] = (bb_u - bb_l) / mid * 100
    lr = np.log(c).diff()
    ann = np.sqrt(bars_per_day / minutes * 252)
    out["hv100"] = lr.rolling(100).std(ddof=0) * ann * 100
    return out


def describe(sym: str, tv: str, df: pd.DataFrame, bars_per_day: int, minutes: int) -> dict:
    f = squeeze_frame(df, bars_per_day, minutes).dropna(subset=["bb_u", "hv100"])
    if len(f) < 120:
        return {"symbol": tv, "tf": f"{minutes}m", "error": "not enough bars"}
    last = f.iloc[-1]
    # current run of consecutive squeeze bars
    run = 0
    for v in f.sq.to_numpy()[::-1]:
        if not v:
            break
        run += 1
    hv_pct = float((f.hv100 <= last.hv100).mean())
    tail = f.iloc[-10:]
    upv = float(tail.Volume[tail.Close > tail.Open].sum()); dnv = float(tail.Volume[tail.Close < tail.Open].sum())
    tot = upv + dnv
    up_share = upv / tot if tot > 0 else np.nan
    lean = "buyers lean" if up_share >= 0.6 else ("sellers lean" if up_share <= 0.4 else "balanced")
    if tot == 0:
        lean = "no volume data"
    res = {
        "symbol": tv, "tf": f"{minutes}m", "last_bar": str(f.index[-1]), "last": round(float(last.Close), 4),
        "squeeze_on": bool(last.sq), "squeeze_bars": run,
        "bb_width_pct": round(float(last.bb_width_pct), 3), "hv100_ann_pct": round(float(last.hv100), 1), "hv100_percentile": round(hv_pct, 2),
        "up_volume_share_10": round(up_share, 2) if up_share == up_share else None, "volume_lean": lean,
    }
    if run > 0:
        seg = f.iloc[-run:]
        hi, lo = float(seg.High.max()), float(seg.Low.min())
        obv = float(((seg.Close > seg.Open).astype(int) - (seg.Close < seg.Open).astype(int)) * seg.Volume).sum() if False else float((np.sign(seg.Close.diff().fillna(0)) * seg.Volume).sum())
        res.update({"range_high": round(hi, 4), "range_low": round(lo, 4), "range_pct": round((hi / lo - 1) * 100, 3),
                    "alert_up": round(hi * 1.0005, 4), "alert_down": round(lo * 0.9995, 4), "obv_change_in_squeeze": obv})
    return res


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--symbols", default=None, help="comma-separated yfinance symbols (default: built-in watchlist)")
    ap.add_argument("--json", default=None)
    a = ap.parse_args()
    import yfinance as yf

    wl = WATCHLIST if a.symbols is None else [(s, s, 390) for s in a.symbols.split(",")]
    rows = []
    for ysym, tv, bpd in wl:
        for minutes, period in ((1, "7d"), (5, "60d")):
            try:
                df = yf.Ticker(ysym).history(period=period, interval=f"{minutes}m", prepost=True)
            except Exception as e:  # noqa: BLE001
                rows.append({"symbol": tv, "tf": f"{minutes}m", "error": str(e)[:80]}); continue
            if df.empty:
                rows.append({"symbol": tv, "tf": f"{minutes}m", "error": "no data"}); continue
            df.index = df.index.tz_convert("America/New_York")
            rows.append(describe(ysym, tv, df, bpd, minutes))
    out = pd.DataFrame(rows)
    pd.set_option("display.width", 250); pd.set_option("display.max_columns", 30)
    cols = [c for c in ["symbol", "tf", "last_bar", "last", "squeeze_on", "squeeze_bars", "bb_width_pct", "hv100_ann_pct", "hv100_percentile", "up_volume_share_10", "volume_lean", "range_high", "range_low", "range_pct", "alert_up", "alert_down", "error"] if c in out.columns]
    print(out[cols].to_string(index=False))
    if a.json:
        Path(a.json).write_text(json.dumps(rows, indent=1, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
