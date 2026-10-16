"""Sleeve E overlay audit: short-term reversal sizing on the overnight hold.

Signal (own ticker, known at the 16:00 close): the day closed down for the
k-th consecutive session (streak), or RSI(2) < 10.  On signal nights E's
overnight position is multiplied by m; all other nights unchanged.  No new
trades: the same 16:00 buy / 09:30 sell, just larger on ~9% of nights.

Origin: screen_price_patterns.py (pre-registered battery, Bonferroni-
significant on SPY/QQQ/IWM/TLT), then screen_reversal_overlay_e.py.
Literature: Lehmann (1990), Jegadeesh (1990) short-term reversal; daily
index autocorrelation turned negative after ~1999 (e.g. Campbell-Lo-
MacKinlay variance ratios; Connors RSI(2) is the practitioner version).

Sections: 1 baseline vs E, 2 walk-forward, 3 grid (k x m x signal),
4 sub-periods, 5 leave-one-out, 6 cost, 7 placebo, 8 tail / risk-rule
interaction.  Verdict needs Sharpe up in BOTH halves, >=80% of grid above
baseline, placebo p<0.05, and a stated answer on the drawdown.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import yfinance as yf

from ten_cent_bot.metrics import max_drawdown, sharpe, sortino

TICKERS = ["SPY", "QQQ", "IWM"]
COST_BPS_SIDE = 1.0


def rsi(c: pd.Series, n: int) -> pd.Series:
    d = c.diff()
    up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    return 100 - 100 / (1 + up / dn.replace(0, np.nan))


def load() -> dict[str, pd.DataFrame]:
    data = yf.download(TICKERS, period="max", interval="1d", auto_adjust=True, progress=False)
    out = {}
    for t in TICKERS:
        df = pd.DataFrame({"open": data["Open"][t], "close": data["Close"][t]}).dropna()
        df["on"] = df["open"].shift(-1) / df["close"] - 1
        down = (df["close"].pct_change() < 0).astype(int)
        df["streak"] = down.groupby((down != down.shift()).cumsum()).cumsum() * down
        df["rsi2"] = rsi(df["close"], 2)
        out[t] = df
    return out


def multiplier(df: pd.DataFrame, k: int, m: float, signal: str) -> pd.Series:
    s_streak = df["streak"] >= k
    s_rsi = df["rsi2"] < 10
    sig = {"streak": s_streak, "rsi2": s_rsi, "either": s_streak | s_rsi, "none": pd.Series(False, index=df.index)}[signal]
    return pd.Series(np.where(sig, m, 1.0), index=df.index)


def portfolio(data: dict, k: int = 3, m: float = 2.0, signal: str = "streak", cost: float = COST_BPS_SIDE, tickers=None) -> pd.Series:
    rets = []
    for t in tickers or TICKERS:
        df = data[t]
        mult = multiplier(df, k, m, signal)
        rets.append(mult * df["on"] - mult.abs() * 2 * cost / 1e4)
    return pd.concat(rets, axis=1).dropna().mean(axis=1)


def S(r: pd.Series) -> dict:
    r = r.dropna(); eq = (1 + r).cumprod()
    return {"sharpe": sharpe(r, 252), "sortino": sortino(r, 252), "cagr": (1 + r.mean()) ** 252 - 1, "mdd": max_drawdown(eq), "n": len(r)}


def fmt(s: dict) -> str:
    return f"Sharpe {s['sharpe']:5.2f}  Sortino {s['sortino']:5.2f}  CAGR {s['cagr']:6.2%}  MaxDD {s['mdd']:6.1%}  n={s['n']}"


def main() -> None:
    data = load()
    base = portfolio(data, signal="none")
    ov = portfolio(data)
    print(f"Window {base.index.min().date()} -> {base.index.max().date()} (limited by IWM)")

    print("\n=== 1. Baseline: E vs E + reversal overlay (k=3, x2, streak) ===")
    print("  E                " + fmt(S(base)))
    print("  E + overlay      " + fmt(S(ov)))
    print("  E + overlay rsi2 " + fmt(S(portfolio(data, signal='rsi2'))))
    print("  E + overlay x1.5 " + fmt(S(portfolio(data, m=1.5))))

    print("\n=== 2. Walk-forward halves (E -> overlay) ===")
    n = len(base) // 2
    for name, sl in [("train", slice(0, n)), ("test", slice(n, None))]:
        print(f"  {name}: E {S(base.iloc[sl])['sharpe']:.2f} -> overlay {S(ov.iloc[sl])['sharpe']:.2f}   ({base.index[sl][0].date()} -> {base.index[sl][-1].date()})")

    print("\n=== 3. Grid: k x multiplier x signal (Sharpe; baseline E in brackets) ===")
    rows = []
    for signal in ["streak", "rsi2", "either"]:
        for k in [2, 3, 4]:
            for m in [1.25, 1.5, 2.0, 3.0]:
                if signal == "rsi2" and k != 3:
                    continue
                s = S(portfolio(data, k=k, m=m, signal=signal))
                rows.append({"signal": signal, "k": k, "m": m, "sharpe": s["sharpe"], "mdd": s["mdd"]})
    g = pd.DataFrame(rows)
    b = S(base)["sharpe"]
    print(g.pivot_table(index=["signal", "k"], columns="m", values="sharpe").round(3).to_string())
    print(f"  baseline E Sharpe [{b:.3f}];  grid cells above baseline: {(g.sharpe > b).mean():.0%} of {len(g)};  MaxDD range {g.mdd.min():.1%} .. {g.mdd.max():.1%}")

    print("\n=== 4. Sub-periods (5y): E Sharpe -> overlay Sharpe ===")
    for start in range(2000, 2027, 5):
        w = (base.index.year >= start) & (base.index.year < start + 5)
        if w.sum() < 300:
            continue
        print(f"  {start}-{start+4}: {S(base[w])['sharpe']:+.2f} -> {S(ov[w])['sharpe']:+.2f}   MaxDD {S(base[w])['mdd']:.1%} -> {S(ov[w])['mdd']:.1%}")

    print("\n=== 5. Leave-one-out ticker ===")
    for drop in TICKERS:
        keep = [t for t in TICKERS if t != drop]
        print(f"  drop {drop}: E {S(portfolio(data, signal='none', tickers=keep))['sharpe']:.2f} -> overlay {S(portfolio(data, tickers=keep))['sharpe']:.2f}")

    print("\n=== 6. Cost sensitivity (bps per side; overlay pays 2x cost on signal nights) ===")
    for c in [0.5, 1.0, 2.0, 3.0, 5.0]:
        print(f"  {c:>3.1f} bps: E {S(portfolio(data, signal='none', cost=c))['sharpe']:.2f} -> overlay {S(portfolio(data, cost=c))['sharpe']:.2f}")

    print("\n=== 7. Placebo: random signal nights, same frequency per ticker (300 seeds) ===")
    rng = np.random.default_rng(41)
    real = S(ov)["sharpe"]
    pl = []
    for _ in range(300):
        rets = []
        for t in TICKERS:
            df = data[t]; f = (df["streak"] >= 3).mean()
            mult = pd.Series(np.where(rng.random(len(df)) < f, 2.0, 1.0), index=df.index)
            rets.append(mult * df["on"] - mult * 2 * COST_BPS_SIDE / 1e4)
        pl.append(sharpe(pd.concat(rets, axis=1).dropna().mean(axis=1), 252))
    pl = np.array(pl); p = float((pl >= real).mean())
    print(f"  real {real:.3f}  placebo {pl.mean():.3f} +/- {pl.std():.3f}  P(placebo>=real)={p:.3f}  {'REAL' if p<0.05 else 'WEAK' if p<0.2 else 'NONE'}")

    print("\n=== 8. Tail and risk-rule interaction ===")
    r = ov.dropna(); rb = base.dropna()
    print(f"  worst night: E {rb.min():.2%} ({rb.idxmin().date()})  overlay {r.min():.2%} ({r.idxmin().date()})")
    print(f"  nights < -2%: E {(rb < -0.02).sum()}  overlay {(r < -0.02).sum()}    nights < -4%: E {(rb < -0.04).sum()}  overlay {(r < -0.04).sum()}")
    print(f"  skew E {rb.skew():.2f} overlay {r.skew():.2f};  ES99 E {rb[rb <= rb.quantile(0.01)].mean():.2%} overlay {r[r <= r.quantile(0.01)].mean():.2%}")
    for label, a, b_ in [("2008-09/10", "2008-09-01", "2008-10-31"), ("2020-02/03", "2020-02-20", "2020-03-31"), ("2022", "2022-01-01", "2022-12-31"), ("2025-04 tariff", "2025-04-01", "2025-04-15")]:
        print(f"  {label:<14} E {rb.loc[a:b_].sum():+7.2%}   overlay {r.loc[a:b_].sum():+7.2%}")
    print("  Note: the README's 2% daily loss cap and 1% risk-per-trade rule are already exceeded by E at 1x on a bad night; a 2x night doubles that. The honest deployment choice is x1.5 or sizing the whole sleeve so that 2x on a signal night stays inside the cap.")


if __name__ == "__main__":
    main()


def library_parity() -> None:
    """Section 9: the deployable code path (ten_cent_bot.overnight with
    E_V2_CONFIG) must reproduce this audit's numbers, or the audit is not
    an audit of what ships."""
    from ten_cent_bot import overnight as ov_lib

    data = load()
    frames = {t: df[["open", "close"]] for t, df in data.items()}
    lib = ov_lib.backtest_portfolio(frames, ov_lib.E_V2_CONFIG)["portfolio_return"]
    lib = lib.loc[: pd.Timestamp("2026-10-14")]
    here = portfolio(data, signal="rsi2", m=2.0)
    j = pd.concat([lib.rename("lib"), here.rename("audit")], axis=1).dropna()
    print("\n=== 9. Library parity: ten_cent_bot.overnight E_V2_CONFIG vs this script ===")
    print(f"  overlap days {len(j)}  max |diff| {(j.lib - j.audit).abs().max():.2e}  Sharpe lib {sharpe(j.lib, 252):.3f} vs audit {sharpe(j.audit, 252):.3f}")
    assert (j.lib - j.audit).abs().max() < 1e-12, "library and audit disagree"
    print("  OK - what ships is what was audited")


if __name__ == "__main__":
    library_parity()


def gap_checks() -> None:
    """Sections 10-11, added 2026-10-16 after self-review.
    10. Early history: E v2 on SPY alone from 1993 and SPY+QQQ from 1999 (the
        main audit starts 2000 because of IWM).
    11. Execution: a market-on-close order must be entered by 15:50, before the
        close that the signal uses.  How often would the signal computed from a
        15:50 price (close +/- 0.2%) differ from the one at the true close?"""
    from ten_cent_bot import overnight as ov_lib

    data = yf.download(["SPY", "QQQ"], period="max", interval="1d", auto_adjust=True, progress=False)
    print("\n=== 10. Early history (library path, E_V2_CONFIG) ===")
    for tks, start in [(["SPY"], "1993-01-01"), (["SPY", "QQQ"], "1999-03-10")]:
        frames = {t: pd.DataFrame({"open": data["Open"][t], "close": data["Close"][t]}).dropna().loc[start:] for t in tks}
        e = ov_lib.backtest_portfolio(frames, ov_lib.OvernightConfig())["portfolio_return"]
        v2 = ov_lib.backtest_portfolio(frames, ov_lib.E_V2_CONFIG)["portfolio_return"]
        for lab, s in [("E", e), ("E v2", v2)]:
            st = S(s)
            print(f"  {'+'.join(tks):<8} {start[:4]}-2026 {lab:<5} " + fmt(st))
        for a, b in [("1993-01-01", "1999-12-31"), ("2000-01-01", "2009-12-31"), ("2010-01-01", "2019-12-31"), ("2020-01-01", "2026-12-31")]:
            ee, vv = e.loc[a:b], v2.loc[a:b]
            if len(ee) > 300:
                print(f"      {a[:4]}-{b[:4]}: E {sharpe(ee,252):+.2f} -> v2 {sharpe(vv,252):+.2f}")

    print("\n=== 11. Signal stability between 15:50 and the close (SPY, RSI2<10) ===")
    c = data["Close"]["SPY"].dropna()
    base = (ov_lib.rsi(c, 2) < 10)
    for bump in [0.001, 0.002, 0.005]:
        flips = 0; tot = 0
        for sgn in (1, -1):
            c2 = c.copy(); c2.iloc[:] = c.values; c2 = c2 * 1.0
            alt = c2.copy(); alt.iloc[:] = c.values * (1 + sgn * bump)
            # only the LAST close is uncertain at 15:50; emulate by recomputing RSI with today's close bumped, yesterday's exact
            r_alt = ov_lib.rsi(pd.concat([c.shift(1).iloc[1:], alt.iloc[-1:]]).dropna(), 2)  # cheap proxy not used
        # exact per-day emulation: recompute RSI where today's close is bumped, all prior closes exact
        d = c.diff(); up = d.clip(lower=0); dn = -d.clip(upper=0)
        up_e = up.ewm(alpha=0.5, adjust=False).mean(); dn_e = dn.ewm(alpha=0.5, adjust=False).mean()
        res = {}
        for sgn in (1, -1):
            d_alt = c * (1 + sgn * bump) - c.shift(1)
            up_alt = 0.5 * up_e.shift(1) + 0.5 * d_alt.clip(lower=0)
            dn_alt = 0.5 * dn_e.shift(1) + 0.5 * (-d_alt.clip(upper=0))
            rsi_alt = 100 - 100 / (1 + up_alt / dn_alt.replace(0, np.nan))
            sig_alt = (rsi_alt < 10)
            res[sgn] = (sig_alt != base) & base.notna()
        flip = (res[1] | res[-1])
        print(f"  price off by {bump:.1%} at 15:50: signal differs on {flip.mean():.2%} of days ({flip.sum()} days), i.e. {flip.sum()/max(base.sum(),1):.0%} of signal days are marginal")


if __name__ == "__main__":
    gap_checks()


def noisy_signal_test() -> None:
    """Section 12: the live order goes in at ~15:50 on a price that is not
    yet the close.  Recompute each signal with today's close perturbed by
    N(0, sigma) before deciding, keep the TRUE overnight return, and see what
    survives.  sigma=0.2% is a typical 10-minute SPY move."""
    from ten_cent_bot import overnight as ov_lib

    data = load()
    rng = np.random.default_rng(99)
    print("\n=== 12. Signal computed on a noisy 15:50 price (true overnight return kept), SPY/QQQ/IWM ===")
    print(f"  {'variant':<22} {'sigma':>6} {'Sharpe':>7} {'MaxDD':>7}   (clean-signal reference in brackets)")
    for signal, m in [("rsi2", 2.0), ("streak", 2.0), ("streak", 1.5), ("either", 2.0)]:
        clean = S(portfolio(data, signal=signal, m=m))
        for sigma in [0.001, 0.002, 0.004]:
            shs = []; mdds = []
            for _ in range(20):
                rets = []
                for t in TICKERS:
                    df = data[t]
                    c_noisy = df["close"] * (1 + rng.normal(0, sigma, len(df)))
                    # yesterday's closes exact, today's noisy: rebuild the series day by day is costly;
                    # approximate by perturbing only the last close used in each signal via a shifted series
                    close_for_signal = pd.Series(np.where(True, c_noisy, df["close"]), index=df.index)
                    cfg = ov_lib.OvernightConfig(reversal_signal=signal, reversal_multiplier=m)
                    fire = ov_lib.reversal_signal(pd.concat([df["close"].shift(1).iloc[1:], close_for_signal.iloc[-1:]]).iloc[:0] if False else close_for_signal, cfg)
                    mult = pd.Series(np.where(fire, m, 1.0), index=df.index)
                    rets.append(mult * df["on"] - mult * 2 * COST_BPS_SIDE / 1e4)
                port = pd.concat(rets, axis=1).dropna().mean(axis=1)
                st = S(port); shs.append(st["sharpe"]); mdds.append(st["mdd"])
            print(f"  {signal + ' x' + str(m):<22} {sigma:>6.1%} {np.mean(shs):>7.3f} {np.mean(mdds):>7.1%}   [{clean['sharpe']:.3f} / {clean['mdd']:.1%}]")
    print("  Note: noise applied to every close in the signal series (harsher than reality, where only today's price is uncertain).")


if __name__ == "__main__":
    noisy_signal_test()


def overbought_downsize_test() -> None:
    """Section 13 (2026-10-16): the indicator battery found 'overbought -> short
    5d' on the equity ETFs.  E v2 is long every night; the pre-registered
    question is whether DOWNSIZING on overbought nights adds to it.
    Variants fixed in advance: x0.5 or x0 when RSI(14) > 70, or when
    Williams %R(14) > -20, on top of E v2 (RSI2<10 x2)."""
    data = load()
    hi = {}; lo = {}
    for t, df in data.items():
        c = df["close"]
        d = c.diff(); up = d.clip(lower=0).ewm(alpha=1 / 14, adjust=False).mean(); dn = (-d.clip(upper=0)).ewm(alpha=1 / 14, adjust=False).mean()
        rsi14 = 100 - 100 / (1 + up / dn.replace(0, np.nan))
        # Williams %R needs highs/lows; approximate with close-based 14d range (no H/L in load())
        hh = c.rolling(14).max(); ll = c.rolling(14).min()
        wr = -100 * (hh - c) / (hh - ll).replace(0, np.nan)
        hi[t] = (rsi14 > 70); lo[t] = (wr > -20)
    print("\n=== 13. E v2 + downsizing on overbought nights (SPY/QQQ/IWM, 1bp/side) ===")
    base_v2 = portfolio(data, signal="rsi2", m=2.0)
    print("  E v2 (RSI2<10 x2)                      " + fmt(S(base_v2)))
    for label, cond, w in [("+ x0.5 when RSI14>70", hi, 0.5), ("+ x0 when RSI14>70", hi, 0.0), ("+ x0.5 when Williams%R>-20", lo, 0.5), ("+ x0 when Williams%R>-20", lo, 0.0)]:
        rets = []
        for t, df in data.items():
            mult = multiplier(df, 3, 2.0, "rsi2")
            mult = mult * np.where(cond[t].reindex(df.index).fillna(False), w, 1.0)
            rets.append(mult * df["on"] - mult.abs() * 2 * COST_BPS_SIDE / 1e4)
        port = pd.concat(rets, axis=1).dropna().mean(axis=1)
        h = len(port) // 2
        print(f"  {label:<38} " + fmt(S(port)) + f"   halves {sharpe(port.iloc[:h],252):.2f}/{sharpe(port.iloc[h:],252):.2f}   nights affected {np.mean([cond[t].mean() for t in data]):.0%}")
    on = pd.DataFrame({t: data[t]["on"] for t in data}).dropna()
    for label, cond in [("RSI14>70", hi), ("Williams%R>-20", lo)]:
        m = pd.DataFrame({t: cond[t] for t in data}).reindex(on.index).fillna(False).astype(bool)
        sel = on[m].stack().dropna(); rest = on[~m].stack().dropna()
        print(f"  overnight mean on {label} nights: {sel.mean()*1e4:+.1f}bp vs other nights {rest.mean()*1e4:+.1f}bp  (t of diff {((sel.mean()-rest.mean())/np.sqrt(sel.var()/len(sel)+rest.var()/len(rest))):+.2f})")


if __name__ == "__main__":
    overbought_downsize_test()


def vix_regime_diagnostic() -> None:
    """Section 14 (2026-10-16): Nagel (2012, 'Evaporating Liquidity') predicts
    short-term reversal returns rise with VIX because reversal = compensated
    liquidity provision.  Diagnostic only (no new rule): E v2's signal-night
    excess overnight return by VIX tercile at the signal close."""
    data = load()
    vix = yf.download("^VIX", period="max", interval="1d", progress=False)["Close"].squeeze()
    vix.index = pd.to_datetime(vix.index).tz_localize(None)
    print("\n=== 14. E v2 signal nights by VIX regime (RSI2<10, next overnight, SPY/QQQ/IWM pooled) ===")
    rows = []
    for t, df in data.items():
        v = vix.reindex(df.index).ffill()
        sig = (df["rsi2"] < 10)
        rows.append(pd.DataFrame({"on": df["on"], "sig": sig, "vix": v}))
    pool = pd.concat(rows).dropna()
    pool["tercile"] = pd.qcut(pool["vix"], 3, labels=["low VIX", "mid VIX", "high VIX"])
    print(f"  {'regime':<9} {'VIX range':>12} {'signal nights':>13} {'signal ON mean':>14} {'other ON mean':>13} {'excess':>8} {'t':>6}")
    for k, g in pool.groupby("tercile", observed=True):
        s = g[g.sig]["on"]; o = g[~g.sig]["on"]
        ex = s.mean() - o.mean(); t = ex / np.sqrt(s.var() / len(s) + o.var() / len(o))
        print(f"  {k:<9} {g.vix.min():>5.1f}-{g.vix.max():<5.1f} {len(s):>13} {s.mean()*1e4:>13.1f}bp {o.mean()*1e4:>12.1f}bp {ex*1e4:>7.1f}bp {t:>6.2f}")
    hi = pool[pool.tercile == "high VIX"]; lo = pool[pool.tercile == "low VIX"]
    print(f"  worst signal night: high-VIX {hi[hi.sig].on.min():.2%}, low-VIX {lo[lo.sig].on.min():.2%}; share of signal nights in high-VIX tercile {(pool[pool.sig].tercile=='high VIX').mean():.0%}")
    print("  Reading: excess rising with VIX = the liquidity-provision mechanism; it also says the overlay's extra size is concentrated in stressed markets, which is where the tail cost comes from.")


if __name__ == "__main__":
    vix_regime_diagnostic()
