"""Two more forced players (2026-11-13).

  1  THE TREASURY. Dealers must absorb 10y/20y/30y auctions, so they sell/hedge beforehand and the
     pressure lifts after (Lou, Yan, Zhang 2013). Nominal coupon auctions incl. reopenings, TIPS
     excluded, dates from fiscaldata.treasury.gov. TLT (and IEF for 10y) close-to-close, day-by-day
     around the auction (results are out at 13:00 ET on day 0), then two trades at 1 bp/side:
       short TLT close(-4) -> close(-1);  long TLT close(0) -> close(+4).
     Controls: random dates (same count per year), halves, by year, 10y vs 30y vs 20y.
  2  TAX-LOSS SELLERS. Rank stocks by year-to-date return at the end of October. Bottom decile =
     losers. Do they get sold Nov 1 -> mid-Dec and rebound mid-Dec -> mid-Jan? Market-adjusted,
     2 bp/side, survivors AND fallen. Control: the identical ranking and windows shifted to every
     other month of the year (is December-January special, or just generic reversal?).
"""
from __future__ import annotations
import pickle
from pathlib import Path
import numpy as np
import pandas as pd
import yfinance as yf

ROOT = Path(__file__).resolve().parent.parent
RNG = np.random.default_rng(13)


def tstat(x):
    x = pd.Series(x).dropna()
    return float(x.mean() / x.std() * np.sqrt(len(x))) if len(x) > 2 and x.std() > 0 else 0.0


def row(label, x, cost=0.0):
    x = pd.Series(x).dropna() - cost; h = len(x) // 2
    print(f"  {label:66s} n {len(x):4d}  mean {x.mean() * 1e4:+6.1f}bp  hit {(x > 0).mean():.2f}  t {tstat(x):+4.1f}  halves {x.iloc[:h].mean() * 1e4:+.0f}/{x.iloc[h:].mean() * 1e4:+.0f}")


def section_1():
    print("=== 1. Treasury auctions: TLT / IEF around 10y, 20y, 30y nominal auctions ===")
    a = pd.read_csv(ROOT / "data" / "treasury_auctions.csv", parse_dates=["auction_date"])
    a = a[(a.inflation_index_security == "No") & (a.floating_rate == "No")]
    yrs = a.security_term.str.extract(r"(\d+)-Year")[0].astype(float)
    a["bucket"] = np.where(yrs >= 29, "30y", np.where(yrs >= 19, "20y", np.where(yrs >= 9, "10y", "short")))
    px = yf.download(["TLT", "IEF", "SPY"], period="max", interval="1d", auto_adjust=True, progress=False)["Close"]
    px.index = pd.DatetimeIndex(px.index).tz_localize(None); px = px.dropna()
    cal = px.index; r = px.pct_change()
    def prof(dates, sym):
        pos = [cal.get_loc(d) for d in dates if d in cal]
        pos = [p for p in pos if 8 <= p < len(cal) - 8]
        out = {k: np.array([r[sym].iloc[p + k] for p in pos]) for k in range(-6, 7)}
        pre = np.array([px[sym].iloc[p - 1] / px[sym].iloc[p - 4] - 1 for p in pos])
        post = np.array([px[sym].iloc[p + 4] / px[sym].iloc[p] - 1 for p in pos])
        day0 = np.array([r[sym].iloc[p] for p in pos])
        return out, pd.Series(pre, index=[cal[p] for p in pos]), pd.Series(post, index=[cal[p] for p in pos]), pd.Series(day0, index=[cal[p] for p in pos])
    uncond = r.TLT.mean()
    print(f"  TLT unconditional daily mean {uncond * 1e4:+.1f}bp; 3-day {((1 + r.TLT).rolling(3).apply(np.prod, raw=True) - 1).mean() * 1e4:+.1f}bp")
    for b, sym in (("30y", "TLT"), ("10y", "TLT"), ("10y", "IEF"), ("20y", "TLT")):
        dates = sorted(set(a[a.bucket == b].auction_date))
        out, pre, post, d0 = prof(dates, sym)
        print(f"  -- {b} auctions, {sym}, n {len(pre)} ({pre.index[0].date()} ->) --")
        print("     day-by-day bp (0 = auction day): " + " ".join(f"{k:+d}:{v.mean() * 1e4:+.1f}{'*' if abs(tstat(v)) > 2 else ''}" for k, v in out.items()))
        row(f"   SHORT {sym} close(-4) -> close(-1), 1bp/side", -pre, 2e-4)
        row(f"   LONG {sym} close(0) -> close(+4), 1bp/side", post, 2e-4)
        row(f"   auction day itself (long)", d0)
        if b == "30y":
            both = pd.concat([-pre - 2e-4, post - 2e-4]).sort_index()
            print("     by year, short-before + long-after (bp sum): " + " ".join(f"{y}:{v * 1e4:+.0f}" for y, v in both.groupby(both.index.year).sum().items()))
            fake_pre, fake_post = [], []
            for _ in range(500):
                fd = []
                for y, g in pd.Series(dates).groupby(pd.Series(dates).dt.year):
                    c = cal[cal.year == y]
                    if len(c) > len(g): fd += list(RNG.choice(c, size=len(g), replace=False))
                _, fp, fq, _ = prof(sorted(pd.DatetimeIndex(fd)), sym)
                fake_pre.append((-fp).mean()); fake_post.append(fq.mean())
            print(f"     placebo random dates: short-before {np.mean(fake_pre) * 1e4:+.1f}bp (p real>= {np.mean(np.array(fake_pre) >= (-pre).mean()):.2f}), long-after {np.mean(fake_post) * 1e4:+.1f}bp (p {np.mean(np.array(fake_post) >= post.mean()):.2f})")
    # all long-end auctions combined, de-overlapped
    dates = sorted(set(a[a.bucket.isin(["10y", "20y", "30y"])].auction_date))
    _, pre, post, _ = prof(dates, "TLT")
    row("   ALL 10y/20y/30y: SHORT TLT close(-4) -> close(-1)", -pre, 2e-4); row("   ALL 10y/20y/30y: LONG TLT close(0) -> close(+4)", post, 2e-4)
    rec = post[post.index >= "2015-01-01"]; row("   ALL, long-after, 2015-", rec, 2e-4); row("   ALL, short-before, 2015-", -pre[pre.index >= "2015-01-01"], 2e-4)


