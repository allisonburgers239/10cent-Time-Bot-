"""Screen: where else does the overnight premium (Sleeve E's edge) live?

Overnight (prev close -> open) vs intraday (open -> close) decomposition on
US-listed ETFs across asset classes, same hygiene as screen_overnight_global
(drop years with >5% fake opens), placebo = random nightly sign.

Pre-registered groups for the audit that follows (fixed before looking):
  E        SPY QQQ IWM                       (deployed)
  E+intl   + EFA EEM                         (foreign day session rides inside the US overnight)
  E+gold   + GLD                             (gold's known off-NY-hours drift; MGC on Tradovate)
  E+bonds  + TLT                             (ZB/UB on Tradovate)
  E-multi  SPY QQQ IWM EFA EEM GLD TLT
Each group vs E: Sharpe, MaxDD, correlation, both halves, placebo.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import yfinance as yf

from ten_cent_bot.metrics import max_drawdown, sharpe

UNIVERSE = {
    "SPY": "US large", "QQQ": "US tech", "IWM": "US small", "DIA": "US Dow", "MDY": "US mid",
    "EFA": "Developed ex-US", "EEM": "Emerging", "EWJ": "Japan", "FXI": "China", "EWZ": "Brazil", "VGK": "Europe", "EWY": "Korea", "INDA": "India",
    "TLT": "20y Treasury", "IEF": "7-10y Treasury", "HYG": "High yield", "LQD": "IG credit", "TIP": "TIPS",
    "GLD": "Gold", "SLV": "Silver", "USO": "Oil", "UNG": "Nat gas", "DBC": "Commodities", "DBA": "Agriculture",
    "XLE": "Energy", "XLF": "Financials", "XLK": "Tech", "XLU": "Utilities", "XLV": "Health", "VNQ": "REITs", "UUP": "Dollar",
}
GROUPS = {"E": ["SPY", "QQQ", "IWM"], "E+intl": ["SPY", "QQQ", "IWM", "EFA", "EEM"], "E+gold": ["SPY", "QQQ", "IWM", "GLD"],
          "E+bonds": ["SPY", "QQQ", "IWM", "TLT"], "E-multi": ["SPY", "QQQ", "IWM", "EFA", "EEM", "GLD", "TLT"],
          "gold alone": ["GLD"], "intl alone": ["EFA", "EEM"], "bonds alone": ["TLT"]}


def clean(df):
    stale = (df["open"] == df["close"].shift(1)) | (df["open"] == df["close"])
    by = stale.groupby(df.index.year).mean(); bad = by[by >= 0.05].index.tolist()
    cutoff = max(bad) + 1 if bad else df.index.year.min()
    return df[df.index.year >= cutoff]


def main():
    rng = np.random.default_rng(9)
    data = yf.download(list(UNIVERSE), period="max", interval="1d", auto_adjust=True, progress=False)
    on = {}; idr = {}
    print("=== Overnight vs intraday, US-listed ETFs (clean-open years), 1bp/side cost on the overnight leg ===")
    print(f"{'ETF':<5} {'what':<16} {'from':>5} {'n':>6} {'ON Sharpe':>9} {'ID Sharpe':>9} {'B&H':>6} {'ON CAGR':>8} {'ID CAGR':>8} {'placebo p':>9}")
    for tk, what in UNIVERSE.items():
        df = pd.DataFrame({"open": data["Open"][tk], "close": data["Close"][tk]}).dropna()
        df = df[(df > 0).all(axis=1)]; df.index = pd.to_datetime(df.index).tz_localize(None); df = clean(df)
        if len(df) < 1000:
            print(f"{tk:<5} {what:<16} too short / unusable opens"); continue
        o = (df["open"].shift(-1) / df["close"] - 1 - 2 / 1e4).dropna(); i = (df["close"] / df["open"] - 1).dropna(); bh = df["close"].pct_change().dropna()
        on[tk] = o; idr[tk] = i
        pl = np.array([sharpe(o * rng.choice([-1.0, 1.0], len(o)), 252) for _ in range(200)]); p = float((pl >= sharpe(o, 252)).mean())
        print(f"{tk:<5} {what:<16} {df.index.year.min():>5} {len(o):>6} {sharpe(o,252):>9.2f} {sharpe(i,252):>9.2f} {sharpe(bh,252):>6.2f} {((1+o.mean())**252-1):>8.1%} {((1+i.mean())**252-1):>8.1%} {p:>9.3f}")

    print("\n=== Pre-registered groups vs E (equal-weight overnight, 1bp/side), common window ===")
    on_df = pd.DataFrame(on)
    print(f"{'group':<12} {'window':>22} {'Sharpe':>7} {'CAGR':>7} {'MaxDD':>7} {'halves':>11} {'corr w/ E':>9}")
    e_full = on_df[["SPY", "QQQ", "IWM"]].dropna().mean(axis=1)
    for g, tks in GROUPS.items():
        sub = on_df[tks].dropna(); port = sub.mean(axis=1); e = e_full.reindex(port.index)
        h = len(port) // 2; eq = (1 + port).cumprod()
        print(f"{g:<12} {str(port.index.min().date())+'..'+str(port.index.max().date()):>22} {sharpe(port,252):>7.2f} {((1+port.mean())**252-1):>7.1%} {max_drawdown(eq):>7.1%} {sharpe(port.iloc[:h],252):>5.2f}/{sharpe(port.iloc[h:],252):<5.2f} {port.corr(e):>9.2f}")
    print("  (E on the same window as each group is the fair comparison; E's own number shifts with the window)")
    for g in ["E+intl", "E+gold", "E+bonds", "E-multi"]:
        sub = on_df[GROUPS[g]].dropna(); port = sub.mean(axis=1); e = on_df.loc[port.index, ["SPY", "QQQ", "IWM"]].mean(axis=1)
        print(f"  {g:<9} window: E {sharpe(e,252):.2f} / {max_drawdown((1+e).cumprod()):.1%}   ->   {g} {sharpe(port,252):.2f} / {max_drawdown((1+port).cumprod()):.1%}")


if __name__ == "__main__":
    main()
