"""Audit: weekday-filtered Sleeve E (overnight drift, SPY/QQQ/IWM).

Hypothesis (pre-registered from the 2026-07-11 screen): the overnight
drift concentrates in Tue/Wed/Fri sessions; Mon (weekend hold) and Thu
are the weak sessions across all three ETFs. Candidate variant
"E-TWF" holds overnight only into Tue/Wed/Fri opens.

Seven-section audit in the house style. The dangerous failure mode here
is data-mining (5 weekday buckets x 3 correlated tickers), so Section 2
is the load-bearing test: weekday selection is re-derived on the train
half only, then evaluated frozen on the test half.

Usage: python scripts/audit_overnight_weekday.py
"""
from __future__ import annotations

import itertools

import numpy as np
import pandas as pd
import yfinance as yf

ANN = 252
TICKERS = ["SPY", "QQQ", "IWM"]
COST_PER_SIDE = 0.0001  # 1bp/side, same as audit_overnight.py
CANDIDATE_DAYS = (1, 2, 4)  # Tue, Wed, Fri opens (0=Mon)
DAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri"]


def sharpe(r: pd.Series) -> float:
    r = r.dropna()
    if len(r) < 20 or r.std() == 0:
        return float("nan")
    return float(r.mean() / r.std() * np.sqrt(ANN))


def cagr(r: pd.Series) -> float:
    r = r.dropna()
    if not len(r):
        return float("nan")
    return float((1 + r).prod() ** (ANN / len(r)) - 1)


def maxdd(r: pd.Series) -> float:
    eq = (1 + r.fillna(0)).cumprod()
    return float((eq / eq.cummax() - 1).min())


def overnight_returns(tkr: str) -> pd.Series:
    """Close -> next open, net of cost, indexed by the open's date."""
    d = yf.download(tkr, start="1993-01-01", progress=False, auto_adjust=False)
    if isinstance(d.columns, pd.MultiIndex):
        d.columns = d.columns.get_level_values(0)
    adj = d["Adj Close"] / d["Close"]
    o = d["Open"] * adj
    c = d["Adj Close"]
    gross = (o / c.shift(1) - 1).dropna()
    return gross - 2 * COST_PER_SIDE


def portfolio(rets: dict[str, pd.Series], days: tuple[int, ...]) -> pd.Series:
    """Equal-weight portfolio, holding only overnights into `days`."""
    df = pd.DataFrame(rets)
    port = df.mean(axis=1, skipna=True).dropna()
    mask = port.index.dayofweek.isin(days)
    # Non-traded nights are flat (0), so Sharpe/CAGR stay on daily calendar.
    return port.where(mask, 0.0)


