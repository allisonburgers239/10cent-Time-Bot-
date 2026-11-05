"""Daily early-session scan (Temur's idea, automated 2026-11-04).

Run at ~10:00 ET on trading days. No TradingView login needed: the screener is
TradingView's public scanner endpoint, bars come from yfinance (5-minute with
pre/post market), news freshness from TradingView's public headlines feed.

Rules (fixed, pre-registered so the log can be scored honestly):
  universe   US stocks, price >= $5, day volume >= 500k
  gap        |open vs prior close| >= 3%
  volume     relative volume (today vs 10-day average) >= 2.5x
  news       a headline inside the last 12 hours (flag; not a hard filter, the
             screener cannot filter on it)
  top N      by relative volume (default 8)
  verdict    from the regular-session bars up to now:
               BUY  imbalance: >= 70% of bars closed above session VWAP, last close > VWAP, last > pre-market high
               SELL imbalance: >= 70% of bars closed below VWAP, last close < VWAP, last < pre-market low
               else: lean-up / lean-down / two-sided
Every run appends one row per symbol to results/scan_log.csv with the price at
scan time; scripts/score_scan_log.py fills in the close and scores the verdicts.

Usage: python scripts/daily_scan.py [--top 8] [--dry]
"""
from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import requests

ROOT = Path(__file__).resolve().parent.parent
LOG = ROOT / "results" / "scan_log.csv"
UA = {"User-Agent": "Mozilla/5.0", "Origin": "https://www.tradingview.com", "Referer": "https://www.tradingview.com/"}
TZ = "America/New_York"


def screener(top: int) -> pd.DataFrame:
    url = "https://scanner.tradingview.com/america/scan"
    cols = ["name", "close", "change", "gap", "premarket_gap", "premarket_change", "premarket_volume", "relative_volume_10d_calc", "volume", "market_cap_basic", "exchange", "sector"]
    rows = []
    for op, val in (("greater", 3), ("less", -3)):
        payload = {
            "filter": [
                {"left": "gap", "operation": op, "right": val},
                {"left": "relative_volume_10d_calc", "operation": "greater", "right": 2.5},
                {"left": "close", "operation": "greater", "right": 5},
                {"left": "volume", "operation": "greater", "right": 500000},
                {"left": "type", "operation": "equal", "right": "stock"},
            ],
            "columns": cols,
            "sort": {"sortBy": "relative_volume_10d_calc", "sortOrder": "desc"},
            "range": [0, 50],
        }
        r = None
        for attempt in range(5):  # the 10:00 run once failed on a DNS blip; retry with backoff
            try:
                r = requests.post(url, json=payload, headers=UA, timeout=30); r.raise_for_status(); break
            except Exception as e:  # noqa: BLE001
                import time; print(f"screener attempt {attempt + 1} failed: {e}"); time.sleep(20 * (attempt + 1))
        if r is None:
            continue
        for row in r.json().get("data", []):
            rows.append(dict(zip(cols, row["d"]), symbol=row["s"]))
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df = df.sort_values("relative_volume_10d_calc", ascending=False).drop_duplicates("symbol").head(top)
    return df.reset_index(drop=True)


def fresh_news(symbol: str, hours: float = 12.0) -> tuple[bool, str]:
    try:
        url = f"https://news-headlines.tradingview.com/v2/headlines?client=web&lang=en&symbol={symbol}"
        r = requests.get(url, headers=UA, timeout=15)
        items = r.json().get("items", []) if r.ok else []
        now = dt.datetime.now(dt.timezone.utc).timestamp()
        for it in items:
            if now - float(it.get("published", 0)) <= hours * 3600:
                return True, str(it.get("title", ""))[:120]
        return False, (str(items[0].get("title", ""))[:120] if items else "")
    except Exception:  # noqa: BLE001
        return False, "news lookup failed"


def analyse(ticker: str) -> dict | None:
    import yfinance as yf

    try:
        h = yf.Ticker(ticker).history(period="5d", interval="5m", prepost=True)
    except Exception:  # noqa: BLE001
        return None
    if h.empty:
        return None
    h.index = h.index.tz_convert(TZ)
    day = h.index[-1].date()
    s = h[h.index.date == day]
    pre = s.between_time("04:00", "09:29")
    reg = s.between_time("09:30", "15:59")
    prev = h[h.index.date < day].between_time("09:30", "15:59")
    if len(reg) < 3 or prev.empty:
        return None
    tp = (reg.High + reg.Low + reg.Close) / 3
    vol = reg.Volume.replace(0, np.nan).fillna(1.0)
    vwap = (tp * vol).cumsum() / vol.cumsum()
    above = (reg.Close > vwap)
    last = float(reg.Close.iloc[-1])
    pm_high = float(pre.High.max()) if len(pre) else np.nan
    pm_low = float(pre.Low.min()) if len(pre) else np.nan
    prev_close = float(prev.Close.iloc[-1])
    share = float(above.mean())
    if share >= 0.7 and last > vwap.iloc[-1] and (np.isnan(pm_high) or last > pm_high):
        verdict = "BUY_IMBALANCE"
    elif share <= 0.3 and last < vwap.iloc[-1] and (np.isnan(pm_low) or last < pm_low):
        verdict = "SELL_IMBALANCE"
    elif share >= 0.7 and last > vwap.iloc[-1]:
        verdict = "LEAN_UP"
    elif share <= 0.3 and last < vwap.iloc[-1]:
        verdict = "LEAN_DOWN"
    else:
        verdict = "TWO_SIDED"
    return {
        "prev_close": prev_close, "open": float(reg.Open.iloc[0]), "gap_pct": (float(reg.Open.iloc[0]) / prev_close - 1) * 100,
        "pm_high": pm_high, "pm_low": pm_low, "vwap": float(vwap.iloc[-1]), "last": last,
        "last_vs_vwap_pct": (last / float(vwap.iloc[-1]) - 1) * 100, "share_above_vwap": share,
        "bars": int(len(reg)), "verdict": verdict,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--top", type=int, default=8)
    ap.add_argument("--dry", action="store_true", help="print only, do not append to the log")
    a = ap.parse_args()
    now = pd.Timestamp.now(tz=TZ)
    scr = screener(a.top)
    if scr.empty:
        print(f"{now:%Y-%m-%d %H:%M} ET: screener returned nothing")
        return 0
    rows = []
    for _, r in scr.iterrows():
        tk = str(r["name"])
        an = analyse(tk)
        fresh, title = fresh_news(str(r["symbol"]))
        row = {"scan_time_et": f"{now:%Y-%m-%d %H:%M}", "symbol": r["symbol"], "rel_volume": round(float(r["relative_volume_10d_calc"]), 2),
               "screener_gap_pct": round(float(r["gap"]), 2), "news_12h": fresh, "headline": title}
        if an:
            row.update({k: (round(v, 4) if isinstance(v, float) else v) for k, v in an.items()})
        else:
            row["verdict"] = "NO_DATA"
        rows.append(row)
    out = pd.DataFrame(rows)
    pd.set_option("display.width", 250)
    print(f"Scan {now:%Y-%m-%d %H:%M} ET - {len(out)} names")
    print(out[["symbol", "rel_volume", "screener_gap_pct", "news_12h", "pm_high", "vwap", "last", "last_vs_vwap_pct", "share_above_vwap", "verdict"]].to_string(index=False))
    if not a.dry:
        LOG.parent.mkdir(exist_ok=True)
        out.to_csv(LOG, mode="a", header=not LOG.exists(), index=False)
        print(f"appended to {LOG}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
