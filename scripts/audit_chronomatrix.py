"""Sleeve I audit: ChronoMatrix / Time Distortion Theory (mechanical version).

Systematic test of the two falsifiable claims in
ChronoMatrix_V5_Guide_FRESH.md, pre-registered 2026-07-12 BEFORE any
results were computed (same treatment Sleeve G's AMDX framework got).

PRE-REGISTERED INTERPRETATION
  Cycle:  node = (bars since 09:30 session open) mod 27 + 1, on 5-min
          RTH bars. "3 circles x 9 candles = 27" (guide section 3 +
          glossary "Po3"). Cycle direction at bar t = sign of return
          from the current cycle's first bar to t.
  Claims tested (guide section 3):
    C1  N7 "exhaustion - the leg after N7 is often the largest":
        cycle-direction-aligned forward return over the next 6 bars
        (N7 -> N13) should be significantly POSITIVE (continuation).
    C2  N21 "final push - the next move is the reset": aligned forward
        return after N21 should be NEGATIVE (reversal).
    C3  N25 "reset begins": aligned forward return NEGATIVE.
    C4  Global: node position carries ANY information - the spread of
        per-node aligned forward returns should exceed a placebo where
        each day's node numbering is rotated by a random offset.
  Sweep (guide section 7):
    S1  Sweep bar = wick through prior-day RTH high (low) with body
        closing back inside. Entry: close of the NEXT bar ("trust the
        bar after"), faded direction (short after PDH sweep, long
        after PDL sweep), skipped if that bar also wicks through.
        Exits: +30min, +60min, session close. Placebo: random bars on
        the same days, same holding period, matched direction mix.

Universe: SPY/QQQ/IWM 5-min (257 days) primary; MES/MNQ 5-min
(~3.5 months) secondary confirmation.

Verdict standard: same as every sleeve - placebo p < 0.05 or shelved.

Usage: python scripts/audit_chronomatrix.py
"""
from __future__ import annotations

import os

import numpy as np
import pandas as pd

CYCLE = 27
FWD_BARS = 6  # 30 minutes of 5-min bars
KEY_NODES = {"N7 continuation (C1)": (7, +1),
             "N21 reversal (C2)": (21, -1),
             "N25 reversal (C3)": (25, -1)}


def load_5m(repo: str, fname: str) -> pd.DataFrame:
    df = pd.read_csv(os.path.join(repo, fname))
    df["dt"] = (pd.to_datetime(df["time"], unit="s", utc=True)
                .dt.tz_convert("America/New_York"))
    df = df.set_index("dt").sort_index()
    return df.between_time("09:30", "15:55")


def day_arrays(df: pd.DataFrame) -> list[pd.DataFrame]:
    return [g for _, g in df.groupby(df.index.date) if len(g) >= 60]


# ---------------- cycle test ----------------

def node_stats(days: list[pd.DataFrame], rng: np.random.Generator | None = None):
    """Per-node cycle-direction-aligned forward returns (bp).

    If rng is given, each day's node numbering is rotated by a random
    offset (the placebo transform), destroying any true node alignment
    while preserving intraday autocorrelation structure.
    """
    per_node = {n: [] for n in range(1, CYCLE + 1)}
    for g in days:
        c = g["close"].values
        n_bars = len(c)
        offset = int(rng.integers(0, CYCLE)) if rng is not None else 0
        for i in range(n_bars - FWD_BARS):
            node = (i + offset) % CYCLE + 1
            cyc_start = i - (i % CYCLE)  # true cycle anchor (not shifted)
            if rng is not None:
                cyc_start = max(0, i - ((i + offset) % CYCLE))
            if i == cyc_start:
                continue  # no direction defined at cycle birth
            direction = np.sign(c[i] / c[cyc_start] - 1)
            if direction == 0:
                continue
            fwd = c[i + FWD_BARS] / c[i] - 1
            per_node[node].append(direction * fwd * 1e4)
    return {n: (np.mean(v), np.std(v) / np.sqrt(len(v)), len(v)) if v else (np.nan,) * 3
            for n, v in per_node.items()}


