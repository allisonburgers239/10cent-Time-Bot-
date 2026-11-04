"""Audit: gap-down hold extension for Sleeve E v2 (2026-11-04).

Rule: on mornings where open / prev close - 1 <= thr (default -2%), keep the overnight position
until the close of the first intraday bar instead of selling at the 09:30 open. Everything else
is E v2 (RSI(2)<10 -> 2x), 1 bp per side. The library implements it
(overnight.OvernightConfig.gapdown_hold_thr); this audit uses the library.

Data: hourly TradingView files 2015- (SPY/QQQ/IWM, first bar = 09:30-10:30) and the 30-minute
SPY file 2020- (first bar = 09:30-10:00). Daily open/close come from the same files.

Sections: 0 data + library check, 1 baseline, 2 walk-forward (threshold chosen on 2015-2020),
3 grid (threshold x first-bar length), 4 by year, 5 leave-one-ticker-out (portfolio), 6 costs,
7 placebo (same number of random mornings), 8 tail, 9 interaction with the RSI 2x nights,
10 why: what the first bar does after a big gap down vs any morning.
"""
from __future__ import annotations

from dataclasses import replace

import numpy as np
import pandas as pd

from ten_cent_bot import overnight as ov
from ten_cent_bot.tv_data import load_tv_csv

TZ = "America/New_York"
RNG = np.random.default_rng(21)


def tstat(x) -> float:
    x = pd.Series(x).dropna()
    return float(x.mean() / x.std() * np.sqrt(len(x))) if len(x) > 2 and x.std() > 0 else 0.0


def sh(x) -> float:
    x = pd.Series(x).dropna()
    return float(x.mean() / x.std() * np.sqrt(252)) if x.std() > 0 else 0.0


def load(sym: str, tf: int, first_end: str) -> tuple[pd.DataFrame, pd.Series]:
    df = load_tv_csv(f"/Users/temurk/projects/10cent-time-bot/BATS_{sym}, {tf}.csv"); df.index = df.index.tz_convert(TZ)
    df = df.between_time("09:30", "15:59")
    g = df.groupby(df.index.date)
    daily = pd.DataFrame({"open": g.open.first(), "close": g.close.last()}); daily.index = pd.to_datetime(daily.index)
    fb = df[df.index.strftime("%H:%M") == "09:30"].close
    fb.index = pd.to_datetime(fb.index.date)
    return daily, fb


def run(daily, fb, cfg) -> pd.Series:
    return ov.backtest_single(daily, cfg, first_bar_close=fb)["net_return"].dropna()