def main() -> None:
    rets = {t: overnight_returns(t) for t in TICKERS}
    df = pd.DataFrame(rets)
    port_all = df.mean(axis=1, skipna=True).dropna()

    print("=" * 66)
    print("AUDIT: weekday-filtered overnight drift (E-TWF: Tue/Wed/Fri)")
    print(f"Universe {TICKERS}, {port_all.index[0].date()} -> "
          f"{port_all.index[-1].date()}, cost {COST_PER_SIDE*1e4:.0f}bp/side")
    print("=" * 66)

    base_full = portfolio(rets, (0, 1, 2, 3, 4))
    base_twf = portfolio(rets, CANDIDATE_DAYS)

    # --- 1. Baseline ---
    print("\n[1] Baseline")
    for name, r in [("E (all nights)", base_full), ("E-TWF", base_twf)]:
        print(f"  {name:<16} Sharpe {sharpe(r):5.2f}  CAGR {cagr(r)*100:5.2f}%"
              f"  MaxDD {maxdd(r)*100:6.1f}%")

    # --- 2. Walk-forward: re-derive day selection on train only ---
    print("\n[2] Walk-forward (day selection re-derived on train half)")
    half = len(port_all) // 2
    train_idx, test_idx = port_all.index[:half], port_all.index[half:]
    train = port_all.loc[train_idx]
    by_day_train = {d: sharpe(train[train.index.dayofweek == d]) for d in range(5)}
    ranked = sorted(by_day_train, key=by_day_train.get, reverse=True)
    picked = tuple(sorted(ranked[:3]))
    print("  Train-half weekday Sharpe: "
          + "  ".join(f"{DAY_NAMES[d]} {by_day_train[d]:.2f}" for d in range(5)))
    print(f"  Train-selected top-3 days: {[DAY_NAMES[d] for d in picked]}"
          f"  (pre-registered: {[DAY_NAMES[d] for d in CANDIDATE_DAYS]})")
    r_train = portfolio(rets, picked).loc[train_idx]
    r_test = portfolio(rets, picked).loc[test_idx]
    r_test_full = base_full.loc[test_idx]
    print(f"  Train Sharpe {sharpe(r_train):.2f} -> Test {sharpe(r_test):.2f}"
          f"   (unfiltered E on test half: {sharpe(r_test_full):.2f})")

    # --- 3. Parameter grid: every day-subset of size 2-4 ---
    print("\n[3] Parameter grid (all weekday subsets, size 2-4)")
    grid = []
    for k in (2, 3, 4):
        for combo in itertools.combinations(range(5), k):
            grid.append((combo, sharpe(portfolio(rets, combo))))
    vals = np.array([s for _, s in grid])
    beat = (vals > sharpe(base_full)).mean()
    print(f"  {len(grid)} subsets: {(vals > 0).mean()*100:.0f}% positive, "
          f"mean {vals.mean():.2f}, {beat*100:.0f}% beat unfiltered E")
    top = sorted(grid, key=lambda x: -x[1])[:5]
    for combo, s in top:
        print(f"    {'/'.join(DAY_NAMES[d] for d in combo):<20} {s:.2f}")

    # --- 4. Sub-periods (5y) ---
    print("\n[4] Sub-periods (5y windows): E-TWF vs E")
    wins = 0
    n_win = 0
    for y0 in range(1993, 2026, 5):
        m_twf = base_twf[(base_twf.index.year >= y0) & (base_twf.index.year < y0 + 5)]
        m_all = base_full[(base_full.index.year >= y0) & (base_full.index.year < y0 + 5)]
        s_t, s_a = sharpe(m_twf), sharpe(m_all)
        n_win += 1
        wins += int(s_t > s_a)
        print(f"    {y0}-{min(y0+4, 2026)}: E-TWF {s_t:5.2f}  vs E {s_a:5.2f}"
              f"  {'TWF' if s_t > s_a else 'E':>4} wins")
    print(f"  E-TWF beats E in {wins}/{n_win} windows")

    # --- 5. Leave-one-out (drop a ticker) ---
    print("\n[5] Leave-one-out ticker drop (E-TWF)")
    s_base = sharpe(base_twf)
    for t in TICKERS:
        sub = {k: v for k, v in rets.items() if k != t}
        s = sharpe(portfolio(sub, CANDIDATE_DAYS))
        print(f"    drop {t}: {s:.2f}  (delta {s - s_base:+.2f})")

    # --- 6. Cost sensitivity ---
    print("\n[6] Cost sensitivity (E-TWF, bp/side)")
    gross = {t: overnight_returns(t) + 2 * COST_PER_SIDE for t in TICKERS}
    for bps in (0, 1, 2, 3, 5, 10):
        r = {t: v - 2 * bps / 1e4 for t, v in gross.items()}
        print(f"    {bps:>2}bp: Sharpe {sharpe(portfolio(r, CANDIDATE_DAYS)):.2f}")

    # --- 7. Placebo: random 3-day subsets vs the chosen one ---
    print("\n[7] Placebo (all C(5,3)=10 subsets ranked + random-night placebo)")
    threes = [(c, sharpe(portfolio(rets, c))) for c in itertools.combinations(range(5), 3)]
    threes.sort(key=lambda x: -x[1])
    rank = [c for c, _ in threes].index(tuple(CANDIDATE_DAYS)) + 1
    print(f"  E-TWF rank among 3-day subsets: {rank}/10")
    # random-night placebo: same *number* of nights, ignoring weekday structure
    rng = np.random.default_rng(0)
    n_nights = int(port_all.index.dayofweek.isin(CANDIDATE_DAYS).sum())
    plc = []
    for _ in range(200):
        idx = rng.choice(len(port_all), n_nights, replace=False)
        mask = np.zeros(len(port_all), bool)
        mask[idx] = True
        plc.append(sharpe(port_all.where(pd.Series(mask, index=port_all.index), 0.0)))
    plc = np.array(plc)
    real = sharpe(base_twf)
    print(f"  Random-{n_nights}-night placebo: {plc.mean():.2f} +/- {plc.std():.2f},"
          f"  real {real:.2f},  P(random >= real) = {(plc >= real).mean():.3f}")


if __name__ == "__main__":
    main()