def run_cycle_test(name: str, days: list[pd.DataFrame]) -> None:
    print(f"\n--- Cycle test: {name} ({len(days)} days) ---")
    real = node_stats(days)
    print(f"  {'node':>5} {'aligned fwd 30m (bp)':>21} {'t':>6} {'n':>7}")
    for label, (node, want) in KEY_NODES.items():
        mu, se, n = real[node]
        t = mu / se if se else np.nan
        direction = "continuation" if want > 0 else "reversal"
        ok = (np.sign(mu) == want) and abs(t) > 2
        print(f"  N{node:<4} {mu:>21.2f} {t:>6.2f} {int(n):>7}   "
              f"claim: {direction:<12} -> {'SUPPORTED' if ok else 'not supported'}")

    # C4: global information content vs placebo
    spread_real = np.nanstd([real[n][0] for n in real])
    rng = np.random.default_rng(0)
    spreads = []
    for _ in range(100):
        plc = node_stats(days, rng=rng)
        spreads.append(np.nanstd([plc[n][0] for n in plc]))
    spreads = np.array(spreads)
    p = (spreads >= spread_real).mean()
    print(f"  C4 node-effect spread: real {spread_real:.2f}bp vs placebo "
          f"{spreads.mean():.2f} +/- {spreads.std():.2f}bp,  p = {p:.3f}")


# ---------------- sweep test ----------------

def sweep_trades(days: list[pd.DataFrame]) -> pd.DataFrame:
    rows = []
    prev_high = prev_low = None
    for g in days:
        h, l, c, o = (g[k].values for k in ("high", "low", "close", "open"))
        if prev_high is not None:
            for i in range(len(g) - 2):
                # PDH sweep: wick above, body back inside
                if h[i] > prev_high and c[i] < prev_high and o[i] < prev_high:
                    if h[i + 1] > prev_high:  # "sweep is not done - wait"
                        continue
                    entry = c[i + 1]
                    rows.append({"dir": -1, "entry_i": i + 1, "entry": entry,
                                 "r30": entry / c[min(i + 7, len(g) - 1)] - 1,
                                 "r60": entry / c[min(i + 13, len(g) - 1)] - 1,
                                 "rclose": entry / c[-1] - 1})
                if l[i] < prev_low and c[i] > prev_low and o[i] > prev_low:
                    if l[i + 1] < prev_low:
                        continue
                    entry = c[i + 1]
                    rows.append({"dir": +1, "entry_i": i + 1, "entry": entry,
                                 "r30": c[min(i + 7, len(g) - 1)] / entry - 1,
                                 "r60": c[min(i + 13, len(g) - 1)] / entry - 1,
                                 "rclose": c[-1] / entry - 1})
        prev_high, prev_low = h.max(), l.min()
    return pd.DataFrame(rows)


def run_sweep_test(name: str, days: list[pd.DataFrame]) -> None:
    print(f"\n--- Sweep test: {name} ---")
    tr = sweep_trades(days)
    if tr.empty:
        print("  no qualifying sweeps")
        return
    n_short = (tr["dir"] == -1).sum()
    print(f"  {len(tr)} sweep entries ({n_short} PDH shorts, {len(tr)-n_short} PDL longs)")
    for col, label in [("r30", "+30min"), ("r60", "+60min"), ("rclose", "to close")]:
        v = tr[col] * 1e4
        t = v.mean() / (v.std() / np.sqrt(len(v)))
        print(f"    {label:<9} mean {v.mean():+6.1f}bp  t={t:+5.2f}  win {(v>0).mean()*100:.0f}%")

    # placebo: random long/short entries, same days, hold to close
    rng = np.random.default_rng(1)
    real = (tr["rclose"] * 1e4).mean()
    plc = []
    for _ in range(200):
        vals = []
        for g in days:
            c = g["close"].values
            k = rng.integers(1, max(2, len(c) - 2))
            d = rng.choice([-1, 1])
            vals.append(d * (c[-1] / c[k] - 1) * 1e4)
        samp = rng.choice(vals, size=len(tr), replace=True)
        plc.append(samp.mean())
    plc = np.array(plc)
    print(f"    placebo (random-entry hold-to-close): {plc.mean():+.1f} +/- {plc.std():.1f}bp,"
          f"  real {real:+.1f}bp,  P(rand >= real) = {(plc >= real).mean():.3f}")
    print("    (ETF cost context: ~2bp round trip)")


def main() -> None:
    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    files = {
        "SPY": "BATS_SPY, 5.csv", "QQQ": "BATS_QQQ, 5.csv", "IWM": "BATS_IWM, 5.csv",
        "MES": "CME_MINI_MES1!, 5.csv", "MNQ": "CME_MINI_MNQ1!, 5 (1).csv",
    }
    print("=" * 70)
    print("SLEEVE I AUDIT: ChronoMatrix 27-node cycle + sweep-reclaim")
    print("(pre-registered mechanical interpretation - see docstring)")
    print("=" * 70)
    for name, fname in files.items():
        days = day_arrays(load_5m(repo, fname))
        run_cycle_test(name, days)
        run_sweep_test(name, days)


if __name__ == "__main__":
    main()
