"""Earnings events on the 450 largest US stocks, ~25 years (2026-11-11).

Two published "forced-attention" edges, tested on our own data:
  P  Earnings-announcement premium: buy the close before the report, sell the open after (one night).
     Also: hold to the reaction-day close; enter 5 days early (the run-up).
  D  Post-earnings drift: after the reaction day, do the biggest positive reactions keep going for
     weeks and the biggest negative ones keep falling? Ranked within each calendar quarter by the
     market-adjusted reaction (pre-close -> post-close) and separately by Yahoo's EPS surprise %.
Everything is market-adjusted (minus SPY over the same window), costed at 2 bp per side, split in
halves and by year, with a placebo: the same stocks, the same NUMBER of events per year, on random
non-earnings dates. Survivorship: the universe is today's 450 largest, so a plain long-only drift is
biased upward - the placebo on the same stocks measures that bias and is subtracted in "excess".
Data check first (section 0): the report-time classification (before open / after close) is
verified by where the |jump| lands - if "after close" is right the big move is the NEXT open.
"""
from __future__ import annotations

import argparse
import pickle
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DIR = ROOT / "data" / "earnings"
RNG = np.random.default_rng(7)
COST = 2e-4


def tstat(x) -> float:
    x = pd.Series(x).dropna()
    return float(x.mean() / x.std() * np.sqrt(len(x))) if len(x) > 2 and x.std() > 0 else 0.0


def halves(x) -> str:
    x = pd.Series(x).dropna(); h = len(x) // 2
    return f"{x.iloc[:h].mean() * 1e4:+.0f}/{x.iloc[h:].mean() * 1e4:+.0f}"


def load_events(close: pd.DataFrame) -> pd.DataFrame:
    """One row per event: ticker, report_ts, when (BMO/AMC), pre (last close before the news is
    public), post (first session after the news), as positional indexes into the price calendar."""
    cal = close.index
    rows = []
    for f in sorted(DIR.glob("*.csv")):
        t = f.stem
        if t not in close.columns:
            continue
        e = pd.read_csv(f)
        e["report_ts"] = pd.to_datetime(e["report_ts"], utc=True).dt.tz_convert("America/New_York")
        e = e[e.eps_act.notna()]
        for _, r in e.iterrows():
            ts = r.report_ts
            hm = ts.hour * 60 + ts.minute
            d = pd.Timestamp(ts.date())
            if hm < 9 * 60 + 30:
                when = "BMO"; post_i = cal.searchsorted(d)                      # the report day itself
            else:
                when = "AMC"; post_i = cal.searchsorted(d + pd.Timedelta(days=1))  # next session
            if post_i >= len(cal) or post_i < 1:
                continue
            rows.append((t, ts, when, post_i - 1, post_i, r.surprise_pct, r.eps_est, r.eps_act))
    ev = pd.DataFrame(rows, columns=["ticker", "report_ts", "when", "pre", "post", "surprise", "eps_est", "eps_act"])
    ev["date"] = cal[ev.post]
    ev = ev[ev.date >= "2001-01-01"]
    return ev.drop_duplicates(["ticker", "post"]).reset_index(drop=True)


