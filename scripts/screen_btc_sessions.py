"""Screen: Bitcoin perpetual returns by time-of-day session and weekday.

24/7 market, so the equity 'overnight' concept becomes 'which session
carries the drift'.  Uses the repo's Binance BTCUSDT.P 60-min export
(2024-01 -> 2026-06, ~2.5y: screen-grade only).

Sessions (UTC): Asia 00-08, Europe 08-13, US 13-21, late 21-24.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    df = pd.read_csv(ROOT / "BINANCE_BTCUSDT.P, 60.csv")
    df["t"] = pd.to_datetime(df["time"], unit="s", utc=True)
    df = df.set_index("t").sort_index()
    r = np.log(df["close"]).diff().dropna()
    print(f"BTCUSDT.P 60-min: {r.index.min().date()} -> {r.index.max().date()}, {len(r)} bars, total {r.sum():+.1%}")
    hr = r.groupby(r.index.hour)
    print("\n  UTC hour  mean(bp)   t    ")
    for h, x in hr:
        print(f"  {h:>8}  {x.mean()*1e4:+7.1f}  {x.mean()/(x.std(ddof=1)/np.sqrt(len(x))):+5.2f}")
    sess = pd.cut(r.index.hour, [-1, 7, 12, 20, 23], labels=["Asia 00-08", "Europe 08-13", "US 13-21", "late 21-24"])
    print("\n  session        ann.ret   ann.vol  Sharpe   share of total")
    for s, x in r.groupby(sess, observed=True):
        bars_per_year = len(x) / (len(r) / (365.25 * 24))
        ann = x.mean() * bars_per_year
        vol = x.std(ddof=0) * np.sqrt(bars_per_year)
        print(f"  {s:<14} {ann:+8.1%}  {vol:7.1%}  {ann/vol:6.2f}   {x.sum()/r.sum():6.0%}")
    print("\n  weekday   mean(bp/bar)   t")
    for d, x in r.groupby(r.index.dayofweek):
        print(f"  {['Mon','Tue','Wed','Thu','Fri','Sat','Sun'][d]:<8} {x.mean()*1e4:+8.2f}  {x.mean()/(x.std(ddof=1)/np.sqrt(len(x))):+5.2f}")
    wk = r[r.index.dayofweek < 5]; we = r[r.index.dayofweek >= 5]
    print(f"\n  weekday total {wk.sum():+.1%}  weekend total {we.sum():+.1%}  (weekend = {len(we)/len(r):.0%} of bars)")
    rng = np.random.default_rng(1)
    real = r[sess == "US 13-21"].sum()
    pl = np.array([r.sample(frac=1, random_state=int(rng.integers(1e9))).values[: (sess == 'US 13-21').sum()].sum() for _ in range(300)])
    print(f"  placebo: random hour-subset of same size vs US-session total {real:+.1%}: placebo {pl.mean():+.1%} +/- {pl.std():.1%}, P(rand>=real) {float((pl>=real).mean()):.3f}")


if __name__ == "__main__":
    main()
