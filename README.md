# 10c Time Bot

A systematic, multi-sleeve trading bot for index futures, futures baskets,
and crypto perpetuals. Built around three of the best-documented
retail-accessible edges in derivatives markets.

## Strategy (original design + iteration)

| Sleeve | Edge | Instrument | Audit status |
|---|---|---|---|
| A - Opening Range Breakout | Intraday momentum on NY open | MNQ / liquid ETFs | **Shelved** - failed audit on 12.5mo real 5-min sample (may revisit with 2-5y data) |
| B - Time-Series Momentum   | 12-month trend on multi-asset basket | ~10 liquid ETFs / futures | **Deployable** - 7/7 robustness checks pass. 2026-10-16: month-end Sharpe 0.71 is the top of a 0.30-0.71 rebalance-day band (mean 0.52); **tranche the rebalance (15th + month-end) -> 0.72 without the date luck** |
| B v2 - CTA-enhanced        | Multi-horizon + vol/corr filters on top of B | Same basket as B | **Shelved** - layers hurt on ETF basket (Sharpe 0.72 -> 0.31) |
| C - Crypto Cash-and-Carry  | Funding-rate arbitrage | BTC/ETH spot vs perp | **Shelved** - failed walk-forward |
| D - Sector XSMOM           | Sector ETF rotation | 9 SPDR sectors | **Shelved** - no real edge |
| E - Overnight Drift        | Buy at close, sell at open next day | SPY/QQQ/IWM | **Deployable** - 7/7 pass, Sharpe 0.73 over 33y OOS |
| E3 - E + gold | Same overnight hold, basket SPY/QQQ/IWM/GLD equal weight | + GLD (MGC on Tradovate) | **Deployable, pending MGC tracking check** - 7/7 pass: E 0.49 -> 0.59 Sharpe, MaxDD -29% -> -22%, both halves up, placebo p<0.001; with the v2 overlay 0.67 / -23% (`overnight.E3_TICKERS`) |
| E v2 - E + reversal sizing | Same trades; 2x size on nights after RSI(2)<10 (~9% of nights) | SPY/QQQ/IWM | **Deployable, switch OFF by default** - 7/7 pass on Sharpe (0.47 -> 0.56 on 2000-2026), MaxDD -29% -> -31.5%; `overnight.E_V2_CONFIG` |
| F - Stock XSMOM (long-only) | Top-N momentum on large-caps | 25 US large-caps | **Shelved** - beats random selection but not SPY buy-and-hold |
| G - COT / AMDX bias | Weekly CFTC positioning phase-mapping on NQ | NQ futures via Tradovate | **Shelved** - systematic version fails audit (p=0.42 vs random) |
| H - Commodity hedger pressure | Cross-sectional long-short on 12 commodities by CFTC Producer/Merchant HP | GC, SI, HG, CL, NG, ZC, ZS, ZW, SB, CT, KC, LE | **Weak-pass** - audit clean, Sharpe 0.15 LS (p<0.001 vs random) |
| E variants - weekday filter / VIX regime / sectors | Conditioning or extending Sleeve E | SPY/QQQ/IWM, 9 SPDR sectors, ^VIX | **Shelved** - all three fail (see Status); E stays as designed |

Each sleeve has published out-of-sample evidence in the academic
literature. Robustness auditing in this repo is what determines whether
that evidence reproduces on our specific implementation and data window.
See **Status** below for current results.

## Evidence

- **ORB**: Zarattini & Aziz, *Can Day Trading Really Be Profitable?* (SSRN, 2023)
- **TSMOM**: Hurst, Ooi & Pedersen, *A Century of Evidence on Trend-Following* (AQR, 2017);
  Moskowitz, Ooi & Pedersen, *Time Series Momentum* (JFE, 2012)
- **Cash-and-carry**: Standard derivatives arbitrage; basis = perp - spot,
  capture funding when basis > execution cost

## Target profile

Two sleeves are audit-clean and deployable:

**Sleeve B (TSMOM, monthly rebalance):**
- Sharpe 0.71 net of 10bps (ETF basket), 0.46 net (futures basket)
- CAGR 4-5% at 10% target vol (scales linearly with leverage)
- Max drawdown -14% (ETF), -11% (futures)
- Expect multi-year flat stretches (2015-2019 was Sharpe ~0)

