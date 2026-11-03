"""What do the README's two operating rules cost Sleeve E when actually applied?

  R1  2% daily loss cap -> for an overnight sleeve: skip the next entry after
      a night that lost more than 2% of sleeve equity.
  R2  30-day rolling Sharpe < 0.3 -> sleeve off (the orchestrator's risk_gate),
      re-enabled when it recovers.  Evaluated daily on the sleeve's own equity.

Applied to E v2 (SPY/QQQ/IWM, RSI2<10 x2, 1bp/side) and E3 v2, 2000-2026,
with the same code the tickets use.  Rules are only worth having if their
cost in Sharpe is small relative to the tail they remove; this prints both.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import yfinance as yf

from ten_cent_bot import overnight as ov
from ten_cent_bot.metrics import max_drawdown, sharpe
from ten_cent_bot.orchestrator import risk_gate
from ten_cent_bot.risk import daily_loss_cap_hit


def summ(r):
    r = r.dropna(); eq = (1 + r).cumprod()
    return f"Sharpe {sharpe(r,252):5.2f}  CAGR {((1+r.mean())**252-1):6.2%}  MaxDD {max_drawdown(eq):6.1%}  worst night {r.min():6.2%}  nights < -2% {(r < -0.02).sum():>3}"


def apply_rules(r: pd.Series, cap: float | None, kill: bool) -> tuple[pd.Series, int, int]:
    eq = [1.0]; out = []; skipped_cap = 0; skipped_kill = 0
    for i, x in enumerate(r.values):
        hist = pd.Series(eq)
        trade = True
        if cap is not None:
            hit, _ = daily_loss_cap_hit(hist, cap)
            if hit: trade = False; skipped_cap += 1
        if trade and kill and len(hist) > 31:
            ok, _ = risk_gate(pd.Series(hist.values, index=pd.bdate_range("2000-01-03", periods=len(hist))))
            if not ok: trade = False; skipped_kill += 1
        ret = x if trade else 0.0
        out.append(ret); eq.append(eq[-1] * (1 + ret))
    return pd.Series(out, index=r.index), skipped_cap, skipped_kill


def main():
    d = yf.download(ov.E3_TICKERS, period="max", interval="1d", auto_adjust=True, progress=False)
    fr = {t: pd.DataFrame({"open": d["Open"][t], "close": d["Close"][t]}).dropna() for t in ov.E3_TICKERS}
    for f in fr.values(): f.index = pd.to_datetime(f.index).tz_localize(None)
    for label, tks in [("E v2", ov.E_TICKERS), ("E3 v2", ov.E3_TICKERS)]:
        start = max(fr[t].index.min() for t in tks)
        r = ov.backtest_portfolio({t: fr[t].loc[start:] for t in tks}, ov.E_V2_CONFIG)["portfolio_return"].dropna()
        print(f"\n=== {label}, {r.index.min().date()} -> {r.index.max().date()} ===")
        print(f"  no rules                 " + summ(r))
        for cap, kill, lab in [(0.02, False, "R1 2% cap (skip next night)"), (0.03, False, "R1 at 3%"), (None, True, "R2 30d Sharpe<0.3 kill switch"), (0.02, True, "R1 + R2")]:
            rr, sc, sk = apply_rules(r, cap, kill)
            h = len(rr) // 2
            print(f"  {lab:<28} " + summ(rr) + f"   skipped: cap {sc:>3}, kill {sk:>4}   halves {sharpe(rr.iloc[:h],252):.2f}/{sharpe(rr.iloc[h:],252):.2f}")
    print("\nReading: R1 touches a handful of nights and should cost ~nothing; R2 turns the sleeve off in flat stretches - if it costs Sharpe, the README rule is wrong for E and should be replaced (e.g. drawdown-based) before it is wired live.")


if __name__ == "__main__":
    main()


def drawdown_kill_variants() -> None:
    """R3: drawdown circuit breaker. Off when sleeve equity is more than `off`
    below its peak; back on when equity makes a new `reentry`-day high.
    Pre-registered grid: off in {15,20,25}%, reentry 120 days."""
    d = yf.download(ov.E_TICKERS, period="max", interval="1d", auto_adjust=True, progress=False)
    fr = {t: pd.DataFrame({"open": d["Open"][t], "close": d["Close"][t]}).dropna() for t in ov.E_TICKERS}
    for f in fr.values(): f.index = pd.to_datetime(f.index).tz_localize(None)
    r = ov.backtest_portfolio(fr, ov.E_V2_CONFIG)["portfolio_return"].dropna()
    print("\n=== R3: drawdown circuit breaker on E v2 (off below -X% from peak, on at a new 120-day equity high) ===")
    print("  no rules                 " + summ(r))
    for off in [0.15, 0.20, 0.25]:
        eq = 1.0; peak = 1.0; on = True; out = []; hist = []; offs = 0
        for x in r.values:
            if on:
                ret = x
            else:
                ret = 0.0; offs += 1
            eq *= 1 + ret; hist.append(eq); peak = max(peak, eq)
            # shadow equity (what the sleeve would do) decides re-entry
            if on and eq / peak - 1 < -off:
                on = False; shadow = eq; shadow_hist = [eq]
            elif not on:
                shadow *= 1 + x; shadow_hist.append(shadow)
                if shadow >= max(shadow_hist[-120:]) and len(shadow_hist) >= 120:
                    on = True; eq = eq  # resume
            out.append(ret)
        rr = pd.Series(out, index=r.index); h = len(rr) // 2
        print(f"  off at -{off:.0%}, on at new 120d high   " + summ(rr) + f"   days off {offs:>5}   halves {sharpe(rr.iloc[:h],252):.2f}/{sharpe(rr.iloc[h:],252):.2f}")
    print("  Reading: E's crashes recover fast; any rule that stays out until a new high misses the rebound. Alert-and-review beats auto-off.")


if __name__ == "__main__":
    drawdown_kill_variants()
