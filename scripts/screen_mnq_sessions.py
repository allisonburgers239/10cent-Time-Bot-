"""Screen: what we know about edges on MNQ (micro Nasdaq futures).

1. Session decomposition on 2 years of hourly NQ=F (yfinance 1h, 730-day
   limit): where in the 24h day does the Nasdaq's return accrue?
   Sessions (ET): RTH 09:30-16:00, post-close 16:00-18:00, Asia 18:00-02:00,
   Europe/pre-open 02:00-09:30.  Placebo = random sign per hour-bar.
2. E v2 on the future itself: RSI(2) of RTH closes -> next overnight (16:00
   -> 09:30) NQ return, signal vs other nights.
3. MNQ vs QQQ overnight tracking on the repo's 5-min MNQ file (2026-03 -> 06).
4. Reference: Sleeve B's standalone 12m TSMOM on NQ (highest in the basket).

Depth caveat: 2 years of hourly data is screen-grade, not an audit.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

from ten_cent_bot.metrics import sharpe
from ten_cent_bot.tv_data import load_tv_csv

ROOT = Path(__file__).resolve().parents[1]


def sessions(sym: str, rng):
    h = yf.download(sym, period="730d", interval="1h", auto_adjust=False, progress=False)
    h = pd.DataFrame({"open": h["Open"].squeeze(), "close": h["Close"].squeeze()}).dropna()
    h.index = pd.to_datetime(h.index)
    h.index = h.index.tz_convert("America/New_York") if h.index.tz is not None else h.index.tz_localize("UTC").tz_convert("America/New_York")
    r = np.log(h["close"] / h["close"].shift(1)).dropna()
    hr = r.index.hour + r.index.minute / 60
    sess = pd.Series(np.select([(hr >= 9.5) & (hr < 16), (hr >= 16) & (hr < 18), (hr >= 18) | (hr < 2), (hr >= 2) & (hr < 9.5)],
                               ["RTH 09:30-16", "post 16-18", "Asia 18-02", "Europe 02-09:30"], default="other"), index=r.index)
    print(f"\n=== {sym}: {r.index.min().date()} -> {r.index.max().date()}, {len(r)} hourly bars ===")
    print(f"  {'session':<16} {'bars':>6} {'ann.ret':>8} {'ann.vol':>8} {'Sharpe':>7} {'share of total':>14} {'placebo p':>9}")
    bars_per_year = len(r) / (len(r) / (365.25 * 24))  # ~ hours in a year of trading
    tot = r.sum()
    for s in ["RTH 09:30-16", "post 16-18", "Asia 18-02", "Europe 02-09:30"]:
        x = r[sess == s]
        if len(x) < 50: continue
        days = (r.index[-1] - r.index[0]).days / 365.25
        ann = x.sum() / days; vol = x.std() * np.sqrt(len(x) / days)
        pl = np.array([(x * rng.choice([-1, 1], len(x))).sum() / days for _ in range(300)])
        print(f"  {s:<16} {len(x):>6} {ann:>8.1%} {vol:>8.1%} {ann/vol:>7.2f} {x.sum()/tot:>13.0%} {float((pl>=ann).mean()):>9.3f}")
    # daily overnight (16:00 -> 09:30) vs RTH (09:30 -> 16:00) from the hourly bars
    d = h.copy(); d["date"] = d.index.date; hh = d.index.hour + d.index.minute / 60
    rth_open = d[(hh >= 9.5) & (hh < 10.5)].groupby("date")["open"].first()
    rth_close = d[(hh >= 15) & (hh < 16)].groupby("date")["close"].last()
    rth = (rth_close / rth_open - 1).dropna()
    on = (rth_open.shift(-1) / rth_close - 1).dropna()
    print(f"  daily split: overnight(16->09:30) Sharpe {sharpe(on,252):.2f} ann {((1+on.mean())**252-1):+.1%}  |  RTH Sharpe {sharpe(rth,252):.2f} ann {((1+rth.mean())**252-1):+.1%}  ({len(on)} days)")
    return rth_close, on


def ev2_on_future(rth_close: pd.Series, on: pd.Series):
    c = rth_close.astype(float)
    d = c.diff(); up = d.clip(lower=0).ewm(alpha=0.5, adjust=False).mean(); dn = (-d.clip(upper=0)).ewm(alpha=0.5, adjust=False).mean()
    rsi2 = 100 - 100 / (1 + up / dn.replace(0, np.nan))
    sig = (rsi2 < 10).reindex(on.index).fillna(False)
    s = on[sig]; o = on[~sig]
    t = (s.mean() - o.mean()) / np.sqrt(s.var() / len(s) + o.var() / len(o))
    print(f"  E v2 signal on the future: {len(s)} signal nights, next-overnight mean {s.mean()*1e4:+.1f}bp vs other {o.mean()*1e4:+.1f}bp  (t={t:+.2f}); x2 overlay Sharpe {sharpe(on*np.where(sig,2,1),252):.2f} vs plain {sharpe(on,252):.2f}")


def tracking():
    mnq = load_tv_csv(ROOT / "CME_MINI_MNQ1!, 5 (1).csv").tz_convert("America/New_York")
    qqq = load_tv_csv(ROOT / "BATS_QQQ, 5.csv").tz_convert("America/New_York")
    def on_from(bars):
        e = bars.between_time("15:55", "15:55")["close"]; x = bars.between_time("09:30", "09:30")["open"]
        e.index = e.index.tz_localize(None).normalize(); x.index = x.index.tz_localize(None).normalize()
        e = e[~e.index.duplicated()]; x = x[~x.index.duplicated()]
        days = sorted(set(e.index) & set(x.index)); return pd.Series({d: x[days[i+1]] / e[d] - 1 for i, d in enumerate(days[:-1])})
    j = pd.concat([on_from(mnq).rename("MNQ"), on_from(qqq).rename("QQQ")], axis=1).dropna()
    beta = np.polyfit(j.QQQ, j.MNQ, 1)[0]
    print(f"\n=== 3. MNQ vs QQQ overnight tracking, {j.index.min().date()} -> {j.index.max().date()}, {len(j)} nights: corr {j.corr().iloc[0,1]:.3f}, beta {beta:.3f}, tracking error {(j.MNQ-j.QQQ).std()*1e4:.1f}bp/night, mean diff {(j.MNQ-j.QQQ).mean()*1e4:+.1f}bp ===")


def main():
    rng = np.random.default_rng(12)
    print("=== 1-2. Session decomposition + E v2 signal on the future (yfinance hourly, 2y) ===")
    for sym in ["NQ=F", "ES=F"]:
        rc, on = sessions(sym, rng)
        ev2_on_future(rc, on)
    tracking()
    print("\n=== 4. From the B audits: standalone 12m TSMOM Sharpe on NQ=F (2000-2026, raw yfinance) +0.60, the highest single market in the basket; MNQ is already in B's deployment basket. ===")


if __name__ == "__main__":
    main()
