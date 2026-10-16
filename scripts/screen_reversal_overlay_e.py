"""Screen: short-term reversal as a sizing overlay on Sleeve E.

The pattern battery (screen_price_patterns.py) found that in equity ETFs
the day after 3 consecutive down closes, or after RSI(2) < 10, carries a
positive excess return at p < 0.003 on several tickers.  Sleeve E already
holds every overnight, so the tradable question is: does the NEXT
OVERNIGHT carry the reversal, and does scaling E on those nights help?

Pre-registered family (not tuned): k consecutive down closes for k=2..5,
and RSI(2) < 10.  Decompose next-day return into overnight (E's leg) and
intraday.  Overlay variants fixed in advance: x2 on signal nights, x1.5.
Sub-periods and a random-nights placebo close it out.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import yfinance as yf

from ten_cent_bot.metrics import max_drawdown, sharpe

TICKERS = ["SPY", "QQQ", "IWM", "EFA"]


def rsi(c: pd.Series, n: int) -> pd.Series:
    d = c.diff()
    up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    return 100 - 100 / (1 + up / dn.replace(0, np.nan))


def stat(x: pd.Series, base: float) -> str:
    x = x.dropna()
    t = (x.mean() - base) / (x.std(ddof=1) / np.sqrt(len(x)))
    return f"{x.mean()*1e4:+6.1f}bp (excess {((x.mean()-base)*1e4):+5.1f}, t={t:+5.2f}, n={len(x):>4})"


def main() -> None:
    data = yf.download(TICKERS, period="max", interval="1d", auto_adjust=True, progress=False)
    frames = {}
    for t in TICKERS:
        df = pd.DataFrame({"open": data["Open"][t], "close": data["Close"][t]}).dropna()
        df["r"] = df["close"].pct_change()
        df["on"] = df["open"].shift(-1) / df["close"] - 1          # next overnight
        df["id"] = df["close"].shift(-1) / df["open"].shift(-1) - 1  # next intraday
        df["nxt"] = df["close"].shift(-1) / df["close"] - 1
        down = (df["r"] < 0).astype(int)
        streak = down.groupby((down != down.shift()).cumsum()).cumsum() * down
        df["streak"] = streak
        df["rsi2"] = rsi(df["close"], 2)
        frames[t] = df

    print("=== Next-day return after k consecutive down closes, split overnight / intraday ===")
    for t, df in frames.items():
        print(f"\n--- {t} ({df.index.min().date()} -> {df.index.max().date()})")
        b_on, b_id, b_n = df["on"].mean(), df["id"].mean(), df["nxt"].mean()
        print(f"  unconditional: overnight {b_on*1e4:+.1f}bp  intraday {b_id*1e4:+.1f}bp  close-close {b_n*1e4:+.1f}bp")
        for k in [2, 3, 4, 5]:
            m = df["streak"] >= k
            print(f"  >= {k} down: overnight {stat(df.loc[m,'on'], b_on)}   intraday {stat(df.loc[m,'id'], b_id)}")
        m = df["rsi2"] < 10
        print(f"  RSI2 < 10 : overnight {stat(df.loc[m,'on'], b_on)}   intraday {stat(df.loc[m,'id'], b_id)}")

    print("\n=== Sub-periods: excess NEXT-OVERNIGHT return after >=3 down closes (bp, t) ===")
    for t, df in frames.items():
        parts = []
        for start in range(1993, 2027, 5):
            w = (df.index.year >= start) & (df.index.year < start + 5)
            m = w & (df["streak"] >= 3)
            if m.sum() < 20:
                continue
            x = df.loc[m, "on"]; base = df.loc[w, "on"].mean()
            parts.append(f"{start}: {((x.mean()-base)*1e4):+5.1f} (t{((x.mean()-base)/(x.std(ddof=1)/np.sqrt(len(x)))):+.1f})")
        print(f"  {t:<4} " + "  ".join(parts))

    print("\n=== Overlay on E: overnight SPY/QQQ/IWM, 1bp/side, multiplier on nights after >=3 down closes (own ticker) ===")
    on = pd.DataFrame({t: frames[t]["on"] for t in ["SPY", "QQQ", "IWM"]}).dropna()
    sig = pd.DataFrame({t: (frames[t]["streak"] >= 3) for t in ["SPY", "QQQ", "IWM"]}).reindex(on.index).fillna(False)
    rsi_sig = pd.DataFrame({t: (frames[t]["rsi2"] < 10) for t in ["SPY", "QQQ", "IWM"]}).reindex(on.index).fillna(False)
    rng = np.random.default_rng(31)
    variants = {
        "E baseline": pd.DataFrame(1.0, index=on.index, columns=on.columns),
        "x2 after >=3 down": 1.0 + sig.astype(float),
        "x1.5 after >=3 down": 1.0 + 0.5 * sig.astype(float),
        "x2 when RSI2<10": 1.0 + rsi_sig.astype(float),
        "x2 after >=3 down OR RSI2<10": 1.0 + (sig | rsi_sig).astype(float),
        "x0 after >=3 down (the opposite)": 1.0 - sig.astype(float),
    }
    base_sh = None
    for label, mult in variants.items():
        port = (mult * on - mult.abs() * 2 / 1e4).mean(axis=1)
        eq = (1 + port).cumprod()
        sh = sharpe(port, 252)
        base_sh = base_sh or sh
        h = len(port) // 2
        print(f"  {label:<34} Sharpe {sh:5.2f}  CAGR {((1+port.mean())**252-1):6.2%}  MaxDD {max_drawdown(eq):6.1%}  halves {sharpe(port.iloc[:h],252):.2f}/{sharpe(port.iloc[h:],252):.2f}  gross {mult.mean().mean():.2f}x  signal nights {sig.mean().mean():.0%}")
    real = sharpe(((1.0 + sig.astype(float)) * on - (1.0 + sig.astype(float)) * 2 / 1e4).mean(axis=1), 252)
    pl = []
    for _ in range(200):
        rs = pd.DataFrame(rng.random(sig.shape) < sig.values.mean(), index=sig.index, columns=sig.columns)
        m = 1.0 + rs.astype(float)
        pl.append(sharpe((m * on - m * 2 / 1e4).mean(axis=1), 252))
    pl = np.array(pl)
    print(f"  placebo (random nights, same frequency, x2): real {real:.3f}, placebo {pl.mean():.3f} +/- {pl.std():.3f}, P(rand>=real)={float((pl>=real).mean()):.3f}")


if __name__ == "__main__":
    main()
