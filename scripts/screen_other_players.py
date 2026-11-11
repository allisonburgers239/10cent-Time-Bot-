"""Play the other players: who is FORCED to trade at a known time, in a known direction? (2026-11-11)

  1  PENSIONS - quarter-end rebalancing between stocks and bonds. After a quarter in which stocks beat
     bonds by a lot, pensions must sell stocks / buy bonds in the last sessions (and the reverse after a
     stock crash). Test: SPY minus TLT over the last 5 sessions of each quarter, conditional on the
     quarter-to-date spread measured 5 sessions before the end; the first 5 sessions of the next quarter
     for the rebound. Daily 2002- (TLT starts 2002-07). Control: the same test at random 5-day windows
     inside the quarter, and monthly ends.
  2  INDEX FUNDS - S&P 500 additions and deletions (Wikipedia 'Historical components', effective dates +
     reasons). Index funds trade at the close before the effective date. Test, market-adjusted vs SPY:
     run-up/run-down from 6 sessions before to the close before (the forced flow), then the
     5/20/60-session reversal after. Deletions limited to 'market capitalization' reasons (the forced
     sells); acquisitions excluded. Only still-listed names have prices, so the deletion bounce is
     biased UP by the firms that survived - stated, and the short 5-day window limits it.
  3  FUND MANAGERS - window dressing. In the last 3 sessions of a quarter the quarter's winners are
     bought and losers sold; first 3 sessions of the new quarter undo it. Long top-decile / short
     bottom-decile by quarter-to-date return (ranked 4 sessions before the end), on today's 428
     survivors AND the 119 fallen names (same answer in both = not survivorship). Placebo: the same
     long-short at random 3-day windows mid-quarter.
All costed (1 bp/side ETFs, 2 bp/side stocks), halves, t-stats, by year where it matters.
"""
from __future__ import annotations

import pickle
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

ROOT = Path(__file__).resolve().parent.parent
DIR = ROOT / "data" / "earnings"
RNG = np.random.default_rng(3)


def tstat(x) -> float:
    x = pd.Series(x).dropna()
    return float(x.mean() / x.std() * np.sqrt(len(x))) if len(x) > 2 and x.std() > 0 else 0.0


def halves(x) -> str:
    x = pd.Series(x).dropna(); h = len(x) // 2
    return f"{x.iloc[:h].mean() * 1e4:+.0f}/{x.iloc[h:].mean() * 1e4:+.0f}bp"


def row(label, x, cost=0.0):
    x = pd.Series(x).dropna() - cost
    print(f"  {label:70s} n {len(x):4d}  mean {x.mean() * 1e4:+6.0f}bp  hit {(x > 0).mean():.2f}  t {tstat(x):+4.1f}  halves {halves(x)}")


def quarter_ends(idx: pd.DatetimeIndex) -> np.ndarray:
    q = pd.Series(idx.to_period("Q"), index=idx)
    return np.flatnonzero((q != q.shift(-1)).to_numpy())[:-1]  # positional index of each quarter's last session (drop the live quarter)