def main() -> None:
    base_cfg = ov.E_V2_CONFIG
    hold_cfg = replace(base_cfg, gapdown_hold_thr=-0.02)
    data = {"SPY": load("SPY", 60, "10:30"), "QQQ": load("QQQ", 60, "10:30"), "IWM": load("IWM", 60, "10:30")}
    spy30 = load("SPY", 30, "10:00")
    print("=== 0. Data and library check ===")
    for s, (d, fb) in data.items():
        print(f"  {s}: {len(d)} days {d.index[0].date()} -> {d.index[-1].date()}, first-bar closes {len(fb)}")
    d, fb = data["QQQ"]
    manual = (d.open.shift(-1) / d.close - 1)
    gap = d.open.shift(-1) / d.close - 1; held = gap <= -0.02
    manual[held] = (fb.reindex(d.index).shift(-1) / d.close - 1)[held]
    lib = ov.backtest_single(d, ov.OvernightConfig(cost_bps_per_side=0, gapdown_hold_thr=-0.02), first_bar_close=fb)["gross_return"]
    print(f"  library == manual (QQQ, 1x): max |diff| {np.abs(lib - manual).max():.2e}")

    print("\n=== 1. Baseline: E v2 vs E v2 + gap-down hold (thr -2%, exit at the first bar's close) ===")
    port_b, port_h = [], []
    for s, (d, fb) in data.items():
        b, h = run(d, fb, base_cfg), run(d, fb, hold_cfg)
        port_b.append(b); port_h.append(h)
        n_ev = int(((d.open.shift(-1) / d.close - 1) <= -0.02).sum())
        print(f"  {s} hourly: E v2 Sharpe {sh(b):.2f} CAGR {b.mean() * 252:.1%} MaxDD {((1 + b).cumprod() / (1 + b).cumprod().cummax() - 1).min():.1%}  ->  hold {sh(h):.2f} CAGR {h.mean() * 252:.1%} MaxDD {((1 + h).cumprod() / (1 + h).cumprod().cummax() - 1).min():.1%}  | events {n_ev} ({n_ev / (len(d) / 252):.1f}/yr), added {((h - b)[(h - b) != 0]).mean() * 1e4:+.0f}bp per event t {tstat((h - b)[(h - b) != 0]):+.1f}")
    pb = pd.concat(port_b, axis=1).mean(axis=1); ph = pd.concat(port_h, axis=1).mean(axis=1)
    print(f"  E basket (3 ETFs): E v2 Sharpe {sh(pb):.2f} CAGR {pb.mean() * 252:.1%}  ->  hold {sh(ph):.2f} CAGR {ph.mean() * 252:.1%}")
    d, fb = spy30
    b, h = run(d, fb, base_cfg), run(d, fb, hold_cfg)
    print(f"  SPY 30-min (exit 10:00, 2020-): E v2 {sh(b):.2f} -> hold {sh(h):.2f}; added per event {((h - b)[(h - b) != 0]).mean() * 1e4:+.0f}bp")

    print("\n=== 2. Walk-forward: threshold chosen on 2015-2020, judged on 2021-2026 (E basket) ===")
    def basket(cfg, start=None, end=None):
        rs = []
        for s, (d, fb) in data.items():
            x = run(d, fb, cfg)
            if start: x = x[x.index >= start]
            if end: x = x[x.index < end]
            rs.append(x)
        return pd.concat(rs, axis=1).mean(axis=1)
    best, best_sh = None, -9
    for thr in (-0.01, -0.015, -0.02, -0.025, -0.03):
        s_ = sh(basket(replace(base_cfg, gapdown_hold_thr=thr), end="2021-01-01"))
        if s_ > best_sh: best, best_sh = thr, s_
    print(f"  chosen on train: thr {best * 100:+.1f}% (train Sharpe {best_sh:.2f}); train E v2 {sh(basket(base_cfg, end='2021-01-01')):.2f}")
    print(f"  TEST 2021-2026: E v2 {sh(basket(base_cfg, start='2021-01-01')):.2f}  chosen thr {sh(basket(replace(base_cfg, gapdown_hold_thr=best), start='2021-01-01')):.2f}  default -2% {sh(basket(hold_cfg, start='2021-01-01')):.2f}")

    print("\n=== 3. Grid: threshold (rows) x exit (10:00 on SPY 30m, 10:30 on hourly) ===")
    for thr in (-0.01, -0.015, -0.02, -0.025, -0.03, -0.04):
        cfg = replace(base_cfg, gapdown_hold_thr=thr)
        cells = [f"{s} {sh(run(d, fb, cfg)):.2f}" for s, (d, fb) in data.items()]
        cells.append(f"SPY30 {sh(run(spy30[0], spy30[1], cfg)):.2f}")
        print(f"  thr {thr * 100:+.1f}%: basket {sh(basket(cfg)):.2f} | " + " ".join(cells))

    print("\n=== 4. By year: basket Sharpe E v2 vs hold, and bp added by the hold ===")
    pb_, ph_ = basket(base_cfg), basket(hold_cfg); diff = ph_ - pb_
    for y in sorted(set(pb_.index.year)):
        m = pb_.index.year == y
        print(f"  {y}: E v2 {sh(pb_[m]):5.2f}  hold {sh(ph_[m]):5.2f}  added {diff[m].sum() * 1e4:+5.0f}bp over {int((diff[m] != 0).sum())} events")

    print("\n=== 5. Leave-one-ticker-out (basket Sharpe, E v2 -> hold) ===")
    for drop in data:
        rs_b, rs_h = [], []
        for s, (d, fb) in data.items():
            if s == drop: continue
            rs_b.append(run(d, fb, base_cfg)); rs_h.append(run(d, fb, hold_cfg))
        print(f"  without {drop}: {sh(pd.concat(rs_b, axis=1).mean(axis=1)):.2f} -> {sh(pd.concat(rs_h, axis=1).mean(axis=1)):.2f}")

    print("\n=== 6. Cost sensitivity (the hold removes no trades and adds none) ===")
    for c in (0.5, 1.0, 2.0, 3.0):
        print(f"  {c}bp/side: E v2 {sh(basket(replace(base_cfg, cost_bps_per_side=c))):.2f} -> hold {sh(basket(replace(hold_cfg, cost_bps_per_side=c))):.2f}")

    print("\n=== 7. Placebo: hold through the first bar on the same NUMBER of random mornings (300 draws, basket) ===")
    real = sh(ph_)
    fake = []
    for _ in range(300):
        rs = []
        for s, (d, fb) in data.items():
            gap = d.open.shift(-1) / d.close - 1
            n_ev = int((gap <= -0.02).sum())
            pick = RNG.choice(np.arange(len(d) - 1), size=n_ev, replace=False)
            on = (d.open.shift(-1) / d.close - 1).copy()
            fbc = (fb.reindex(d.index).shift(-1) / d.close - 1)
            on.iloc[pick] = fbc.iloc[pick]
            r2 = ov.rsi(d.close, 2); pos = pd.Series(1.0, index=d.index); pos[r2 < 10] = 2.0
            rs.append((pos * on - 2e-4 * pos).dropna())
        fake.append(sh(pd.concat(rs, axis=1).mean(axis=1)))
    fake = np.array(fake)
    print(f"  real {real:.3f} | placebo mean {fake.mean():.3f} sd {fake.std():.3f} | p(placebo >= real) = {(fake >= real).mean():.3f}")

    print("\n=== 8. Tail: worst held mornings (basket), worst day with vs without ===")
    ev = diff[diff != 0].sort_values()
    print("  worst 5 holds (bp vs selling at the open): " + ", ".join(f"{t.date()} {v * 1e4:+.0f}" for t, v in ev.head(5).items()))
    print("  best 5 holds: " + ", ".join(f"{t.date()} {v * 1e4:+.0f}" for t, v in ev.tail(5).items()))
    print(f"  worst single day: E v2 {pb_.min():+.2%} -> hold {ph_.min():+.2%} | hit rate of the hold {(ev > 0).mean():.2f} over {len(ev)} events")

    print("\n=== 9. Interaction with the RSI 2x nights ===")
    d, fb = data["QQQ"]
    gap = d.open.shift(-1) / d.close - 1; r2 = ov.rsi(d.close, 2)
    fbc = fb.reindex(d.index).shift(-1) / d.open.shift(-1) - 1   # first-bar return after the open
    big = gap <= -0.02
    print(f"  QQQ big gap-down mornings: {int(big.sum())}; on RSI 2x nights: {int((big & (r2 < 10)).sum())}; first-bar return after a big gap down: {fbc[big].mean() * 1e4:+.0f}bp (on 2x nights {fbc[big & (r2 < 10)].mean() * 1e4:+.0f}, on 1x nights {fbc[big & ~(r2 < 10)].mean() * 1e4:+.0f}) vs all mornings {fbc.mean() * 1e4:+.0f}bp")

    print("\n=== 10. Why: first-bar return by gap bucket (QQQ hourly) ===")
    for lo, hi in [(-1, -0.03), (-0.03, -0.02), (-0.02, -0.01), (-0.01, 0.01), (0.01, 0.02), (0.02, 1)]:
        m = (gap > lo) & (gap <= hi)
        print(f"  gap {lo * 100:+.0f}..{hi * 100:+.0f}%: n {int(m.sum()):4d} first-bar {fbc[m].mean() * 1e4:+5.0f}bp t {tstat(fbc[m]):+.1f}")


if __name__ == "__main__":
    main()
