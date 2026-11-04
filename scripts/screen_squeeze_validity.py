"""Does a Bollinger-inside-Keltner squeeze predict a bigger move? Tested, not assumed.

On every 5-minute file in the repo (ETFs 1y, stocks 1y, micro futures 3.5mo):
  squeeze bar  = BB(20,2) inside KC(20, 1.5 ATR)
  release bar  = first bar after a run of >= 6 squeeze bars where the squeeze is off
  For the release bar and for every bar (baseline) measure the absolute return over the next
  3 / 6 / 12 bars, scaled by the bar's own ATR(20), so instruments are comparable.
  Claim 1 (size): |move after release| > |move after a random bar|.
  Claim 2 (direction): the up-volume share over the last 10 squeeze bars predicts the sign of the
  next 12-bar return (only where the file has real volume).
  Claim 3 (level): a trade entered on the first close beyond the squeeze range (stop at the range
  midpoint, exit after 12 bars or at the stop) - the "breakout from the squeeze" trade - with 1 bp/side.
"""
from __future__ import annotations

import glob
from pathlib import Path

import numpy as np
import pandas as pd

from ten_cent_bot.tv_data import load_tv_csv

ROOT = Path(__file__).resolve().parent.parent
FILES = sorted(glob.glob(str(ROOT / "BATS_*, 5.csv"))) + sorted(glob.glob(str(ROOT / "CME_MINI_M*1!, 5.csv"))) + sorted(glob.glob(str(ROOT / "COMEX_MINI_MGC1!, 5.csv")))


def tstat(x) -> float:
    x = pd.Series(x).dropna()
    return float(x.mean() / x.std() * np.sqrt(len(x))) if len(x) > 2 and x.std() > 0 else 0.0


def run(path: str) -> dict | None:
    raw = pd.read_csv(path)
    has_vol = "Volume" in raw.columns
    df = load_tv_csv(path); df.index = df.index.tz_convert("America/New_York")
    if "BATS" in path or "scan" in path:
        df = df.between_time("09:30", "15:55")
    df = df[df.index.date != df.index.date[-1]]  # drop the partial last day
    c, h, l, o, v = df.close, df.high, df.low, df.open, df.volume
    mid = c.rolling(20).mean(); sd = c.rolling(20).std(ddof=0)
    bb_u, bb_l = mid + 2 * sd, mid - 2 * sd
    ema = c.ewm(span=20, adjust=False).mean()
    tr = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1 / 20, adjust=False).mean()
    sq = ((bb_u < ema + 1.5 * atr) & (bb_l > ema - 1.5 * atr)).to_numpy()
    cl, hi, lo, op, vol, at = c.to_numpy(), h.to_numpy(), l.to_numpy(), o.to_numpy(), v.to_numpy(), atr.to_numpy()
    d = df.index.date
    n = len(df)
    base = {H: [] for H in (3, 6, 12)}
    rel = {H: [] for H in (3, 6, 12)}
    direction = []
    trades = []
    run_len = 0
    for i in range(25, n - 13):
        if at[i] <= 0 or np.isnan(at[i]):
            continue
        for H in (3, 6, 12):
            if d[i + H] == d[i]:
                base[H].append(abs(cl[i + H] / cl[i] - 1) * cl[i] / at[i])
        if sq[i]:
            run_len += 1
            continue
        if run_len >= 6 and d[i + 12] == d[i]:
            seg = slice(i - run_len, i)
            rh, rl = hi[seg].max(), lo[seg].min()
            for H in (3, 6, 12):
                rel[H].append(abs(cl[i + H] / cl[i] - 1) * cl[i] / at[i])
            if has_vol:
                s10 = slice(max(i - 10, i - run_len), i)
                upv = vol[s10][cl[s10] > op[s10]].sum(); dnv = vol[s10][cl[s10] < op[s10]].sum()
                if upv + dnv > 0:
                    share = upv / (upv + dnv)
                    direction.append((share, np.sign(cl[i + 12] / cl[i] - 1)))
            # breakout trade: first close beyond the range within the next 6 bars
            for j in range(i, min(i + 6, n - 13)):
                if d[j] != d[i]:
                    break
                side = 1 if cl[j] > rh else (-1 if cl[j] < rl else 0)
                if side:
                    entry = cl[j]; stop = (rh + rl) / 2; ex = cl[min(j + 12, n - 1)]
                    for k in range(j + 1, min(j + 13, n)):
                        if d[k] != d[j]:
                            ex = cl[k - 1]; break
                        if (side == 1 and lo[k] <= stop) or (side == -1 and hi[k] >= stop):
                            ex = stop; break
                    trades.append(side * (ex / entry - 1) - 2e-4)
                    break
        run_len = 0
    if not rel[12]:
        return None
    out = {"file": Path(path).stem, "bars": n, "releases": len(rel[12]), "has_volume": has_vol}
    for H in (3, 6, 12):
        b, r = np.array(base[H]), np.array(rel[H])
        out[f"move{H}_release_vs_base"] = f"{r.mean():.2f} vs {b.mean():.2f} ATR (ratio {r.mean() / b.mean():.2f}, t {(r.mean() - b.mean()) / np.sqrt(r.var() / len(r) + b.var() / len(b)):+.1f})"
    if direction:
        dd = pd.DataFrame(direction, columns=["share", "sign"])
        buy = dd[dd.share >= 0.6].sign; sell = dd[dd.share <= 0.4].sign
        out["direction"] = f"buyers-lean n {len(buy)} up-rate {(buy > 0).mean():.2f} | sellers-lean n {len(sell)} up-rate {(sell > 0).mean():.2f} | corr(share, sign) {dd.share.corr(dd.sign):+.3f}"
    if trades:
        tr = np.array(trades)
        out["breakout_trade"] = f"n {len(tr)} mean {tr.mean() * 1e4:+.1f}bp win {(tr > 0).mean():.2f} t {tstat(tr):+.1f}"
    return out


def main() -> None:
    for f in FILES:
        r = run(f)
        if r:
            print(f"\n{r['file']}: {r['bars']} bars, {r['releases']} squeeze releases, volume={r['has_volume']}")
            for k in ("move3_release_vs_base", "move6_release_vs_base", "move12_release_vs_base", "direction", "breakout_trade"):
                if k in r:
                    print(f"  {k:24s} {r[k]}")


if __name__ == "__main__":
    main()
