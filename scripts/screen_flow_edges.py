"""Flow-driven edge screen: four hypotheses where a dated, mechanical
institutional flow forces price-insensitive trading.

Rationale: every sleeve that survived audit (B, E, FOMC drift) has an
identifiable counterparty paying a premium for a structural reason;
every price-pattern claim failed. This screen only tests hypotheses
with a known flow mechanism:

  T1  Month-end pension rebalancing (Hartley-Schwarz 2019): when
      equities outrun bonds intramonth, pensions sell equity / buy
      bonds into month-end. CONDITIONAL signal, unlike plain TOM.
  T2  Treasury auction supply pressure (Lou-Yan-Zhang 2013, JF):
      dealers demand concession into scheduled 10y auctions; price
      recovers after. Dates from the TreasuryDirect API.
  T3  Post-crash short-term reversal: liquidity provision after
      forced-deleveraging days (buy close after a -2 sigma day).
  T4  OpEx-week / post-OpEx-week drift (Stivers-Sun): deterministic
      3rd-Friday option-hedging flows.

Each test: effect size, t-stat, halves, placebo. Screen only -
survivors get the full 7-section audit.

Usage: python scripts/screen_flow_edges.py
"""
from __future__ import annotations

import json
import urllib.request

import numpy as np
import pandas as pd
import yfinance as yf

ANN = 252


def sharpe(r: pd.Series) -> float:
    r = r.dropna()
    if len(r) < 20 or r.std() == 0:
        return float("nan")
    return float(r.mean() / r.std() * np.sqrt(ANN))


def dl(tkr: str, start: str = "1993-01-01") -> pd.DataFrame:
    d = yf.download(tkr, start=start, progress=False, auto_adjust=True)
    if isinstance(d.columns, pd.MultiIndex):
        d.columns = d.columns.get_level_values(0)
    return d


def tstat(v: pd.Series) -> float:
    v = v.dropna()
    return float(v.mean() / (v.std() / np.sqrt(len(v))))


# ------------------------------------------------------------------
def t1_month_end_rebalancing() -> None:
    print("=" * 68)
    print("T1  MONTH-END PENSION REBALANCING (SPY vs TLT, 2002-2026)")
    print("=" * 68)
    spy = dl("SPY", "2002-07-01")["Close"]
    tlt = dl("TLT", "2002-07-01")["Close"]
    px = pd.concat([spy.rename("SPY"), tlt.rename("TLT")], axis=1).dropna()
    r = px.pct_change()

    month = px.index.to_period("M")
    rows = []
    for _, g in px.groupby(month):
        if len(g) < 15:
            continue
        # signal: relative performance from month start through T-3
        sig_win = g.iloc[: len(g) - 2]
        rel = (sig_win["SPY"].iloc[-1] / sig_win["SPY"].iloc[0]
               - sig_win["TLT"].iloc[-1] / sig_win["TLT"].iloc[0])
        # trade window: last 2 trading days
        spy_le = g["SPY"].iloc[-1] / g["SPY"].iloc[-3] - 1
        tlt_le = g["TLT"].iloc[-1] / g["TLT"].iloc[-3] - 1
        rows.append({"rel": rel, "spy_le": spy_le, "tlt_le": tlt_le,
                     "spread": tlt_le - spy_le, "month": g.index[-1]})
    df = pd.DataFrame(rows).set_index("month")

    hi = df[df["rel"] > df["rel"].quantile(2 / 3)]   # equities ran hard
    lo = df[df["rel"] < df["rel"].quantile(1 / 3)]   # bonds ran hard
    print(f"  {len(df)} months. Signal = SPY-TLT relative return, day 1 -> T-3.")
    print(f"  After equity outperformance (top tercile, n={len(hi)}):")
    print(f"    last-2-day TLT-SPY spread: {hi['spread'].mean()*1e4:+6.1f}bp  t={tstat(hi['spread']):+.2f}")
    print(f"  After bond outperformance (bottom tercile, n={len(lo)}):")
    print(f"    last-2-day TLT-SPY spread: {lo['spread'].mean()*1e4:+6.1f}bp  t={tstat(lo['spread']):+.2f}")

    # strategy: hold the rebalancing-flow side for the last 2 days each month
    strat = np.where(df["rel"] > 0, df["spread"], -df["spread"])
    strat = pd.Series(strat, index=df.index) - 0.0004  # 2bp/side x 2 legs
    h = len(strat) // 2
    print(f"  Sign-following L/S strategy (12x2 days/yr, net 4bp/rt):")
    print(f"    mean {strat.mean()*1e4:+.1f}bp/month-end  t={tstat(strat):+.2f}  "
          f"halves t: {tstat(strat.iloc[:h]):+.2f} / {tstat(strat.iloc[h:]):+.2f}")
    # placebo: random 2-day windows mid-month with same conditioning
    rng = np.random.default_rng(0)
    plc = []
    months = list(px.groupby(month))
    for _ in range(200):
        vals = []
        for _, g in months:
            if len(g) < 15:
                continue
            k = rng.integers(4, len(g) - 4)
            sig_win = g.iloc[:k - 1]
            rel = (sig_win["SPY"].iloc[-1] / sig_win["SPY"].iloc[0]
                   - sig_win["TLT"].iloc[-1] / sig_win["TLT"].iloc[0])
            spread = ((g["TLT"].iloc[k + 1] / g["TLT"].iloc[k - 1] - 1)
                      - (g["SPY"].iloc[k + 1] / g["SPY"].iloc[k - 1] - 1))
            vals.append(spread if rel > 0 else -spread)
        plc.append(np.mean(vals) * 1e4 - 4)
    plc = np.array(plc)
    real = strat.mean() * 1e4
    print(f"    placebo (random 2-day windows, same conditioning): "
          f"{plc.mean():+.1f} +/- {plc.std():.1f}bp,  P(rand >= real) = {(plc >= real).mean():.3f}")


