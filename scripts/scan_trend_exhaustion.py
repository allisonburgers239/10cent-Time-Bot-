"""Trend-exhaustion scan (Temur's idea, 2026-11-04): bullish daily trend, oversold 4-hour.

Universe: top 50 US mid-cap tech stocks by market cap ($2-10B, sectors
"Technology Services" and "Electronic Technology") from TradingView's public
scanner, or any list passed with --symbols.

Rules (exact):
  trend      daily close > daily EMA(200)
  exhaustion 4-hour close < lower Bollinger(20, 2 sd) AND 4-hour RSI(14) < 30
             4-hour bars = regular-session 1-hour bars (yfinance, 60 days) resampled from
             09:30 ET in 4-hour blocks (09:30-13:30, 13:30-16:00), so each day has 2 bars
  sentiment  TradingView daily technical rating (Recommend.All: <= -0.5 = Strong Sell,
             <= -0.1 = Sell) and the VIX close. There is no "institutional selling" field;
             this is what exists and it is reported as such.
  earnings   excluded if the next earnings date is within 7 calendar days
  rank       z = (4h SMA20 - close) / 4h 20-bar sd  (largest first)
  R:R        reward = distance back to the 4h SMA20; risk = distance to the lowest low of the
             last 10 4-hour bars minus 0.5 ATR(14). Reported, not guessed.

Usage: python scripts/scan_trend_exhaustion.py [--symbols A,B,C] [--all]   (--all prints every name, not only matches)
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import requests

ROOT = Path(__file__).resolve().parent.parent
UA = {"User-Agent": "Mozilla/5.0", "Origin": "https://www.tradingview.com", "Referer": "https://www.tradingview.com/"}
TZ = "America/New_York"


def universe(n: int = 50) -> pd.DataFrame:
    url = "https://scanner.tradingview.com/america/scan"
    cols = ["name", "close", "market_cap_basic", "sector", "industry", "earnings_release_next_date", "Recommend.All", "EMA200", "exchange"]
    payload = {
        "filter": [
            {"left": "market_cap_basic", "operation": "in_range", "right": [2e9, 10e9]},
            {"left": "sector", "operation": "in_range", "right": ["Technology Services", "Electronic Technology"]},
            {"left": "type", "operation": "equal", "right": "stock"},
            {"left": "exchange", "operation": "in_range", "right": ["NASDAQ", "NYSE", "AMEX"]},
            {"left": "volume", "operation": "greater", "right": 200000},
        ],
        "columns": cols, "sort": {"sortBy": "market_cap_basic", "sortOrder": "desc"}, "range": [0, n],
    }
    r = requests.post(url, json=payload, headers=UA, timeout=30); r.raise_for_status()
    rows = [dict(zip(cols, x["d"]), symbol=x["s"]) for x in r.json().get("data", [])]
    return pd.DataFrame(rows)


def rating_and_earnings(symbols: list[str]) -> pd.DataFrame:
    url = "https://scanner.tradingview.com/america/scan"
    cols = ["name", "close", "earnings_release_next_date", "Recommend.All", "EMA200", "market_cap_basic", "sector"]
    payload = {"symbols": {"tickers": symbols}, "columns": cols}
    r = requests.post(url, json=payload, headers=UA, timeout=30); r.raise_for_status()
    rows = [dict(zip(cols, x["d"]), symbol=x["s"]) for x in r.json().get("data", [])]
    return pd.DataFrame(rows)


def rsi(x: pd.Series, n: int = 14) -> pd.Series:
    d = x.diff(); up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean(); dn = (-d).clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    return 100 - 100 / (1 + up / dn.replace(0, np.nan))


def four_hour(ticker: str) -> pd.DataFrame | None:
    import yfinance as yf
    try:
        h = yf.Ticker(ticker).history(period="60d", interval="1h", prepost=False)
    except Exception:  # noqa: BLE001
        return None
    if h.empty:
        return None
    h.index = h.index.tz_convert(TZ)
    h = h.between_time("09:30", "15:59")
    g = h.resample("4h", origin="start_day", offset="9h30min").agg({"Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"}).dropna()
    return g


def daily(ticker: str) -> pd.DataFrame | None:
    import yfinance as yf
    try:
        d = yf.Ticker(ticker).history(period="2y", interval="1d")
    except Exception:  # noqa: BLE001
        return None
    return d if not d.empty else None


def analyse(ticker: str) -> dict | None:
    d = daily(ticker); f = four_hour(ticker)
    if d is None or f is None or len(d) < 210 or len(f) < 30:
        return None
    ema200 = d.Close.ewm(span=200, adjust=False).mean().iloc[-1]
    c = f.Close
    sma20 = c.rolling(20).mean(); sd20 = c.rolling(20).std(ddof=0)
    bb_l = sma20 - 2 * sd20
    r = rsi(c, 14)
    tr = pd.concat([f.High - f.Low, (f.High - c.shift()).abs(), (f.Low - c.shift()).abs()], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1 / 14, adjust=False).mean()
    last = float(c.iloc[-1])
    z = float((sma20.iloc[-1] - last) / sd20.iloc[-1]) if sd20.iloc[-1] > 0 else np.nan
    low10 = float(f.Low.iloc[-10:].min())
    stop = low10 - 0.5 * float(atr.iloc[-1])
    reward = float(sma20.iloc[-1]) - last; risk = last - stop
    return {
        "last": round(last, 2), "daily_ema200": round(float(ema200), 2), "above_ema200": bool(last > ema200),
        "pct_vs_ema200": round((last / ema200 - 1) * 100, 1),
        "bb_lower_4h": round(float(bb_l.iloc[-1]), 2), "below_bb": bool(last < bb_l.iloc[-1]),
        "rsi14_4h": round(float(r.iloc[-1]), 1), "sma20_4h": round(float(sma20.iloc[-1]), 2), "z_below_sma20": round(z, 2),
        "stop": round(stop, 2), "reward_pct": round(reward / last * 100, 2), "risk_pct": round(risk / last * 100, 2),
        "rr": round(reward / risk, 2) if risk > 0 else np.nan, "last_4h_bar": str(f.index[-1]),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--symbols", default=None); ap.add_argument("--all", action="store_true")
    a = ap.parse_args()
    import yfinance as yf
    vix = float(yf.Ticker("^VIX").history(period="5d").Close.dropna().iloc[-1])
    if a.symbols:
        syms = [s if ":" in s else s for s in a.symbols.split(",")]
        meta = rating_and_earnings(syms)
    else:
        meta = universe(50)
    if meta.empty:
        print("no universe"); return 1
    today = pd.Timestamp.now(tz=TZ).normalize().tz_localize(None)
    rows = []
    for _, m in meta.iterrows():
        tk = str(m["name"])
        an = analyse(tk)
        if an is None:
            continue
        raw_ed = m.get("earnings_release_next_date")
        ed = pd.to_datetime(raw_ed, unit="s", errors="coerce") if isinstance(raw_ed, (int, float)) and not pd.isna(raw_ed) else pd.to_datetime(raw_ed, errors="coerce")
        days_to_earn = (ed.tz_localize(None) - today).days if pd.notna(ed) else np.nan
        rating = m.get("Recommend.All")
        rating_txt = "Strong Sell" if rating is not None and rating <= -0.5 else ("Sell" if rating is not None and rating <= -0.1 else ("Buy" if rating is not None and rating >= 0.1 else "Neutral"))
        row = {"symbol": m["symbol"], "mcap_B": round(float(m.get("market_cap_basic", np.nan)) / 1e9, 1) if m.get("market_cap_basic") else np.nan,
               "days_to_earnings": days_to_earn, "tv_daily_rating": rating_txt, **an}
        row["match"] = bool(an["above_ema200"] and an["below_bb"] and an["rsi14_4h"] < 30 and (np.isnan(days_to_earn) or days_to_earn > 7))
        rows.append(row)
    t = pd.DataFrame(rows)
    pd.set_option("display.width", 260); pd.set_option("display.max_columns", 40)
    print(f"VIX {vix:.1f} ({'extreme fear >30' if vix > 30 else 'elevated 20-30' if vix > 20 else 'calm <20'}); universe {len(t)} names; 4h bar ends {t.last_4h_bar.iloc[0] if len(t) else ''}")
    cols = ["symbol", "mcap_B", "last", "pct_vs_ema200", "rsi14_4h", "bb_lower_4h", "sma20_4h", "z_below_sma20", "tv_daily_rating", "days_to_earnings", "stop", "reward_pct", "risk_pct", "rr", "match"]
    show = t if a.all else t[t.match]
    show = show.sort_values("z_below_sma20", ascending=False)
    print(show[cols].to_string(index=False) if len(show) else "no symbol matches all three conditions today")
    near = t[t.above_ema200 & (t.rsi14_4h < 35) & ~t.match].sort_values("z_below_sma20", ascending=False)
    if len(near) and not a.all:
        print("\nnear-misses (above EMA200, 4h RSI < 35, but not all conditions):")
        print(near[cols].head(10).to_string(index=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
