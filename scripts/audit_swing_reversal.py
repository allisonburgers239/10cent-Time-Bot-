"""Full audit - Sleeve I candidate: ETF oversold swing (2026-11-04).

Data: the 12 hourly TradingView exports (SPY, QQQ, IWM, XLB, XLE, XLF, XLI, XLK, XLP, XLU, XLV,
XLY; 2015-01 -> 2026-11), resampled to two 4-hour session bars a day. Daily sanity check on
yfinance 1993-.

Sections
  0  data, signal counts, library == audit check
  1  baseline: per-trade stats pooled and per ETF; portfolio (5 slots, 5-day hold, 1 bp/side)
  2  walk-forward: parameters chosen on 2015-2020, evaluated on 2021-2026
  3  parameter grid (rsi_thr x hold x bb_k x trend_ema), per-trade mean + t and portfolio Sharpe
  4  sub-periods (2-year blocks)
  5  leave-one-ETF-out
  6  cost sensitivity
  7  placebo: same number of random uptrend bars per ETF (300 draws) -> p-value; shuffled signal dates
  8  tail: worst trades / weeks, drawdown length, concurrent-position usage
  9  overlap with E v2 (overnight RSI(2) reversal): shared signal days, book-level test
 10  daily-bar variant on SPY/QQQ/IWM 1993- (yfinance): does the effect exist on daily bars over 30 years
"""
from __future__ import annotations

import glob
import itertools
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd

from ten_cent_bot import overnight as ov
from ten_cent_bot import swing_reversal as sw
from ten_cent_bot.tv_data import load_tv_csv

ROOT = Path(__file__).resolve().parent.parent
TZ = "America/New_York"
RNG = np.random.default_rng(42)
ETFS = ["SPY", "QQQ", "IWM", "XLB", "XLE", "XLF", "XLI", "XLK", "XLP", "XLU", "XLV", "XLY"]


def tstat(x) -> float:
    x = pd.Series(x).dropna()
    return float(x.mean() / x.std() * np.sqrt(len(x))) if len(x) > 2 and x.std() > 0 else 0.0


def load_bars() -> dict[str, pd.DataFrame]:
    out = {}
    for s in ETFS:
        df = load_tv_csv(ROOT / f"BATS_{s}, 60.csv"); df.index = df.index.tz_convert(TZ)
        out[s] = sw.to_4h(df)
    return out


def pooled_trades(bars, cfg) -> pd.DataFrame:
    rows = []
    for s, b in bars.items():
        f = sw.signals(b, cfg); tr = sw.trade_returns(f, cfg)
        for t, r in tr.items():
            rows.append((t, s, r))
    return pd.DataFrame(rows, columns=["t", "sym", "ret"])


def uptrend_baseline(bars, cfg) -> pd.Series:
    """Return of holding `hold_bars` from the next open, for EVERY uptrend bar (the honest baseline)."""
    out = []
    for s, b in bars.items():
        f = sw.signals(b, cfg)
        o = f.open.to_numpy(); c = f.close.to_numpy(); n = len(f)
        up = f.trend.to_numpy() & f.ema.notna().to_numpy()
        for i in np.flatnonzero(up):
            if i + 1 + cfg.hold_bars < n:
                out.append(c[i + 1 + cfg.hold_bars] / o[i + 1] - 1 - 2 * cfg.cost_bps_per_side / 1e4)
    return pd.Series(out)


def sub(bars, start=None, end=None):
    out = {}
    for s, b in bars.items():
        x = b
        if start: x = x[x.index >= pd.Timestamp(start, tz=TZ)]
        if end: x = x[x.index < pd.Timestamp(end, tz=TZ)]
        out[s] = x
    return out


def line(name, res) -> str:
    s = sw.summary(res)
    return f"{name:28s} trades {s['trades']:4d} win {s['win']:.2f} mean {s['mean_trade_bp']:+6.0f}bp worst {s['worst_trade_bp']:+6.0f}bp | CAGR {s['cagr']:+6.1%} Sharpe {s['sharpe']:5.2f} MaxDD {s['max_drawdown']:6.1%}"


