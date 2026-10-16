"""Sleeve E overlay audit: short-term reversal sizing on the overnight hold.

Signal (own ticker, known at the 16:00 close): the day closed down for the
k-th consecutive session (streak), or RSI(2) < 10.  On signal nights E's
overnight position is multiplied by m; all other nights unchanged.  No new
trades: the same 16:00 buy / 09:30 sell, just larger on ~9% of nights.

Origin: screen_price_patterns.py (pre-registered battery, Bonferroni-
significant on SPY/QQQ/IWM/TLT), then screen_reversal_overlay_e.py.
Literature: Lehmann (1990), Jegadeesh (1990) short-term reversal; daily
index autocorrelation turned negative after ~1999 (e.g. Campbell-Lo-
MacKinlay variance ratios; Connors RSI(2) is the practitioner version).

Sections: 1 baseline vs E, 2 walk-forward, 3 grid (k x m x signal),
4 sub-periods, 5 leave-one-out, 6 cost, 7 placebo, 8 tail / risk-rule
interaction.  Verdict needs Sharpe up in BOTH halves, >=80% of grid above
baseline, placebo p<0.05, and a stated answer on the drawdown.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import yfinance as yf

from ten_cent_bot.metrics import max_drawdown, sharpe, sortino

TICKERS = ["SPY", "QQQ", "IWM"]
COST_BPS_SIDE = 1.0


def rsi(c: pd.Series, n: int) -> pd.Series:
    d = c.diff()
    up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    return 100 - 100 / (1 + up / dn.replace(0, np.nan))


def load() -> dict[str, pd.DataFrame]:
    data = yf.download(TICKERS, period="max", interval="1d", auto_adjust=True, progress=False)
    out = {}
    for t in TICKERS:
        df = pd.DataFrame({"open": data["Open"][t], "close": data["Close"][t]}).dropna()
        df["on"] = df["open"].shift(-1) / df["close"] - 1
        down = (df["close"].pct_change() < 0).astype(int)
        df["streak"] = down.groupby((down != down.shift()).cumsum()).cumsum() * down
        df["rsi2"] = rsi(df["close"], 2)
        out[t] = df
    return out


def multiplier(df: pd.DataFrame, k: int, m: float, signal: str) -> pd.Series:
    s_streak = df["streak"] >= k
    s_rsi = df["rsi2"] < 10
    sig = {"streak": s_streak, "rsi2": s_rsi, "either": s_streak | s_rsi, "none": pd.Series(False, index=df.index)}[signal]
    return pd.Series(np.where(sig, m, 1.0), index=df.index)


def portfolio(data: dict, k: int = 3, m: float = 2.0, signal: str = "streak", cost: float = COST_BPS_SIDE, tickers=None) -> pd.Series:
    rets = []
    for t in tickers or TICKERS:
        df = data[t]
        mult = multiplier(df, k, m, signal)
        rets.append(mult * df["on"] - mult.abs() * 2 * cost / 1e4)
    return pd.concat(rets, axis=1).dropna().mean(axis=1)


def S(r: pd.Series) -> dict:
    r = r.dropna(); eq = (1 + r).cumprod()
    return {"sharpe": sharpe(r, 252), "sortino": sortino(r, 252), "cagr": (1 + r.mean()) ** 252 - 1, "mdd": max_drawdown(eq), "n": len(r)}


def fmt(s: dict) -> str:
    return f"Sharpe {s['sharpe']:5.2f}  Sortino {s['sortino']:5.2f}  CAGR {s['cagr']:6.2%}  MaxDD {s['mdd']:6.1%}  n={s['n']}"


def main() -> None:
    data = load()
    base = portfolio(data, signal="none")
    ov = portfolio(data)
    print(f"Window {base.index.min().date()} -> {base.index.max().date()} (limited by IWM)")

    print("\n=== 1. Baseline: E vs E + reversal overlay (k=3, x2, streak) ===")
    print("  E                " + fmt(S(base)))
    print("  E + overlay      " + fmt(S(ov)))
    print("  E + overlay rsi2 " + fmt(S(portfolio(data, signal='rsi2'))))
    print("  E + overlay x1.5 " + fmt(S(portfolio(data, m=1.5))))

    print("\n=== 2. Walk-forward halves (E -> overlay) ===")
    n = len(base) // 2
    for name, sl in [("train", slice(0, n)), ("test", slice(n, None))]:
        print(f"  {name}: E {S(base.iloc[sl])['sharpe']:.2f} -> overlay {S(ov.iloc[sl])['sharpe']:.2f}   ({base.index[sl][0].date()} -> {base.index[sl][-1].date()})")

    print("\n=== 3. Grid: k x multiplier x signal (Sharpe; baseline E in brackets) ===")
    rows = []
    for signal in ["streak", "rsi2", "either"]:
        for k in [2, 3, 4]:
            for m in [1.25, 1.5, 2.0, 3.0]:
                if signal == "rsi2" and k != 3:
                    continue
                s = S(portfolio(data, k=k, m=m, signal=signal))
                rows.append({"signal": signal, "k": k, "m": m, "sharpe": s["sharpe"], "mdd": s["mdd"]})
    g = pd.DataFrame(rows)
    b = S(base)["sharpe"]
    print(g.pivot_table(index=["signal", "k"], columns="m", values="sharpe").round(3).to_string())
    print(f"  baseline E Sharpe [{b:.3f}];  grid cells above baseline: {(g.sharpe > b).mean():.0%} of {len(g)};  MaxDD range {g.mdd.min():.1%} .. {g.mdd.max():.1%}")

    print("\n=== 4. Sub-periods (5y): E Sharpe -> overlay Sharpe ===")
    for start in range(2000, 2027, 5):
        w = (base.index.year >= start) & (base.index.year < start + 5)
        if w.sum() < 300:
            continue
        print(f"  {start}-{start+4}: {S(base[w])['sharpe']:+.2f} -> {S(ov[w])['sharpe']:+.2f}   MaxDD {S(base[w])['mdd']:.1%} -> {S(ov[w])['mdd']:.1%}")

    print("\n=== 5. Leave-one-out ticker ===")
    for drop in TICKERS:
        keep = [t for t in TICKERS if t != drop]
        print(f"  drop {drop}: E {S(portfolio(data, signal='none', tickers=keep))['sharpe']:.2f} -> overlay {S(portfolio(data, tickers=keep))['sharpe']:.2f}")

    print("\n=== 6. Cost sensitivity (bps per side; overlay pays 2x cost on signal nights) ===")
    for c in [0.5, 1.0, 2.0, 3.0, 5.0]:
        print(f"  {c:>3.1f} bps: E {S(portfolio(data, signal='none', cost=c))['sharpe']:.2f} -> overlay {S(portfolio(data, cost=c))['sharpe']:.2f}")

    print("\n=== 7. Placebo: random signal nights, same frequency per ticker (300 seeds) ===")
    rng = np.random.default_rng(41)
    real = S(ov)["sharpe"]
    pl = []
    for _ in range(300):
        rets = []
        for t in TICKERS:
            df = data[t]; f = (df["streak"] >= 3).mean()
            mult = pd.Series(np.where(rng.random(len(df)) < f, 2.0, 1.0), index=df.index)
            rets.append(mult * df["on"] - mult * 2 * COST_BPS_SIDE / 1e4)
        pl.append(sharpe(pd.concat(rets, axis=1).dropna().mean(axis=1), 252))
    pl = np.array(pl); p = float((pl >= real).mean())
    print(f"  real {real:.3f}  placebo {pl.mean():.3f} +/- {pl.std():.3f}  P(placebo>=real)={p:.3f}  {'REAL' if p<0.05 else 'WEAK' if p<0.2 else 'NONE'}")

    print("\n=== 8. Tail and risk-rule interaction ===")
    r = ov.dropna(); rb = base.dropna()
    print(f"  worst night: E {rb.min():.2%} ({rb.idxmin().date()})  overlay {r.min():.2%} ({r.idxmin().date()})")
    print(f"  nights < -2%: E {(rb < -0.02).sum()}  overlay {(r < -0.02).sum()}    nights < -4%: E {(rb < -0.04).sum()}  overlay {(r < -0.04).sum()}")
    print(f"  skew E {rb.skew():.2f} overlay {r.skew():.2f};  ES99 E {rb[rb <= rb.quantile(0.01)].mean():.2%} overlay {r[r <= r.quantile(0.01)].mean():.2%}")
    for label, a, b_ in [("2008-09/10", "2008-09-01", "2008-10-31"), ("2020-02/03", "2020-02-20", "2020-03-31"), ("2022", "2022-01-01", "2022-12-31"), ("2025-04 tariff", "2025-04-01", "2025-04-15")]:
        print(f"  {label:<14} E {rb.loc[a:b_].sum():+7.2%}   overlay {r.loc[a:b_].sum():+7.2%}")
    print("  Note: the README's 2% daily loss cap and 1% risk-per-trade rule are already exceeded by E at 1x on a bad night; a 2x night doubles that. The honest deployment choice is x1.5 or sizing the whole sleeve so that 2x on a signal night stays inside the cap.")


if __name__ == "__main__":
    main()
