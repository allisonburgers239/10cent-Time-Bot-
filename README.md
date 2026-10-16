# 10c Time Bot

A systematic, multi-sleeve trading bot for index futures, futures baskets,
and crypto perpetuals. Built around three of the best-documented
retail-accessible edges in derivatives markets.

## Strategy (original design + iteration)

| Sleeve | Edge | Instrument | Audit status |
|---|---|---|---|
| A - Opening Range Breakout | Intraday momentum on NY open | MNQ / liquid ETFs | **Shelved** - failed audit on 12.5mo real 5-min sample (may revisit with 2-5y data) |
| B - Time-Series Momentum   | 12-month trend on multi-asset basket | ~10 liquid ETFs / futures | **Deployable** - 7/7 robustness checks pass |
| B v2 - CTA-enhanced        | Multi-horizon + vol/corr filters on top of B | Same basket as B | **Shelved** - layers hurt on ETF basket (Sharpe 0.72 -> 0.31) |
| C - Crypto Cash-and-Carry  | Funding-rate arbitrage | BTC/ETH spot vs perp | **Shelved** - failed walk-forward |
| D - Sector XSMOM           | Sector ETF rotation | 9 SPDR sectors | **Shelved** - no real edge |
| E - Overnight Drift        | Buy at close, sell at open next day | SPY/QQQ/IWM | **Deployable** - 7/7 pass, Sharpe 0.73 over 33y OOS |
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

## Risk rules (hard-coded)

- 1% risk per trade
- 2% daily loss cap - flatten and stop
- No-trade window for high-impact macro events (FOMC, CPI, NFP +/- 30 min)
- Sleeve kill-switch on 30-day rolling Sharpe < 0.3

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

**Data finding that matters for Sleeve B.** Every futures number in this
repo so far (incl. `audit_tsmom_futures.py`) runs on yfinance's
unadjusted front-month series. On the 21 markets where TradingView
front+second pairs allow a roll-adjusted return, 12-month TSMOM goes from
Sharpe 0.24 (raw) to 0.45 (adjusted), MaxDD -16.9% -> -10.3%; the gap
held at 3, 12, 16 and 21 markets. The futures audit for B must be
redone on roll-adjusted data before it is trusted for sizing.

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
