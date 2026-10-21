"""Reference numbers for pine/e_v2_overnight.pine under TradingView's fill
convention, computed in Python on the repo's 5-min BATS exports
(SPY/QQQ/IWM, 2025-06 -> 2026-06).

TV convention replicated exactly:
  entry  = close of the 15:55 bar (process_orders_on_close), qty = floor(equity * mult / price)
  exit   = close of the 09:30 bar (= 09:35 print)
  RSI(2) = Wilder EWM (alpha 1/2) on the sequence of 15:55 closes, seeded on the first diff
  cost   = 0.01% per side (commission_value = 0.01)
  equity compounds; no entry on days without a 15:55 bar (half days)
  warm-up = no signal in the first 10 sessions (Wilder seeding gives RSI 0 after one down day)
Prints the summary TV's Strategy Tester should match (net profit, trades,
win rate, max DD) and the first/last trades for line-by-line comparison.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from ten_cent_bot.tv_data import load_tv_csv

ROOT = Path(__file__).resolve().parents[1]


def run(sym: str, equity0: float = 25000.0, thr: float = 10.0, mult: float = 2.0, cost: float = 0.0001):
    bars = load_tv_csv(ROOT / f"BATS_{sym}, 5.csv").tz_convert("America/New_York")
    ent = bars.between_time("15:55", "15:55")["close"]; ent.index = ent.index.normalize()
    ext = bars.between_time("09:30", "09:30")["close"]; ext.index = ext.index.normalize()
    ent = ent[~ent.index.duplicated()]; ext = ext[~ext.index.duplicated()]
    days = sorted(ent.index)
    au = ad = None; prev = None; equity = equity0; trades = []; eq_curve = []
    for i, d in enumerate(days):
        c = float(ent[d])
        rsi = np.nan
        if prev is not None:
            diff = c - prev; up = max(diff, 0); dn = max(-diff, 0)
            au = up if au is None else 0.5 * au + 0.5 * up
            ad = dn if ad is None else 0.5 * ad + 0.5 * dn
            rsi = 100.0 if ad == 0 else 100 - 100 / (1 + au / ad)
        prev = c
        if i + 1 >= len(days):
            break
        nxt = days[i + 1]
        if nxt not in ext.index:
            continue
        sig = (not np.isnan(rsi)) and i > 10 and rsi < thr   # 10-day warm-up, same as the Pine input
        m = mult if sig else 1.0
        qty = int(equity * m // c)
        if qty <= 0:
            continue
        px_out = float(ext[nxt])
        pnl = qty * (px_out - c) - cost * qty * (c + px_out)
        equity += pnl
        trades.append({"entry": d.date(), "exit": nxt.date(), "rsi2": round(rsi, 1) if not np.isnan(rsi) else None, "mult": m, "qty": qty, "in": c, "out": px_out, "pnl": round(pnl, 2), "equity": round(equity, 2)})
        eq_curve.append(equity)
    t = pd.DataFrame(trades)
    eq = pd.Series(eq_curve)
    r = eq.pct_change().dropna()
    print(f"\n=== {sym}: {t.entry.min()} -> {t.exit.max()}, {len(t)} trades, signal nights {(t.mult > 1).sum()} ===")
    print(f"  net profit ${equity - equity0:,.2f} ({(equity/equity0 - 1):+.2%})   win rate {(t.pnl > 0).mean():.1%}   max DD {((eq - eq.cummax())/eq.cummax()).min():.2%}   Sharpe (ann.) {r.mean()/r.std()*np.sqrt(252):.2f}")
    print(f"  avg trade ${t.pnl.mean():,.2f}; signal-night avg ${t[t.mult>1].pnl.mean():,.2f} vs normal ${t[t.mult==1].pnl.mean():,.2f}")
    print("  first 5 trades:"); print(t.head(5).to_string(index=False))
    print("  last 5 trades:"); print(t.tail(5).to_string(index=False))
    return t


def main():
    print("TradingView Strategy Tester reference: pine/e_v2_overnight.pine, 5-min chart, initial 25000, commission 0.01%, 100% equity x mult")
    for s in ["SPY", "QQQ", "IWM"]:
        run(s)
    print("\nIf TV's numbers differ: check (1) chart is 5-min with the 15:55 bar present, (2) commission 0.01% per order, (3) 'Recalculate: after order is filled' OFF, (4) data range equals 2025-06-16 -> 2026-06-29, (5) bar magnifier OFF.")


if __name__ == "__main__":
    main()