def section_2():
    print("\n=== 2. Tax-loss sellers: October-end YTD losers, sold into December, rebound into January? ===")
    d = pickle.load(open(ROOT / "data" / "earnings" / "ohlc.pkl", "rb"))
    for key in ("survivors", "fallen"):
        C = d[key]["close"]; C = C[C.index >= "2001-06-01"]; spy = C["SPY"]; S = C.drop(columns="SPY")
        cal = C.index
        me = pd.Series(np.arange(len(cal)), index=cal).groupby(cal.to_period("M")).last()   # last session index per month
        res = {}
        for anchor in range(1, 13):                       # anchor month = the ranking month-end (10 = October = the real one)
            sell, reb, top_reb = [], [], []
            for per, e in me.items():
                if per.month != anchor: continue
                e0 = e - 210                              # ~10 months back, so every anchor uses the same lookback
                if e0 < 0 or e + 55 >= len(cal): continue
                ytd = S.iloc[e] / S.iloc[e0] - 1
                ok = ytd.dropna()
                if len(ok) < 60: continue
                lose = ok[ok <= ok.quantile(0.1)].index; win = ok[ok >= ok.quantile(0.9)].index
                a, b, c2 = e, e + 32, e + 52             # ~Nov 1 -> ~Dec 17 -> ~Jan 16 for the October anchor
                def adj(names, i, j): return (S[names].iloc[j] / S[names].iloc[i] - 1).mean() - (spy.iloc[j] / spy.iloc[i] - 1)
                sell.append(adj(lose, a, b)); reb.append(adj(lose, b, c2) - 4e-4); top_reb.append(adj(win, b, c2))
            res[anchor] = (pd.Series(sell), pd.Series(reb), pd.Series(top_reb))
        s, rb, tr = res[10]
        print(f"  -- {key}: {S.shape[1]} stocks, {len(s)} years --")
        row("   losers, Nov 1 -> ~Dec 17 (the selling window), vs SPY", s)
        row("   losers, ~Dec 17 -> ~Jan 16 (the rebound), vs SPY, 2bp/side", rb)
        row("   winners, same rebound window, vs SPY", tr)
        row("   losers minus winners, rebound window", rb - tr)
        others = pd.concat([res[m][1] for m in range(1, 13) if m != 10]); oth_sell = pd.concat([res[m][0] for m in range(1, 13) if m != 10])
        row("   CONTROL: same rule anchored on the other 11 months, 'rebound' leg", others)
        row("   CONTROL: other 11 months, 'selling' leg", oth_sell)
        print("     rebound leg by anchor month (10 = the real one): " + " ".join(f"{m}:{res[m][1].mean() * 1e4:+.0f}" for m in range(1, 13)))
        print(f"     hit rate of the January rebound by year: {(rb > 0).mean():.2f}; worst {rb.min():+.1%}, best {rb.max():+.1%}; last 10 years mean {rb.iloc[-10:].mean() * 1e4:+.0f}bp")


if __name__ == "__main__":
    section_1(); section_2()
