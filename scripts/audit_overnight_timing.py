"""Where inside the night does E's edge live, and should E enter earlier / exit later? (2026-11-11)

E holds 16:00 -> 09:30. Three questions, all on data in the repo, all costed at 1 bp/side (ETFs):
  A  ENTRY: enter at 15:00 / 15:30 / 15:45 instead of the close (exit 09:30 open). The difference is
     the last-hour / last-30-min return, which is either free money or free risk.
     SPY 30-min 2020- (15:00, 15:30), SPY/QQQ/IWM hourly 2015- (15:00), 5-min ETFs ~1y (15:45).
  B  EXIT: exit at the 10:00 / 10:30 / 11:00 / 12:00 open instead of 09:30 (unconditional, vs the
     gap-down-only hold already adopted). Same data.
  C  NIGHT WINDOWS on the futures (ES/NQ hourly ETH 2023-, ES 30-min 2025-): 16:00-18:00 (close to
     Globex reopen), 18:00-02:00 (Asia), 02:00-08:30 (Europe), 08:30-09:30 (US data + pre-open).
     Which windows carry the premium, which are flat, and is any one negative (an early exit on the
     MES rail would then cut risk for free). Short history -> screen-grade.
Controls: both halves, by year, E v2 signal nights (RSI(2)<10 at the close) vs other nights, bootstrap
CI on every difference (2000 resamples).
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from ten_cent_bot import overnight as ov
from ten_cent_bot.tv_data import load_tv_csv

ROOT = Path(__file__).resolve().parent.parent
TZ = "America/New_York"
RNG = np.random.default_rng(11)
C = 1e-4


def tstat(x) -> float:
    x = pd.Series(x).dropna()
    return float(x.mean() / x.std() * np.sqrt(len(x))) if len(x) > 2 and x.std() > 0 else 0.0


def sh(x) -> float:
    x = pd.Series(x).dropna()
    return float(x.mean() / x.std() * np.sqrt(252)) if x.std() > 0 else 0.0


def halves(x) -> str:
    x = pd.Series(x).dropna(); h = len(x) // 2
    return f"{x.iloc[:h].mean() * 1e4:+.1f}/{x.iloc[h:].mean() * 1e4:+.1f}"


def boot_ci(x, n=2000) -> str:
    x = pd.Series(x).dropna().to_numpy()
    m = np.array([RNG.choice(x, size=len(x), replace=True).mean() for _ in range(n)])
    return f"[{np.percentile(m, 2.5) * 1e4:+.1f}, {np.percentile(m, 97.5) * 1e4:+.1f}]"


def load(path) -> pd.DataFrame:
    df = load_tv_csv(ROOT / path); df.index = df.index.tz_convert(TZ); return df


def landmarks(df: pd.DataFrame, times: list[str]) -> pd.DataFrame:
    """Per day: the OPEN at each hh:mm in `times`, plus the day's last close (16:00) and first open."""
    rth = df.between_time("09:30", "15:59")
    hm = df.index.strftime("%H:%M")
    out = {"close": rth.groupby(rth.index.date).close.last(), "open": rth.groupby(rth.index.date).open.first()}
    for t in times:
        s = df[hm == t]
        out[f"o{t.replace(':', '')}"] = s.groupby(s.index.date).open.first()
    t = pd.DataFrame(out); t.index = pd.to_datetime(t.index)
    return t


def rsi_signal(close: pd.Series) -> pd.Series:
    return ov.rsi(close, 2) < 10


def section_A(name, t, entries):
    base = t.open.shift(-1) / t.close - 1 - 2 * C   # 16:00 -> 09:30
    sig = rsi_signal(t.close)
    print(f"  {name}: close->09:30 open  Sharpe {sh(base):.2f}  mean {base.mean() * 1e4:+.1f}bp  n {base.notna().sum()}")
    for e in entries:
        col = f"o{e.replace(':', '')}"
        if col not in t or t[col].notna().sum() < 100:
            continue
        alt = t.open.shift(-1) / t[col] - 1 - 2 * C
        d = (alt - base).dropna()
        print(f"     enter {e} instead: Sharpe {sh(alt):.2f}  mean {alt.mean() * 1e4:+.1f}bp | the extra {e}->close leg: {d.mean() * 1e4:+.1f}bp t {tstat(d):+.1f} halves {halves(d)} CI {boot_ci(d)} | on E v2 signal days {d[sig.reindex(d.index).fillna(False)].mean() * 1e4:+.1f}bp (n {int(sig.reindex(d.index).fillna(False).sum())}) | by year: " +
              " ".join(f"{y}:{v * 1e4:+.0f}" for y, v in d.groupby(d.index.year).mean().items()))