**Sleeve E (Overnight drift, daily hold-and-flip):**
- Sharpe 0.73 net of 1bp/side (33y OOS, 1993-2026)
- CAGR 8.8% at 1x notional
- Max drawdown -29% (much better than SPY buy-and-hold's -55%)
- Persistent through 7/7 five-year sub-periods including 2008 GFC and 2020 COVID
- Beats SPY buy-and-hold on Sharpe and MaxDD

**Combined B+E portfolio (audited on 2007-2026 overlap window):**

Correlation B <-> E: **-0.045** (essentially uncorrelated - confirmed
empirically, not just theorized).

  Weighting         Sharpe   CAGR    AnnVol   MaxDD
  Sleeve B alone     0.704   4.05%   5.65%   -14.3%
  Sleeve E alone     0.475   5.69%   11.68%  -28.7%
  Combined 50/50     0.748   4.87%   6.37%   -12.3%
  Combined 70/30     0.862   4.54%   5.16%    -9.5%   <- Sharpe-max
  Risk-parity 67/33  0.854   4.58%   5.36%    -9.2%

(E's Sharpe in this overlap window is 0.48 vs 0.73 over its full 33y
history because 2008-2012 was E's weakest sub-period. Combined audit
still passes despite the weaker E slice.)

Combined B+E audit (`scripts/audit_combined_be.py`) - 7/7 pass:

  1. Baseline (50/50)    Sharpe 0.748, CAGR 4.87%, MaxDD -12.3%
  2. Walk-forward        Train 0.574 -> Test 0.899 (STRENGTHENED OOS)
  3. Weight sensitivity  Sweet spot at w_b=0.70
  4. Sub-periods (4y)    8/8 positive - zero losing 4y windows
  5. Leave-one-out       Combined beats both solos
  6. Cost sensitivity    Breakeven ~40bps B + 4bps E (way above real)
  7. Placebo (60 seeds)  Real 0.75 vs random -0.75 +/- 0.17, p<0.001

Deployment implication: at the Sharpe-max 70/30 weighting the combined
portfolio delivers -9.5% MaxDD vs -14% (B) and -29% (E) - meaningful
tail-risk reduction, not just Sharpe improvement. Requires two
execution paths (Tradovate for B, equity broker for E) but the
economic value is now formally supported.

## What's not in this bot

- Novel cycle theories without statistical backing
- Discretionary overrides
- Indicators whose alpha source is unspecified
- Anything that can't be backtested

## Risk and operating rules (what is actually implemented, 2026-11-03)

The original list ("1% risk per trade, 2% daily loss cap, macro blackout,
30-day Sharpe kill switch") was aspirational: nothing fed the kill switch
and nothing enforced the cap. `scripts/audit_e_cooldown.py` measured each
rule on Sleeve E's history before wiring anything:

| Rule | Measured on E v2 (2000-2026) | Status |
|---|---|---|
| 2% daily loss cap, applied as "skip the next entry after a >2% night" | Helps plain E (0.56 -> 0.60) but hurts E v2 (SPY 0.63 -> 0.60, E3 v2 0.67 -> 0.60): the night after a >2% loss averages +16 bp vs +4 normally, i.e. it is the reversal E v2 doubles into | **Removed 2026-11-04** (Temur). Only the drawdown gate brakes E now |
| 30-day rolling Sharpe < 0.3 -> sleeve off (`orchestrator.risk_gate`) | Sleeve off 75% of days; CAGR 8.8% -> 2.3%, Sharpe 0.56 -> 0.40 | **Not wired. Wrong rule for a daily sleeve** (and a 30-day window is meaningless for monthly B). Kept in code for tests only |
| Drawdown circuit breaker (off at -15/-20/-25%, on at a new 120d high) | Sits out most of the sample; E's crashes recover too fast for any auto-off rule (see the VIX-regime diagnostic: the edge is largest right after drops) | **Not wired as auto-off** |
| **Drawdown gate: alert at -15%, hard stop at -25% from the equity-history peak** (`orchestrator.drawdown_gate`) | Never triggered historically on E v2 (MaxDD -31% at 1x would have: that is the point - a human looks) | **Wired** in both tickets; needs `data/equity_history.csv`, which both tickets now append |
| Stale / implausible quote at order time | n/a | **Wired**: no trade if the last 1-min bar is >10 min old or the quote moved >8% vs prior close (`risk.price_is_fresh`, `price_is_plausible`) |
| NYSE holiday + early-close calendar (`calendar_nyse.py`) | n/a | **Wired**: no ticket on non-trading days; early-close days warn to run at 12:50 |
| VIX-scaled sizing of E (`--vol-scale vix`) | Sharpe 0.80 -> 0.92 (E), 0.88 -> 1.00 (E3), MaxDD -31.5% -> -21.1%, placebo p=0.000 | **ON by default since 2026-11-04** (Temur's go); in the QQQ Pine script as the `useVolScale` input (daily VIX close via `request.security`); the MNQ script stays unscaled (1 contract cannot be halved) |
| Dry-run must not fake fills | n/a | **Fixed 2026-11-04**: `monthly_rebalance.py` writes `data/pending_rebalance.json`; positions change only on `--confirm-fills` |
| Equity too small for the Sleeve B basket | at $25k only 3 of 10 markets get a contract (silver, bonds, FX, copper round to 0) | **Warned 2026-11-04** in the ticket (`RebalancePlan.unfunded`, `min_equity_full_basket`); B needs ~$100k+ to be the audited basket |
| Futures contract rolls (`rolls.py`) | n/a | **Wired** in `monthly_rebalance.py`: tracks the contract month per position in `data/state.json`, prints ROLL orders when the held month is past its roll date (equity index 8 days before 3rd Friday, energy/rates ~17th of the month before, metals/grains ~3 days before prior month-end) |
| 1% risk per trade | not applicable to B/E as sized (vol-targeted / 1x notional) | Unchanged; `risk.position_size` exists for stop-based sleeves only |
| Macro-event blackout (FOMC/CPI/NFP +/-30 min) | E enters at 16:00 and exits 09:30, outside every window | Not needed for E; relevant only to a future intraday sleeve |

Equity history is the one new operational input: run each ticket daily /
monthly and `data/equity_history.csv` accumulates; the drawdown gate works
from the second entry.

## Status

Phase 1 - validation. Three sleeves implemented, two audited, one passes.

### Research round 2026-10-15 (branch `research/tv-screens-2026-10`)

Six new edges screened or audited, plus a data-quality finding that
affects Sleeve B. Outputs are captured in `results/*_2026-10-15.txt`.

| Candidate | Script | Verdict |
|---|---|---|
| V - VIX-futures roll-down (vol risk premium) | `audit_vol_carry.py` | **Shelved** as a return sleeve: walk-forward 0.95 -> 0.08, negative since 2024. The long-when-inverted side made money in every crash window (GFC, 2011, Volmageddon, COVID, Aug-2024) -> crash-hedge candidate, not alpha |
| Global overnight (E's edge abroad) | `screen_overnight_global.py` | **Confirmed worldwide**: DAX 1.02, Nikkei 0.99, HSI 0.81, KOSPI 1.32, Nifty 2.55 overnight Sharpe vs <=0 intraday, all placebo p<0.001. Tradable follow-up: Nikkei via CME NKD (needs hourly bars) |
| Turn-of-month overlay on E | `screen_turn_of_month.py` | **Shelved**: TOM is real on SPX 1950+ (t=4.4) but lives in the *intraday* session; every overnight overlay lowers E's Sharpe (0.73 -> 0.58-0.69) |
| Macro announcement days (FOMC + NFP) | `screen_announcement_days.py` | Savor-Wilson premium real 1993-2017 (+15bp/day, t=3.2, p=0.002), fading since 2018. The July FOMC-intraday overlay is the right-sized use; no new sleeve |
| K - Futures carry (roll yield) | `audit_carry.py` + `carry.py` | **Shelved** (21 markets, no energy): carry predicts next-month return (XS IC t=2.3, placebo p=0.02) but the time-series sign rule is Sharpe 0.11, walk-forward 0.16 -> 0.05, below the equal-weight long basket (0.32). Structurally-contango markets (GC, SI, 6J, 6S) sink it and demeaning (Koijen 'carry timing') doesn't fix it. B70/K30 blend: MaxDD -10.3% -> -9.5% for -0.02 Sharpe. Only cell worth a future pre-registered test: cross-sectional, 6m-smoothed (0.39-0.50 across variants) |
| BTC session-of-day | `screen_btc_sessions.py` | **Nothing** (p=0.96 on 2.5y of hourly data) |
| B breadth (10 -> 37 markets) | `audit_tsmom_breadth.py` | Broadening on raw yfinance `=F` **hurts** (0.47 -> 0.38): unadjusted roll gaps are wrong-signed in contango commodities (NG, CL, grains all <= 0). See data finding below |

**Pattern round (same day, later).** A pre-registered battery of 19
classic price patterns on 6 ETFs (`screen_price_patterns.py`, Bonferroni
bar p<0.003), calendar seasonality with literature behind it
(`screen_seasonality.py`), and the July ChronoMatrix audit
(`audit_chronomatrix.py`, Temur's untracked script, output captured):

| Pattern | Verdict |
|---|---|
| Short-term reversal in equity ETFs (3 down closes, RSI(2)<10, fresh 52w low) | **Real** at p<0.003 on SPY/QQQ/IWM (and TLT for streaks); the only cells in the battery that clear the bar. Next-day excess +15-40bp, present in both halves |
| **E + reversal overlay** (`audit_overnight_reversal.py`) | **PASS 7/7 on Sharpe**: E 0.47 -> 0.55 (streak x2) / 0.56 (RSI2 x2); both walk-forward halves up (0.37->0.44, 0.57->0.67); 100% of 28 grid cells above E; placebo p=0.007; all leave-one-out up; MORE cost-robust than E. **Tail cost**: MaxDD -29% -> -37% (streak x2) or -31.5% (RSI2 x2); ES99 -3.3% -> -4.2%. Deployable cells: RSI2 x2 or streak x1.5. No new trades, just size on ~9% of nights. Conflicts with the 2%-daily-cap rule on the same nights E already breaches it |
| Everything else in the battery (engulfing, inside day, NR7, gap fades, MA filters, Monday/Friday, pre-holiday, 3-up momentum) | **Nothing** at the bar; several negative |
| Halloween / sell-in-May (10 world indices) | Same sign in 9/10 markets and both halves, each p~0.07-0.10 vs random 6-month windows; as an overlay on E it does nothing (overnight t=0.6) |
| Faber 10-month SMA timing on the B ETF basket, long-only | Sharpe 0.83 vs 0.63 buy-and-hold, MaxDD -11.6% vs -38.9%, placebo p<0.001. A long-only cousin of B worth a head-to-head in the full-book audit |
| Commodity seasonal windows (11, roll-adjusted) | None pass Bonferroni; soy/corn harvest shorts look good on t but placebo p=0.10/0.29 (seasonal autocorrelation) |
| "AI edge" frameworks (`screen_frameworks.py`, 2026-10-16): trend-filtered oversold, laggard catch-up, correlation-breakdown pairs | Trend filter (close > 200d) adds **nothing** to the RSI(2) reversal already in E v2 (above-200d vs any-trend: same). Laggard catch-up in sector ETFs after big SPY up-days: **nothing** (p 0.6-0.8). Pairs z>2 fade, 8 pre-registered pairs: one hit (XLF~SPY, +29bp/5d, t=2.3, p=0.003) decaying 41 -> 18bp across halves; BTC~QQQ dead in the second half. Not a sleeve. VWAP/liquidity-grab needs intraday history we lack (its cousin, the PDH/PDL sweep test, is dead); the "continuous screener" is a live scan with no backtest, excluded by design |
| TradingView standard indicators + mechanical S/R/trendlines (`screen_indicator_battery.py`, 2026-10-16: 416 tests, 8 ETFs, bar p<0.0015) | **Every "oversold -> long" oscillator clears the bar on the equity ETFs** (RSI14<30, Stochastic<20, Williams%R<-80, CCI<-100, lower Bollinger; +15-200bp over 1-5d, both halves positive on SPY/QQQ/EFA/EEM) - they are all the short-term reversal E v2 already captures. "Overbought -> short" works modestly at 5d (+10-20bp). **Every trend/breakout tool is zero or negative at 1-5d** (MACD, SuperTrend, Donchian, EMA cross, ADX). **Mechanical support bounce, resistance rejection, level breaks and trendline touches: nothing.** Downsizing E v2 on overbought nights (RSI14>70 / Williams>-20, x0.5 / x0): no Sharpe gain (0.56 -> 0.53-0.57); Williams x0.5 trades 0.01 Sharpe for 3.5pp less MaxDD - a sizing preference, not an edge |
| **Single stocks** (`screen_single_stocks.py`, 40 large/mid caps incl. fallen names; `audit_stock_reversal.py`) | Stocks DO show more than the ETFs in-sample: 5-day oscillator reversal clears the bar on 22/40 names (Williams<-80 -> +30bp median/5d), overnight > intraday on 30/40 (AVGO 1.47, F 1.37, TSLA 1.25, AMD 1.23, NVDA 1.20 overnight Sharpe), 52w-low bounce on 10/34 (survivorship-inflated). **Neither survives as a basket.** Weekly reversal L/S bottom-5/top-5: gross 0.17, -0.38 at 10bps (turnover eats it), long-only 0.52 vs EW universe 0.92. "E on stocks" EW overnight: 0.62 at 1bp/side, -0.20 at 3bps (realistic single-stock spread), corr 0.94 with E. Of the four names asked about: V is a mean-reversion machine (every reversal test p<0.001, both halves), NVDA only gap-down fade, TSLA only 52w-high continuation (halves disagree), PLTR nothing and negative on reversal. Same lesson as Sleeve F: single-name edges exist statistically and die at retail costs. **No sleeve** |
| ChronoMatrix 27-node cycle + sweeps (5 instruments) | Cycle claims not supported anywhere (placebo p 0.87-0.96); SPY sweep-to-close +9bp p=0.01 is 1 of 5 at that level = multiple testing. Dead |

**Second pass, 2026-10-16 (open items from the memo that daily data can settle):**

| Item | Script | Verdict |
|---|---|---|
| Long-VIX-when-inverted as a crash hedge on E | `audit_vix_hedge_e.py` | **Shelved as a sleeve, keep as optional insurance.** Pays in 8 of 10 crash windows (2020: E -29% -> book -18%), timing beats random (placebo p=0.025), but no out-of-sample Sharpe gain (test half E 0.59 -> 0.51) and the MaxDD improvement is no better than random timing (p=0.41). Best cell k=0.05, w=1: Sharpe +0.04, MaxDD +2pp |
| Sleeve H on roll-adjusted returns | `audit_h_rolladj.py` | Spliced series flatter every long commodity position: EW long basket 0.53 raw -> 0.21 adjusted. H's long-only top-2 falls 0.53 -> 0.40 but now BEATS the passive basket (the original objection reverses). Long-short dead (-0.06, placebo p=0.95). Still a modest-weight candidate at most; the full-book audit (raw H) said it adds nothing |
| E via MES on Tradovate (one broker) | `screen_e_via_mes.py` | **Works.** 72 overlapping nights: MES 16:00->09:30 vs SPY close->open corr 0.997, beta 1.00, tracking error 4.6bp/night, mean diff -0.7bp. E and E v2 can run on Tradovate; the equity-broker dependency goes away. Caveat: short window; MES forgoes SPY's ~1.3%/yr dividend yield but SPY's overnight already drops by the dividend on ex-dates, so the overnight legs match |
| Full book with E v2 and Faber | `audit_full_book_v2.py` | **B70/E2 30: Sharpe 0.86 -> 0.96, MaxDD -9.5% -> -9.0%, both halves up** (0.75/0.95 -> 0.77/1.15). The gain is what E v2's standalone audit predicts (time-shuffled placebo p=0.18: no extra timing magic, none claimed). Faber-timed basket: 0.90 alone, corr 0.46 with B; adding it looks good on paper (1.03) but a time-shuffled F helps MORE (p=1.0), i.e. its value is overlap with B. Not an addition. Open question for a separate pre-registered audit: is long-only 10m-SMA timing a better B on the ETF basket (0.90 vs 0.69, MaxDD -11.6% vs -14.3%, 2007-2026 only)? |
| Real CPI/NFP dates from TradingView's calendar | probe only | Calendar has history since 2003 but returns ~35KB per year of events; 23 years is too much to route through this channel. First-Friday NFP stands; CPI stays omitted |

**Third pass, 2026-10-16 (where else does E's edge live; clean breadth for B; why E v2 works):**

| Item | Script | Verdict |
|---|---|---|
| Overnight premium across 31 ETFs, all asset classes | `screen_overnight_universe.py` | Strong and placebo-clean in gold (GLD overnight 0.46, intraday 0.04, p=0.005), US mid caps, utilities, REITs, energy, Brazil, high yield. **Negative** in Treasuries (TLT/IEF overnight -0.4/-0.7: bond returns come intraday) and in developed-market ETFs (EFA/EWJ/VGK: their overnight contains the foreign day session). Pre-registered groups vs E on the same window: E+intl worse (0.53 -> 0.38), E+bonds worse, E-multi worse, **E+gold better (0.49 -> 0.59, MaxDD -29% -> -22%)** |
| **E + GLD audit** | `audit_overnight_gold.py` | **PASS 7/7 through the shipped code path.** Walk-forward 0.43 -> 0.75 (E 0.38 -> 0.58); GLD weight grid monotone up to 0.4; 5/6 four-year windows up; leave-one-out: dropping GLD is the only drop; placebo (GLD sign randomized) p<0.001; crash windows all better (GLD leg +14% in 2008-Q4, +9% in Mar-2020, +6% Apr-2025; -8% in 2022). GLD overnight corr with E +0.10. With the v2 overlay: 0.67 Sharpe, -23% MaxDD. Applying the RSI(2) overlay to GLD itself adds nothing (equities-only = all). Tradable as MGC; tracking check pending the 5-min re-export |
| Clean ETF breadth for B (no roll gaps) | `audit_tsmom_etf_breadth.py` | **Breadth does not help on ETFs either**: B10 0.71; +sectors 0.70 (WF 0.92 -> 0.48); +countries 0.48; +rates 0.70; +commodities 0.69 with the best MaxDD (-11.9%) and the most consistent WF (0.68 -> 0.71); all-29 0.59. B10 beats 99% of random 10-ETF subsets of the 29 (p=0.01), so the deployed basket choice carries some in-sample selection. No change to B |
| Why E v2 works: VIX regime | `audit_overnight_reversal.py` s.14 | Nagel (2012) mechanism confirmed: signal-night excess overnight return 6.9bp (low VIX) -> 6.2 (mid) -> 11.4bp (high VIX), significant in every tercile. 52% of signal nights fall in the high-VIX tercile, which is exactly where the overlay's tail cost comes from. Diagnostic, no new rule |

**Fourth pass, 2026-10-16 (deployment realism):**

| Item | Script | Verdict |
|---|---|---|
| **B's rebalance-day luck** | `audit_tsmom_rebalance_day.py` | Same rule sampled on the 5th/10th/15th/20th/25th/month-end: Sharpe 0.49 / 0.71 / 0.51 / 0.30 / 0.42 / **0.71**, mean 0.52, std 0.15. The audited month-end number sits at the top of the timing-luck band; the honest expectation for B is ~0.5. **Tranching (half the book on the 15th, half at month-end) gives 0.72 with MaxDD -13.1%** and removes the dependence on one date. Standard CTA practice, not a fitted parameter - recommended for deployment |
| Final book with E3 | `results/audit_full_book_e3_2026-10-16.txt` | 2007-06 -> 2026-10: E3v2 standalone Sharpe 0.76 / MaxDD -19.1% (E 0.48 / -28.7%). **B70/E3v2 30: Sharpe 1.01, MaxDD -8.2%, halves 0.81/1.21** vs current B70/E30 0.86 / -9.5% (0.75/0.95). Correlation of every E variant with B is ~0 |
| Daily ticket + sizing reality | `daily_overnight_ticket.py` | Dry-run ticket for E/E v2/E3 on both rails with tests. Micro futures can't be sized to 1x below ~$150-200k; ETF shares can. Today's live ticket (2026-10-16 15:21 CT): QQQ fired (RSI2 0.6, x2), SPY marginal (10.6) |
| July studies, outputs captured | `results/execution_e_analysis_*`, `audit_sector_overnight_*`, `audit_overnight_weekday_*` | Continuous prints 15:50-15:55 / 09:30-09:40 do no worse than the auction fills (slightly better, +1.7-2.4bp/night, t~1.6) -> the MES rail has no fill drag. Sector overnight basket corr 0.91 with E, WF 0.76 -> 0.35 (shelved, as in July). Tue/Wed/Fri-only E beats E in 3/7 windows, placebo p=0.05 (shelved) |

**MNQ specifically (2026-10-21, `screen_mnq_sessions.py`, Ali's instrument):**
2 years of hourly NQ=F (yfinance 730-day limit; screen-grade): overnight
16:00->09:30 Sharpe 1.13 (+18.9%/yr) vs RTH 0.19 (+2.9%); the Asia session
(18:00-02:00 ET) carries 42% of the total. The E v2 signal works on the
future itself: 63 signal nights, next-overnight +40.6bp vs +2.8bp (t=2.3),
x2 overlay Sharpe 1.47 vs 1.13. MNQ tracks QQQ's overnight at corr 1.000,
tracking error 2.3bp/night (72 nights). So the MNQ edges are the ones
already audited on QQQ over 26 years: E v2 on QQQ alone = Sharpe 0.63 ->
0.66 with the overlay, CAGR 9.4% -> 12.3%, MaxDD -39% -> -43%, worst night
-16% (`results/e_v2_qqq_only_*`; the overlay helps QQQ less than the 3-ETF basket), and B's trend (NQ is
the strongest single market in B's basket at +0.60). One MNQ is ~$59k of
exposure, so at $25k it is 2.4x leverage on a single-index version of E.
Nothing intraday on NQ has survived (ORB, ChronoMatrix, sweeps).

**Roll adjustment and Sleeve B (corrected 2026-10-16).** Every futures
number in this repo runs on unadjusted front-month series (yfinance `=F`
or TradingView `1!`), which splice contracts without removing the roll
gap. On a 21-market basket heavy in grains and softs that matters a lot
(12-month TSMOM Sharpe 0.24 raw -> 0.45 adjusted). On **B's own basket**
it does not: `audit_tsmom_rolladj.py` on 9 of B's 10 markets (CL missing)
gives Sharpe 0.48 adjusted vs 0.50 raw, MaxDD -9.7% vs -13.2%, placebo
p<0.001 - rates improve, metals and NQ worsen, and it nets out. B as
deployed holds up. The earlier "must be redone before sizing" note in
this section was an over-reach from the 21-market result; the lesson is
that roll adjustment is mandatory for any commodity-heavy basket, not that
B's numbers were wrong.

**Data sources that now work without manual exports:**

- `scripts/fetch_cboe_vx.py` pulls every VIX-futures contract file from
  CBOE's free archive (2004-05 -> listed), `ten_cent_bot/vx_data.py`
  builds VX1/VX2/CM30 with correct P&L across expiries.
- TradingView's official MCP (`mcp.tradingview.com/mcp`, Essential+ plan)
  serves daily/weekly/monthly bars back to listing for any symbol incl.
  continuous futures (`CBOE:VX1!`, `CME_MINI:ES2!`); intraday depth is
  ~1 year on every plan. Monthly interval is `1mo` (`1M` means 1 minute).
  `ten_cent_bot/tv_mcp.py` loads its JSON. Bulk history still has to be
  written to disk by hand or by a script holding the OAuth token; the 42
  monthly 1!/2! files in `data/tv/` were transcribed by workers and each
  verified against the server's own summary (count, first/last, extremes)
  and against yfinance monthly returns (corr 0.99 financials, 0.87-0.96
  grains where roll timing differs). NYMEX energy and HE/HO/PA are missing.

### Sleeve B - TSMOM (deployable)

10-ETF basket (SPY/QQQ/IWM/EFA/EEM/TLT/IEF/GLD/USO/DBC), 2007-2026,
229 months, net of 10bps round-trip:

- Sharpe 0.71, CAGR 4.06% (at 10% vol/position), MaxDD -14.3%
- Monthly win rate 57%
- Consistent with AQR Hurst/Ooi/Pedersen 2017; Moskowitz-Ooi-Pedersen 2012

Robustness audit (`scripts/audit_tsmom.py`) - all seven sections pass:

1. Baseline (reproducibility)              OK   Sharpe 0.72
2. Walk-forward train/test split           OK   0.82 -> 0.62 (delta 0.21)
3. Parameter grid (63 configs)             OK   100% positive, mean 0.57
4. Sub-period analysis (9x 4y windows)     OK   9/9 positive
5. Leave-one-out asset drop                OK   max delta 0.12 (QQQ)
6. Transaction-cost sensitivity            OK   breakeven at 200bps
7. Randomized-signal placebo (100 seeds)   OK   real 0.72 vs placebo -0.26, p<0.001

**Deployment basket (CME futures via Tradovate)** - audited separately
(`scripts/audit_tsmom_futures.py`) since the user's broker is futures-only:

  Basket: ES, NQ, ZN, ZB, GC, SI, HG, CL, 6E, ZC
          (equity x2, rates x2, metals x3, energy, FX, grain)
  Period: 2000-09 -> 2026-06 (310 months, 25.8 years)
  Sharpe at 10bps: 0.46   At realistic ~3bps futures cost: ~0.49
  Walk-forward:   Train 0.50 / Test 0.43, delta 0.07 (highly consistent)
  Sub-periods:    10/11 positive (same 2015-2019 flat as ETF version)
  Placebo:        p<0.001 -- real edge confirmed

Sharpe is lower than the ETF version (0.46 vs 0.71) primarily due to
basket composition (futures version trades intl/broad-commodity ETF
exposures for FX/grain). The deployment-ready audit is the futures
one - the ETF version remains the canonical reference implementation.

### Sleeve E - Overnight drift (deployable)

Buy SPY / QQQ / IWM at the 4pm close, sell at 9:30am the following day's
open. Flat during regular trading hours. Long-only.

The "overnight vs intraday" anomaly is dramatic and clean across 33 years
of daily bars (1993-2026):

  SPY:  Overnight Sharpe 0.95 / Intraday 0.13 / Buy-Hold 0.65
  QQQ:  Overnight 0.98 / Intraday 0.00 / Buy-Hold 0.52
  IWM:  Overnight 1.01 / Intraday -0.10 / Buy-Hold 0.47

Essentially all risk-adjusted return in these ETFs over the last 33
years came from the overnight session. Being long intraday added vol
without adding return.

Portfolio (equal-weight SPY+QQQ+IWM, 1bp/side cost) audit
(`scripts/audit_overnight.py`) - 7/7 sections pass:

  1. Baseline               Sharpe 0.73, CAGR 8.8%, MaxDD -29%
  2. Walk-forward           SPY delta 0.20, QQQ 0.01, IWM 0.003
                            Very stable especially QQQ/IWM.
  3. Parameter grid (32)    53% > 0.5 Sharpe, best 1.28
  4. Sub-periods (5y wins)  7/7 positive, 6/7 > 0.5
                            Weakest 2008-2012 (0.06), still positive.
  5. Leave-one-out          Max delta 0.09 (IWM) - diversified
  6. Cost sensitivity       Breakeven at ~3bps/side; retail is 0.5-1bp
  7. Placebo (100 seeds)    Real 0.73 vs random 0.02 +/- 0.17, p<0.001

Deployment: needs an equity broker with cheap execution. Cobra/DAS
(pending API setup) or IBKR/Alpaca are the natural fits. Tradovate
doesn't trade ETFs.

### Sleeve E variants - weekday filter, VIX regime, sectors (all shelved)

Three attempts to refine or extend the deployed E (2026-07-11); all
fail, which is itself useful - E as designed is the robust version.

**Weekday filter ("E-TWF": hold only into Tue/Wed/Fri opens).** Full-
sample weekday Sharpe looked dramatic (Tue 1.5-1.8 vs Mon/Thu 0.5-0.6
across all three ETFs). Audit (`scripts/audit_overnight_weekday.py`)
kills it at walk-forward: re-deriving the "best 3 days" on the train
half picks a *different* set (Mon/Tue/Fri - Wednesday was the worst
day in H1 at 0.07 and among the best in H2), and the frozen selection
scores 0.39 on the test half vs 0.58 for unfiltered E. Only 4% of the
25 possible day-subsets beat unfiltered E; placebo p=0.08. Weekday
ranking is noise, not structure. Same lesson as B v2: conditioning a
clean edge subtracts.

**VIX-regime filter.** Overnight drift by prior-day VIX expanding
percentile is non-monotone (lowest bucket 0.83, 75-90th 1.24, >90th
0.66); every "hold only when VIX elevated" variant underperforms
unconditional E and decays in the second half (0.63 -> 0.36).

**Sector extension.** The anomaly does generalize to all 9 SPDR
sectors over 28y (`scripts/audit_sector_overnight.py`: EW-9 overnight
Sharpe 0.55 vs intraday -0.02; XLU alone 0.93) - but correlation with
the E portfolio is 0.91. Same trade, lower Sharpe, no diversification.
Bonus from the same script: the repo's 11.5y 60-min sector CSVs
cross-validate the daily-bar result, and hour-of-day decomposition
finds no intraday seasonality that clears a 2bp round-trip.

### Sleeve E v2 - reversal sizing overlay (deployable, off by default)

Found by the 2026-10-15 pattern battery and audited in
`scripts/audit_overnight_reversal.py`. On any night where 2-day RSI of the
ticker's own closes is below 10 (about 9% of nights), E's overnight
position is doubled. No new orders: the same 16:00 buy and 09:30 sell,
larger on signal nights.

  Window 2000-05 -> 2026-10 (limited by IWM), SPY/QQQ/IWM equal-weight, 1bp/side:

  1. Baseline         E Sharpe 0.47 / MaxDD -29.0%  ->  E v2 Sharpe 0.56 / MaxDD -31.5%
  2. Walk-forward     E 0.37 -> 0.57   |   E v2 0.44 -> 0.67   (both halves up)
  3. Grid (28)        100% of k x multiplier x signal cells above E
  4. Sub-periods      5 of 6 five-year windows up
  5. Leave-one-out    up with any ticker dropped
  6. Cost             more cost-robust than E (at 2bps/side: E 0.06, E v2 0.17)
  7. Placebo (300)    random nights at the same frequency: p = 0.007
  8. Tail             worst night -9.7% -> -13.3% (2008-10-23); nights < -4%: 12 -> 21
  9. Parity           `overnight.E_V2_CONFIG` reproduces the audit to 1e-12
  10. Early history   SPY alone 1993-2026: E 0.48 -> v2 0.63, no decade worse
                      (1993-99 flat, 2000-09 -0.01 -> +0.23, 2020-26 0.35 -> 0.65)
  11. Order timing    RSI(2)<10 is knife-edge at the close: with the 15:50 price
                      0.2% off, ~46% of signal days are marginal...
  12. ...but it survives: signal computed on a noisy price (sigma 0.2%) keeps
                      Sharpe 0.54 (clean 0.56, E 0.47); streak rule degrades more

The tail row is the price. The streak variant (3 down closes, 2x) has the
same Sharpe and a worse MaxDD (-37%); streak at 1.5x is the gentle setting
(0.52 / -33%). Unit tests in `tests/test_overnight.py` pin the signal lag
(signal uses closes up to the entry-day close only) and the cost scaling.

To run E v2 in any script that calls `overnight.backtest_*`, pass
`overnight.E_V2_CONFIG` instead of `OvernightConfig()`. The live E process
is unchanged until that is done deliberately.

Alerts: TradingView's MCP only creates plain price-level alerts (no
indicator conditions), so an RSI(2)<10 alert has to be set on tradingview.com
by hand until the daily runner exists.

Deployment rail: `screen_e_via_mes.py` shows MES replicates the SPY
overnight leg (corr 0.997, beta 1.00). **But micro futures cannot be sized
to 1x below roughly $150-200k of equity**: one MES is ~$38k, MNQ ~$59k,
MGC ~$42k, so at $25k the equal-weight targets round to zero and the
minimum book (one contract per leg) is ~8x equity. `daily_overnight_ticket.py`
prints both. Realistic choices: ETF rail at an equity broker (shares size
to any equity), or a futures-only sub-book (e.g. MES alone at $25k = 1.5x)
that is a different, un-audited sleeve.

Daily ticket (dry-run, mirrors `monthly_rebalance.py`):

```bash
python scripts/daily_overnight_ticket.py --equity 25000                 # E3 + v2 overlay, futures rail
python scripts/daily_overnight_ticket.py --equity 25000 --rail etf      # shares
```

Run at ~15:50 ET. It appends today's last price as the provisional close,
computes the RSI(2) overlay per ticker, flags MARGINAL signals (RSI2 within
1 point of 10), sizes per rail, and writes `data/last_overnight_ticket.json`.
Unit tests in `tests/test_daily_ticket.py`.

### Sleeve B v2 - CTA-enhanced Sleeve B (shelved)

Attempted to boost the audited Sleeve B with four CTA-industry-standard
layers: multi-horizon signal blend (3/6/12m), trend-strength filter
(z-score threshold), vol-regime filter (rolling percentile skip),
correlation-adjusted gross exposure.

Audit (`scripts/audit_tsmom_cta.py`) showed each layer either doesn't
help or actively hurts on the 10-ETF basket:

  v1 baseline                Sharpe 0.72
  CTA: multi-horizon only    Sharpe 0.69  (-0.03)
  CTA: trend-strength only   Sharpe 0.59  (-0.12)
  CTA: vol-regime only       Sharpe 0.40  (-0.32)
  CTA: corr-filter only      Sharpe 0.71  (-0.01)
  CTA: FULL stack            Sharpe 0.31  (-0.40)

Only 3% of the 64-config parameter grid beat baseline, and only
marginally. Diagnosis: the ETF basket is already diversified and
vol-scaled; the layers were designed for wider CTA baskets and mostly
cut profitable trades on this universe. v1 remains the deployable
version.

### Sleeve F - Stock XSMOM (shelved)

Long-only cross-sectional momentum on 25 US large-caps (AAPL/MSFT/JNJ/
XOM/JPM/etc, all continuously listed 1993-2026). Both vanilla momentum
and residual momentum (Blitz-Hanauer-Vidojevic 2020, market-beta-adjusted)
tested. Long-short variant loses money on this universe (short side
drags on always-up-drifting large-caps); long-only works nominally.

Audit (`scripts/audit_stock_xsmom.py`), long-only variant:

  Section 1 baseline           Sharpe 0.78, CAGR 16.4%
  Section 4 sub-periods (15)   14/15 positive - persistent
  Section 5 leave-one-out      Max delta 0.04 - not dominated
  Section 6 SPY benchmark      **Sharpe 0.82** (over same 33y period)
  Section 7 placebo (100)      Real 0.78 vs random-5-stocks 0.63 +/- 0.11
                               P(random >= real) = 0.08 (WEAK)

Verdict shelved. The 0.78 headline is misleading. SPY buy-and-hold has
higher Sharpe over the same window (0.82). Random 5-stock selection
from this universe already gets 0.63 - most of the "signal" is just
long large-cap equity beta. Momentum selection adds ~0.15 Sharpe over
random but doesn't clear p<0.05 significance AND doesn't beat SPY.

Real learning: stock XSMOM in the published literature uses 500+
stocks with monthly cross-sectional cap rebalancing. Retail-scale
25-stock replication doesn't reproduce the effect.

### Sleeve H - Commodity hedger pressure (weak-pass)

Fresh implementation of Hong-Yogo (2012) / Basu-Miffre (2013) hedger
pressure on 12 commodity futures. Uses the Disaggregated COT report
(different endpoint and trader categories than Sleeve G) - the
Producer/Merchant category is the theoretically-motivated hedger group.

  HP = (short_hedger - long_hedger) / (short_hedger + long_hedger)

Positive HP -> commercials net short -> speculators demand risk premium
             -> positive expected long-side return.

Universe: GC, SI, HG, CL, NG, ZC, ZS, ZW, SB, CT, KC, LE
Window: 2000-2026 (~26y, 1,384 weekly obs).

Audit (`scripts/audit_commodity_cot.py`) - PASSES on core checks:

  Cross-sectional variants (top-N ranked by HP each week):
    top-2 long-only:  Sharpe 0.53, CAGR 10.5%
    top-3 long-only:  Sharpe 0.52, CAGR 8.8%
    top-3 long-short: Sharpe 0.15 (market-neutral baseline)

  Walk-forward:       Train 0.23 / Test 0.09, CONSISTENT, both halves positive
  Param grid (18):    100% positive Sharpe, mean 0.33
  Placebo (100):      Real 0.15 vs random -0.68, p<0.001 - REAL EDGE

Distinguishing marks vs the shelved sleeves (C, D, F, G):
  - Walk-forward CONSISTENT and both halves positive
  - Every parameter config positive Sharpe (100% of 18)
  - Placebo decisively rejected at p<0.001
  - Signal direction consistent across the asset class

Distinguishing marks vs the deployable sleeves (B, E):
  - Sharpe is much lower (0.15 LS vs 0.72-0.73)
  - Doesn't beat equal-weight commodity buy-and-hold (0.65) on any variant

Verdict: WEAK-PASS. Real edge but modest. First fresh strategy to
survive placebo since Sleeve E. Include at modest weight - different
asset class, different frequency, near-zero expected correlation with
B and E. Fits naturally on Tradovate (futures broker).

### Sleeve G - CFTC COT / AMDX (shelved)

Systematized version of a collaborator-shared discretionary framework
that maps weekly CFTC Traders in Financial Futures (TFF) positioning
to an AMDX phase model (Accumulation / Manipulation / Distribution /
eXpansion) to produce weekly bias on NQ/MNQ.

Audit (`scripts/audit_cot.py`) on 16 years of free CFTC TFF data
(Jun 2010 -> Jul 2026) plus 26 years of NQ weekly prices:

  MD's claim vs my systematic reproduction:
    X phases:        MD 71%   -> systematic 37-43% (worse than random)
    Overall accuracy: MD 56% -> systematic 47.7%
    Baseline:        AMDX Sharpe -0.26   vs NQ buy-and-hold +0.47
    81-config grid:  0% of configs profitable
    Placebo (100):   p = 0.42 - indistinguishable from random weekly bias

The framework's persuasive "success" in the shared conversation was
one big correct bearish call (before the June 5-6 2026 NQ drop). Over
16 years, the signal carries no measurable predictive power.

The CFTC data-loader (`cot.py`) is kept - the free Socrata endpoint is
useful for any future COT-related research; the specific AMDX rule set
just didn't survive systematic validation.

### Sleeve C - Crypto basis (shelved)

Initial unaudited backtest looked great: BTC+ETH equal-weight, 2020-2026
(6.4 years of Deribit funding history), portfolio Sharpe 1.29, BTC
standalone 2.07. Robustness audit (`scripts/audit_basis.py`) showed
the result is entirely a 2020-2021 bull-market funding-spike artifact:

  Walk-forward BTC:  train (2020-2023) 4.01 -> test (2023-2026) -0.65
  Walk-forward ETH:  train (2020-2023) 2.10 -> test (2023-2026) -2.81

  Annual Sharpe (BTC / ETH):
    2020  +7.9 / +5.0     (early bull)
    2021  +11.5 / +9.1    (peak funding ~1.5 bps/8h)
    2022  -11.8 / -13.5   (LUNA/FTX, funding flipped negative)
    2023  +0.7 / +3.8
    2024  +5.8 / +2.3
    2025  -3.5 / -11.4    (funding mean ~0.5 bps/8h, costs dominate)
    2026  -15.3 / -15.2   (partial year, bleeding)

The strategy can't pay its own transaction costs when funding mean
drops below ~1 bps per 8 hours. Do not deploy as-is. May be revisited
with a regime filter (e.g. only trade when 30-day mean funding >
threshold), but that's parameter-tuning to past data unless validated
out-of-sample on fresh data.

### Sleeve D - Cross-sectional sector momentum (shelved)

Attempted as an additional sleeve uncorrelated with B. Universe: 9 SPDR
sector ETFs (XLB, XLE, XLF, XLI, XLK, XLP, XLU, XLV, XLY), 1998-2026
(331 months). Long top-3 by trailing 12-month return, short bottom-3.

Audit (`scripts/audit_xsmom.py`) finds no real edge:

- Baseline Sharpe -0.06 over 28 years (MaxDD -54.5%)
- 84-config grid: only 21% positive, 0% above Sharpe 0.3
- Cost sensitivity: Sharpe is only +0.015 even at zero cost - the
  signal itself carries essentially no edge before transaction costs
- Placebo (random ranks): p-value 0.11, not significant
- Long-only variant: equal-weight benchmark across all 9 sectors has
  Sharpe 0.67; best long-only momentum variant has Sharpe 0.60. The
  momentum selection subtracts edge vs holding the basket equally.

Lesson: the cross-sectional momentum literature (Jegadeesh-Titman 1993,
Asness-Moskowitz-Pedersen 2013) is about **individual stocks** ranked
across hundreds of names. Sector-level aggregates are too coarse for
the same effect to survive - consistent with Moskowitz-Grinblatt 1999
findings that industry momentum is much weaker than stock momentum.

A more ambitious version would rank individual stocks (e.g. S&P 500
constituents). Operationally heavier and out of scope for v1.

### Sleeve A - ORB (incomplete)

Validated against QQQ + 7-ETF basket over ~60 days (the only window
with free 5-min intraday data via yfinance). Portfolio Sharpe near
zero on that sample. Longer 5-min history (Polygon, Databento, or
a broker export) is required before iterating on filters; otherwise
filter selection is overfitting to a 60-day noise window.

### Retail-bot strategies screened on the new intraday data (2026-11-03)

With the issue #3 exports in hand (30-min SPY 2020-, ES regular-hours 2021-,
60-min SPY/QQQ/IWM 2015-) the strategies that retail bots and TradingView
scripts most often run were tested the same way as the sleeves, 1 bp per side,
per-year P&L shown so one good year cannot hide
(`scripts/screen_retail_bot_strategies.py`, `results/retail_bot_strategies_2026-11-03.txt`):

| Strategy | Best cell | Verdict |
|---|---|---|
| Intraday momentum (first 30 min -> last 30 min, Gao et al. 2018) | corr -0.07 on SPY: the sign has flipped | dead; fading it loses too after costs |
| Opening-range breakout (30/60-min range, stop far side, 1% risk) | Sharpe 0.08 SPY | nothing; 2026 -33% |
| Supertrend(10,3) long/flat | Sharpe 0.89 QQQ 60m vs 0.83 buy-and-hold | a trend filter, not an edge; long/short ~0 everywhere |
| Monday-range breakout / fade (Ali's script) | breakout Sharpe 0.49 QQQ, negative 2025-26 | nothing; the fade is negative everywhere |
| Fair value gap, continuation and return-to-gap (Ali's FVG script) | Sharpe -2 to -3 on SPY/ES 30-min | strongly negative; the gap direction is *anti*-predictive at 30 min |
| "3 hit" trendline (Temur's method: two swing points make a line, trade the third touch) | made precise in `scripts/screen_three_hit_trendline.py` (pivot strength 5, touch = within 0.25 ATR, exit after 1-16 bars or on a break); 15m/30m/1h/2h/3h/6h/daily, SPY/QQQ/IWM/ES/NQ | lines do get a third touch 65-85% of the time, but the return after the touch is no better than any random bar, and a line shifted by a random amount gives the same numbers: the line carries no information. Buying support touches lags buy-and-hold everywhere; shorting resistance touches loses everywhere. (`results/three_hit_trendline_2026-11-04.txt`) |

The same day's survey of where bot and AI traders make money
(`results/bot_landscape_survey_2026-11-03.md`) says the same thing from the
outside: every named retail strategy with a following has failed an honest
costed replication, published predictors lose about half their return after
publication, the one retail-open bot edge with real evidence (crypto funding
carry) is our already-shelved Sleeve C, and live LLM-agent trading has no
audited track record. Our two kept sleeves are slow, structural and decades
old, which is the kind that survives.

### Out-of-the-box theories (2026-11-04)

TradingView's chart export turned out to go back much further on indices than
on ETFs (`TVC_DJI, 1D.csv` 1898-, `SP_SPX, 1D.csv` 1871-, both close-to-close
only because historical index opens are not real), so the calendar-type
theories got 80-128 years of data. Script `scripts/screen_out_of_the_box.py`,
full numbers in `results/out_of_the_box_2026-11-04.txt`, follow-ups on the
tradeable ETFs inline there.

| Theory | What the data says | Verdict |
|---|---|---|
| Moon phase (Dichev & Janes 2003) | Dow +4.8 bp/day near new moon vs +2.3 near full, 128 yrs, t 1.3; S&P t 2.0. Holds in most decades. On SPY overnight it adds nothing (0.64 vs 0.63). | real-looking curiosity, no trade |
| Session before an NYSE holiday (Ariel 1990) | Dow +19.5 bp vs +2.2 normal, t 7.1, 128 yrs, both halves strong. On ETFs since 1993 it has faded (SPY +2.8 bp, t 0.6; GLD +8.6, t 2.3). Holding E through the pre-holiday day: Sharpe +0.00 to +0.05. | faded; free +0.2-0.7%/yr if we ever want it |
| Options-expiration week | +4.6 bp/day vs +3.5 average, t 2.5, fading in the second half; OPEX day and quad witching slightly negative, not significant | nothing |
| Turnaround Tuesday | Tuesday after a down Monday +6.6 bp (Dow, t 3.1), but negative 1940s-1970s, positive since 1980. On ETFs the gain is the Monday NIGHT (+12 bp SPY, t 4.5). Adding 2x on those nights to E v2: +0.01 to +0.03 Sharpe, and the placebo (2x after a down close on any other weekday) does as well. | it is E v2's reversal signal wearing a hat |
| Fade the big overnight gap | after a >1% gap either way the day session is positive on average (+11 to +17 bp, t 1-2); fading loses (SPY Sharpe -0.41) | nothing |
| Size the overnight hold by yesterday's volume / range (stress) | overnight return flat across quintiles; 2x on top-quintile days lowers Sharpe on all three ETFs | nothing; E v2's RSI is the right stress gauge |
| Bitcoin day-of-week | Monday +48 bp/day (t 3.3, both halves +), weekends half the Sharpe of weekdays | one cell of seven, note only |
| ES sessions: Asia -> US | sign of the Asia session is *negatively* related to the US day (corr -0.17, t -3.6, 4 yrs hourly ES; NQ agrees). Fading it by year: 2023 +6%, 2024 -12%, 2025 +34%, 2026 +4%. | 2025 artifact until proven otherwise; re-check in a year |

Net: nothing deployable. The two calendar effects with real history (pre-holiday,
new moon) are the kind of thing that was large before index funds and is small
now; the ES session fade is the only one worth re-testing with new data.

### Scalp / day-trade battery (2026-11-04)

Temur's point: a 30% win rate is fine if the winners are big. So every
strategy below reports win rate, average winner, average loser and payoff,
with costs, per instrument (`scripts/screen_scalp_strategies.py`,
`results/scalp_battery_2026-11-04.txt`). Data: 5-minute bars for QQQ/SPY/IWM
(1 year), TSLA/NVDA/PLTR/AMD/AAPL/COIN (1 year, exported from TradingView),
MNQ/MES/M2K/MGC (3.5 months), BTC/ETH perps (2.5 months). Costs per side:
ETF 1 bp, stocks 2 bp, micro futures 0.2-0.9 bp (1 tick + $0.62), crypto 5 bp.
Fills at the next bar's open; stops and targets checked on highs/lows with
the stop assumed first; a random-entry placebo on every instrument.

18 strategies x 17 instruments: opening-range breakouts with targets of 2, 5
and 10 times the risk (the "lose 70%, win big" shape), prior-day high/low
breaks, stop-run reversals, 5-minute RSI(2), EMA 9/21 crosses, 20-bar
breakouts with trailing stops, climax-bar fades, first-30-minute
continuation, last-30-minute long, three-bar momentum and its fade.

Result: **nothing**. The asymmetric breakouts do exactly what Temur
described - 25-35% winners that are 2-5x the losers - and the two sides
cancel to within a few basis points of zero before costs, on every
instrument. The best cell in the whole table (TSLA, 5-min opening range
with a 5x target) is +11 bp per trade with t = 1.1, i.e. noise, and the
same rule loses on PLTR and AMD. Every high-frequency rule (RSI(2), three-bar
momentum/fade, stop-runs) loses roughly its cost per trade, exactly like the
random placebo. Crypto perps at 5 bp per side lose on everything. One
curiosity: the first 30 minutes of the day drifted up strongly in the
2025-26 ETF files (+10 bp/day), but on 2015-2026 hourly data it is +1 bp/day
with t ~1 and flips sign by year, so holding E to 10:00 instead of 09:30 is
not adopted (`results/first_bar_drift_and_e_exit_extension_2026-11-04.txt`).

Why the percentages game does not rescue it: the market prices the stop
distance. A tight stop with a far target buys a low win rate and a high
payoff, a wide stop the reverse, and expectancy lands at the same place -
the drift - minus costs. An edge has to come from a condition where the
distribution itself is shifted (the overnight premium is one); a payoff
shape alone cannot create one.

### Own-ideas round and a self-review of the testing (2026-11-04, evening)

Temur asked whether the batteries could have missed an edge. Four honest
weaknesses, and what was done about each:

1. The scalp fill rule assumed the stop fires first when a bar touches both
   stop and target. Re-run with the optimistic rule (`--optimistic`): the
   verdict does not move (best cells still t 1.1-1.6 on one year of data).
2. Long and short were pooled. Re-run long-only (`--long-only`): same verdict.
3. Default parameters only, to avoid overfitting. Still true; a walk-forward
   parameter sweep is the remaining gap, and it only matters if some cell were
   near significance, which none is.
4. One-year single-stock samples cannot show a small real edge. True, and
   not fixable with chart exports.

Then six ideas of my own, chosen because the data goes back far enough to
answer (`scripts/screen_own_ideas.py`, `results/own_ideas_2026-11-04.txt`):

| Idea | Result |
|---|---|
| **Size the overnight hold by the VIX** (position x min(2, 20/VIX), total capped at 2x) | **Passes the full audit** (`scripts/audit_overnight_volscale.py`, `results/audit_overnight_volscale_2026-11-04.txt`): E basket Sharpe 0.80 -> 0.92, E3 0.88 -> 1.00, E3 MaxDD -31.5% -> -21.1%, worst night -12.0% -> -8.6%, better in all seven 5-year blocks, both halves, every leave-one-out, shuffled-VIX placebo p = 0.000, every (ref, cap) cell in the grid above the baseline. Why it works: the premium per night grows with VIX but the variance grows faster (VIX>35: +1.4 bp at 189 bp std), so equalising risk per night helps. Caveats: CAGR is slightly lower (12.0% -> 11.0%, run gross 1.1x to match), it needs ETF-level costs (at 2 bp/side the gain is gone), and GLD gets no help (VIX is not gold's vol). Built as `overnight.E_V2_VOL_CONFIG` and `daily_overnight_ticket.py --vol-scale vix`, switched **on** by Temur on 2026-11-04 (ticket default; `--vol-scale none` turns it off). |
| Sector overnight reversal (long the worst-3 intraday sectors overnight, short the best-3; hourly 2015-) | nothing: cross-sectional correlation +0.02, long/short -5 bp/night, same as random ranks; shorting sectors overnight just pays the premium away |
| QQQ/SPY ratio reversion (z-score of the ratio, 5-min and hourly) | loses at every window after two legs of costs |
| Single-stock gap fill / fade (5-min, 8 stocks) | gaps >2% fill only 10-30% of the time; fade and ride both land at cost; one PLTR cell at t 2.6 out of 32 cells |
| BTC/ETH drift around funding settlements | +2 bp in the 30 minutes before funding on BTC, t 1.0; 5 bp/side fees make it -24 bp/day |
| Intraday relative strength among the 8 stocks (rank the first hour, trade to the close) | cross-sectional correlation -0.002; nothing |

Net of the day: one real improvement to the sleeve we already run (risk
sizing), zero new edges. That is consistent with everything else: the
overnight premium is the one shifted distribution we can reach with this
data, and the work that pays is running it better, not finding a second one
in intraday bars.

### Daily gap + volume + news scan (Temur's idea, logging since 2026-11-04)

The idea: at ~10:00 ET, find stocks gapping >= 3% on >= 2.5x relative volume
with news inside 12 hours, and read whether the first 30 minutes show an
institutional imbalance (holding above the session VWAP and the pre-market
high = buyers; cascading below VWAP and the pre-market low = sellers).

It cannot be backtested - TradingView keeps no history of what the screener
showed on past mornings - so it is being **forward-logged**:

- `scripts/daily_scan.py` runs the public TradingView scanner (no login),
  pulls 5-minute pre/post-market bars from yfinance, checks the headline feed,
  computes VWAP / pre-market high / verdict, and appends to `results/scan_log.csv`.
- `ops/install_daily_scan.sh` installs it as a launchd job, Mon-Fri 10:00 ET
  (09:00 Central). The Mac has to be awake.
- `scripts/score_scan_log.py` fills in each day's close and scores the log.

**Pre-registered test (so we cannot fool ourselves later):** the verdict at
10:00 predicts 10:00 -> close. Claim: `BUY_IMBALANCE` names beat
`SELL_IMBALANCE` names by more than ~20 bp round trip. First read after ~30
trading days. Anything else that shows up in the log is a new hypothesis to
test next, not a result. Known weakness: TradingView's relative volume is
today-vs-10-day-average, not time-of-day adjusted, so morning readings run hot.

First manual run (2026-11-04, 15:30 ET, 8 names): CRCT and DOX buyers in
control, UNM sellers, the rest two-sided (`results/scan_gap_volume_vwap_2026-11-04.txt`).
Alerts were set at each pre-market high through the TradingView API.

### Volatility-squeeze scanner, and whether a squeeze means anything (2026-11-04)

Temur's ask: scan 1- and 5-minute bars for a Bollinger-inside-Keltner squeeze
(BB(20,2) inside KC(20, 1.5 ATR)), rolling 100-bar volatility, the volume lean
of the last 10 bars, the breakout levels, and alerts 0.05% beyond the range.
Built as `scripts/squeeze_scan.py` (yfinance 1m/5m with pre/post market, no
login; 15-symbol watchlist "10c HF volatility" also created in TradingView).
Alerts are set through the TradingView API on live 1-minute squeezes.

Before trusting the premise, `scripts/screen_squeeze_validity.py` tested it
on 24 five-minute files (ETFs and stocks 1 year, micro futures 3.5 months,
~4,000 squeeze releases; `results/squeeze_validity_2026-11-04.txt`):

- **Size of the move after a squeeze releases:** 10-20% larger than after a
  random bar on single stocks (AMD 1.3x, t 3.3; QQQ/IWM 1.2x, t 2.1-2.6),
  no larger on SPY or the index futures (ratio 0.9-1.0). Real but small.
  "Massive imminent breakout" is not what the data shows.
- **Direction from the volume lean (up-volume share of the last 10 bars):**
  no predictive power anywhere. Correlation with the next move's sign is
  between -0.17 and +0.08; buyers-lean squeezes went up 30-60% of the time.
  Where there is any pattern it is contrarian (AMD, NVDA, TSLA, MES).
- **The breakout trade itself** (buy/sell the first close beyond the range,
  stop at the midpoint, 12 bars): negative on 19 of 24 files, -2 to -11 bp a
  trade, MES t -5.5. Chasing the alert is a losing trade on average.

So the scanner is useful as a map of where ranges are tight and where the
next move will be somewhat bigger than normal; it does not say which way,
and buying the break does not pay. Live state at the first run is in
`results/squeeze_scan_2026-11-04.txt`.

### Trend-exhaustion swing scan, and the audit behind it (2026-11-04)

Temur's ask: daily uptrend (close > EMA200) + 4-hour exhaustion (close below
the lower Bollinger(20,2) and RSI(14) < 30) + bearish sentiment, no earnings
inside 7 days, ranked by the z-distance below the 4-hour SMA20, for a 3-5 day
reversal. Built as `scripts/scan_trend_exhaustion.py` (public TradingView
scanner for the top-50 mid-cap tech universe, earnings date and daily rating;
yfinance hourly bars resampled to two 4-hour session bars a day). "Sentiment"
is TradingView's daily technical rating plus the VIX; there is no
institutional-selling field anywhere, so none is claimed.

Audit (`scripts/audit_trend_exhaustion.py`, `results/audit_trend_exhaustion_2026-11-04.txt`):

| Universe | Signals | 5-day return after signal | Right baseline (uptrend bars) | Excess t | Positive years |
|---|---|---|---|---|---|
| 12 ETFs (SPY/QQQ/IWM + 9 sectors), hourly 2015-2026 | 704 | +81 bp, hit 67% | +14 bp (placebo +14, sd 8) | **6.7** | 12 of 12 (2015-2026) |
| top-50 mid-cap tech, yfinance hourly 2024-2026 | 336 | +53 bp, hit 50% | +41 bp (placebo +41, sd 39) | 0.3 | 2 of 3 (2025: -102 bp) |

So: on broad ETFs the 5-day bounce after "uptrend + oversold 4-hour" is real
and steady - it is the same short-term-reversal effect that E v2 uses, seen
on a 5-day horizon, and the RSI(14)<30 condition carries most of it (+69 bp
alone vs +22 bp for the band alone). On the mid-cap tech stocks Temur asked
about it does not exist in the two years available: no better than any
uptrend bar, 50% hit rate, worst trade -36%. The tight-stop swing version
(stop below the 10-bar low, target the SMA20) also fails on the ETFs: win
rate 23-47%, the stop gets hit before the bounce.

Portfolio simulation of the ETF version (every signal, 5-day hold, 5 slots,
1 bp/side): Sharpe 0.79, MaxDD -9.5%, but only 2.7% a year because the
capital is idle most of the time (1.6 of 5 slots used on average). Candidate
for a slow swing sleeve on ETFs, **not adopted**: it still needs the overlap
test against E v2 (same reversal, same nights) and the full 7-section audit.

Today's scan: zero matches. Every oversold mid-cap tech name (SANM, KTOS,
AMKR, VICR, ONTO, NVMI ...) is 20-46% below its 200-day EMA, so none is in
an uptrend, and half of them report earnings within 5 days. The closest
uptrend name, ESTC, has a 4-hour RSI of 36 and is still above its lower
band. Full table in `results/trend_exhaustion_scan_2026-11-04.txt`.

### Sleeve I candidate - ETF oversold swing: full audit (2026-11-04)

Built as a library sleeve (`src/ten_cent_bot/swing_reversal.py`, 5 tests) and
audited in `scripts/audit_swing_reversal.py` ->
`results/audit_swing_reversal_2026-11-04.txt`. Rule: two 4-hour session bars a
day; buy next open when the 4h close is below the lower Bollinger(20,2), 4h
RSI(14) < 30 and yesterday's close is above the daily EMA(200); hold 10 bars
(5 days), no stop; 1/5 of capital per trade, 5 slots; 1 bp/side. 12 ETFs
(SPY/QQQ/IWM + 9 sectors), 2015-2026, 704 signals.

| Section | Result |
|---|---|
| 0 library == audit | 300 portfolio trades identical to the audit's, max diff 0 |
| 1 baseline | per trade +79 bp, hit 66%, t 7.9; vs any uptrend bar +12 bp, excess t 6.7; positive mean on 12/12 ETFs. Portfolio: Sharpe 0.79, **CAGR 2.7%**, MaxDD -9.6% |
| 2 walk-forward | params chosen on 2015-20 (rsi 30 / hold 15 / k 1.5) -> 2021-26 test Sharpe 1.11; defaults 1.28. But the 2015-20 train period itself: Sharpe 0.14, CAGR 0.4% |
| 3 grid | 54 cells: hold 10-15 all positive (t 3-10); hold 6 (3 days) weak; thr 25 best per trade, fewest trades. Robust, not knife-edge |
| 4 sub-periods | 2015-16 +, **2017-18 negative (-40 bp/trade)**, 2019-20 weak, 2021-26 strong (Sharpe 0.7 / 1.6 / 2.3) |
| 5 leave-one-out | Sharpe 0.67-0.86 for every drop; no single ETF carries it |
| 6 costs | 0.5 -> 5 bp/side: Sharpe 0.81 -> 0.68. Insensitive (5-day hold) |
| 7 placebo | random uptrend bars, same count: +12 bp (sd 8) vs real +79, p = 0.000; shuffled dates p = 0.000 |
| 8 tail | worst trade -8.6% (XLE 2018-02-02), worst week -4.5%, **longest drawdown 897 trading days (3.5 years)**, 5th-percentile trade -3.6% |
| 9 overlap with E v2 | **90% of SPY/QQQ/IWM signals fall on E v2 signal days** (it is the same oversold reversal); sector ETFs are the only new information. Book 80% E3 v2 / 20% swing: Sharpe 0.84 -> 0.91 but CAGR 8.7% -> 7.5% (idle capital drag); corr -0.02 |
| 10 daily bars 1993- | SPY n 19 (+138 bp, t 1.9), QQQ n 12, IWM n 8: too few signals to say anything over 30 years; the effect is a 4-hour, 2015+ finding |

**Verdict: real signal, weak sleeve. Not adopted.** The per-trade edge is
genuine (placebo p = 0 two ways, every ETF positive, robust to parameters and
costs), but as a use of capital it fails the standard: 2.7% a year, flat
for 2015-2020, a 3.5-year drawdown, and 90% overlap with E v2 on the index
ETFs. It earns its keep only when capital is large enough that 20% sitting
mostly idle costs nothing (~$100k+), and even then it lifts the book's Sharpe
by 0.07 while lowering its return. Kept in the library for that day; the
daily scan stays off.

### Forced-flow ideas (2026-11-04 evening): who has to trade on a schedule?

Temur's framing: an edge is money left by people who must trade regardless of
price (the overnight premium = institutions that cannot hold overnight; the
reversal multiplier = margin-call selling that has finished). Four candidates
were named; two are testable with free data today, two are not.

| Idea | Test | Result |
|---|---|---|
| **1. Big stocks down >= 15% in a week on 2x volume, non-earnings, buy the close, hold 5 days** | 398 stocks > $5B today (survivorship-biased: an upper bound), 10 years, earnings weeks removed with yfinance's earnings-date history (`scripts/screen_crash_week_reversal.py`) | Headline looks great: +2.9% next week (t 2.6) vs +0.4% for any week. But 214 of 296 events are March 2020 and most of the rest are the April-2025 tariff week. Split by whether the whole market crashed that week: market-wide weeks +3.4%; single-stock crashes +1.9%; single-stock crashes excluding 2020 and 2025 **+0.2% (t 0.2), below the +0.4% baseline**. The bounce is the index V-recovery, not forced selling in one name. Shelved. |
| **3. Closed-end funds at an unusually wide discount to NAV, hold a month** | 35 CEFs with Yahoo price + NAV history (2004-2026, survivorship in the list), z-score of the discount vs its own 2-year history, widest-5 each month, 5 bp/side (`scripts/screen_cef_discount.py`, variants file) | Real but small. Widest-5: +1.22%/month, Sharpe 0.78, vs +0.87%/month and 0.64 for holding all 35 funds; excess +0.35%/month, t 2.7, both halves, placebo p = 0.000; the gain is entirely discount narrowing (the NAVs of the picked funds return 0.0%). Funds at unusually *narrow* discounts lose -0.76%/month, the mirror image. Caveats: the excess shrinks to +0.1-0.2%/month after 2011 (t 0.9-2.0), halves at 10 bp/side, and the biggest years are 2009, 2010 and 2020 (discounts blow out in panics and close after). The deepest-absolute-discount variant is the strongest (+0.45%/month excess, t 3.6). **Candidate for a slow monthly sleeve** at retail size; needs the full audit and a cleaner fund list (including dead funds) before adoption. |
| 2. Selling overpriced options before earnings | Needs options price history (IBKR account). Not testable here. | Open |
| 4. The overnight premium in other countries (DAX, KOSPI, HSI, Nikkei) | Proven in October on index data; needs futures access and ~$100k to size. | Open; the most certain of the four, parked on capital |

### Day-session forced flows on the most liquid names, and one that passed (2026-11-04 night)

Temur: "you have TradingView, why stop? Look into day trading." Applied his
forced-flow lens to the day session on the most liquid ETFs and stocks
(`scripts/screen_intraday_flows.py`, `results/intraday_flows_2026-11-04.txt`;
22 five-minute files plus SPY 30-min 2020- and hourly 2015-):

| Who has to trade | Prediction | Result |
|---|---|---|
| Leveraged-ETF rebalancing into the close | last 30 min continues a big day | **No.** The last 30 minutes mildly *reverse* the day (SPY -2 to -4 bp, t 3-5 on small-move days), on every instrument, 2015-2026. The documented 2008-2011 effect is gone |
| Institutional VWAP orders worked all day | afternoon continues the morning, more so on high-volume days | No. Negative on most names; the two positive cells (NVDA, PLTR on 1.5x volume) have n 12-26 |
| Dealer hedging on OPEX Fridays | last hour pins / fades the day | No consistent pattern; 11-12 OPEX days per stock, SPY 79 days t -1.4 |
| Pension rebalancing at month/quarter end | last 30 min of the month's last day | Nothing (SPY/QQQ/IWM, 143 month-ends) |
| Overnight panic overshoot at the open | a big gap reverses in the first bar | **Yes, on the index ETFs.** After a gap of -2% or worse, QQQ's first hour is +77 bp (-3% or worse: +152 bp, t 4.3); SPY similar; gap-ups do not reverse. Small gaps: nothing |

The last row is the same event as an improvement to the sleeve we already
run: on those mornings E v2 is *selling* at 09:30, into the overshoot.
**Gap-down hold:** when the open is 2% or more below the previous close, keep
the overnight position until the first bar closes (10:00 on 30-minute bars,
10:30 on hourly) instead of selling at the open. Implemented in the library
(`OvernightConfig.gapdown_hold_thr`, off by default, 42 tests pass) and
audited in `scripts/audit_overnight_gapdown_hold.py`
(`results/audit_overnight_gapdown_hold_2026-11-04.txt`):

| Section | Result |
|---|---|
| baseline, hourly 2015-2026 | E basket Sharpe 0.57 -> 0.71, CAGR 8.7% -> 10.5%; QQQ 0.64 -> 0.92 (+93 bp per event, t 3.1); SPY 0.47 -> 0.59; IWM 0.50 -> 0.52; SPY 30-min 2020- 0.54 -> 0.69 |
| walk-forward | threshold chosen on 2015-20 (-1%), test 2021-26: 0.54 -> 0.61; default -2% also 0.61 |
| grid | every threshold -1% to -3% gives basket 0.70-0.74 vs 0.57; -4% 0.66 |
| by year | hold adds money in 10 of 12 years (2019 -25 bp, 2021 -23 bp); 2020 is 26 of 69 events but every other year is positive too |
| leave-one-out | 0.60 -> 0.76, 0.50 -> 0.57, 0.57 -> 0.79 |
| costs | no trades added or removed; gain survives at every cost level |
| placebo | hold on the same number of random mornings: 0.568 (sd 0.015) vs real 0.713, p = 0.000 |
| tail | worst single day -12.1% -> -9.5%; worst hold 2025-04-03 -243 bp; hit rate 61% over 69 events |
| why | first-bar return by gap: -3% or worse +152 bp, -3..-2% +26 bp, -2..-1% -4 bp, everything else 0 |

**Verdict: passes. Adopted 2026-11-05 (Temur's go).** Live rule: one extra
check at 09:30 - if the open is 2% or more below yesterday's close, hold
until 10:30 (`daily_overnight_ticket.py --morning` prints HOLD/SELL per leg
from live quotes; `overnight.E_V3_CONFIG` is the audited config; both Pine
scripts have `useGapHold`, estimating the gap from the 09:25 pre-market
print because the open is not known before it prints). About 4 mornings a
year per ETF, no extra trades, cuts the worst day. Caveats: a slow
accumulation; 2020 and 2025 supplied the biggest single mornings; IWM gains
nothing.

### Selloff days: which side pays? (2026-11-05, written on a -5.5% QQQ day)

Temur: "sell-offs like this from news are common - how do we capitalize,
shorting or?" (`scripts/screen_selloff_days.py`, `results/selloff_days_2026-11-05.txt`,
`results/e_crashday_holdthrough_2026-11-05.txt`.)

| Question | Answer from the data |
|---|---|
| Short the continuation once the first hour is bad? | **No.** Shorting from 10:30 to the close after a first hour of -1% or worse: flat to negative on SPY/QQQ/IWM 2015-2026; after a -2% morning, shorting the afternoon lost 149 bp on average (n 10). Intraday selloffs mean-revert inside the day |
| Short the day after a crash, or fade a gap-up the next morning? | No. Both lose 30-120 bp per trade |
| Short volatility after a VIX spike? | **No.** Mean positive (+1-2% per 5-10 days, 60-70% hit) but t <= 1.4 and the worst trades are -58%, -85%, -109% of the position. The classic blow-up |
| Rotate into the worst-hit sectors? | Nothing (worst-3 vs best-3 next 5 days: t 0.3, n 37) |
| Where is the bounce after a <= -3% day? | **Not overnight.** The next overnight is flat (-3 bp SPY, -1 bp QQQ). The bounce is the **next day session** (+53 bp SPY, +61 IWM, +80 SPY after -4%) and the next 5 days (+83-134 bp vs +23 unconditional) |
| What does E v2 already get on those nights? | Nothing: the night after a <= -3% day averages -6 to -8 bp. The sleeve's crash money comes from the 2-down-day RSI signal (which fires the night after), not from the first crash night |

That suggested an E extension: after a <= -3% close, do not sell at the
next open; hold through the next day session (one round trip saved). Tested
on daily data 1993-2026 with the VIX-scaled E v2: SPY 0.72 -> 0.82, QQQ 0.75
-> 0.83, IWM 0.77 -> 0.91, GLD worse (0.41 -> 0.34; equities only), E3
basket 1.00 -> 1.14, placebo p 0.005-0.05. **But the gain is old:** by
year, the holds added money 1996-2011 and roughly nothing or a loss since
2012 (SPY 2015 -278 bp, 2020 -194, 2022 -180; QQQ 2022 -321, 2024 -293,
2026 -526); second-half Sharpe 0.71 -> 0.72. The day-after bounce has
faded in the last decade. **Not adopted.** The gap-down hold (previous
section) is the version that still works, because it targets the first 30-60
minutes of the morning, not the whole day.

So for days like today the honest playbook is the one we already have:
be long the overnight after the forced sellers finish (E v2's 2x signal
fires after two down days), scale size down by the VIX, and, once switched
on, hold through the first hour when the open gaps 2% or more. Nothing on
the short side pays after costs.

### 90-minute session cycles (Ali's idea, 2026-11-06)

Ali uses a 90-minute cycle view on MNQ. His saved TradingView scripts do not
contain the cycle logic (checked: AlliKairos, 10Cent AI v2, Golden Zone
Forecaster, Volatility Target Zones), so the three standard readings of
"90-minute cycles" were tested instead, on 34 intraday files (ETFs, 20
stocks, MNQ/MES, SPY 30-min 2020-), blocks anchored at 09:30
(`scripts/screen_90min_cycles.py`, `results/ninety_min_cycles_2026-11-06.txt`):

| Reading | Result |
|---|---|
| Block momentum: block k's direction carries into block k+1 | The opposite, and tiny: -1 to -6 bp per block on almost every instrument (SPY -0.9, QQQ -0.1, MNQ 0.0). The same mild reversal shows on blocks shifted by 45 minutes, so it is generic intraday mean reversion, not a 90-minute clock |
| Sweep of the previous block's high/low that closes back inside, faded over the next block | Negative on most names (AMD -13 bp, JPM -9, XOM -7); flat on the index ETFs; nothing on MNQ/MES |
| Breakout of each block's first-30-minute range, exit at the block's close | Negative on 33 of 34 instruments, hit rate 38-48%, equal to the random-direction placebo |

Verdict: no 90-minute structure in the data beyond the general tendency of
intraday moves to reverse a little, which is below costs. If Ali's rule is
something specific (a particular block, a manipulation-then-expansion
pattern, a time-of-day filter), send the exact rule or the script name and
it gets replicated exactly.

### Earnings nights on large caps: a published edge that is survivorship in our data (2026-11-11)

Idea: everyone must react to an earnings report at a fixed moment, so buy the close before the
report and sell the open after (the "earnings-announcement premium"), and ride the weeks after a
big surprise ("post-earnings drift"). Data: Yahoo earnings calendars (date + before-open/after-close
flag + EPS surprise) for the 450 largest US stocks today, ~35k reports 2002-2026, daily adjusted
open/close, market-adjusted against SPY, 2 bp/side. Scripts: `fetch_earnings.py`,
`fetch_earnings_prices.py`, `fetch_earnings_fallen.py`, `screen_earnings_events.py`; outputs in
`results/earnings_events_screen{,_fallen}_2026-11-11.txt`.

| test | today's top 450 | 162 stocks removed from the S&P 500 since 2000, still listed |
|---|---|---|
| one night, pre close -> post open | +23 bp, t +9.1, both halves | **-2 bp**, t -0.3 |
| after-close reporters only | +35 bp | -13 bp (2016-: **-38 bp**) |
| placebo (same stocks, random nights) | -3 bp | -2 bp |
| ex-post winners / laggards since 2010 | +37 / **-2 bp** | +17 / -19 bp |
| ex-ante laggards (trailing 1y below median) | +16 bp | -18 bp |

The premium only exists in the stocks that went on to become today's winners; the companies that
fell out of the index show nothing or worse, and 193 of the 355 removed names are gone from Yahoo
entirely (acquired/delisted), so the true ex-ante number is below even the blend. A published
full-universe study (Heitz, Narayanamoorthy, Zekhnini, "The Disappearing Earnings Announcement
Premium") finds the US premium gone in recent years. Post-earnings drift: top-vs-bottom quintile
+27 bp per leg over 20 days before 4 legs of cost, second half negative. "Buy after a 10%+ earnings
jump, hold 20 days" (+172 bp) is beaten by the control of any non-earnings 10% up day (+403 bp),
i.e. it is momentum in survivors, not an earnings effect. **Shelved.** The lesson for every stock
screen in this repo: a universe picked today is a list of winners; test on the fallen too.

### Overnight timing audit and single-stock overnight, survivorship-aware (2026-11-11, second round)

**Entry/exit times of E** (`audit_overnight_timing.py`, `results/audit_overnight_timing_2026-11-11.txt`).
Entering at 15:00/15:30/15:45/15:55 instead of the close: the extra leg is 0 within noise everywhere
(SPY 30-min 2020-, hourly 2015-, 5-min 2025-; bootstrap CIs all straddle 0), and on the RSI(2)
signal days the last hour is -13 to -24 bp (the selling that creates the signal is still running), so
buying before the close hurts exactly when E sizes up. Exiting at 10:00-12:00 instead of 09:30:
+0.8 to +1.4 bp on SPY/QQQ (t 1.2-1.4), -1 bp on IWM, CIs straddle 0 - nothing beyond the gap-down
hold already adopted. Night windows on ES/NQ (hourly ETH 2023-, 30-min 2025-): the premium is
front-loaded - 16:00-18:00 carries 30% (ES) / 49% (NQ) of the night in two hours at the lowest
variance, Asia 18:00-02:00 another ~40%, Europe and the US pre-open ~0 - but 2-4 years of data
give CIs that include 0 per window, so no early-exit rule on the MES rail. **Keep 16:00 -> 09:30.**

**Single-stock overnight** (`screen_stock_overnight_fallen.py`, `results/screen_stock_overnight_fallen_2026-11-11.txt`,
2002-2026, equal weight, Yahoo adjusted open/close). The famous names are real: AAPL 0.77, NVDA 1.02,
AVGO 1.26, AMD 1.12, TSLA 1.11, F 1.53 overnight Sharpe over 24 years - and they are the winners again.
The equal-weight basket tells the honest story and it is survivorship-clean, because both sets agree:

| | 428 survivors | 119 fallen ex-S&P names |
|---|---|---|
| gross overnight | +4.2 bp/night, Sharpe 0.95 | +4.3 bp/night, Sharpe 0.81 |
| corr / beta to SPY overnight | 0.97 / 0.98 | 0.92 / 1.12 |
| net Sharpe at 0.5 / 1 / 2 bp per side | 0.72 / 0.50 / 0.05 | 0.62 / 0.44 / 0.06 |
| + E v2 overlay (RSI2<10 -> 2x), net at 1 bp | 0.55 | 0.54 |

So the stock overnight premium is about +1 bp/night above the index's own, at the same risk, in
winners and losers alike (Lou-Polk-Skouras, confirmed here without survivorship). But it is the same
factor (corr 0.97) and it has to be bought across dozens of names at single-stock costs; at 1 bp/side
it lands at 0.50 (0.55 with the overlay), below E v3 on the ETFs (~1.0). **Not adopted**; recorded so
the next "overnight on NVDA/TSLA" idea has its answer.

### Play the other players: who is forced to trade, and when? (2026-11-11, third round)

`screen_other_players.py`, output `results/screen_other_players_2026-11-11.txt`. Three forced
players, each with its own placebo (same rule at random windows / same tickers at random dates).

| player | the forced trade | what the data says |
|---|---|---|
| **Pensions & balanced funds, month-end** (SPY vs TLT, 2002-07 ->, 291 month-ends) | after a month where stocks beat bonds by >3% they must sell stocks / buy bonds in the last sessions, and the reverse after stocks lag | **Candidate.** Fade the forced flow over the last 5 sessions as a pair: +104 bp net per event, t 4.3, n 168, both halves; every cell of a 4x3 grid (threshold 2-5% x last 2/3/5 sessions) positive, t 1.9-4.3; walk-forward (cell chosen on 2002-13) test 2014-26 +91 bp t 3.3 n 85; placebo p = 0.00; both sides pay (short-stocks side +64 bp t 2.9, long-stocks side +178 bp t 3.2); the unconditional month-end spread is -8 bp, so it is not a bond month-end effect. ~8 events a year, ~1% each on the pair notional. Quarter-end version: nothing (p 0.16) - the flow is monthly. Lumpy by year (2020 -15%, 2011 +15%). Literature: Etula, Rinne, Suominen, Vaittinen (2020, JFE) month-end institutional flows |
| **Index funds, S&P 500 changes** (Wikipedia historical components, 200 additions / 85 market-cap deletions with prices, 2005->) | buy the add / dump the delete at the close before the effective date | The +157 bp run-up over the 3 sessions before (t 3.8) is **entirely the announcement-day jump**: 73 events with a >4% single-session move average +435 bp, the other 127 average -3 bp (t -0.1). Without the announcement in hand there is nothing to front-run. Deletions: -91 bp before, no bounce (survivors-only anyway). The one leftover: new members **reverse** after inclusion, short from close(+1) to +20 sessions -143 bp market-adjusted (t -2.1, halves -146/-139) vs +47 bp placebo - a known effect, ~10-17 shorts a year on a $25k book, parked as a candidate |
| **Fund managers, quarter-end window dressing** (428 survivors and 119 fallen names) | buy the quarter's winners / sell its losers in the last 3 sessions | **Nothing** on either set; the placebo windows look the same |

Next step for the month-end pair if wanted: a full audit through a library implementation (costs on
the TLT leg, duration-matched sizing, IEF instead of TLT, the micro-futures rail: MES vs ZN has no
micro, so the ETF rail), then a forward log like the scans. Not adopted yet.

### Sleeve M candidate: month-end stock/bond rebalancing pair - full audit (2026-11-11)

Temur: "go with the month-end pension trade." Library `src/ten_cent_bot/monthend_pair.py` (5 tests),
audit `scripts/audit_monthend_pair.py` -> `results/audit_monthend_pair_2026-11-11.txt`, ticket
`scripts/monthend_pair_ticket.py` (+ `--log` forward record in `results/monthend_pair_log.csv`,
launchd job `ops/com.10c.monthend-pair.plist`, Mon-Fri 15:45 ET; install with
`ops/install_monthend_pair.sh`).

**Rule.** At the close of the session with 5 sessions left in the month: MTD(SPY) - MTD(TLT) > +3%
-> short SPY / long TLT; < -3% -> long SPY / short TLT; equal dollar legs; close both at the
month's last close. ~7 events a year, in the market 14% of the time.

| check | result |
|---|---|
| library == hand computation | max diff 0 over 292 months |
| baseline 2002-07 -> 2026 | 168 events, **+104 bp net/event**, hit 65%, t 4.3, halves +114/+94; both sides pay (+64 / +178 bp) |
| walk-forward (cell chosen on 2002-13) | test 2014-26: +94 bp, t 3.4, n 84 (the chosen cell IS the default 3%/5) |
| sub-periods | 2002-09 +118, 2010-17 +123, 2018-26 +83 bp; 20 of 25 years positive |
| grid 4 thresholds x 4 windows | all 16 cells positive, t 1.9-4.3; L=5 best in every row |
| proxies | SPY/IEF +88, SPY/AGG +90, QQQ/TLT +89, IWM/TLT +91 bp - not a TLT quirk |
| costs | +88 bp at 5 bp/side |
| placebo | random mid-month 5-session windows: -6 bp, p = 0.000; the week BEFORE (sessions -10..-5): -55 bp - the flow is month-end specific |
| tail | worst event -6.3% (2020-04), p5 -4.1%, max 3 losers in a row, worst daily pair move -10.8% |
| legs | stock leg +68 bp (t 3.5), bond leg +36 bp (t 3.0): the pair, not one leg |
| overlap with E v3 | corr 0.00. E v3 0.77 -> E v3 + pair at 0.5x notional **1.01**, MaxDD -21% -> -16%; 2014-: 0.83 -> 1.05 |
| $25k sizing | $12.5k per leg: +$130/event, ~+$870/yr, worst event -$790; the short leg needs a margin account |

October 2026 dry run: signal on Oct 26 (spread -5.1%) = long SPY / short TLT, exit Oct 30 -> about
-1.5% on the pair. That is what a losing event looks like; the audit says 35% of them lose.
**Status: audited, ticket + forward log ready, not yet traded** - installing the launchd job and
putting it on the book (ETF rail, margin account for the short leg) are Temur's calls.

### Old resistance as new support after a selloff (Temur's NVDA note, 2026-11-13)

NVDA fell from 243 to a 148.80 low on Nov 12 and closed 166 that day, off the "150 area, previous
resistance". `screen_polarity_bounce.py` defines the level mechanically (a 60-session pivot high,
later broken by 1% and extended 8%), the event (first return to the level while down >= 8% in 5
sessions; HELD = close back above it), and buys the next open, market-adjusted, 2 bp/side.
551 stocks 2002-2026, survivors and fallen names; the rule flags NVDA on Nov 12 by itself
(level ~152.5, held). Output `results/screen_polarity_bounce_2026-11-13.txt`.

| both sets, next open -> +10 / +20 sessions | n | 10d | 20d |
|---|---|---|---|
| real level, selloff into it, held (the claim) | 2,803 | +74 bp | +146 bp |
| **placebo level** (real level shifted +-7%), held | 6,017 | +72 bp | +118 bp |
| same selloff, **no level nearby**, up-close day | 2,468 | +158 bp | +253 bp |
| real level touched without a selloff, held | 11,404 | +72 bp | +86 bp |
| real level, selloff >= 15% (NVDA-sized), held | 409 | +106 bp | +271 bp (second half -2 bp at 10d) |

The bounce is real but the level is not what causes it: a fake level 7% away gives the same number
and selloffs that land on no level bounce more. "Closed >= 5% off the low on a level" (NVDA's day)
is 0 bp at 10 days. What remains is the plain post-selloff bounce in stocks, already examined
(crash-week reversal, shelved: survivors-inflated, halves decay, 2026 negative). **Shelved**; the
chart level is a place people look, not a place the odds change.

### Two more forced players: the Treasury and tax-loss sellers (2026-11-13)

`screen_auctions_and_taxloss.py`, `audit_preauction_short.py`; auction dates from fiscaldata.treasury.gov
(`data/treasury_auctions.csv`); outputs `results/screen_auctions_and_taxloss_2026-11-13.txt`,
`results/audit_preauction_short_2026-11-13.txt`.

**Treasury auctions - a weak candidate.** Dealers make room before 10y/20y/30y auctions. Short TLT
over the 3 sessions before any of them, one position (no double counting of the 10y/30y pair), 1 bp/side,
2006-2026: in the market 23% of days, +8.2 bp/day (t 3.0), Sharpe 0.64 vs TLT buy-and-hold 0.25,
MaxDD -13%. The same calendar shifted by 6-20 sessions never matches it (0 of 30 shifts; mean -0.18),
and the same days are +7 bp for stocks, so it is not a risk-off window. Zero overlap with Sleeve M
(1 shared day; M 0.77 + this = 1.00). The post-auction rebound does not exist (2015-: -13 bp).
**Why only "weak":** first half 0.19 vs second half 1.00; Sharpe 1.31 in years TLT fell and 0.19 in
years it rose, so much of it is being short bonds in a bond bear market; and the walk-forward cell
chosen on 2006-15 scored 0.33 on 2016- (the default cell 0.90, which is luck of the default). Parked;
revisit if yields trend up again or with intraday data around the 13:00 ET result.

**Tax-loss selling - nothing.** October-end YTD bottom decile, survivors and fallen: the losers are
not sold Nov -> mid-Dec (+3.4% vs SPY), and their mid-Dec -> mid-Jan rebound (+2.1%) is matched by
the WINNERS (+2.6%) and by the same rule anchored on 9 of the other 11 months. It is equal-weight
versus SPY, not a January effect. Shelved.

## TradingView Strategy Tester (forward test without a broker)

`pine/e_v2_overnight.pine` is Sleeve E v2 as a Pine v6 strategy. Load it on
a 5-minute chart of SPY, QQQ, IWM or GLD **with extended hours ON** (E3 = the
same script on all four, one chart each; Pine strategies are single-symbol).
Since 2026-11-04 the orders fill at the next bar's open: the buy goes in on
the 15:55 bar and fills at the 16:00 post-market bar's open (the first
after-hours print, within cents of the closing auction), the sell goes in on
the 09:25 pre-market bar and fills at the 09:30 open (the opening print
exactly). Before that the exit was the 09:30 bar's close, i.e. the 09:35
print, which is not what a market-on-open order gets. Without extended hours
the buy would fill at the next day's open, so the script refuses to run
(runtime error) rather than report wrong trades; a delayed open is handled by
selling on the first regular bar. RSI(2) of the 15:55 closes decides 1x or
2x, commission 0.01%/order. Verified 2026-11-04 on QQQ: TV's exits equal the
official 09:30 opens from the data API to the cent, entries are 2-12 cents
off the close (after-hours first print), and the 2x nights match the daily
RSI list (`results/tv_trades_qqq_2026-11-04_openfill.csv`).

Why this is useful even though the bot has its own backtester: a strategy
left running on a live chart keeps simulating forward on real bars, i.e. a
forward test that needs no API credentials. It is NOT broker paper trading
(nothing is executed) and it is NOT a substitute for the audit (one symbol,
chart-depth data, TV's fill rules).

Reference numbers to check TV against, same fills in Python on the repo's
5-min files (`scripts/replicate_tv_strategy.py`, 2025-06-16 -> 2026-06-29,
$25k, 256 trades each):

  SPY  net +27.8%  win 58%  MaxDD -7.1%     QQQ  net +41.8%  win 56%  MaxDD -6.4%     IWM  net +27.3%  win 57%  MaxDD -13.3%

Those are one bull year; the 26-year audited Sharpe is 0.56, not 2.5. If
TV disagrees with these: 5-min chart with the 15:55 bar present, commission
0.01% per order, "recalculate after order is filled" OFF, bar magnifier OFF,
same date range. Half days (13:00 close) have no 15:55 bar and are skipped.

Verified in TradingView on 2026-11-03 (loaded through the browser into the
team account, QQQ 5-min, chart depth 2025-10-20 -> 2026-11-03):

  QQQ  net +25.7%  MaxDD -9.0%  265 trades  win 51%  PF 1.25  commission load 5.2%

Python replica on the same nights: signal agreement 100%, per-night return
correlation 0.9986 (`results/tv_vs_python_qqq_2026-11-03.txt`). One finding
that cost an afternoon: **TradingView silently drops any order larger than
equity unless the strategy declares margin** - the 2x nights never fired
until `margin_long = 50, margin_short = 50` (shares) / `5` (MNQ) went into the
`strategy()` call. Both Pine files now carry it; without it the tester
shows 1x only and quietly disagrees with the Python.

MNQ (`pine/e_v2_overnight_mnq.pine`, 1 contract / 2 on signal, chart depth
2026-07-19 -> 2026-11-03): +0.7%, MaxDD -19.9%, 75 trades, PF 1.00. Three and
a half months of a 2.4x-levered single index says nothing yet; it is the
forward test, not evidence.

Both strategies are saved in the team TradingView account ("E v2 overnight
(10c)", "E v2 overnight MNQ (10c)") and the QQQ one runs on the layout
"10c E v2 QQQ forward test". Leave that tab open; the trade list is the
forward log.

Chart-data export cap (relevant to issue #3): "Download chart data" writes
the bars loaded on the chart, and a chart loads ~20k bars at most. So
60-min SPY reaches 2015, 30-min SPY (regular hours) 2020, and 30-min ES1!
(23-hour sessions) only 2025. Deeper intraday futures history needs
Databento, not TradingView.

Cheaper data path than manual exports: the "Claude Code Trading Bot"
tutorial Ali shared (Steven Ace Trades, 2026-10-13) buys 16 years of NQ
futures from Databento - that also unblocks the intraday-momentum sleeve on
issue #3. The tutorial's method (real data with fees, unseen-year test,
coin-flip placebo, document, combine, paper trade, size small) is this
repo's harness.

### Broker research for live trading (2026-11-11)

What the book needs: closing- and opening-auction orders (MOC/MOO) for E, 2x overnight margin,
short SPY/TLT for the month-end pair, micro futures (Sleeve B and the futures rail), cheap ETF
commissions, and an API so the tickets can become orders. Verified against current docs/reviews:

| broker | MOC/MOO | shorts + 2x overnight | micro futures | API | cost | verdict |
|---|---|---|---|---|---|---|
| **IBKR Pro** | yes | yes | yes, same account | yes (TWS / Web API) | $0.0035/sh, $1 min (~1 bp on our sizes); $0.85/contract + exchange fees | **one account does everything** |
| IBKR Lite | yes | yes | futures priced as Pro | **no API** | $0 stocks | fine for manual tickets only |
| Alpaca | yes (`opg` / `cls`, cutoffs 09:28 / 15:50 ET) | yes, 2x overnight | **no** | best-in-class, paper mode | $0 | ETF sleeves only; pair with Tradovate for futures |
| Tradovate | n/a (futures) | n/a | yes | yes (already coded, `tradovate.py`) | per-contract | futures rail only |
| tastytrade | **no MOC** on the platform | yes | yes | yes | $0 stocks, $0.75 micro | out: E needs the auction |
| Schwab / thinkorswim | yes on platform | yes | yes on platform | API excludes futures | $0 | manual-only for futures |

Recommendation: **IBKR Pro** as the single account (E on the ETF rail with MOC/MOO, the pair's short
leg, B's micros, one API). Runner-up: **Alpaca + Tradovate** if zero ETF commission and the simplest
API matter more than one account. Our orders are auction orders, so "fast" means automation, not
latency. PDT does not apply (E holds overnight, the pair holds 5 sessions).

## Quick start

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev,data]"
pytest                                  # run unit tests
python scripts/run_orb_backtest.py      # synthetic data smoke test
```

## Running the bot (Sleeve B, monthly rebalance)

Two modes:

### Mode 1 - Manual execution (no credentials needed)

```bash
# First run: pass starting equity. Outputs a trade ticket you execute
# manually on the Tradovate UI.
python scripts/monthly_rebalance.py --source file --equity-override 25000

# Subsequent runs: reads current positions + equity from data/state.json,
# updates the file after computing the new month's orders.
python scripts/monthly_rebalance.py --source file
```

Output is a human-readable trade ticket like:

```
Sleeve B monthly rebalance
As of:           2026-06-30
Account equity:  $25,000.00

Symbol  Current  Target  Action
----------------------------------------
    6E       +0      +0  HOLD
   MCL       +0      +1  BUY 1
   MES       +0      +1  BUY 1
   ZC       +0      +1  BUY 1
...
----------------------------------------
3 order(s) to enter
```

Execute the orders on Tradovate, then update `data/state.json` with the
actual fills (the script writes its computed end state automatically;
adjust the file if fills differ from intent).

### Mode 2 - Automated via Tradovate REST API

Request API access from Tradovate support to get `cid` + `sec`. Then:

```bash
export TRADOVATE_NAME="your_tradovate_login"
export TRADOVATE_PASSWORD="..."
export TRADOVATE_CID=12345
export TRADOVATE_SEC="..."

# Dry-run against demo account (always safe)
python scripts/monthly_rebalance.py --source tradovate --paper

# Live, but still dry-run by default (no orders sent)
python scripts/monthly_rebalance.py --source tradovate

# Actually place orders on the demo account
python scripts/monthly_rebalance.py --source tradovate --paper --auto-fire

# Live trading on real money (only after paper validation)
python scripts/monthly_rebalance.py --source tradovate --auto-fire
```

Cron suggestion (1st trading day of month, 5pm ET):

```cron
0 17 1 * 1-5  /path/to/.venv/bin/python /path/to/scripts/monthly_rebalance.py --source tradovate
```

### Deployment basket

`src/ten_cent_bot/contracts.py:DEPLOYMENT_BASKET` defines the 10
contracts the bot trades. Default uses micros where available (MES,
MNQ, MGC, MCL) so small accounts can size positions in integer
contracts.

## Project layout

```
src/ten_cent_bot/
  data.py        # OHLCV loader + synthetic data generator
  orb.py         # Sleeve A: Opening Range Breakout (shelved)
  tsmom.py       # Sleeve B: TSMOM on multi-asset basket (DEPLOYABLE)
  tsmom_cta.py   # Sleeve B v2: CTA-enhanced TSMOM (shelved - layers didn't help)
  basis.py       # Sleeve C: Crypto cash-and-carry (shelved)
  xsmom.py       # Sleeve D: Sector cross-sectional momentum (shelved)
  overnight.py   # Sleeve E: Overnight drift on equity ETFs (DEPLOYABLE)
  stock_xsmom.py # Sleeve F: Stock-level XSMOM incl. residual momentum (shelved)
  contracts.py   # CME futures contract specs
  orchestrator.py # Monthly rebalance logic + position diff + risk gates
  tradovate.py   # Tradovate REST client (auth, positions, orders)
  das.py         # DAS Trader Pro CMD client (scaffold, awaits Cobra CMD access)
  tv_data.py     # TradingView CSV export loader
  risk.py        # Position sizing (1% rule)
  backtest.py    # ORB backtest engine (signals -> equity curve)
  metrics.py     # Sharpe, Sortino, max drawdown, Calmar, win rate
scripts/
  monthly_rebalance.py       # Deployment entry: trade ticket (file mode) or auto-trade (Tradovate)
  run_orb_backtest.py        # ORB on synthetic data
  fetch_and_run_qqq.py       # ORB on QQQ via yfinance
  multi_ticker_orb.py        # ORB cross-sectional check across ETF basket
  run_tsmom_backtest.py      # TSMOM on 10-ETF basket via yfinance
  run_basis_backtest.py      # Crypto basis on BTC/ETH via Deribit
  run_xsmom_backtest.py      # Cross-sectional sector momentum
  audit_tsmom.py             # Sleeve B audit on ETF basket (PASSES)
  audit_tsmom_futures.py     # Sleeve B audit on Tradovate futures basket (PASSES)
  audit_tsmom_cta.py         # Sleeve B v2 CTA-enhanced audit (SHELVED - no improvement)
  audit_orb.py               # Sleeve A audit on real 5-min TV data (FAILS)
  audit_basis.py             # Sleeve C audit (FAILS walk-forward)
  audit_xsmom.py             # Sleeve D audit (no real edge)
  audit_overnight.py         # Sleeve E audit on SPY/QQQ/IWM daily bars (PASSES)
  audit_stock_xsmom.py       # Sleeve F audit on 25 large-caps (SHELVED - worse than SPY)
  audit_combined_be.py       # Combined B+E portfolio audit (PASSES - Sharpe 0.75 at 50/50, 0.86 at 70/30)
tests/
  test_orb.py
  test_orchestrator.py
```

## Disclaimer

For research and personal use. Not financial advice. Past performance
does not guarantee future results. Test in paper before live capital.
