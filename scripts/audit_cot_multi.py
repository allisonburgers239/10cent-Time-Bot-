"""Stress-test the AMDX/COT framework across multiple instruments + signal
inversion, to check whether the initial NQ result was a wrong-instrument /
wrong-direction problem or a genuine no-edge result.

Two hypotheses being tested:
  H1: AMDX signal is inverse-informative (contrarian), so inverting sign helps.
  H2: The signal works on other financial futures where the COT literature
      is stronger (bonds, FX, other equity indices).
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import yfinance as yf

from ten_cent_bot import cot


# Financial futures available in the TFF report. Selected for variety of
# asset classes + liquidity + long yfinance history.
CONTRACTS = {
    "NASDAQ-100 Consolidated - CHICAGO MERCANTILE EXCHANGE": "NQ=F",
    "E-MINI S&P 500 - CHICAGO MERCANTILE EXCHANGE":          "ES=F",
    "RUSSELL 2000 MINI - CHICAGO MERCANTILE EXCHANGE":       "RTY=F",
    "DJIA x $5 - CHICAGO BOARD OF TRADE":                    "YM=F",
    "10-YEAR U.S. TREASURY NOTES - CHICAGO BOARD OF TRADE":  "ZN=F",
    "30-YEAR U.S. TREASURY BONDS - CHICAGO BOARD OF TRADE":  "ZB=F",
    "EURO FX - CHICAGO MERCANTILE EXCHANGE":                 "6E=F",
    "JAPANESE YEN - CHICAGO MERCANTILE EXCHANGE":            "6J=F",
}


def _s(ret):
    return cot.summary_from_returns(ret)


def run_instrument(cftc_name: str, yf_sym: str) -> dict | None:
    try:
        tff = cot.fetch_tff_history(contract=cftc_name)
    except Exception as e:
        return {"error": f"CFTC fetch failed: {e}"}
    if tff.empty:
        return {"error": "no COT data returned"}

    px = yf.download(yf_sym, period="max", interval="1wk", auto_adjust=True, progress=False)
    if isinstance(px.columns, pd.MultiIndex):
        px.columns = px.columns.get_level_values(0)
    if px.empty:
        return {"error": "no price data"}

    signals = cot.compute_amdx_signals(tff)
    combined = cot.align_to_weekly_price(signals, px)
    if combined.empty:
        return {"error": "alignment empty"}

    real_ret = cot.backtest(combined)["net_return"]
    real_stats = _s(real_ret)

    # Inverted: flip the sign of every signal (contrarian read)
    inv = combined.copy()
    inv["signal"] = -combined["signal"]
    inv_stats = _s(cot.backtest(inv)["net_return"])

    # Buy-and-hold benchmark on the same window
    bh_stats = _s(combined["weekly_return"].dropna())

    return {
        "weeks_total": len(combined),
        "weeks_active": int((combined["signal"] != 0).sum()),
        "real": real_stats,
        "inverted": inv_stats,
        "buyhold": bh_stats,
        "period": (combined.index.min().date(), combined.index.max().date()),
    }


def main() -> None:
    print("Running AMDX framework across 8 TFF financial futures + signal inversion")
    print("(direction fix + wrong-instrument hypotheses)\n")

    rows = []
    for cftc, yf_sym in CONTRACTS.items():
        short = yf_sym.replace("=F", "")
        print(f"  {short:>4} ...", end=" ", flush=True)
        res = run_instrument(cftc, yf_sym)
        if res is None or "error" in (res or {}):
            print(f"skip ({res.get('error', 'no result')})")
            continue
        rows.append({
            "sym": short,
            "period": f"{res['period'][0]} -> {res['period'][1]}",
            "weeks": res["weeks_total"],
            "active": res["weeks_active"],
            "real_sharpe": res["real"].get("sharpe", 0),
            "real_cagr": res["real"].get("cagr", 0),
            "inv_sharpe": res["inverted"].get("sharpe", 0),
            "inv_cagr": res["inverted"].get("cagr", 0),
            "bh_sharpe": res["buyhold"].get("sharpe", 0),
            "bh_cagr": res["buyhold"].get("cagr", 0),
        })
        print(f"real Sharpe {rows[-1]['real_sharpe']:>6.3f}, "
              f"inverted Sharpe {rows[-1]['inv_sharpe']:>6.3f}, "
              f"buy-hold Sharpe {rows[-1]['bh_sharpe']:>6.3f}")

    if not rows:
        print("No results.")
        return

    df = pd.DataFrame(rows)
    print("\n" + "=" * 78)
    print("Per-instrument summary:")
    print(df.to_string(index=False))

    print("\n=" + "=" * 77)
    print("Verdict scan:")
    real_wins  = (df["real_sharpe"] > df["bh_sharpe"]).sum()
    inv_wins   = (df["inv_sharpe"] > df["bh_sharpe"]).sum()
    real_pos   = (df["real_sharpe"] > 0).sum()
    inv_pos    = (df["inv_sharpe"] > 0).sum()
    print(f"  Instruments where REAL AMDX beats buy-and-hold:     {real_wins}/{len(df)}")
    print(f"  Instruments where INVERTED AMDX beats buy-and-hold: {inv_wins}/{len(df)}")
    print(f"  Instruments where REAL AMDX has positive Sharpe:    {real_pos}/{len(df)}")
    print(f"  Instruments where INVERTED AMDX has positive Sharpe:{inv_pos}/{len(df)}")

    # Which single instrument has the best real-signal Sharpe?
    best_real = df.loc[df["real_sharpe"].idxmax()]
    best_inv  = df.loc[df["inv_sharpe"].idxmax()]
    print(f"\n  Best REAL:      {best_real['sym']}  Sharpe {best_real['real_sharpe']:.3f}  "
          f"(vs buy-hold {best_real['bh_sharpe']:.3f})")
    print(f"  Best INVERTED:  {best_inv['sym']}   Sharpe {best_inv['inv_sharpe']:.3f}  "
          f"(vs buy-hold {best_inv['bh_sharpe']:.3f})")


if __name__ == "__main__":
    main()