def section_1(spy: pd.Series, tlt: pd.Series) -> None:
    print("=== 1. PENSIONS: quarter-end stock/bond rebalancing (SPY vs TLT, 2002-07 ->) ===")
    df = pd.DataFrame({"spy": spy, "tlt": tlt}).dropna()
    qe = quarter_ends(df.index)
    rows = []
    for e in qe:
        s = np.flatnonzero(df.index.to_period("Q") == df.index[e].to_period("Q"))[0]  # first session of the quarter
        if e - 5 <= s or e + 5 >= len(df):
            continue
        qtd = (df.spy.iloc[e - 5] / df.spy.iloc[s - 1] - 1) - (df.tlt.iloc[e - 5] / df.tlt.iloc[s - 1] - 1)
        last5 = (df.spy.iloc[e] / df.spy.iloc[e - 5] - 1) - (df.tlt.iloc[e] / df.tlt.iloc[e - 5] - 1)
        next5 = (df.spy.iloc[e + 5] / df.spy.iloc[e] - 1) - (df.tlt.iloc[e + 5] / df.tlt.iloc[e] - 1)
        spy_last5 = df.spy.iloc[e] / df.spy.iloc[e - 5] - 1
        rows.append((df.index[e], qtd, last5, next5, spy_last5))
    t = pd.DataFrame(rows, columns=["qend", "qtd_spread", "last5_spread", "next5_spread", "spy_last5"]).set_index("qend")
    print(f"  {len(t)} quarters; corr(QTD stock-bond spread, last-5-session spread) = {t.qtd_spread.corr(t.last5_spread):+.2f}; corr with next-5 = {t.qtd_spread.corr(t.next5_spread):+.2f}")
    for lo, hi, lab in ((-9, -0.05, "stocks LAGGED bonds by >5% QTD (pensions must buy stocks)"), (-0.05, 0.05, "spread within +-5%"), (0.05, 9, "stocks BEAT bonds by >5% QTD (pensions must sell stocks)")):
        m = (t.qtd_spread > lo) & (t.qtd_spread <= hi)
        row(f"   {lab}: last 5 sessions SPY-TLT", t.last5_spread[m])
        row(f"      ... SPY alone, last 5 sessions", t.spy_last5[m])
        row(f"      ... first 5 sessions of the next quarter SPY-TLT", t.next5_spread[m])
    # the trade: short SPY / long TLT when spread > +5%, long SPY / short TLT when < -5%, last 5 sessions, 1bp/side x 2 legs
    sig = np.where(t.qtd_spread > 0.05, -1, np.where(t.qtd_spread < -0.05, 1, 0))
    trade = pd.Series(sig * t.last5_spread.to_numpy(), index=t.index); trade = trade[sig != 0]
    row("   TRADE: fade the forced flow (pair, last 5 sessions), 1bp/side x 4 legs", trade, 4e-4)
    print("   by year: " + " ".join(f"{y}:{v * 1e4:+.0f}" for y, v in trade.groupby(trade.index.year).sum().items()))
    # control: same conditioning, random 5-session windows NOT at the quarter end
    fake = []
    for _ in range(500):
        vals = []
        for e in qe:
            s = np.flatnonzero(df.index.to_period("Q") == df.index[e].to_period("Q"))[0]
            if e - 25 <= s + 5:
                continue
            k = RNG.integers(s + 10, e - 15)  # a window ending mid-quarter
            qtd = (df.spy.iloc[k - 5] / df.spy.iloc[s - 1] - 1) - (df.tlt.iloc[k - 5] / df.tlt.iloc[s - 1] - 1)
            l5 = (df.spy.iloc[k] / df.spy.iloc[k - 5] - 1) - (df.tlt.iloc[k] / df.tlt.iloc[k - 5] - 1)
            sg = -1 if qtd > 0.05 else (1 if qtd < -0.05 else 0)
            if sg: vals.append(sg * l5)
        fake.append(np.mean(vals) if vals else np.nan)
    fake = np.array(fake)
    print(f"   placebo (same rule at random mid-quarter windows): mean {np.nanmean(fake) * 1e4:+.0f}bp, p(placebo >= real {trade.mean() * 1e4 + 4:+.0f}bp gross) = {np.nanmean(fake >= trade.mean() + 4e-4):.2f}")
    # month-ends, same logic, threshold 3%
    me = np.flatnonzero((pd.Series(df.index.to_period('M'), index=df.index) != pd.Series(df.index.to_period('M'), index=df.index).shift(-1)).to_numpy())[:-1]
    vals = []
    for e in me:
        s = np.flatnonzero(df.index.to_period("M") == df.index[e].to_period("M"))[0]
        if e - 3 <= s: continue
        mtd = (df.spy.iloc[e - 3] / df.spy.iloc[s - 1] - 1) - (df.tlt.iloc[e - 3] / df.tlt.iloc[s - 1] - 1)
        l3 = (df.spy.iloc[e] / df.spy.iloc[e - 3] - 1) - (df.tlt.iloc[e] / df.tlt.iloc[e - 3] - 1)
        sg = -1 if mtd > 0.03 else (1 if mtd < -0.03 else 0)
        if sg: vals.append(sg * l3)
    real_m = pd.Series(vals)
    row("   month-end version (|MTD spread| > 3%, last 3 sessions), 4 legs", real_m, 4e-4)
    fake = []
    for _ in range(500):
        v = []
        for e in me:
            s = np.flatnonzero(df.index.to_period("M") == df.index[e].to_period("M"))[0]
            if e - 10 <= s + 4: continue
            k = RNG.integers(s + 6, e - 4)
            mtd = (df.spy.iloc[k - 3] / df.spy.iloc[s - 1] - 1) - (df.tlt.iloc[k - 3] / df.tlt.iloc[s - 1] - 1)
            l3 = (df.spy.iloc[k] / df.spy.iloc[k - 3] - 1) - (df.tlt.iloc[k] / df.tlt.iloc[k - 3] - 1)
            sg = -1 if mtd > 0.03 else (1 if mtd < -0.03 else 0)
            if sg: v.append(sg * l3)
        fake.append(np.mean(v))
    fake = np.array(fake)
    print(f"   placebo (same rule, random mid-month 3-session windows): mean {fake.mean() * 1e4:+.0f}bp, p(placebo >= real {real_m.mean() * 1e4:+.0f}bp gross) = {(fake >= real_m.mean()).mean():.2f}")
    def month_rule(thr, L, start=None, end=None):
        v = []
        for e in me:
            s0 = np.flatnonzero(df.index.to_period("M") == df.index[e].to_period("M"))[0]
            if e - L <= s0: continue
            if start and df.index[e] < pd.Timestamp(start): continue
            if end and df.index[e] >= pd.Timestamp(end): continue
            mtd = (df.spy.iloc[e - L] / df.spy.iloc[s0 - 1] - 1) - (df.tlt.iloc[e - L] / df.tlt.iloc[s0 - 1] - 1)
            lL = (df.spy.iloc[e] / df.spy.iloc[e - L] - 1) - (df.tlt.iloc[e] / df.tlt.iloc[e - L] - 1)
            sg = -1 if mtd > thr else (1 if mtd < -thr else 0)
            if sg: v.append(sg * lL - 4e-4)
        return pd.Series(v)
    print("   month-end grid (threshold x last-L sessions): mean bp net / t / n")
    for thr in (0.02, 0.03, 0.04, 0.05):
        print(f"     |MTD| > {thr:.0%}: " + " | ".join(f"L={L}: {month_rule(thr, L).mean() * 1e4:+.0f}bp t{tstat(month_rule(thr, L)):+.1f} n{len(month_rule(thr, L))}" for L in (2, 3, 5)))
    best = max(((thr, L) for thr in (0.02, 0.03, 0.04, 0.05) for L in (2, 3, 5)), key=lambda c: tstat(month_rule(*c, end="2014-01-01")))
    print(f"   walk-forward: best cell on 2002-2013 = thr {best[0]:.0%}, L={best[1]} (train t {tstat(month_rule(*best, end='2014-01-01')):+.1f}); TEST 2014-2026: {month_rule(*best, start='2014-01-01').mean() * 1e4:+.0f}bp t{tstat(month_rule(*best, start='2014-01-01')):+.1f} n{len(month_rule(*best, start='2014-01-01'))} | the 3%/3 cell on test: {month_rule(0.03, 3, start='2014-01-01').mean() * 1e4:+.0f}bp t{tstat(month_rule(0.03, 3, start='2014-01-01')):+.1f}")
    unc = []; side = {1: [], -1: []}
    for e in me:
        s0 = np.flatnonzero(df.index.to_period("M") == df.index[e].to_period("M"))[0]
        if e - 5 <= s0: continue
        l5 = (df.spy.iloc[e] / df.spy.iloc[e - 5] - 1) - (df.tlt.iloc[e] / df.tlt.iloc[e - 5] - 1); unc.append(l5)
        mtd = (df.spy.iloc[e - 5] / df.spy.iloc[s0 - 1] - 1) - (df.tlt.iloc[e - 5] / df.tlt.iloc[s0 - 1] - 1)
        if mtd > 0.03: side[-1].append(-l5 - 4e-4)
        elif mtd < -0.03: side[1].append(l5 - 4e-4)
    row("   UNCONDITIONAL last 5 sessions of every month, SPY minus TLT (no signal)", pd.Series(unc))
    row("   side -1 only: stocks beat bonds MTD -> short SPY / long TLT last 5", pd.Series(side[-1]), 0)
    row("   side +1 only: stocks lagged bonds MTD -> long SPY / short TLT last 5", pd.Series(side[1]), 0)
    fake5 = []
    for _ in range(500):
        v = []
        for e in me:
            s0 = np.flatnonzero(df.index.to_period("M") == df.index[e].to_period("M"))[0]
            if e - 12 <= s0 + 6: continue
            k = RNG.integers(s0 + 8, e - 6)
            mtd = (df.spy.iloc[k - 5] / df.spy.iloc[s0 - 1] - 1) - (df.tlt.iloc[k - 5] / df.tlt.iloc[s0 - 1] - 1)
            l5 = (df.spy.iloc[k] / df.spy.iloc[k - 5] - 1) - (df.tlt.iloc[k] / df.tlt.iloc[k - 5] - 1)
            sg = -1 if mtd > 0.03 else (1 if mtd < -0.03 else 0)
            if sg: v.append(sg * l5)
        fake5.append(np.mean(v))
    r35 = month_rule(0.03, 5)
    print(f"   placebo for the 3%/L=5 cell (random mid-month 5-session windows, same rule): mean {np.mean(fake5) * 1e4:+.0f}bp, p(placebo >= real {r35.mean() * 1e4 + 4:+.0f}bp gross) = {np.mean(np.array(fake5) >= r35.mean() + 4e-4):.2f}")
    print("   month-end by year: " + " ".join(f"{y}:{v * 1e4:+.0f}" for y, v in pd.Series(vals, index=[df.index[e] for e in me if e - 3 > np.flatnonzero(df.index.to_period("M") == df.index[e].to_period("M"))[0] and abs((df.spy.iloc[e - 3] / df.spy.iloc[np.flatnonzero(df.index.to_period("M") == df.index[e].to_period("M"))[0] - 1] - 1) - (df.tlt.iloc[e - 3] / df.tlt.iloc[np.flatnonzero(df.index.to_period("M") == df.index[e].to_period("M"))[0] - 1] - 1)) > 0.03]).groupby(lambda d: d.year).sum().items()))