def main() -> None:
    bars = load_bars()
    cfg = sw.SwingConfig()
    print("=== 0. Data and library check ===")
    for s, b in bars.items():
        print(f"  {s}: {len(b)} 4h bars {b.index[0].date()} -> {b.index[-1].date()}")
    tr = pooled_trades(bars, cfg)
    res = sw.backtest(bars, cfg)
    # library == audit: the per-trade returns the portfolio took must equal the pooled ones
    merged = res["trades"].merge(tr, left_on=["entry_signal", "symbol"], right_on=["t", "sym"])
    print(f"  library == audit: {len(merged)} portfolio trades matched, max |diff| {np.abs(merged.ret_x - merged.ret_y).max():.2e}")

    print("\n=== 1. Baseline (RSI14<30, close<BB(20,2), yesterday close > EMA200, hold 10 x 4h bars, 1bp/side) ===")
    base = uptrend_baseline(bars, cfg)
    print(f"  pooled per-trade: n {len(tr)} mean {tr.ret.mean() * 1e4:+.0f}bp median {tr.ret.median() * 1e4:+.0f}bp hit {(tr.ret > 0).mean():.2f} t {tstat(tr.ret):+.1f} | uptrend baseline {base.mean() * 1e4:+.0f}bp (n {len(base)}) | excess t {(tr.ret.mean() - base.mean()) / np.sqrt(tr.ret.var() / len(tr) + base.var() / len(base)):+.1f}")
    for s in ETFS:
        x = tr[tr.sym == s].ret
        print(f"    {s}: n {len(x):3d} mean {x.mean() * 1e4:+5.0f}bp hit {(x > 0).mean():.2f} t {tstat(x):+.1f}")
    print("  " + line("portfolio 5 slots", res))
    for k in (1, 2, 3, 12):
        print("  " + line(f"portfolio {k} slots", sw.backtest(bars, replace(cfg, max_slots=k))))

    print("\n=== 2. Walk-forward: pick (rsi_thr, hold, bb_k) on 2015-2020, test on 2021-2026 ===")
    train, test = sub(bars, end="2021-01-01"), sub(bars, start="2021-01-01")
    best, best_sh = None, -9
    for thr, hold, k in itertools.product((25, 30, 35), (6, 10, 15), (1.5, 2.0, 2.5)):
        c2 = replace(cfg, rsi_thr=thr, hold_bars=hold, bb_k=k)
        sh = sw.summary(sw.backtest(train, c2))["sharpe"]
        if sh > best_sh:
            best, best_sh = c2, sh
    print(f"  chosen on train: rsi_thr {best.rsi_thr} hold {best.hold_bars} bb_k {best.bb_k} (train Sharpe {best_sh:.2f})")
    print("  " + line("TEST 2021-2026, chosen params", sw.backtest(test, best)))
    print("  " + line("TEST 2021-2026, default params", sw.backtest(test, cfg)))
    print("  " + line("TRAIN 2015-2020, default params", sw.backtest(train, cfg)))

    print("\n=== 3. Parameter grid (per-trade mean bp / t / portfolio Sharpe) ===")
    for ema in (100, 200):
        for k in (1.5, 2.0, 2.5):
            cells = []
            for thr in (25, 30, 35):
                for hold in (6, 10, 15):
                    c2 = replace(cfg, trend_ema=ema, bb_k=k, rsi_thr=thr, hold_bars=hold)
                    t2 = pooled_trades(bars, c2); sh = sw.summary(sw.backtest(bars, c2))["sharpe"]
                    cells.append(f"thr{thr}/h{hold}: {t2.ret.mean() * 1e4:+4.0f}/{tstat(t2.ret):+4.1f}/{sh:4.2f}")
            print(f"  ema{ema} k{k}: " + "  ".join(cells))

    print("\n=== 4. Sub-periods (2-year blocks, default params) ===")
    for y in range(2015, 2027, 2):
        r2 = sw.backtest(sub(bars, start=f"{y}-01-01", end=f"{y + 2}-01-01"), cfg)
        if len(r2["trades"]):
            print("  " + line(f"{y}-{y + 1}", r2))

    print("\n=== 5. Leave-one-ETF-out ===")
    for s in ETFS:
        r2 = sw.backtest({k: v for k, v in bars.items() if k != s}, cfg)
        print("  " + line(f"without {s}", r2))

    print("\n=== 6. Cost sensitivity (bp per side) ===")
    for c in (0.5, 1.0, 2.0, 3.0, 5.0):
        print("  " + line(f"{c} bp/side", sw.backtest(bars, replace(cfg, cost_bps_per_side=c))))

    print("\n=== 7. Placebo ===")
    real_mean = tr.ret.mean(); real_sh = sw.summary(res)["sharpe"]
    counts = tr.groupby("sym").size()
    fake_means = []
    for _ in range(300):
        vals = []
        for s, b in bars.items():
            f = sw.signals(b, cfg)
            o = f.open.to_numpy(); c = f.close.to_numpy(); n = len(f)
            up = np.flatnonzero(f.trend.to_numpy() & f.ema.notna().to_numpy())
            up = up[up + 1 + cfg.hold_bars < n]
            pick = RNG.choice(up, size=min(int(counts.get(s, 0)), len(up)), replace=False)
            vals.extend(c[pick + 1 + cfg.hold_bars] / o[pick + 1] - 1 - 2 * cfg.cost_bps_per_side / 1e4)
        fake_means.append(np.mean(vals))
    fake_means = np.array(fake_means)
    print(f"  random uptrend bars, same count per ETF: placebo mean {fake_means.mean() * 1e4:+.0f}bp sd {fake_means.std() * 1e4:.0f}bp | real {real_mean * 1e4:+.0f}bp | p(placebo >= real) = {(fake_means >= real_mean).mean():.3f}")
    # shuffled signal dates within each ETF (keeps count, kills timing)
    sh_vals = []
    for _ in range(100):
        bars_sh = {}
        for s, b in bars.items():
            f = sw.signals(b, cfg)
            idx = np.flatnonzero(f.sig.to_numpy())
            new = np.sort(RNG.choice(np.arange(25, len(f) - cfg.hold_bars - 2), size=len(idx), replace=False))
            g = f.copy(); g["sig"] = False; g.iloc[new, g.columns.get_loc("sig")] = True
            bars_sh[s] = g
        # reuse backtest machinery on pre-signalled frames
        events = []
        for s, g in bars_sh.items():
            trr = sw.trade_returns(g, cfg)
            for t, r in trr.items():
                events.append(r)
        sh_vals.append(np.mean(events))
    sh_vals = np.array(sh_vals)
    print(f"  shuffled signal dates: mean {sh_vals.mean() * 1e4:+.0f}bp sd {sh_vals.std() * 1e4:.0f}bp | p(shuffled >= real) = {(sh_vals >= real_mean).mean():.3f}")

    print("\n=== 8. Tail ===")
    t = res["trades"].sort_values("ret")
    print("  worst 5 trades: " + ", ".join(f"{r.symbol} {r.entry_signal.date()} {r.ret * 1e4:+.0f}bp" for _, r in t.head(5).iterrows()))
    d = res["daily"]; eq = res["equity"]; dd = eq / eq.cummax() - 1
    under = (dd < 0).astype(int); runs = under.groupby((under != under.shift()).cumsum()).sum()
    print(f"  worst day {d.min():+.2%} | worst week {d.rolling(5).sum().min():+.2%} | longest drawdown {runs.max()} trading days | max concurrent positions {res['trades'].groupby(res['trades'].entry_signal.dt.date).size().max()}")
    print(f"  trade return percentiles (bp): 5% {np.percentile(res['trades'].ret, 5) * 1e4:+.0f}  25% {np.percentile(res['trades'].ret, 25) * 1e4:+.0f}  50% {np.percentile(res['trades'].ret, 50) * 1e4:+.0f}  75% {np.percentile(res['trades'].ret, 75) * 1e4:+.0f}  95% {np.percentile(res['trades'].ret, 95) * 1e4:+.0f}")

    print("\n=== 9. Overlap with E v2 (daily RSI(2) < 10 on the same ETF) ===")
    import yfinance as yf
    raw = yf.download(["SPY", "QQQ", "IWM", "GLD", "^VIX"], period="max", interval="1d", auto_adjust=True, progress=False)
    vix = raw["Close"]["^VIX"].dropna()
    shared = 0; total = 0; r_on = []; r_off = []
    for s in ("SPY", "QQQ", "IWM"):
        dfd = pd.DataFrame({"open": raw["Open"][s], "close": raw["Close"][s]}).dropna()
        r2 = ov.rsi(dfd.close, 2)
        fire_days = set(r2[r2 < 10].index.date)
        x = tr[tr.sym == s]
        for _, row in x.iterrows():
            total += 1
            if row.t.date() in fire_days:
                shared += 1; r_on.append(row.ret)
            else:
                r_off.append(row.ret)
    print(f"  SPY/QQQ/IWM swing signals: {total}; on an E v2 signal day: {shared} ({shared / max(total, 1):.0%}) | swing return when E v2 also fires {np.mean(r_on) * 1e4:+.0f}bp (n {len(r_on)}), when it does not {np.mean(r_off) * 1e4:+.0f}bp (n {len(r_off)})")
    # book test: E3 v2 + VIX (daily, 2015-) vs E3 v2 + VIX with 20% of capital in the swing sleeve
    e_rets = {}
    for s in ("SPY", "QQQ", "IWM", "GLD"):
        dfd = pd.DataFrame({"open": raw["Open"][s], "close": raw["Close"][s]}).dropna()
        e_rets[s] = ov.backtest_single(dfd, ov.E_V2_VOL_CONFIG, vix=vix)["net_return"]
    e3 = pd.DataFrame(e_rets).mean(axis=1).dropna()
    e3.index = pd.DatetimeIndex(e3.index).tz_localize(None)
    swd = res["daily"].copy(); swd.index = pd.DatetimeIndex(swd.index)
    common = e3.index.intersection(swd.index)
    e3c, swc = e3[common], swd[common]
    def shp(x): return x.mean() / x.std() * np.sqrt(252)
    print(f"  2015-2026 common days {len(common)}: E3 v2+VIX alone Sharpe {shp(e3c):.2f} CAGR {e3c.mean() * 252:.1%} | swing alone Sharpe {shp(swc):.2f} CAGR {swc.mean() * 252:.1%} | corr {e3c.corr(swc):+.2f}")
    for w in (0.1, 0.2, 0.3, 0.5):
        book = (1 - w) * e3c + w * swc
        print(f"    book {1 - w:.0%} E3 / {w:.0%} swing: Sharpe {shp(book):.2f} CAGR {book.mean() * 252:.1%}")

    print("\n=== 10. Daily-bar variant, SPY/QQQ/IWM 1993- (daily RSI14<30, close<BB(20,2), close>EMA200 yesterday, hold 5 days) ===")
    for s in ("SPY", "QQQ", "IWM"):
        dfd = pd.DataFrame({"open": raw["Open"][s], "close": raw["Close"][s]}).dropna()
        c = dfd.close; ema = c.ewm(span=200, adjust=False).mean().shift(1)
        sma = c.rolling(20).mean(); sd = c.rolling(20).std(ddof=0); r14 = sw.rsi(c, 14)
        sig = (c < sma - 2 * sd) & (r14 < 30) & (c > ema)
        fwd = dfd.open.shift(-1).rdiv(1) * 0  # placeholder
        fwd = c.shift(-6) / dfd.open.shift(-1) - 1 - 2e-4
        up = (c > ema)
        x = fwd[sig].dropna(); b = fwd[up].dropna()
        yrs = x.groupby(x.index.year).mean()
        pos_years = int((yrs > 0).sum())
        print(f"  {s}: since {c.index[0].date()}  n {len(x)} mean {x.mean() * 1e4:+.0f}bp hit {(x > 0).mean():.2f} t {tstat(x):+.1f} | uptrend base {b.mean() * 1e4:+.0f}bp | excess t {(x.mean() - b.mean()) / np.sqrt(x.var() / len(x) + b.var() / len(b)):+.1f} | positive years {pos_years}/{len(yrs)}")


if __name__ == "__main__":
    main()
