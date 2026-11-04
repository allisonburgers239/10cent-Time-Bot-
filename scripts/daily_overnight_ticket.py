"""Daily order ticket for Sleeve E / E v2 / E3 (overnight hold), dry-run.

Mirrors scripts/monthly_rebalance.py's file mode for Sleeve B: computes
tonight's signal and sizes, prints a human-readable ticket, writes
data/last_overnight_ticket.json.  No broker calls.  Run at ~15:50 ET.

  python scripts/daily_overnight_ticket.py --equity 25000                # E3 + v2 overlay, futures rail
  python scripts/daily_overnight_ticket.py --equity 25000 --basket e --overlay none --rail etf

Rails:
  futures  SPY->MES, QQQ->MNQ, IWM->M2K, GLD->MGC on Tradovate (sizes in contracts)
  etf      shares of the ETFs at an equity broker

Signal: ten_cent_bot.overnight.reversal_signal on daily closes with TODAY's
last price appended as the provisional close (the real close is unknown at
15:50; the audit's Section 11-12 shows the edge survives that).  A ticker
whose RSI(2) is within +/-1 point of the threshold is flagged MARGINAL.

Sizing: target notional per leg = equity * gross / N * multiplier.  With
micro contracts a small account cannot reach 1x: one MES is ~$39k, so the
ticket also prints the minimum viable book (1 contract per leg) and the
leverage it implies.  That is a decision, not something this script hides.
"""
from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from ten_cent_bot import overnight as ov
from ten_cent_bot import calendar_nyse as cal
from ten_cent_bot.contracts import CONTRACTS
from ten_cent_bot.orchestrator import drawdown_gate
from ten_cent_bot.risk import price_is_fresh, price_is_plausible
from ten_cent_bot.state import append_equity, load_equity_history

ROOT = Path(__file__).resolve().parents[1]
EQUITY_FILE = ROOT / "data" / "equity_history.csv"
BASKETS = {"e": ov.E_TICKERS, "e3": ov.E3_TICKERS}
FUT_MAP = {"SPY": ("MES", "ES=F", 10.0), "QQQ": ("MNQ", "NQ=F", 40.0), "IWM": ("M2K", "RTY=F", 10.0), "GLD": ("MGC", "GC=F", 10.0)}
#  (micro symbol, futures price ticker, approx ETF->futures price ratio used only as a fallback)


@dataclass
class Leg:
    etf: str
    multiplier: float
    rsi2: float
    marginal: bool
    target_notional: float
    instrument: str
    price: float
    unit_notional: float
    qty: int
    min_viable_qty: int