def section_2(px: dict, pxf: dict) -> None:
    print("\n=== 2. INDEX FUNDS: S&P 500 additions and deletions, market-adjusted vs SPY ===")
    ch = pd.read_csv(DIR / "sp500_changes.csv", parse_dates=["date"])
    ch = ch[ch.date >= "2002-01-01"]
    o = pd.concat([px["open"], pxf["open"].drop(columns="SPY")], axis=1); c = pd.concat([px["close"], pxf["close"].drop(columns="SPY")], axis=1)
    c = c.loc[:, ~c.columns.duplicated()]; o = o.loc[:, ~o.columns.duplicated()]
    cal = c.index
    def windows(tickers_dates, label):
        out = []
        for t, d in tickers_dates:
            if t not in c.columns: continue
            e = cal.searchsorted(d) - 1   # the close BEFORE the effective date = the index funds' trade
            if e < 7 or e + 61 >= len(cal) or pd.isna(c[t].iloc[e - 6]) or pd.isna(c[t].iloc[e]) or pd.isna(c[t].iloc[e + 60]): continue
            def r(a, b, s=t): return c[s].iloc[b] / c[s].iloc[a] - 1
            out.append({"ticker": t, "date": cal[e], "pre6": r(e - 6, e) - r(e - 6, e, "SPY"), "post5": r(e, e + 5) - r(e, e + 5, "SPY"), "post20": r(e, e + 20) - r(e, e + 20, "SPY"), "post60": r(e, e + 60) - r(e, e + 60, "SPY"), "lastday": r(e - 1, e) - r(e - 1, e, "SPY")})
        w = pd.DataFrame(out)
        print(f"  {label}: {len(w)} events with prices (of {len(tickers_dates)} in the table)")
        if w.empty: return w
        row("   6 sessions before -> close before effective (the forced flow)", w.pre6, 4e-4)
        row("   the last session alone (the day index funds trade at the close)", w.lastday, 4e-4)
        row("   close before effective -> +5 sessions (reversal?)", w.post5, 4e-4)
        row("   -> +20 sessions", w.post20, 4e-4)
        row("   -> +60 sessions", w.post60, 4e-4)
        print("   by year (pre6 / post20): " + " ".join(f"{y}:{a * 1e4:+.0f}/{b * 1e4:+.0f}" for (y, a), (_, b) in zip(w.groupby(w.date.dt.year).pre6.mean().items(), w.groupby(w.date.dt.year).post20.mean().items())))
        return w
    adds = [(str(t), d) for t, d in zip(ch.added, ch.date) if isinstance(t, str) and t != "nan"]
    rem_mc = [(str(t), d) for t, d, r in zip(ch.removed, ch.date, ch.reason.fillna("").astype(str)) if isinstance(t, str) and t != "nan" and "apitalization" in r]
    rem_all = [(str(t), d) for t, d in zip(ch.removed, ch.date) if isinstance(t, str) and t != "nan"]
    wa = windows(adds, "ADDITIONS")
    windows([(t, cal[RNG.integers(cal.searchsorted(pd.Timestamp("2005-01-01")), len(cal) - 100)]) for t, _ in adds for _ in range(3)], "   placebo: the ADDED tickers on random dates 2005-")
    wd = windows(rem_mc, "DELETIONS for 'market capitalization' (the forced sells; survivors only -> bounce biased up)")
    windows([(t, cal[RNG.integers(cal.searchsorted(pd.Timestamp("2005-01-01")), len(cal) - 100)]) for t, _ in rem_mc for _ in range(3)], "   placebo: the DELETED tickers on random dates 2005-")
    windows(rem_all, "DELETIONS, all reasons")
    # day-by-day profile around the effective date (market-adjusted daily return, mean over events)
    for w, lab in ((wa, "ADDITIONS"), (wd, "DELETIONS (market cap)")):
        prof = {}
        for k in range(-10, 11):
            vals = []
            for t, d in zip(w.ticker, w.date):
                e = cal.get_loc(d) + k
                if 0 < e < len(cal) and not pd.isna(c[t].iloc[e]) and not pd.isna(c[t].iloc[e - 1]):
                    vals.append((c[t].iloc[e] / c[t].iloc[e - 1] - 1) - (c["SPY"].iloc[e] / c["SPY"].iloc[e - 1] - 1))
            prof[k] = (np.mean(vals), tstat(vals))
        print(f"  {lab} day-by-day (0 = the close before the effective date): " + " ".join(f"{k:+d}:{m * 1e4:+.0f}{'*' if abs(t_) > 2 else ''}" for k, (m, t_) in prof.items()))
    def win(w, a, b, label):
        vals = []
        for t, d in zip(w.ticker, w.date):
            e = cal.get_loc(d)
            if e + a < 0 or e + b >= len(cal) or pd.isna(c[t].iloc[e + a]) or pd.isna(c[t].iloc[e + b]): continue
            vals.append((c[t].iloc[e + b] / c[t].iloc[e + a] - 1) - (c["SPY"].iloc[e + b] / c["SPY"].iloc[e + a] - 1))
        v = pd.Series(vals, index=[d for t, d in zip(w.ticker, w.date) if True][:len(vals)])
        row(label, v, 4e-4)
        return v
    print("  TRADABLE windows (market-adjusted, 2 bp/side x 2 legs on the stock; SPY leg ignored):")
    v = win(wa, -4, -1, "   ADD: buy close(-4) -> sell close(-1)  [3 sessions, after the announcement]")
    print("      by year: " + " ".join(f"{y}:{x * 1e4:+.0f}({n})" for (y, x), (_, n) in zip(v.groupby(v.index.year).mean().items(), v.groupby(v.index.year).size().items())))
    # announcement contamination: an announcement-day jump inside -3..-1 would inflate the window. Median, and the
    # mean excluding events with any single-session |mkt-adj move| > 4% inside the window.
    jumps = []; clean = []
    for t, d in zip(wa.ticker, wa.date):
        e = cal.get_loc(d)
        if e - 4 < 0 or any(pd.isna(c[t].iloc[e - 4:e + 1])): continue
        dr = (c[t].iloc[e - 4:e].pct_change().dropna() - c["SPY"].iloc[e - 4:e].pct_change().dropna()).abs()
        tot = (c[t].iloc[e - 1] / c[t].iloc[e - 4] - 1) - (c["SPY"].iloc[e - 1] / c["SPY"].iloc[e - 4] - 1) - 4e-4
        (jumps if dr.max() > 0.04 else clean).append(tot)
    print(f"      median of the 3-session window {np.median(jumps + clean) * 1e4:+.0f}bp; events with a >4% single-session jump inside: {len(jumps)} (mean {np.mean(jumps) * 1e4:+.0f}bp), without: {len(clean)} (mean {np.mean(clean) * 1e4:+.0f}bp, t {tstat(clean):+.1f}, hit {(np.array(clean) > 0).mean():.2f})")
    win(wa, -4, 0, "   ADD: buy close(-4) -> sell at the effective-eve close (the index funds' print)")
    win(wa, 0, 20, "   ADD: hold on from the effective-eve close -> +20 (the reversal; SHORT it = minus this)")
    win(wa, 1, 20, "   ADD: short from close(+1) -> +20")
    pa = pd.DataFrame({"ticker": [t for t, _ in adds for _ in range(3) if t in c.columns], "date": [cal[RNG.integers(cal.searchsorted(pd.Timestamp("2005-01-01")), len(cal) - 100)] for t, _ in adds for _ in range(3) if t in c.columns]})
    win(pa, -4, -1, "   placebo (added tickers, random dates): close(-4) -> close(-1)")
    win(pa, 0, 20, "   placebo: close(0) -> +20")
    win(wd, -4, 0, "   DELETE: short close(-4) -> cover at the effective-eve close")
    win(wd, 0, 20, "   DELETE: buy the effective-eve close -> +20 (bounce; survivors-only)")
    print("  (* = |t| > 2; S&P announces ~5 sessions before; the announcement jump sits inside -10..-3 and is not separable without announcement dates)")


