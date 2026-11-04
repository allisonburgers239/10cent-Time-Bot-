"""Sleeve I candidate - ETF oversold swing (built 2026-11-04, from Temur's trend-exhaustion idea).

Rule
  bars      two 4-hour session bars per day (09:30-13:30, 13:30-16:00 ET) built from hourly bars
  trend     previous day's daily close > daily EMA(trend_ema) of daily closes
  oversold  4h close < lower Bollinger(bb_len, bb_k) AND 4h RSI(rsi_len) < rsi_thr
  entry     next 4h bar's open; hold `hold_bars` 4h bars, no stop; one position per ETF at a time
  sizing    each position gets 1/max_slots of the sleeve's capital; at most max_slots open at once
  cost      cost_bps_per_side per side

Everything is a pure function of the bars so the audit can prove library == audit.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

TZ = "America/New_York"


@dataclass(frozen=True)
class SwingConfig:
    trend_ema: int = 200
    bb_len: int = 20
    bb_k: float = 2.0
    rsi_len: int = 14
    rsi_thr: float = 30.0
    hold_bars: int = 10
    max_slots: int = 5
    cost_bps_per_side: float = 1.0


def rsi(x: pd.Series, n: int) -> pd.Series:
    d = x.diff()
    up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    dn = (-d).clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    return 100 - 100 / (1 + up / dn.replace(0, np.nan))


def to_4h(hourly: pd.DataFrame) -> pd.DataFrame:
    """Regular-session hourly OHLC (tz-aware, ET) -> two 4h bars per day."""
    df = hourly.between_time("09:30", "15:59")
    return df.resample("4h", origin="start_day", offset="9h30min").agg({"open": "first", "high": "max", "low": "min", "close": "last"}).dropna()


def signals(bars4h: pd.DataFrame, cfg: SwingConfig) -> pd.DataFrame:
    """Add trend / oversold / sig columns. Uses only information available at each bar's close."""
    f = bars4h.copy()
    c = f.close
    daily_close = c.groupby(f.index.date).last()
    ema = daily_close.ewm(span=cfg.trend_ema, adjust=False).mean().shift(1)  # yesterday's EMA
    f["ema"] = [ema.get(d, np.nan) for d in f.index.date]
    sma = c.rolling(cfg.bb_len).mean(); sd = c.rolling(cfg.bb_len).std(ddof=0)
    f["bb_l"] = sma - cfg.bb_k * sd
    f["rsi"] = rsi(c, cfg.rsi_len)
    f["trend"] = c > f.ema
    f["oversold"] = (c < f.bb_l) & (f.rsi < cfg.rsi_thr)
    f["sig"] = f.trend & f.oversold & f.ema.notna() & f.bb_l.notna()
    return f


def trade_returns(f: pd.DataFrame, cfg: SwingConfig) -> pd.Series:
    """Per-signal return of entering at the next bar's open and exiting at the close `hold_bars`
    bars later (or the last bar), net of costs. Index = signal bar time."""
    o = f.open.to_numpy(); c = f.close.to_numpy(); n = len(f)
    out = {}
    for i in np.flatnonzero(f.sig.to_numpy()):
        if i + 1 >= n:
            continue
        j = min(i + 1 + cfg.hold_bars, n - 1)
        out[f.index[i]] = c[j] / o[i + 1] - 1 - 2 * cfg.cost_bps_per_side / 1e4
    return pd.Series(out, dtype=float)


def backtest(bars_by_symbol: dict[str, pd.DataFrame], cfg: SwingConfig | None = None) -> dict:
    """Portfolio simulation across symbols. Returns daily sleeve returns on the sleeve's capital
    (each trade = 1/max_slots of capital, booked on its exit day), the trade list, and per-symbol frames."""
    cfg = cfg or SwingConfig()
    frames = {s: signals(b, cfg) for s, b in bars_by_symbol.items()}
    events = []
    for s, f in frames.items():
        tr = trade_returns(f, cfg)
        idx = {t: i for i, t in enumerate(f.index)}
        for t, r in tr.items():
            i = idx[t]
            exit_i = min(i + 1 + cfg.hold_bars, len(f) - 1)
            events.append((t, f.index[exit_i], s, r))
    events.sort()
    open_trades: list[tuple[pd.Timestamp, str]] = []  # (exit_time, symbol)
    taken = []
    for t, exit_t, s, r in events:
        open_trades = [x for x in open_trades if x[0] > t]
        if any(x[1] == s for x in open_trades) or len(open_trades) >= cfg.max_slots:
            continue
        open_trades.append((exit_t, s)); taken.append((t, exit_t, s, r))
    trades = pd.DataFrame(taken, columns=["entry_signal", "exit", "symbol", "ret"])
    all_days = sorted(set(d.date() for f in frames.values() for d in f.index))
    daily = pd.Series(0.0, index=pd.DatetimeIndex(all_days))
    for _, x in trades.iterrows():
        daily[pd.Timestamp(x.exit.date())] += x.ret / cfg.max_slots
    equity = (1 + daily).cumprod()
    return {"frames": frames, "trades": trades, "daily": daily, "equity": equity}


def summary(res: dict, periods_per_year: int = 252) -> dict:
    d = res["daily"]; t = res["trades"]
    eq = res["equity"]
    yrs = len(d) / periods_per_year
    return {
        "trades": int(len(t)), "win": float((t.ret > 0).mean()) if len(t) else float("nan"),
        "mean_trade_bp": float(t.ret.mean() * 1e4) if len(t) else float("nan"),
        "worst_trade_bp": float(t.ret.min() * 1e4) if len(t) else float("nan"),
        "cagr": float(eq.iloc[-1] ** (1 / yrs) - 1) if yrs > 0 else float("nan"),
        "sharpe": float(d.mean() / d.std() * np.sqrt(periods_per_year)) if d.std() > 0 else 0.0,
        "max_drawdown": float((eq / eq.cummax() - 1).min()),
        "days": int(len(d)),
    }
