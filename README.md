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

Phase 0 - scaffolding. Sleeve A (ORB) implemented; B and C pending.

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
  risk.py        # Position sizing (1% rule)
  backtest.py    # Backtest engine (signals -> equity curve)
  metrics.py     # Sharpe, Sortino, max drawdown, Calmar, win rate
scripts/
  run_orb_backtest.py
tests/
  test_orb.py
```

## Disclaimer

For research and personal use. Not financial advice. Past performance
does not guarantee future results. Test in paper before live capital.
