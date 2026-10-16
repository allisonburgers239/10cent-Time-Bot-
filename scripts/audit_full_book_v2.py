"""Full-book comparison with the 2026-10 candidates in it.

Components (monthly, 2007-06 -> 2026-10 to match audit_combined_be.py):
  B    TSMOM on the 10-ETF basket (deployed reference, 10bps)
  E    overnight SPY/QQQ/IWM, 1bp/side
  E2   E with the RSI(2)<10 x2 overlay (overnight.E_V2_CONFIG)
  F    Faber 10-month SMA long-only timing on the same 10-ETF basket
Questions: does swapping E -> E2 change the B70/E30 book?  Does F add
anything next to B (it is a long-only cousin)?  Correlations first.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import yfinance as yf

from ten_cent_bot import overnight as ov
from ten_cent_bot import tsmom
from ten_cent_bot.metrics import max_drawdown, sharpe

ETFS = ["SPY", "QQQ", "IWM", "EFA", "EEM", "TLT", "IEF", "GLD", "USO", "DBC"]


def monthly_from_daily(r: pd.Series) -> pd.Series:
    return (1 + r.fillna(0)).resample("ME").prod() - 1


def summ(r: pd.Series) -> str:
    r = r.dropna(); eq = (1 + r).cumprod()
    return f"Sharpe {sharpe(r,12):5.2f}  CAGR {((1+r.mean())**12-1):6.2%}  Vol {r.std(ddof=0)*np.sqrt(12):5.1%}  MaxDD {max_drawdown(eq):6.1%}"


def main():
    px = yf.download(ETFS, period="max", interval="1d", auto_adjust=True, progress=False)["Close"]
    px.index = pd.to_datetime(px.index).tz_localize(None)
    m = px.resample("ME").last()
    B = tsmom.backtest(m)["monthly_return_net"]
    ret = m.pct_change(); sig = (m > m.rolling(10).mean()).shift(1).astype(float)
    F = (sig * ret).mean(axis=1) - sig.diff().abs().mean(axis=1) * 10 / 1e4
    d = yf.download(["SPY", "QQQ", "IWM"], period="max", interval="1d", auto_adjust=True, progress=False)
    frames = {t: pd.DataFrame({"open": d["Open"][t], "close": d["Close"][t]}).dropna() for t in ["SPY", "QQQ", "IWM"]}
    for f in frames.values():
        f.index = pd.to_datetime(f.index).tz_localize(None)
    E = monthly_from_daily(ov.backtest_portfolio(frames, ov.OvernightConfig())["portfolio_return"])
    E2 = monthly_from_daily(ov.backtest_portfolio(frames, ov.E_V2_CONFIG)["portfolio_return"])
    df = pd.concat([B.rename("B"), E.rename("E"), E2.rename("E2"), F.rename("F")], axis=1).loc["2007-06-30":"2026-10-31"].dropna()
    print(f"window {df.index.min().date()} -> {df.index.max().date()}, {len(df)} months\n")
    for c in df.columns:
        print(f"  {c:<3} " + summ(df[c]))
    print("\ncorrelations:\n" + df.corr().round(3).to_string())

    print("\n=== Books (static weights, monthly rebalanced) ===")
    books = {
        "B70/E30 (current)": {"B": 0.7, "E": 0.3},
        "B70/E2 30": {"B": 0.7, "E2": 0.3},
        "B60/E2 40": {"B": 0.6, "E2": 0.4},
        "B50/E2 50": {"B": 0.5, "E2": 0.5},
        "F100 (Faber alone)": {"F": 1.0},
        "B50/F50": {"B": 0.5, "F": 0.5},
        "B50/E2 25/F25": {"B": 0.5, "E2": 0.25, "F": 0.25},
        "B40/E2 30/F30": {"B": 0.4, "E2": 0.3, "F": 0.3},
    }
    rows = []
    for name, w in books.items():
        r = sum(df[k] * v for k, v in w.items())
        h = len(r) // 2
        rows.append((name, r))
        print(f"  {name:<22} " + summ(r) + f"   halves {sharpe(r.iloc[:h],12):.2f}/{sharpe(r.iloc[h:],12):.2f}")

    print("\n=== Sharpe-max weight scan over (B, E2, F), 10% steps, no leverage, long-only ===")
    best = []
    for wb in np.arange(0, 1.01, 0.1):
        for we in np.arange(0, 1.01 - wb, 0.1):
            wf = 1 - wb - we
            r = wb * df["B"] + we * df["E2"] + wf * df["F"]
            best.append((sharpe(r, 12), wb, we, wf, max_drawdown((1 + r).cumprod())))
    best.sort(reverse=True)
    for s, wb, we, wf, mdd in best[:6]:
        print(f"  B {wb:.1f} / E2 {we:.1f} / F {wf:.1f}: Sharpe {s:.3f}  MaxDD {mdd:.1%}")
    print("  (a scan is a description of the sample, not a weight to deploy)")

    print("\n=== Placebo: F and E2 block-shuffled in time (12m blocks, 300 seeds): does the REAL timing beat a sleeve with the same return distribution but no co-movement? ===")
    rng = np.random.default_rng(21)
    def block_shuffle(x: pd.Series) -> pd.Series:
        v = x.values.copy(); blocks = [v[i:i+12] for i in range(0, len(v), 12)]; rng.shuffle(blocks)
        return pd.Series(np.concatenate(blocks)[: len(v)], index=x.index)
    tests = [
        ("E -> E2 in B70/x30", lambda: 0.7 * df["B"] + 0.3 * df["E"], lambda: 0.7 * df["B"] + 0.3 * df["E2"], lambda: 0.7 * df["B"] + 0.3 * block_shuffle(df["E2"])),
        ("add F: B70/E2 30 -> B50/E2 25/F25", lambda: 0.7 * df["B"] + 0.3 * df["E2"], lambda: 0.5 * df["B"] + 0.25 * df["E2"] + 0.25 * df["F"], lambda: 0.5 * df["B"] + 0.25 * df["E2"] + 0.25 * block_shuffle(df["F"])),
    ]
    for label, base_f, real_f, pl_f in tests:
        base = sharpe(base_f(), 12); real = sharpe(real_f(), 12) - base
        pl = np.array([sharpe(pl_f(), 12) - base for _ in range(300)])
        print(f"  {label:<36} real gain {real:+.3f}   shuffled {pl.mean():+.3f} +/- {pl.std():.3f}   P(shuffled>=real)={float((pl>=real).mean()):.3f}")
    print("  Reading: a shuffled sleeve keeps its mean and vol but loses its timing relative to B; if it 'helps' as much as the real one, the benefit is just diversification by a positive-mean series, not skill.")


if __name__ == "__main__":
    main()
