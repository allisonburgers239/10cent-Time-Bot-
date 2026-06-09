# 10c Time Bot

A systematic, multi-sleeve trading bot for index futures, futures baskets,
and crypto perpetuals. Built around three of the best-documented
retail-accessible edges in derivatives markets.

## Strategy

| Sleeve | Edge | Instrument | Timeframe | Weight |
|---|---|---|---|---|
| A - Opening Range Breakout | Intraday momentum on NY open | MNQ | 5-min, 1 trade/day | 40% |
| B - Time-Series Momentum   | 12-month trend on futures basket | ~12 liquid futures | Daily, monthly rebalance | 45% |
| C - Crypto Cash-and-Carry  | Funding-rate arbitrage | BTC/ETH spot vs perp | 8h funding | 15% |

Each sleeve has published out-of-sample evidence; the three are
weakly correlated, so the portfolio Sharpe meaningfully exceeds any
single sleeve.

## Evidence

- **ORB**: Zarattini & Aziz, *Can Day Trading Really Be Profitable?* (SSRN, 2023)
- **TSMOM**: Hurst, Ooi & Pedersen, *A Century of Evidence on Trend-Following* (AQR, 2017);
  Moskowitz, Ooi & Pedersen, *Time Series Momentum* (JFE, 2012)
- **Cash-and-carry**: Standard derivatives arbitrage; basis = perp - spot,
  capture funding when basis > execution cost

## Target profile (after costs)

- Net Sharpe: 1.0 - 1.4
- Max drawdown: 12 - 18%
- Annual return: 15 - 25% on allocated capital
- Daily trading effort: ~10 minutes (review + monitoring)

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

Phase 0 - scaffolding. All three sleeves implemented with real-data
backtests.

**Sleeve B - TSMOM** (10-ETF basket, 2007-2026, 229 months, net of 10bps
round-trip): Sharpe 0.71, CAGR 4.06% (at 10% vol/position), MaxDD -14.3%,
monthly win rate 57%. Consistent with AQR Hurst/Ooi/Pedersen 2017 and
Moskowitz-Ooi-Pedersen 2012.

**Sleeve C - Crypto basis** (BTC+ETH equal-weight, 2020-2026, 6.4 years
of Deribit funding history, 5bps per position change): portfolio Sharpe
1.29, CAGR 0.99%, MaxDD -12.4% at 1x notional. BTC standalone Sharpe
2.07; ETH 0.24. Delta-neutral, so the strategy is leverage-scalable -
5x notional brings CAGR into the 5% range at similar Sharpe.

**Sleeve A - ORB** validated against QQQ + 7-ETF basket over ~60 days
(only window with free 5-min data). Portfolio Sharpe near zero on that
sample; longer 5-min history is required before iterating on filters,
otherwise filter selection is just overfitting to noise.

## Quick start

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest                                  # run unit tests
python scripts/run_orb_backtest.py      # synthetic data smoke test
```

## Project layout

```
src/ten_cent_bot/
  data.py        # OHLCV loader + synthetic data generator
  orb.py         # Sleeve A: Opening Range Breakout signal generation
  tsmom.py       # Sleeve B: Time-Series Momentum on multi-asset basket
  basis.py       # Sleeve C: Crypto cash-and-carry on perp funding rates
  risk.py        # Position sizing (1% rule)
  backtest.py    # ORB backtest engine (signals -> equity curve)
  metrics.py     # Sharpe, Sortino, max drawdown, Calmar, win rate
scripts/
  run_orb_backtest.py        # ORB on synthetic data
  fetch_and_run_qqq.py       # ORB on QQQ via yfinance
  multi_ticker_orb.py        # ORB cross-sectional check across ETF basket
  run_tsmom_backtest.py      # TSMOM on 10-ETF basket via yfinance
  run_basis_backtest.py      # Crypto basis on BTC/ETH via Deribit
tests/
  test_orb.py
```

## Disclaimer

For research and personal use. Not financial advice. Past performance
does not guarantee future results. Test in paper before live capital.
