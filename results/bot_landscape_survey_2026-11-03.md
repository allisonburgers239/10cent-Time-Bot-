# Where bot / AI traders actually make money — survey, 2026-11-03

Web survey (sources below) done to answer: "we're not the only ones doing this —
where do people trading with bots or AI make money, and what of that is open to
a two-person retail team ($25k-$200k, Python + TradingView, no colocation)?"

## 1. Machine-learning return prediction — retail-available: marginal
- Gu, Kelly & Xiu 2020 (RFS; https://www.nber.org/papers/w25398): trees/neural nets beat
  linear models on 30k US stocks 1957-2016. No transaction costs modelled.
- Avramov, Cheng & Metzker 2023 (Mgmt Sci; https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3450322):
  the ML profit sits in microcaps / hard-to-arbitrage names and shrinks sharply at realistic costs.
- Kirtac & Germano 2024 (https://arxiv.org/abs/2412.19245): LLM news sentiment, Sharpe 3 after
  10 bps, Aug 2021-Jul 2023. One backtest, one regime, not replicated.
- Verdict: the signal is real in academic samples; it survives costs only in corners a small
  account can't scale into, and needs point-in-time data + a risk model we don't have.

## 2. Retail bot categories — mostly break-even-to-negative after costs
- Crypto grid / DCA bots: slightly negative EV once breakouts and fees are included
  (https://quantitativepy.substack.com/p/grid-bots-sell-volatility-for-free). Works in chop, gives it back on trends.
- Perp funding-rate carry: real historically (https://gerbil.life/papers/CarryTrade.v1.2.pdf),
  compressed sharply since 2024. **Already our Sleeve C (shelved): walk-forward 4.0 -> -0.65 on BTC,
  can't pay costs when funding < ~1 bp / 8h.** Nothing new here.
- TradingView-alert-to-webhook bots (3Commas etc.): plumbing, not a strategy; inherits the indicator's (lack of) edge.
- 0DTE option selling: retail lost ~$184k/day in aggregate 2021-23, 60% of it to spreads
  (https://wp.lancs.ac.uk/fofi2024/files/2024/04/FoFI-2024-146-Leander-Gayda.pdf).
- Prop-firm funded accounts: ~14% pass, ~7% ever get a payout
  (https://propfirmscompare.com/how-many-traders-pass-prop-firm-challenges/). A fee funnel.

## 3. What pro shops earn that we can't
Market making / latency: Citadel Securities $9.7B net trading revenue 2024, Jane Street + Citadel
$30B derivatives market-making (https://www.navnoorbawaresearch.com/p/market-making-in-derivatives-crushes-directional-hedge-fund-trading-a-20b-revenue-gap).
That's a cost structure (colocation, rebates, billions of shares/day), not a strategy. Don't chase.

## 4. Crowding / decay — the most useful finding
- McLean & Pontiff 2016 (JF): 97 published predictors lose 35% out-of-sample and 49.5% post-publication.
- Zarattini & Aziz 2023 ORB (https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4416622): independent
  replication (https://github.com/giovannibrusco/zarattini-2023-orb-qqq) breaks even at ~2.2c/share slippage,
  76% of P&L from 2022 alone.
- Supertrend replication over 6.7 yrs with real costs: profit factor 0.80-0.86
  (https://hackernoon.com/the-truth-about-tradingviews-supertrend-strategy-after-67-years-of-backtesting).
- ICT / FVG: no statistically significant forward edge on SPY + 3 other markets
  (https://statoasis.com/overfit/research/ict-backtest-what-survives).
- Verdict: anything popular enough to have a name and a YouTube following is pre-decayed.
  Our own screen the same day (`retail_bot_strategies_2026-11-03.txt`) agrees: intraday momentum,
  ORB, Supertrend, Monday-range all flat or negative at 1 bp/side on 2015-2026 data.

## 5. "AI agent" live trading 2024-2026 — thin
Alpha Arena (nof1, https://www.alphaarena.ai/): six LLMs, $10k each, autonomous crypto trading,
season ended 2025-11-03. Four of six lost money; best +22%, worst -59%. N=6, weeks-long, no cost
disclosure. No fund has disclosed audited LLM-agent P&L. Capability demo, not evidence of edge.

## What this means for us
- Our two kept sleeves (12-month trend on futures, overnight hold with reversal sizing) are the
  *kind* of edge that survives: slow, structural, boring, published for decades and still there.
- Treat popularity as a negative signal. We tested the popular ones on the same day; none passed.
- The only retail-open "bot" edge with real evidence (funding carry) we already audited and shelved.
- ML / LLM sentiment is not off the table, but it needs data we don't have and costs we can't pay at our size.
- Nothing in this survey beats forward-testing what we have. Keep the QQQ layout open.