def section_B(name, t, exits):
    base = t.open.shift(-1) / t.close - 1 - 2 * C
    sig = rsi_signal(t.close)
    print(f"  {name}: exit 09:30 open  Sharpe {sh(base):.2f}  mean {base.mean() * 1e4:+.1f}bp")
    for e in exits:
        col = f"o{e.replace(':', '')}"
        if col not in t or t[col].notna().sum() < 100:
            continue
        alt = t[col].shift(-1) / t.close - 1 - 2 * C
        d = (alt - base).dropna()
        print(f"     exit {e} instead: Sharpe {sh(alt):.2f}  mean {alt.mean() * 1e4:+.1f}bp | the extra 09:30->{e} leg: {d.mean() * 1e4:+.1f}bp t {tstat(d):+.1f} halves {halves(d)} CI {boot_ci(d)} | on E v2 signal days {d[sig.reindex(d.index).fillna(False)].mean() * 1e4:+.1f}bp | by year: " +
              " ".join(f"{y}:{v * 1e4:+.0f}" for y, v in d.groupby(d.index.year).mean().items()))


def section_C(name, df, cuts):
    """cuts: ordered list of hh:mm; windows are consecutive pairs, the last pair crosses midnight."""
    hm = df.index.strftime("%H:%M")
    px = {}
    for t in cuts:
        s = df[hm == t]; px[t] = pd.Series(s.open.to_numpy(), index=pd.DatetimeIndex(s.index.date))
    P = pd.DataFrame(px)
    # night of day d: from cuts[0] on d (16:00) to later cuts; after midnight the cut belongs to d+1
    rows = {}
    prev = None
    for t in cuts:
        cur = P[t] if t >= cuts[0] else P[t].shift(-1)
        if prev is not None:
            rows[f"{prev_t}->{t}"] = cur / prev - 1
        prev, prev_t = cur, t
    W = pd.DataFrame(rows).dropna()
    total = (1 + W).prod(axis=1) - 1
    sig = rsi_signal(P[cuts[0]]).reindex(W.index).fillna(False)
    print(f"  {name}: {len(W)} nights {W.index[0].date()} -> {W.index[-1].date()}; whole night {total.mean() * 1e4:+.1f}bp/night Sharpe {sh(total):.2f}")
    for w in W.columns:
        x = W[w]
        print(f"     {w:13s} mean {x.mean() * 1e4:+5.1f}bp  sd {x.std() * 1e4:4.0f}bp  Sharpe {sh(x):+.2f}  share {x.sum() / total.sum():+.0%}  halves {halves(x)}  CI {boot_ci(x)}  | signal nights {x[sig].mean() * 1e4:+.1f}bp (n {int(sig.sum())}) other {x[~sig].mean() * 1e4:+.1f}bp")


def main() -> None:
    spy30 = load("BATS_SPY, 30.csv"); t30 = landmarks(spy30, ["15:00", "15:30", "10:00", "10:30", "11:00", "12:00"])
    h60 = {s: landmarks(load(f"BATS_{s}, 60.csv"), ["15:00", "10:30", "11:30", "12:30"]) for s in ("SPY", "QQQ", "IWM")}
    f5 = {s: landmarks(load(f"BATS_{s}, 5.csv"), ["15:00", "15:30", "15:45", "15:55", "09:35", "09:45", "10:00", "10:30"]) for s in ("SPY", "QQQ", "IWM")}
    print("=== A. ENTRY earlier than the close (exit 09:30 open) ===")
    section_A("SPY 30-min 2020-", t30, ["15:00", "15:30"])
    for s, t in h60.items():
        section_A(f"{s} hourly 2015-", t, ["15:00"])
    for s, t in f5.items():
        section_A(f"{s} 5-min ~1y", t, ["15:00", "15:30", "15:45", "15:55"])
    print("\n=== B. EXIT later than the 09:30 open (unconditional) ===")
    section_B("SPY 30-min 2020-", t30, ["10:00", "10:30", "11:00", "12:00"])
    for s, t in h60.items():
        section_B(f"{s} hourly 2015-", t, ["10:30", "11:30", "12:30"])
    for s, t in f5.items():
        section_B(f"{s} 5-min ~1y", t, ["09:35", "09:45", "10:00", "10:30"])
    print("\n=== C. Night windows on the futures (extended hours) ===")
    section_C("ES hourly 2023-", load("CME_MINI_ES1!, 60.csv"), ["16:00", "18:00", "02:00", "08:00", "09:00", "10:00"])
    section_C("NQ hourly 2023-", load("CME_MINI_NQ1!, 60.csv"), ["16:00", "18:00", "02:00", "08:00", "09:00", "10:00"])
    section_C("ES 30-min 2025-", load("CME_MINI_ES1!, 30.csv"), ["16:00", "18:00", "02:00", "08:30", "09:30"])
    print("  (hourly files have no 09:30 bar: 09:00->10:00 mixes the last pre-open half hour with the first RTH half hour)")


if __name__ == "__main__":
    main()