def window_returns(ev: pd.DataFrame, o: pd.DataFrame, c: pd.DataFrame) -> pd.DataFrame:
    """Market-adjusted (minus SPY) log-free simple returns for each event over fixed windows."""
    ov, cv = o.to_numpy(), c.to_numpy()
    col = {t: i for i, t in enumerate(c.columns)}
    spy = col["SPY"]
    out = {}
    def ret(arr_from, i_from, arr_to, i_to, j):
        a = arr_from[i_from, j]; b = arr_to[i_to, j]
        return b / a - 1 if (a > 0 and b > 0) else np.nan
    n = len(cv)
    for name, (f_arr, f_off, t_arr, t_off) in {
        "runup5": (cv, -5, cv, 0),           # close pre-5 -> pre close
        "night": (cv, 0, ov, 1),             # pre close -> post open  (the announcement night)
        "to_close": (cv, 0, cv, 1),          # pre close -> post close (the reaction)
        "post_day": (ov, 1, cv, 1),          # post open -> post close
        "drift5": (cv, 1, cv, 6), "drift10": (cv, 1, cv, 11), "drift20": (cv, 1, cv, 21), "drift40": (cv, 1, cv, 41), "drift60": (cv, 1, cv, 61),
    }.items():
        vals = np.full(len(ev), np.nan); mkt = np.full(len(ev), np.nan)
        for k, (j, pre) in enumerate(zip(ev.ticker.map(col).to_numpy(), ev.pre.to_numpy())):
            i0, i1 = pre + f_off, pre + t_off
            if i0 < 0 or i1 >= n:
                continue
            vals[k] = ret(f_arr, i0, t_arr, i1, j); mkt[k] = ret(f_arr, i0, t_arr, i1, spy)
        out[name] = vals; out[name + "_m"] = mkt
    r = pd.DataFrame(out, index=ev.index)
    for name in list(out):
        if not name.endswith("_m"):
            r[name + "_x"] = r[name] - r[name + "_m"]   # market-adjusted
    return r


def placebo_events(ev: pd.DataFrame, c: pd.DataFrame, min_gap: int = 10) -> pd.DataFrame:
    """Same tickers, same number of events per ticker-year, random dates at least min_gap sessions
    from any real event of that ticker."""
    cal = c.index
    rows = []
    for t, g in ev.groupby("ticker"):
        real = np.sort(g.post.to_numpy())
        valid = c[t].notna().to_numpy()
        for y, gy in g.groupby(g.date.dt.year):
            lo, hi = cal.searchsorted(pd.Timestamp(f"{y}-01-01")), cal.searchsorted(pd.Timestamp(f"{y + 1}-01-01"))
            cand = np.arange(max(lo, 6), min(hi, len(cal) - 61))
            if len(cand) == 0:
                continue
            far = np.min(np.abs(cand[:, None] - real[None, :]), axis=1) >= min_gap
            cand = cand[far & valid[cand]]
            if len(cand) < len(gy):
                continue
            for p in RNG.choice(cand, size=len(gy), replace=False):
                rows.append((t, "PLACEBO", p - 1, p))
    pe = pd.DataFrame(rows, columns=["ticker", "when", "pre", "post"])
    pe["date"] = cal[pe.post]
    return pe.reset_index(drop=True)