# ------------------------------------------------------------------
def t2_auction_pressure() -> None:
    print("\n" + "=" * 68)
    print("T2  10Y TREASURY AUCTION SUPPLY PRESSURE (IEF, 2002-2026)")
    print("=" * 68)
    url = ("https://www.treasurydirect.gov/TA_WS/securities/search"
           "?type=Note&format=json&days=9000")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    rows = json.loads(urllib.request.urlopen(req, timeout=60).read())
    tens = sorted({r["auctionDate"][:10] for r in rows
                   if r.get("securityTerm", "").startswith(("10-", "9-Year"))
                   and r.get("auctionDate")})
    auc = pd.DatetimeIndex(tens)
    auc = auc[auc >= "2002-08-01"]
    print(f"  {len(auc)} 10y auctions (incl. reopenings)")

    ief = dl("IEF", "2002-08-01")["Close"]
    r = ief.pct_change().dropna()
    idx = r.index
    pos = idx.searchsorted(auc)
    pos = np.unique(pos[(pos > 3) & (pos < len(idx) - 4)])
    on_day = idx[pos].intersection(auc)  # only exact matches
    pos = idx.searchsorted(on_day)

    windows = {"t-3": -3, "t-2": -2, "t-1": -1, "auction day": 0,
               "t+1": 1, "t+2": 2, "t+3": 3}
    print(f"  IEF mean daily return by day relative to auction "
          f"(uncond {r.mean()*1e4:.1f}bp):")
    for name, k in windows.items():
        v = r.iloc[pos + k]
        print(f"    {name:<12} {v.mean()*1e4:+5.1f}bp  t={tstat(v):+5.2f}  n={len(v)}")

    # strategy: short IEF t-3->t-1 close? long t0 close -> t+3?
    pre = pd.Series(ief.values[pos - 1] / ief.values[pos - 4] - 1, index=idx[pos])
    post = pd.Series(ief.values[pos + 3] / ief.values[pos] - 1, index=idx[pos])
    print(f"  Pre-auction window (t-3 close -> t-1 close): "
          f"{pre.mean()*1e4:+.1f}bp  t={tstat(pre):+.2f}")
    print(f"  Post-auction window (t0 close -> t+3 close): "
          f"{post.mean()*1e4:+.1f}bp  t={tstat(post):+.2f}")
    strat = post - pre  # long recovery, short concession
    h = len(strat) // 2
    print(f"  Combined (short pre / long post): {strat.mean()*1e4:+.1f}bp per auction  "
          f"t={tstat(strat):+.2f}  halves t: {tstat(strat.iloc[:h]):+.2f} / {tstat(strat.iloc[h:]):+.2f}")
    rng = np.random.default_rng(0)
    plc = []
    for _ in range(300):
        rp = rng.choice(np.arange(4, len(idx) - 4), size=len(pos), replace=False)
        p_ = (ief.values[rp + 3] / ief.values[rp] - 1) - (ief.values[rp - 1] / ief.values[rp - 4] - 1)
        plc.append(p_.mean() * 1e4)
    plc = np.array(plc)
    real = strat.mean() * 1e4
    print(f"  placebo (random dates): {plc.mean():+.1f} +/- {plc.std():.1f}bp, "
          f"P(rand >= real) = {(plc >= real).mean():.3f}")