def plan_overnight(closes: dict[str, pd.Series], last_prices: dict[str, float], equity: float, basket: str, overlay: str,
                   rail: str, fut_prices: dict[str, float] | None = None, gross: float = 1.0) -> list[Leg]:
    cfg = ov.E_V2_CONFIG if overlay == "v2" else ov.OvernightConfig()
    tickers = BASKETS[basket]; n = len(tickers)
    legs = []
    for t in tickers:
        c = closes[t].copy()
        c.loc[pd.Timestamp.now(tz='UTC').tz_localize(None).normalize()] = last_prices[t]   # provisional close
        fire = bool(ov.reversal_signal(c, cfg).iloc[-1]) if cfg.reversal_signal != "none" else False
        r2 = float(ov.rsi(c, 2).iloc[-1])
        mult = cfg.reversal_multiplier if fire else 1.0
        marginal = cfg.reversal_signal != "none" and abs(r2 - cfg.reversal_rsi_threshold) <= 1.0
        target = equity * gross / n * mult
        if rail == "futures":
            sym, fut_tk, ratio = FUT_MAP[t]
            spec = CONTRACTS[sym]
            fp = (fut_prices or {}).get(fut_tk) or last_prices[t] * ratio
            unit = fp * spec.point_value
            qty = int(round(target / unit)); minq = int(math.ceil(mult))
            legs.append(Leg(t, mult, r2, marginal, target, sym, fp, unit, qty, minq))
        else:
            unit = last_prices[t]
            legs.append(Leg(t, mult, r2, marginal, target, t, unit, unit, int(target // unit), int(math.ceil(mult))))
    return legs


def ticket(legs: list[Leg], equity: float, basket: str, overlay: str, rail: str) -> str:
    lines = [f"Sleeve E{'3' if basket == 'e3' else ''}{' v2' if overlay == 'v2' else ''} overnight ticket  ({rail} rail)",
             f"As of:           {datetime.now(timezone.utc).astimezone().strftime('%Y-%m-%d %H:%M %Z')}",
             f"Account equity:  ${equity:,.2f}", "",
             f"{'ETF':>4} {'RSI2':>6} {'mult':>5}  {'instrument':<10} {'price':>10} {'unit $':>10} {'target $':>10} {'qty':>4}  note",
             "-" * 86]
    gross_t = 0.0; gross_min = 0.0
    for L in legs:
        note = "MARGINAL signal" if L.marginal else ("signal x%.1f" % L.multiplier if L.multiplier != 1 else "")
        if L.qty == 0:
            note = (note + " | " if note else "") + "rounds to 0 at this equity"
        lines.append(f"{L.etf:>4} {L.rsi2:>6.1f} {L.multiplier:>5.2f}  {L.instrument:<10} {L.price:>10,.2f} {L.unit_notional:>10,.0f} {L.target_notional:>10,.0f} {L.qty:>4}  {note}")
        gross_t += L.qty * L.unit_notional; gross_min += L.min_viable_qty * L.unit_notional
    lines += ["-" * 86,
              f"BUY at 16:00 ET (MOC / last 5-min print), SELL at 09:30 ET open.",
              f"Gross exposure of this ticket: ${gross_t:,.0f} = {gross_t/equity:.2f}x equity"]
    if any(L.qty == 0 for L in legs) and rail == "futures":
        lines += [f"!! At ${equity:,.0f} the target sizes round to zero on micro contracts.",
                  f"   Minimum viable book (1 contract per leg, x2 on signal legs): ${gross_min:,.0f} = {gross_min/equity:.2f}x equity.",
                  "   The audited sleeve is 1x. Trading the minimum book means running E at that leverage; decide explicitly."]
    return "\n".join(lines)


def fetch(tickers: list[str]) -> tuple[dict, dict, dict]:
    import yfinance as yf
    hist = yf.download(tickers, period="90d", interval="1d", auto_adjust=True, progress=False)["Close"]
    closes = {t: hist[t].dropna() for t in tickers}
    last = {}; last_time = {}
    for t in tickers:
        try:
            m1 = yf.Ticker(t).history(period="1d", interval="1m")
            last[t] = float(m1["Close"].iloc[-1]); last_time[t] = pd.Timestamp(m1.index[-1]).tz_convert("America/New_York").tz_localize(None)
        except Exception:
            last[t] = float(closes[t].iloc[-1]); last_time[t] = pd.Timestamp("1970-01-01")
    futs = {}
    for t in tickers:
        _, ft, _ = FUT_MAP[t]
        try:
            futs[ft] = float(yf.Ticker(ft).fast_info["last_price"])
        except Exception:
            pass
    # if today's close is already in history, don't double-append: drop it and let last_price stand in
    today = pd.Timestamp.now(tz='UTC').tz_localize(None).normalize()
    for t in tickers:
        closes[t].index = pd.to_datetime(closes[t].index).tz_localize(None).normalize()
        closes[t] = closes[t][closes[t].index < today]
    return closes, last, futs, last_time


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--equity", type=float, required=True)
    p.add_argument("--basket", choices=list(BASKETS), default="e3")
    p.add_argument("--overlay", choices=("none", "v2"), default="v2")
    p.add_argument("--rail", choices=("futures", "etf"), default="futures")
    p.add_argument("--gross", type=float, default=1.0, help="gross exposure target as a multiple of equity (audited: 1.0)")
    p.add_argument("--vol-scale", choices=("none", "vix"), default="none", help="size every leg by min(2, 20/VIX) using the latest VIX quote (screened 2026-11-04, off by default)")
    a = p.parse_args()
    closes, last, futs, last_time = fetch(BASKETS[a.basket])
    gross = a.gross
    if a.vol_scale == "vix":
        import yfinance as yf
        vix_now = float(yf.Ticker("^VIX").history(period="5d")["Close"].dropna().iloc[-1])
        vcfg = ov.OvernightConfig(vol_scale="vix")
        factor = float(ov.vol_scale_factor(pd.Series([vix_now]), vcfg).iloc[0])
        gross = a.gross * factor
        print(f"VIX {vix_now:.1f} -> vol-scale factor {factor:.2f}x (gross {a.gross:.2f} -> {gross:.2f}); total per-leg size still capped at {vcfg.vol_scale_cap}x by the reversal cap")
    legs = plan_overnight(closes, last, a.equity, a.basket, a.overlay, a.rail, futs, gross)
    txt = ticket(legs, a.equity, a.basket, a.overlay, a.rail)

    # ---- operating gates (fail closed) ------------------------------------
    today = datetime.now(timezone.utc).astimezone().date()
    blocks: list[str] = []; warns: list[str] = []
    if not cal.is_trading_day(today):
        blocks.append(f"{today} is not an NYSE trading day")
    elif cal.is_early_close(today):
        warns.append("EARLY CLOSE today (13:00 ET): the entry print is 13:00, run this at 12:50")
    now_et = pd.Timestamp.now(tz="America/New_York").tz_localize(None)
    for t in BASKETS[a.basket]:
        ok, why = price_is_fresh(last_time[t], now_et, 10)
        if not ok: blocks.append(f"{t}: {why}")
        ok, why = price_is_plausible(last[t], float(closes[t].iloc[-1]), 0.08)
        if not ok: blocks.append(f"{t}: {why}")
    hist = load_equity_history(EQUITY_FILE)
    allowed, why, alert = drawdown_gate(hist, alert_dd=0.15, stop_dd=0.25)
    if not allowed: blocks.append(why)
    elif alert: warns.append(alert)
    if hist is None or len(hist) < 2:
        warns.append("equity history is empty; drawdown gate starts working from the second run")
    append_equity(EQUITY_FILE, a.equity, today)

    print(txt)
    for w in warns: print(f"WARNING: {w}")
    if blocks:
        print("\n!! NO TRADE TONIGHT:"); [print(f"   - {b}") for b in blocks]
    out = ROOT / "data" / "last_overnight_ticket.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps({"generated": datetime.now(timezone.utc).isoformat(), "equity": a.equity, "basket": a.basket, "overlay": a.overlay, "rail": a.rail,
                               "legs": [L.__dict__ for L in legs], "blocked": blocks, "warnings": warns}, indent=2, default=float))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