def section_3(px: dict, label: str) -> None:
    print(f"\n=== 3. FUND MANAGERS: window dressing, {label} ===")
    c = px["close"]; c = c[c.index >= "2002-01-01"]
    syms = [t for t in c.columns if t != "SPY"]
    cal = c.index; qe = quarter_ends(cal)
    dress, undress, fake_d = [], [], []
    for e in qe:
        s = np.flatnonzero(cal.to_period("Q") == cal[e].to_period("Q"))[0]
        if e - 4 <= s + 5 or e + 3 >= len(cal): continue
        qtd = c.iloc[e - 4] / c.iloc[s - 1] - 1
        ok = qtd.dropna(); ok = ok[c.iloc[e].reindex(ok.index).notna() & c.iloc[e + 3].reindex(ok.index).notna()]
        if len(ok) < 40: continue
        top = ok[ok >= ok.quantile(0.9)].index; bot = ok[ok <= ok.quantile(0.1)].index
        last3 = c.iloc[e] / c.iloc[e - 3] - 1; next3 = c.iloc[e + 3] / c.iloc[e] - 1
        dress.append(last3[top].mean() - last3[bot].mean()); undress.append(next3[top].mean() - next3[bot].mean())
        # placebo: a random 3-session window mid-quarter with the same ranking logic
        k = RNG.integers(s + 12, e - 12)
        qtdk = c.iloc[k - 4] / c.iloc[s - 1] - 1; okk = qtdk.dropna()
        topk = okk[okk >= okk.quantile(0.9)].index; botk = okk[okk <= okk.quantile(0.1)].index
        l3k = c.iloc[k] / c.iloc[k - 3] - 1
        fake_d.append(l3k[topk].mean() - l3k[botk].mean())
    row("   last 3 sessions of the quarter: winners minus losers (2bp/side x 4 legs)", pd.Series(dress), 8e-4)
    row("   first 3 sessions of the next quarter: winners minus losers", pd.Series(undress), 8e-4)
    row("   placebo: same long-short at random 3-session windows mid-quarter", pd.Series(fake_d), 8e-4)


def main() -> None:
    raw = yf.download(["SPY", "TLT"], period="max", interval="1d", auto_adjust=True, progress=False)["Close"]
    raw.index = pd.DatetimeIndex(raw.index).tz_localize(None)
    section_1(raw["SPY"], raw["TLT"])
    px = pickle.load(open(DIR / "prices.pkl", "rb")); pxf = pickle.load(open(DIR / "prices_fallen.pkl", "rb"))
    section_2(px, pxf)
    section_3(px, "428 survivors"); section_3(pxf, "119 fallen names")


if __name__ == "__main__":
    main()