def line(label, x, cost_legs=2):
    x = pd.Series(x).dropna() - cost_legs * COST
    return f"  {label:58s} n {len(x):6d}  mean {x.mean() * 1e4:+6.0f}bp  hit {(x > 0).mean():.2f}  t {tstat(x):+5.1f}  halves {halves(x)}"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--min-year", type=int, default=2002)
    ap.add_argument("--fallen", action="store_true", help="use the fallen (removed from the S&P 500) set instead of today's top 450")
    a = ap.parse_args()
    global DIR
    if a.fallen:
        px = pickle.load(open(DIR / "prices_fallen.pkl", "rb")); DIR = DIR / "fallen"
    else:
        px = pickle.load(open(DIR / "prices.pkl", "rb"))
    o, c = px["open"], px["close"]
    ev = load_events(c); ev = ev[ev.date.dt.year >= a.min_year].reset_index(drop=True)
    R = window_returns(ev, o, c); ev = pd.concat([ev, R], axis=1)
    pe = placebo_events(ev, c); PR = window_returns(pe, o, c); pe = pd.concat([pe, PR], axis=1)

    print("=== 0. Data check ===")
    print(f"  events {len(ev):,} on {ev.ticker.nunique()} tickers, {ev.date.min().date()} -> {ev.date.max().date()}; "
          f"AMC {int((ev.when == 'AMC').sum()):,} BMO {int((ev.when == 'BMO').sum()):,}; placebo events {len(pe):,}")
    # classification check: |move| into the post open vs |move| into the pre open (the day before)
    ev["jump_post"] = (ev.night).abs(); 
    pre_open_jump = np.full(len(ev), np.nan)
    ov_, cv_ = o.to_numpy(), c.to_numpy(); col = {t: i for i, t in enumerate(c.columns)}; spy_ = col["SPY"]
    for k, (t, pre) in enumerate(zip(ev.ticker, ev.pre)):
        j = col[t]
        if pre >= 1: pre_open_jump[k] = abs(ov_[pre, j] / cv_[pre - 1, j] - 1)
    ev["jump_pre"] = pre_open_jump
    for w in ("AMC", "BMO"):
        m = ev.when == w
        by = ev[m].groupby(ev[m].date.dt.year // 5 * 5).agg(post=("jump_post", "median"), pre=("jump_pre", "median"))
        print(f"  {w}: median |gap| INTO the post open vs into the open before: " + ", ".join(f"{y}s {r.post * 1e4:.0f}/{r.pre * 1e4:.0f}bp" for y, r in by.iterrows()))
    print("  (if the classification is right the first number is several times the second in every bucket)")
    print(f"  mean |reaction| pre-close->post-close {ev.to_close.abs().mean() * 1e4:.0f}bp vs a normal day {pe.to_close.abs().mean() * 1e4:.0f}bp")

    print("\n=== P. Announcement premium (market-adjusted, 2 bp/side) ===")
    print(line("buy pre close -> sell post OPEN (one night), real", ev.night_x))
    print(line("   same, placebo nights (same stocks, random dates)", pe.night_x))
    print(line("   AMC only", ev.night_x[ev.when == "AMC"]))
    print(line("   BMO only", ev.night_x[ev.when == "BMO"]))
    print(line("buy pre close -> sell post CLOSE, real", ev.to_close_x))
    print(line("   placebo", pe.to_close_x))
    print(line("buy 5 days before -> sell post open (run-up + night), real", (1 + ev.runup5_x) * (1 + ev.night_x) - 1))
    print(line("   placebo", (1 + pe.runup5_x) * (1 + pe.night_x) - 1))
    print(line("run-up alone: close -5 -> pre close, real", ev.runup5_x))
    print(line("   placebo", pe.runup5_x))
    print(line("post open -> post close (the day session after the news)", ev.post_day_x))
    print(line("   placebo", pe.post_day_x))
    print(line("   one night, 2002-2004 (before the 8-K rule the literature blames)", ev.night_x[ev.date < "2005-01-01"]))
    print(line("   one night, 2005-2015", ev.night_x[(ev.date >= "2005-01-01") & (ev.date < "2016-01-01")]))
    print(line("   one night, 2016-2026", ev.night_x[ev.date >= "2016-01-01"]))
    print("  by year, real minus placebo, one night:")
    yr = ev.groupby(ev.date.dt.year).night_x.mean() - pe.groupby(pe.date.dt.year).night_x.mean()
    print("   " + " ".join(f"{y}:{v * 1e4:+.0f}" for y, v in yr.items()))
    print(f"  raw (not market-adjusted) one night real {ev.night.mean() * 1e4:+.0f}bp vs placebo {pe.night.mean() * 1e4:+.0f}bp; stock-level dispersion: sd of the night {ev.night.std() * 1e2:.1f}% (a 2 bp edge inside a {ev.night.std() * 1e2:.0f}% coin flip)")

    print("\n=== D. Post-earnings drift: rank the reaction within each calendar quarter, hold from the post close ===")
    ev["q"] = ev.date.dt.to_period("Q")
    ev["rank_react"] = ev.groupby("q").to_close_x.rank(pct=True)
    ev["rank_surp"] = ev.groupby("q").surprise.rank(pct=True)
    pe["q"] = pe.date.dt.to_period("Q"); pe["rank_react"] = pe.groupby("q").to_close_x.rank(pct=True)
    for key, lab in (("rank_react", "reaction (pre close -> post close, mkt-adj)"), ("rank_surp", "EPS surprise % (Yahoo)")):
        print(f"  -- ranked by {lab} --")
        for h in ("drift5", "drift10", "drift20", "drift40", "drift60"):
            top = ev[ev[key] >= 0.8][h + "_x"]; bot = ev[ev[key] <= 0.2][h + "_x"]; mid = ev[(ev[key] > 0.4) & (ev[key] < 0.6)][h + "_x"]
            ls = pd.concat([top, -bot])
            print(f"    {h:8s} top20% {top.mean() * 1e4:+5.0f}bp t{tstat(top):+5.1f} | bottom20% {bot.mean() * 1e4:+5.0f}bp t{tstat(bot):+5.1f} | middle {mid.mean() * 1e4:+5.0f} | long-short /leg {ls.mean() * 1e4:+5.0f}bp t{tstat(ls):+5.1f} halves {halves(ls)} | after 4 legs cost {(ls.mean() - 4 * COST) * 1e4:+.0f}bp")
    print("  -- placebo: rank a random day's mkt-adj return the same way (should show reversal/nothing, not drift) --")
    for h in ("drift20", "drift40"):
        top = pe[pe.rank_react >= 0.8][h + "_x"]; bot = pe[pe.rank_react <= 0.2][h + "_x"]
        print(f"    {h:8s} top20% {top.mean() * 1e4:+5.0f}bp t{tstat(top):+5.1f} | bottom20% {bot.mean() * 1e4:+5.0f}bp t{tstat(bot):+5.1f} | long-short /leg {pd.concat([top, -bot]).mean() * 1e4:+5.0f}bp")
    print("  -- by year: long-short per leg, drift20, ranked by reaction --")
    ls = pd.concat([ev[ev.rank_react >= 0.8].assign(x=lambda d: d.drift20_x), ev[ev.rank_react <= 0.2].assign(x=lambda d: -d.drift20_x)])
    yr = ls.groupby(ls.date.dt.year).x.agg(["mean", "count"])
    print("   " + " ".join(f"{y}:{r['mean'] * 1e4:+.0f}({int(r['count'])})" for y, r in yr.iterrows()))
    print("  -- large reactions only: |reaction| >= 5% and >= 10% --")
    for thr in (0.05, 0.10):
        up = ev[ev.to_close_x >= thr]; dn = ev[ev.to_close_x <= -thr]
        for h in ("drift5", "drift20", "drift40"):
            print(f"    |react|>={thr:.0%} {h:8s} after a jump UP n{len(up):5d} {up[h + '_x'].mean() * 1e4:+5.0f}bp t{tstat(up[h + '_x']):+4.1f} halves {halves(up[h + '_x'])} | after a jump DOWN n{len(dn):5d} {dn[h + '_x'].mean() * 1e4:+5.0f}bp t{tstat(dn[h + '_x']):+4.1f} halves {halves(dn[h + '_x'])}")
    print("  -- same, recent decade only (2016-) --")
    rec = ev[ev.date >= "2016-01-01"]
    for thr in (0.05,):
        up = rec[rec.to_close_x >= thr]; dn = rec[rec.to_close_x <= -thr]
        for h in ("drift5", "drift20", "drift40"):
            print(f"    |react|>={thr:.0%} {h:8s} UP n{len(up):5d} {up[h + '_x'].mean() * 1e4:+5.0f}bp t{tstat(up[h + '_x']):+4.1f} | DOWN n{len(dn):5d} {dn[h + '_x'].mean() * 1e4:+5.0f}bp t{tstat(dn[h + '_x']):+4.1f}")

    print("\n=== X. Checks that could kill P (the night) ===")
    nx = ev.night_x - 2 * COST
    print(f"  median night {nx.median() * 1e4:+.0f}bp (mean {nx.mean() * 1e4:+.0f}); worst {nx.min():+.1%} best {nx.max():+.1%}; p5 {nx.quantile(0.05):+.1%} p95 {nx.quantile(0.95):+.1%}; share of nights worse than -10%: {(nx < -0.10).mean():.1%}")
    # survivorship: split tickers by their own total return 2010-> today; if only the winners carry the premium, it is survivorship
    tr = (c.iloc[-1] / c.loc[c.index >= "2010-01-01"].iloc[0]).reindex(ev.ticker.unique()).dropna()
    lag = set(tr[tr <= tr.median()].index); win = set(tr[tr > tr.median()].index)
    print(line("   night, LAGGARD half of today's survivors (worst total return since 2010)", ev.night_x[ev.ticker.isin(lag)]))
    print(line("   night, WINNER half", ev.night_x[ev.ticker.isin(win)]))
    # EX-ANTE splits (only information known at the pre close): trailing 1y and 3y market-adjusted return
    cv_ = c.to_numpy(); ev_j = ev.ticker.map(col).to_numpy(); pre_ = ev.pre.to_numpy()
    for L, lab in ((252, "1y"), (756, "3y")):
        tr_ = np.full(len(ev), np.nan)
        for k, (j, i) in enumerate(zip(ev_j, pre_)):
            if i - L >= 0 and cv_[i - L, j] > 0:
                tr_[k] = cv_[i, j] / cv_[i - L, j] - cv_[i, spy_] / cv_[i - L, spy_]
        tr_ = pd.Series(tr_, index=ev.index)
        print(line(f"   night, trailing {lab} return BELOW median (ex-ante laggards)", ev.night_x[tr_ <= tr_.median()]))
        print(line(f"   night, trailing {lab} return ABOVE median", ev.night_x[tr_ > tr_.median()]))
    # market-cap terciles (today's cap, static)
    uni = {r[0]: r[1] for r in __import__("json").load(open(sorted((ROOT / "data" / "earnings").glob("universe_*.json"))[-1]))}
    uni = {t: uni.get(t, 0.0) for t in ev.ticker.unique()}
    cap = ev.ticker.map(uni); q = cap.rank(pct=True)
    for lo, hi, lab in ((0, 1 / 3, "smallest third"), (1 / 3, 2 / 3, "middle third"), (2 / 3, 1.01, "largest third")):
        print(line(f"   night, {lab} by market cap", ev.night_x[(q > lo) & (q <= hi)]))
    # VIX regime
    import yfinance as yf
    vix = yf.download("^VIX", period="max", interval="1d", auto_adjust=True, progress=False)["Close"]["^VIX"]; vix.index = pd.DatetimeIndex(vix.index).tz_localize(None)
    v = vix.reindex(c.index).ffill().to_numpy()[ev.pre.to_numpy()]
    for lo, hi in ((0, 15), (15, 20), (20, 30), (30, 99)):
        m = (v >= lo) & (v < hi)
        print(line(f"   night, VIX {lo}-{hi} at the pre close", ev.night_x[m]))
    # 2016- only, AMC only (the operational case: buy MOC, sell MOO)
    rec = ev[(ev.date >= "2016-01-01")]
    print(line("   night, 2016-, AMC only", rec.night_x[rec.when == "AMC"]))
    print(line("   night, 2016-, AMC only, RAW (not market-adjusted)", rec.night[rec.when == "AMC"]))
    print(line("   night, 2016-, BMO only", rec.night_x[rec.when == "BMO"]))
    # does the run-up predict the night? (if the 5-day run-up was big, is the night worse?)
    for lo, hi, lab in ((-9, -0.03, "run-up <= -3%"), (-0.03, 0.03, "run-up -3..+3%"), (0.03, 9, "run-up >= +3%")):
        m = (ev.runup5_x > lo) & (ev.runup5_x <= hi)
        print(line(f"   night when 5-day {lab}", ev.night_x[m]))
    # book simulation: AMC only, at most K names per night, equal weight 1/K of the account, picked by largest cap
    print("  -- book: AMC nights only, up to K names per night (largest cap first), 1/K of the account each, RAW returns, 2 bp/side --")
    amc = ev[(ev.when == "AMC") & (ev.date >= "2010-01-01")].copy(); amc["cap"] = amc.ticker.map(uni)
    for K in (3, 5, 8):
        nightly = []
        for d, g in amc.groupby("date"):
            g = g.sort_values("cap", ascending=False).head(K)
            nightly.append(((g.night - 2 * COST).sum() / K))
        nightly = pd.Series(nightly)
        yrs = (amc.date.max() - amc.date.min()).days / 365.25
        print(f"    K={K}: nights {len(nightly)}, avg per night {nightly.mean() * 1e4:+.0f}bp of the account, per year {nightly.sum() / yrs * 100:+.1f}% of the account, worst night {nightly.min():+.1%}, sd/night {nightly.std():.2%}, Sharpe-ish {nightly.mean() / nightly.std() * np.sqrt(len(nightly) / yrs):.2f}")

    print("\n=== Y. Control for the big-jump continuation: random >= 10% up days that are NOT earnings ===")
    # all stock-days with mkt-adj close->close >= +10% at least 10 sessions from any earnings post day
    cc = c.pct_change(); spyr = cc["SPY"]
    rows = []
    real_post = {t: set(g.post) for t, g in ev.groupby("ticker")}
    for t in ev.ticker.unique():
        x = (cc[t] - spyr)
        idx = np.flatnonzero((x >= 0.10).to_numpy())
        for i in idx:
            if i < 1 or i + 41 >= len(c) or c.index[i] < pd.Timestamp("2002-01-01"):
                continue
            if any(abs(i - p) < 10 for p in real_post[t]):
                continue
            rows.append((t, i))
    ctl = pd.DataFrame(rows, columns=["ticker", "post"]); ctl["pre"] = ctl.post - 1; ctl["date"] = c.index[ctl.post]
    CR = window_returns(ctl, o, c)
    for h in ("drift5", "drift20", "drift40"):
        print(f"    non-earnings >= 10% up day, n {len(ctl)}: {h} {CR[h + '_x'].mean() * 1e4:+5.0f}bp t{tstat(CR[h + '_x']):+4.1f} halves {halves(CR[h + '_x'])}")
    up = ev[ev.to_close_x >= 0.10]
    print("    vs earnings >= 10% up: " + " | ".join(f"{h} {up[h + '_x'].mean() * 1e4:+.0f}bp" for h in ("drift5", "drift20", "drift40")))
    print("  -- earnings >= 10% up, by year (drift20) --")
    yr = up.groupby(up.date.dt.year).drift20_x.agg(["mean", "count"])
    print("   " + " ".join(f"{y}:{r['mean'] * 1e4:+.0f}({int(r['count'])})" for y, r in yr.iterrows()))
    print("  -- earnings >= 10% up, entry at the post close vs entry at the NEXT open (we can't trade the post close with a scan at 10:00) --")
    nxt = np.full(len(up), np.nan); ov_, cv_ = o.to_numpy(), c.to_numpy()
    for k, (t, post) in enumerate(zip(up.ticker, up.post)):
        j = col[t]
        if post + 21 < len(c): nxt[k] = cv_[post + 21, j] / ov_[post + 1, j] - 1 - (cv_[post + 21, col["SPY"]] / ov_[post + 1, col["SPY"]] - 1)
    print(f"    buy next open -> +20 sessions close: {np.nanmean(nxt) * 1e4:+.0f}bp t{tstat(nxt):+.1f} (vs from post close {up.drift20_x.mean() * 1e4:+.0f})")

    print("\n=== S. Size of the opportunity for a $25k account ===")
    per_wk = ev[ev.date >= "2016-01-01"].groupby(ev.date.dt.to_period("W")).size()
    print(f"  events per week 2016-: median {per_wk.median():.0f}, 90th pct {per_wk.quantile(0.9):.0f}, max {per_wk.max()}; "
          f"events per year {len(ev[ev.date >= '2016-01-01']) / (ev[ev.date >= '2016-01-01'].date.dt.year.nunique()):.0f}")
    ev.to_csv(ROOT / "results" / f"earnings_events{'_fallen' if a.fallen else ''}_2026-11-11.csv", index=False)
    print("  per-event table written to results/earnings_events_2026-11-11.csv")


if __name__ == "__main__":
    main()