# ------------------------------------------------------------------
def t3_post_crash_reversal() -> None:
    print("\n" + "=" * 68)
    print("T3  POST-CRASH SHORT-TERM REVERSAL (SPY, 1993-2026)")
    print("=" * 68)
    spy = dl("SPY")["Close"]
    r = spy.pct_change().dropna()
    vol = r.rolling(60).std()
    z = (r / vol.shift(1)).dropna()

    for thresh in (-2.0, -2.5, -3.0):
        sig_days = z[z < thresh].index
        # position in SPY price series of the signal day's close
        pos = spy.index.searchsorted(sig_days)
        pos = pos[pos < len(spy) - 4]
        fwd3 = pd.Series([(spy.iloc[p + 3] / spy.iloc[p] - 1) for p in pos],
                         index=spy.index[pos])
        print(f"  z < {thresh}: n={len(fwd3):>3}  fwd-3d {fwd3.mean()*1e4:+6.1f}bp "
              f" t={tstat(fwd3):+5.2f}  win {(fwd3>0).mean()*100:.0f}%"
              f"  (uncond 3d: {r.mean()*3*1e4:.1f}bp)")

    # era split for the -2 threshold (reversal is regime-dependent)
    sig_days = z[z < -2.0].index
    pos = spy.index.searchsorted(sig_days)
    pos = pos[pos < len(spy) - 4]
    fwd3 = pd.Series([(spy.iloc[p + 3] / spy.iloc[p] - 1) for p in pos],
                     index=spy.index[pos])
    for era in [(1993, 2002), (2003, 2012), (2013, 2019), (2020, 2026)]:
        m = fwd3[(fwd3.index.year >= era[0]) & (fwd3.index.year <= era[1])]
        if len(m) > 5:
            print(f"    {era[0]}-{era[1]}: {m.mean()*1e4:+6.1f}bp  t={tstat(m):+5.2f}  n={len(m)}")
    rng = np.random.default_rng(0)
    plc = []
    for _ in range(300):
        rp = rng.choice(np.arange(0, len(r) - 4), size=len(pos), replace=False)
        plc.append(np.mean([(spy.iloc[p + 3] / spy.iloc[p] - 1) for p in rp]) * 1e4)
    plc = np.array(plc)
    real = fwd3.mean() * 1e4
    print(f"  placebo (random days): {plc.mean():+.1f} +/- {plc.std():.1f}bp, "
          f"P(rand >= real) = {(plc >= real).mean():.3f}")


# ------------------------------------------------------------------
def t4_opex() -> None:
    print("\n" + "=" * 68)
    print("T4  OPEX WEEK / POST-OPEX WEEK (SPY, 1993-2026)")
    print("=" * 68)
    spy = dl("SPY")["Close"]
    r = spy.pct_change().dropna()
    # third Friday of each month
    idx = r.index
    third_fri = []
    for (_, _), g in r.groupby([idx.year, idx.month]):
        fridays = g.index[g.index.dayofweek == 4]
        if len(fridays) >= 3:
            third_fri.append(fridays[2])
    tf = pd.DatetimeIndex(third_fri)
    pos = idx.searchsorted(tf)
    pos = pos[(pos > 5) & (pos < len(idx) - 6)]

    opex_wk = pd.Series([spy.iloc[p] / spy.iloc[p - 5] - 1 for p in pos], index=idx[pos])
    post_wk = pd.Series([spy.iloc[p + 5] / spy.iloc[p] - 1 for p in pos], index=idx[pos])
    uncond_wk = r.mean() * 5 * 1e4
    print(f"  {len(pos)} expirations. Unconditional 5d return: {uncond_wk:+.1f}bp")
    for name, v in [("OpEx week (t-5 -> 3rd Fri)", opex_wk),
                    ("post-OpEx week (Fri -> t+5)", post_wk)]:
        h = len(v) // 2
        print(f"  {name:<28} {v.mean()*1e4:+6.1f}bp  t={tstat(v):+5.2f}  "
              f"halves: {v.iloc[:h].mean()*1e4:+.1f} / {v.iloc[h:].mean()*1e4:+.1f}bp")
    diff = opex_wk - post_wk
    print(f"  OpEx-minus-post spread: {diff.mean()*1e4:+.1f}bp  t={tstat(diff):+.2f}")


def main() -> None:
    t1_month_end_rebalancing()
    t2_auction_pressure()
    t3_post_crash_reversal()
    t4_opex()


if __name__ == "__main__":
    main()
