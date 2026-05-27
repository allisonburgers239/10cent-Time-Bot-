# 10cent-Time-Bot-
10cent Time Bot. Trades  and sends signals based of time and price
⧖
10¢ ChronoMatrix CM V5.0
Trader’s Guide
How to Read the Indicator and Structure Your Trades
Time · Structure · Intelligence

Contents


(After opening this document in Word, right-click the contents above and choose “Update Field” to populate the page numbers.)

1. About This Guide
This guide shows you how to use the 10¢ ChronoMatrix indicator to structure long and short trades. It assumes you already have the indicator on a TradingView chart and are working through it either live or in replay.
It covers, in this order: the mental model, the 27-node cycle in depth, the GPS reliability gauge, the AMD phase engine, significant levels, sweep detection, the sessions, how to read every row of the dashboard, the pre-trade checklist, two complete worked trade setups (long and short), the inside-candle context, multi-timeframe alignment, session signals, trade management, when to stand aside, the daily routine, psychology, best instruments and timeframes, risk rules, a glossary, FAQ, and a trade journal template.
It is not a course on Time Distortion Theory itself. The cycle, GPS, AMD and session concepts are introduced briefly and then put to work. If you want the methodological deep dive, that is a different document.
This is not a signal service. The indicator informs; you decide. Every read is visible on the chart, nothing is hidden, and you remain the decision-maker. The framework’s edge is concentrated in a small number of clean setups per day — most of trading well with this tool is the discipline to wait for them.
2. The Mental Model in 60 Seconds
Three ideas hold everything else up.
The cycle. Price moves through 27 nodes — three “circles” of nine. Each key node has a character. N7 feels like exhaustion. N13 is the gear-change pivot. N21 feels like the move will run forever. N25 feels like the end. The character of each node tells you what to expect, not what the price will be.
The sessions. The cycle runs separately for New York, Globex and London. The session you are trading in matters as much as the node you are on.
GPS. The indicator measures how cleanly it can read your cycle position. When it says STRONG or MODERATE, the read is usable. When it says LOST, it is not — and the tool says so plainly. The dial is the most important number on the dashboard.


3. The 27-Node Cycle in Depth
The cycle is 27 nodes — three circles of nine. Every node has a recognisable character. You do not need to recall the literal node number to use the indicator; the dashboard tracks it. You do need to know what each key node feels like, because the indicator’s job is to identify the character of the current bar, and yours is to know what to do with it.
N1 — Birth
The new cycle starts. Price has just reset (usually a sweep at N27) and the first bars of the new direction are forming. What to do: look back at what just got swept. The N1 setup is usually a reversal trade at the sweep extreme. Size conservatively — N1 is the start of a new read, not a confirmation of one.
N5 — First Acceleration
The first real impulse off the base. The cycle has committed to a direction. What to do: if you took the N1 entry, this is where it pays. If you missed N1, the N5 retest of the swept level is your second chance — often a higher-probability entry than N1 itself.
N7 — Exhaustion (CRITICAL)
Feels finished. Looks like the move is over. Usually it is not. The leg after N7 is often the largest in the cycle. What to do: do not counter-trade N7 unless you have heavy confluence (HTF reversal, opposite-side sweep, AMD veto). Hold winners through N7, take partials only. The single most expensive misread in the framework is shorting an up cycle at N7 because it “feels toppy.”
N13 — Gear Change (CRITICAL)
The mid-cycle pivot. Two outcomes: continuation or correction. The signature: a deep retracement that looks like a top but is not always one. What to do: read the surrounding evidence — if MTF lanes agree, lean continuation. If they diverge, take partial profits and tighten the stop. N13 is the most ambiguous node in the cycle. Be slower with conviction here.
N17 — Divergence / Trap
The fake-out node. Looks like a continuation but often traps. Volume and momentum frequently diverge here — the move keeps going but with shrinking conviction. What to do: skeptical of new entries near N17. If you are in a profitable trade, watch the upper lanes — if HTF disagrees, take more off the table.
N21 — Final Push (CRITICAL)
The euphoric (or capitulatory) leg. Feels like it will run forever. What to do: do not add into N21. This is where you take profits, not where you load. The next move is the reset. If anything, N21 is where short-bias setups begin to develop in an up cycle, or long-bias in a down cycle.
N25 — Reset Begins (CRITICAL)
Feels like the world is ending (or like the move will never stop, depending on cycle direction). It is the beginning of the next cycle. What to do: start watching for the next N1 setup. Do not catch the falling knife — wait for the sweep and the reclaim that signal the reset is done. N25 entries are the second-most expensive mistake in the framework after fading N7.
N27 → N1 — The Handover
Sweeps typically happen here. The new cycle’s first setup forms in this transition. The N27 → N1 handover, with a clean sweep of a significant level, is the single highest-confluence trade in the cycle.
Common mistakes by node
Trading against the leg AFTER N7 because N7 felt like the top. It almost never is.
Entering at N17 thinking it is a continuation. N17 traps continuation traders.
Adding to a winner at N21. You are adding right before the reset.
Catching the falling knife at N25. Wait for the reclaim.

4. GPS — Reading the Trust Dial
GPS is the indicator’s honesty engine. Instead of pretending it always knows your cycle position, it reports how clean its current read is.

What GPS measures
GPS compares recent price action to what the cycle’s current position predicts. When recent moves matched the expected node character, levels were respected or cleanly swept, and the multi-timeframe lanes broadly agreed, GPS reads STRONG. When some signals matched and some did not, GPS reads MODERATE. When the read is incoherent, GPS reads LOST.
The three states
STRONG. The cycle reads clean. Trust the map. Trade standard size on qualifying setups.
MODERATE. Some signals are mixed. The map is still usable but not perfect. A-tier setups only — clear sweep, clear level, clear cycle position, MTF alignment. Half size.
LOST. The cycle position cannot be read reliably. This is not a failure of the indicator — it is the indicator being honest that the cycle and the price action are genuinely disagreeing. Action: stand aside, or trade pure price structure without leaning on the cycle.
What degrades GPS
Failed sweeps: price violates a level without reclaiming. The cycle expected a reset; the market did something else.
Choppy price action without clean level interaction. The cycle has nothing to read.
News shocks producing uncharacteristic moves. The cycle did not predict the news.
Low-volume drift, especially overnight.
How to wait it out
GPS reacquires as clean structure returns. Typically a session’s worth of clean action — clear sweeps, levels being respected, decisive directional moves — and GPS comes back to MODERATE, then STRONG. Do not force trades during the recovery. The most expensive trades you will take are the ones you take while GPS is LOST because you wanted to trade.
Sizing by GPS
STRONG = standard size. MODERATE = half size. LOST = no trade. This is the single most important rule in this guide.

5. AMD — Reading the Phases
AMD stands for Accumulation, Manipulation, Distribution. Every move on every timeframe follows this sequence at some level — and the indicator detects which phase you are currently in.

The three phases
Accumulation. Sideways, range-bound, basing. Price oscillates without going anywhere meaningful. Volume is moderate. Smart money is loading the position. Visually: dense bars in a tight range. Time signature: often the longest phase in absolute terms.
Manipulation. A fake-out move — typically a sweep of an obvious level (PDL for a long manipulation, PDH for a short). Reactive traders see the level break and pile in the wrong direction. They become the liquidity for the smart money’s real move. Visually: one or two bars that violate a level and then reclaim. Time signature: brief — minutes to a few bars.
Distribution. The real move. Smart money exits or drives the trend. This is where the move you expected actually happens. Visually: directional candles, expanding bodies, decisive closes. Time signature: shorter than accumulation, larger than manipulation in price terms.
The two-witness method
The indicator only reports a phase confirmed if both price AND the cycle agree. If price looks like distribution but the cycle says accumulation, the dashboard shows a veto rather than a misleading confirmation. Treat a vetoed phase as MODERATE GPS even if GPS itself reads STRONG.
Practical applications
For a long, you want: accumulation completing + cycle near N21 → N1 + sweep of PDL = manipulation completing + distribution to the upside about to begin.
For a short, you want: distribution to the upside completing + cycle at N21 + sweep of PDH = manipulation + distribution to the downside about to begin.
A short during accumulation is fighting the phase. A long during distribution-to-the-downside is fighting the phase. AMD is your bias filter — use it before you consider direction.

6. Significant Levels — Why They Matter
The framework treats certain levels as liquidity targets. These are the levels you watch and the levels the smart money is targeting.
The core levels
PDH (Previous-Day High). The high of the previous trading day. Heavy stops sit above it (shorts from yesterday) and breakout-buy orders sit just above. Sweeping fills both — institutions get liquidity, retail breakout traders get trapped.
PDL (Previous-Day Low). Mirror of PDH. Heavy stops sit below; breakout-sell orders sit just below.
PDM (Previous-Day Midpoint). The midpoint of yesterday’s range, (PDH + PDL) / 2. The “fair value” of the previous session. Often the first target for a sweep reversal.
DO (Daily Open). The opening price of the current trading day. Where overnight positioning meets new-session participation. Often the second magnet.
Higher-timeframe levels
Weekly Open (WO) and Monthly Open (MO). Higher-timeframe versions of the same idea. In play less often, but heavier weight when they are. A PDH that coincides with a WO is a much bigger level than a PDH alone.
Why levels matter
Large resting orders cluster at the obvious previous-session extremes. When a level is approached, two crowds engage: the shorts or longs whose stops sit beyond it, and the breakout traders waiting to enter on the violation. A wick through the level fills both — institutions get the liquidity they need to fill size, retail breakout traders get trapped on the wrong side.
The sweep is the framework’s reset trigger. Without a sweep of a significant level, the framework says: no reset, no edge, no trade.
Level confluence
When a PDL also sits at a 4H key level, a clean swing low, or a Weekly Open, the level is heavier. Heavier levels produce bigger sweeps and better trades. Always check what else is at the level you are watching.
Held levels vs swept levels
A level that held overnight without testing tends to attract a test. A level that already swept may not have residual fuel. Trade the level that is still in play. If both PDH and PDL swept yesterday, today’s setup may need to wait for new structure to form.

7. Sweep Detection — The Reset Trigger
The sweep is the framework’s most important pattern. Reading it correctly is the difference between a trade and a stop-out.

Anatomy of a clean sweep
Price approaches a significant level (PDH, PDL, etc.).
The next bar wicks through the level — long shadow, body still on the original side.
The body closes back inside, away from the level.
The bar after often prints inside compression (the inside-candle pattern).
Structure builds in the new direction.
When all five are present, you have a clean sweep. The indicator’s sweep flag colours the candle so it is unmistakable.
Failed sweeps
Wick through, but body closes outside the level. This is not a reversal — it is a breakout. Two ways to read it:
Take the breakout in the direction of the break, if you have other confluence.
Stand aside. A failed sweep that you tried to fade is the most expensive trade in the framework.
Double sweeps
A sweep that is quickly followed by a second sweep at the OPPOSITE level. Example: PDH gets swept and reclaimed (suggesting a short), but two bars later PDL gets swept and reclaimed (suggesting a long). Now what?
The framework’s answer: wait for the second reclaim and take that direction. The second sweep is the “true” one — it sets the new direction. The first one was the trap.
Sweep timing within sessions
Sweeps near session opens — particularly London open into NY pre-market, and NY open into NY morning — are the most reliable. Volume confirms; clean directional follow-through is more likely.
Late-session sweeps in low volume are often noise. A 2 PM ET sweep on a Friday is not the same animal as a 9:35 AM ET sweep on a Tuesday.
Practical sweep rules
Trust the bar AFTER the swept bar, not the swept bar itself.
Enter on the close of the bar after the sweep, or on a confirming retest.
If the bar after the sweep also wicks beyond the level, the sweep is not done. Wait.

8. The Sessions
The cycle resets per session, and each session has its own personality.

Globex / Asia (18:00 ET prev. day → 03:00 ET)
The overnight session for US-based traders. Lower volume, slower moves, less reliable structure. Useful for: pre-positioning and reading the overnight bias before London opens. Avoid: trying to scalp the noise.
London (03:00 → 12:00 ET)
The first high-volume session of the trading day. The London open often produces a clean directional move that sets the day’s tone. The London-NY overlap (08:00 → 12:00 ET) is the highest-activity window of the day — most major intraday moves occur here.
New York (08:00 → 17:00 ET)
The peak session for US futures and equities. The NY cash open at 09:30 ET is a structural pivot — on many days the morning trend completes by 11:30, then a lunch-time chop window opens, then a fresh afternoon move from 13:30 → 15:00 ET.
Practical session approach
If you are trading the London-NY overlap (08:00 → 12:00 ET), the data is highest-quality. GPS reads cleanest. Sweeps are most decisive.
After 14:00 ET, signal quality starts to degrade. Late-afternoon trades need extra confluence.
The session you are trading in matters. The dashboard’s Sessions panel shows you which one is active and what the cycle has done within it.

9. Reading the Dashboard, Row by Row
The dashboard is laid out in three panels — Sessions, Engine, Intelligence. Each row tells you one specific thing. Read them in order; do not just scan for the “score.”
Sessions panel
Three rows, one per session (NY, GX, LD). Each row shows: session label, open time, current cycle count within that session, zone position (premium / discount / inside range), and a directional bias.
How to read it: look at YOUR currently-active session first. The cycle count tells you how far through that session’s local cycle you are (counts 1 → 9 within the active session). The zone tells you whether price is in the upper third (premium), lower third (discount), or middle (inside range) of the session’s range so far.
Confluence check: glance at the other two sessions. If all three biases agree, that is a strong read. If they conflict, weight the active session — the others are context.
Engine panel
Three rows representing the three timeframe lanes — your chart, a middle TF (typically 4× your chart), and a high TF (typically 16× your chart).
Each lane shows the 27-node cycle as a car travelling a track. The track is the cycle, the car’s position is your current node, the fuel bar shows depletion. The labels under each lane name the current node character.
How to read it: 
All three lanes near the same node range = strong structural read.
Top lane (highest TF) far from bottom lane (your chart TF) = HTF disagrees with your chart. Lean HTF.
All three lanes near a CRITICAL node (N7, N13, N21) = decision time on the chart.
Intelligence panel
GPS row. STRONG / MODERATE / LOST + position confidence percentage. This is the most important row on the dashboard. Read first.
Forecast + Alignment row. Projected next key-node time + MTF alignment score. Tells you how much time until the next decision and whether the timeframes agree.
ATR row. Volatility regime (expanding / contracting) + relative ATR. Helps size stops and targets.
AMD row. Current phase + agreement status. If agreement is shown, you have a confirmed phase read. If a veto is shown, the read is unreliable — treat as MODERATE GPS even if GPS itself reads STRONG.
Score row. Composite setup score. Read as a quality dial: above 75 = A-tier, 50–75 = B-tier (MODERATE GPS conditions only), below 50 = no trade. The score is a summary, not a signal — read the underlying rows to know why the score is what it is.
Reading order at a glance
GPS row.
Active session row (Sessions panel).
Your chart-TF lane (Engine panel).
AMD row.
Significant level + sweep status (on chart, not dashboard).
Score (as a quality summary).
If step 1 reads LOST: stop reading. Stand aside. Do not look for reasons to override the GPS.

10. The Pre-Trade Checklist
Before any entry, run this:
Check
Look for
If it fails
GPS
STRONG or MODERATE
Stand aside
Cycle position
For longs: near a turn node (N21 → N1) or coming out of N25. For shorts: at or near N21 in an established up move.
Wait
AMD phase
Accumulation or post-manipulation for longs; distribution-to-upside completing for shorts. Veto = stand aside.
Wait
Significant level
A PDL, PDH, PDM or DO in striking range, ideally with HTF confluence.
Wait for one
Sweep
The level just swept and reclaimed (sweep flag fires). Failed sweep = breakout, not reversal.
Don’t anticipate it
MTF alignment
Middle and higher lanes agree with your trade direction (ideal), or at minimum do not strongly disagree.
Half size or skip


Two non-negotiables: GPS workable, and a clean sweep. Without those two, there is no trade. The other items are quality filters — if any of them fail, reduce size or skip.

11. The Long Trade — Step by Step
The textbook long: an established downtrend or accumulation base, the cycle in a turn / reset zone, a sweep of the previous-day low, and a reclaim back above it.

Walk-through
Confirm GPS reads STRONG or MODERATE. If LOST, stop here.
Confirm the cycle is in a reset/turn zone — N21 through N1, or coming out of N25. Use the Engine panel; ideally chart-TF and middle-TF agree.
Confirm the AMD phase reads accumulation or post-manipulation. If it reads distribution to the downside (still falling with conviction), the bottom is not in. Wait.
Wait for price to sweep the previous-day low — wick through, body closes back inside. The sweep flag colours the candle. Do not anticipate the sweep.
Optional confirmation: the next bar prints as an inside candle near N7 or N13, boxed green for re-accumulation. Not required, but materially raises the grade.
Enter on the close of the inside bar, or on the next confirming bar that holds back above the swept level. If price wicks back below the swept low, the read is broken — stand aside.
Stop a few ticks below the swept low. Not AT the low — wicks happen. A few ticks gives breathing room without changing the risk meaningfully.
Target the previous-day midpoint first (take 50% off), then the previous-day high (full exit, or trail). Trail with the cycle structure once Target 1 hits — close the runner near N21 if it gets there.
The math is the point. You are risking a few ticks below a level the market has just rejected, against a target several times that distance. The expected value is positive even if your win rate is moderate.
Edge cases on the long
Sweep happens, but no inside candle prints. Take the trade on the confirming bar with a slightly wider stop. Smaller size.
Sweep happens at PDL but PDM is far above (wide previous range). Target 1 is too far. Take partial earlier — at a structural pivot or 1× ATR, then trail.
Sweep happens, you take it, price wicks back through the swept low intrabar but closes above. The trade is still alive until the close. Honour the candle close, not the intrabar wick.

12. The Short Trade — Step by Step
Mirror of the long. An established uptrend or distribution top, the cycle near the final-push zone, a sweep of the previous-day high, and a rejection back below.

Walk-through
Confirm GPS reads STRONG or MODERATE.
Confirm the cycle is at or near N21 — the final-push zone. Ideally MTF agrees: chart-TF and middle-TF both at or near N21.
Confirm the AMD phase reads distribution-to-the-upside completing. If it reads accumulation (still basing), the top is not in. Wait.
Wait for price to sweep the previous-day high — wick through, close back inside. The sweep flag colours the candle.
Optional confirmation: the next bar prints as an inside candle near N21, boxed gold for distribution.
Enter on the close of the inside bar, or on the next confirming bar that holds back below the swept level.
Stop a few ticks above the swept high.
Target the previous-day midpoint first, then the previous-day low. Trail with the cycle.
Edge cases on the short
The cycle hits N21 but no sweep prints — price just stalls and drifts. No trade. The framework requires the trigger.
PDH sweeps, but the next bar gaps back above. The reclaim failed. This is a failed sweep — treat as breakout if other confluence supports it, or stand aside.
PDH sweeps, you take the short, the cycle then reads N1 in the next session. The reset has happened — your short is now counter-trend in the new cycle. Manage tightly.

13. The Inside-Candle Read
The inside candle — a bar whose entire range sits inside the prior bar’s — is compression. The framework says compression means re-accumulation when it lands near the exhaustion or gear-change nodes (N7, N13), and potential distribution when it lands near the final push (N21).
The indicator filters out every other inside bar. You only see the ones that matter.

The three zones
Near N7 (green box). A pause inside the trend at the exhaustion node. The expected resolution is continuation — the leg after N7 is often the largest. Use as confirmation for a continuation entry, not as a trigger by itself.
Near N13 (green box). A pause at the gear-change pivot. Expected resolution is continuation, but N13 is the most ambiguous node in the cycle — sometimes it corrects instead. Treat as confirmation only when MTF agrees.
Near N21 (gold box). A pause near a top. Expected resolution is a turn. Treat as caution if you are long; treat as confirmation if you were already looking for a short setup.
Why N17 is not flagged
N17 is the divergence / trap node — compression there is genuinely ambiguous, and flagging it would create noise rather than signal. If you see an inside candle at N17, read it manually: if HTF is strong, treat as continuation pause; if HTF is weakening, treat as a trap setup.
The timing window
The inside-candle filter looks at the bars within roughly two nodes of N7, N13 and N21. An inside candle that prints two bars away from N7 still flags; one that prints six bars away does not. This is intentional — compression matters when it is near a decision node, not when it is mid-leg.
How to use, in practice
Inside green box near N7 in an up cycle = hold longs through the compression. Often the largest leg follows.
Inside green box near N13 = take partial off, watch for MTF confirmation. If MTF agrees, continuation. If not, exit.
Inside gold box near N21 = take profits if long, or look for short confirmation.

14. Multi-Timeframe Alignment
The Engine panel’s three lanes represent three timeframes: your chart, a middle TF (typically 4× your chart), and a high TF (typically 16× your chart). All three run the same 27-node cycle independently. Reading them together is how you avoid trading against a bigger move.
What alignment looks like
All three lanes near N1 → N5 in an up cycle = strong long bias, expansion in progress.
All three near N21 = decision time, watch for the reset.
Chart TF at N7, middle and high at N13 → cycles in sync, mid-cycle. Continuation read.
What divergence looks like
Chart TF at N1 (expansion just started), high TF at N21 (final push) → the HTF is about to reset. Your local long is likely a counter-HTF trade. Take partials early, do not hold the runner long.
Chart TF at N21 (your local cycle topping), high TF at N5 (HTF trend just started) → your local short is fighting the trend. Reduce or skip.
The practical rule
When HTF and chart TF conflict, lean HTF. Take smaller size if you must take the local-TF trade. Treat the local read as noise inside a bigger move.
When MTF is most useful
During established trends — the HTF dictates direction and the chart TF gives entry timing. The cleanest A-tier setups happen when MTF aligns.
When MTF is less useful
During transitions, where the HTFs are repositioning and reads drift. GPS will usually be MODERATE here — the indicator is telling you the same thing. Smaller size, A-tier setups only.

15. Session Signals (Type A / Gap / Type C)
The indicator grades setups into three tiers. Most of your trades should be Type A. Most of your losses come from Type C taken when you should have stood aside.
Type A — full grade
The highest grade. Every checklist box green: GPS workable, cycle in turn zone, AMD confirmed, significant level swept and reclaimed, MTF aligned. The dashboard score reads above 75. Take with full size. These are the trades the framework is built for.
Gap
Setups built on structural gaps — fair value gaps (FVGs) created by aggressive moves that leave inefficiencies. The indicator marks these zones and tracks retests. A retest of a relevant FVG in confluence with cycle position is a Gap setup. Take with full size if MTF agrees, half size otherwise.
Type C — discretionary
Lower grade. Often counter-trend within an aligned MTF, or with one checklist item failing (GPS MODERATE, AMD veto, no inside-candle confirmation). Take only with smaller size, tight stop, and a quick exit if the trade does not immediately work.
Practical tip
If you are taking more than one trade per session, the second one is usually a Type C. Be more conservative — the framework’s edge concentrates heavily in the Type A setup. Two Type A trades a day is excellent; ten Type C trades a day is usually a losing day.

16. Trade Management
Once you are in a trade, the structure shifts. You are no longer evaluating — you are managing. These rules are not optional; they are part of the edge.
Initial stop placement
A few ticks beyond the swept extreme. Do not put your stop AT the swept extreme — wicks happen. A few ticks beyond gives breathing room without changing the risk meaningfully. On MNQ that is typically 2–4 points beyond the wick. On BTC 5m, typically $30–50 beyond the wick.
Partial exit at PDM (Target 1)
Take 50% off at the previous-day midpoint. This is the first natural magnet for the move. Locking in 50% at PDM means the trade is risk-free from here even if the rest stops out at breakeven.
Move stop to breakeven after partial
Once Target 1 is locked, move the remaining stop to entry. If the trade pulls back to entry, you are flat — no harm. This is the framework’s asymmetric protection: half the position has already paid for the risk.
Trail with the cycle
As price moves toward the next cycle anchor, trail the stop behind the cycle’s structure — not behind every bar, but behind the last node-confirmed swing. Bar-by-bar trailing kills runners. Cycle-anchored trailing keeps you in until the structure breaks.
Runner to PDH/PDL or next cycle anchor
Hold the runner until either: Target 2 hits (PDH for longs, PDL for shorts); the cycle reaches N21 (final push) — close the runner; or a sweep signal fires in the OPPOSITE direction — close immediately.
Early exits
Exit the entire position if any of the following happen mid-trade:
GPS drops to LOST. The map you entered on is no longer valid.
A sweep fires in the opposite direction. Your trade thesis just inverted.
AMD changes phase against you (e.g., you are long in distribution, and a manipulation candle prints downward).
Multi-timeframe alignment breaks down. HTF flips against you.
The principle: you have asymmetric reasons for adding (don’t), reducing (often), holding (default), and closing (when the framework changes). When in doubt, do nothing — but be ready to close completely if the read flips.

17. When NOT to Trade
The discipline to stand aside is most of the edge. Each of these is a hard stop condition.
GPS reads LOST
The framework’s “I don’t know” signal. The cycle and the price are genuinely disagreeing. Most common cause: a failed sweep that should have set up a reversal but didn’t. Wait for clean structure to return — typically a session.
Mid-circle with no levels in play
The cycle is in the middle of a circle (N3–N6, N9–N12, N15–N19, N23–N24) and no significant level is in striking range. Even if GPS reads STRONG, there is no edge in this zone — directionless travel time. Wait for the next key node or a level interaction.
AMD shows conflict
Price says one thing, cycle says another. Even if you are sure which one is right, the indicator is honest about the disagreement. Wait for them to align. A bar or two usually resolves it.
A sweep happens but the candle does not reclaim
Breakout, not reversal. The most expensive mistake in the framework is fading a failed sweep. If you have other confluence for the breakout direction, take that instead. If not, stand aside.
Multi-timeframe alignment is breaking down
HTF says one thing, your TF says another. Bias HTF, or wait. Trades against the higher timeframe rarely work — they are counter-trend within a bigger move by definition.
You missed the entry by more than half the stop distance
Chasing is the second-most expensive habit after fading failed sweeps. The setup did not disappear — there will be another one. Wait.
Scheduled high-impact news
FOMC, CPI, NFP, ECB rate decisions. The cycle has not seen the news. GPS will degrade during and after. Stand aside through the release plus 30 minutes minimum. After that, wait for GPS to reacquire before trading.

18. The Daily Routine
A disciplined process is most of the edge. The framework does not require you to spend 8 hours at the screen — it requires you to be present at the right times with a clear head.
Pre-market (15–30 minutes before your session)
Open the chart in your trading timeframe (5m or 15m).
Note the levels: PDH, PDL, PDM, DO, current Weekly Open, current Monthly Open if relevant.
Note where price closed last session vs those levels — is it sitting above, below, between?
Check the dashboard. What does GPS read? Where is the cycle? What is AMD reading?
Check the news calendar. Any high-impact releases in the next 4 hours?
Form a bias: which side am I leaning, and at what level?
During the session
Wait. Most of the session is waiting.
Watch the levels you marked. The sweep is the trigger.
When a setup forms, run the pre-trade checklist (Section 10).
Take the trade only if all non-negotiable boxes are green.
Manage to the trade-management rules (Section 16).
After a trade closes, take 15 minutes away from the screen. Don’t go straight back in.
End-of-day review
What was the GPS state going into the session? Did I respect it?
Did I take the cleanest setup of the session? If not, why not?
Did I take any trades I shouldn’t have? Why?
Did I manage well? Where did I leave money on the table?
Note the cycle position at session close — useful context for tomorrow’s pre-market.

19. Psychology and Discipline
The indicator is a tool. The trader is the constraint. Most of the difference between profitable and unprofitable use of this framework is psychological, not technical.
The “I don’t know” muscle
GPS LOST is the most useful state for building discipline. The temptation is to trade anyway — you have been waiting all day, you have screen time invested. Resist. The single most differentiating habit between profitable and unprofitable traders is the willingness to sit on hands when the read is not clean.
Confirmation bias
Once you have a bias, you will find evidence for it. The framework’s protection against this is the GPS — but only if you respect it. If GPS says MODERATE but you “feel” STRONG, you are confirming, not reading.
After a losing trade
Walk away from the chart for 15 minutes. Come back, re-evaluate from a flat state. Most revenge trades are taken in the 10 minutes after a loss. The market does not owe you the loss back.
After two losing trades in the same session
Stop. GPS may not have flagged the degradation yet, but two losses in a session is itself a signal. Whatever you do, do not take a third trade immediately.
The boredom problem
Some sessions are just chop. The trade you are looking for does not form. This is normal — the framework’s edge is concentrated in clean setups, and there are not many per session. Boredom is a feature, not a bug. Bored does not equal Trade.
The euphoria problem
After a big winning trade, the temptation is to “press the edge.” Don’t. You are more likely to give back the win than to compound it. Take the win, do the end-of-day review, come back fresh tomorrow.

20. Best Instruments
The tool is built around session structure (New York, Globex, London) and liquidity sweeps of previous-day levels. It works best on instruments that respect those sessions and have deep institutional liquidity.
Primary fit — the native target
Index futures: NQ, MNQ, ES, MES, YM, MYM, RTY, M2K.
This is what the tool is designed around. Clear sessions, clean PDH/PDL/PDM behaviour, deep liquidity at level transitions, 24-hour electronic but clearly session-segmented. If you are trading micro or e-mini index futures intraday, every part of the indicator earns its place. MNQ on the 5m and 15m is the canonical use case.
Strong fit
Major forex pairs: EURUSD, GBPUSD, USDJPY, AUDUSD, USDCAD.
Built for the London-NY rhythm. The session engine maps directly onto the natural forex day. The Globex session is thinner here but still produces tradable structure overnight.
Major crypto: BTC, ETH, SOL (USD or USDT pairs).
Crypto runs 24/7, but session liquidity is still real — large players still concentrate activity around the NY and London opens, and PDH/PDL sweeps remain textbook. The cycle reads cleanly on liquid majors. BTC on the 5m is the second canonical use case.
Liquid commodity futures: GC (gold), CL (crude oil).
Strong session structure during US hours. Works on the 5m and 15m primary windows; less clean overnight.
Workable, with caveats
Highly liquid single stocks and ETFs: SPY, QQQ, AAPL, MSFT, NVDA, TSLA, etc.
Stocks run only during regular trading hours, so the Globex and London sessions are empty. The New York session engine is the active one. Avoid pre-market and post-market — they break the model. Treat the indicator as a New-York-only tool on stocks.
Poor fit — avoid
Thin altcoins, low-volume futures, illiquid pairs. The sweep concept assumes meaningful liquidity is being defended at the level. Thin markets give false sweeps and unreliable cycles.
Mid- and small-cap individual stocks below the top tier. Session structure is not clean; cycle reads drift.
Markets in extreme one-way trends (sustained gap-up or gap-down regimes). The framework assumes mean-revertish behaviour around significant levels; one-way regimes mute that signal.

21. Timeframes
Built for intraday. Defaults are tuned for 5-minute and 15-minute charts.
Primary: 5m and 15m. The sweet spot. Three session cycles per day, several setups per session, clean GPS reads, and node-to-node moves that are large enough to trade meaningfully. If you are starting out, anchor on 15m for context and trade on 5m.
Useful: 1m, 30m, 1H. 1m for scalping clean structure — but only in high-volume windows (London open, NY open). 30m and 1H for slower intraday swings — fewer setups but each one is bigger.
Limited: 4H and above. Session-based logic loses resolution. A 4H bar spans most of a session. The cycle still has meaning but the session engine becomes muted.
Not designed for: daily and weekly. The indicator is session-anchored. Daily aggregates collapse the structure it is built to read.

22. Risk Notes
These are not negotiable.
Stand aside is a valid position. The indicator is built to say “I don’t know” when it doesn’t. Honour that.
Size by GPS. STRONG = standard size. MODERATE = half size. LOST = no trade.
Stops are not optional. The framework’s edge assumes a few-tick stop below or above the swept extreme. If your trading style demands wider stops, this tool is not for you.
Targets in legs. Take part off at the previous-day midpoint, hold the rest for the previous-day extreme or the next cycle anchor. Trailing without partials kills the risk-to-reward.
Do not reverse on a stop-out. A sweep that fails to reclaim is a real signal in the other direction, but it takes its own confirmation. Restart the checklist.
Two losing trades in a row in the same session — stop trading the session. GPS is probably degraded even if it is not reading LOST.
Risk per trade should not exceed 1% of account, ever. The framework’s edge is positive expected value, not magical certainty.
Daily loss cap: if you are down 2% on the day, close TradingView and walk away. Tomorrow is another setup.

23. Glossary
AMD  —  Accumulation / Manipulation / Distribution — the three-phase model of every move.
ATR  —  Average True Range — a volatility measure used to size stops and targets.
A-tier  —  The highest-grade setup classification (also called Type A).
DO  —  Daily Open — the opening price of the current trading day.
FVG  —  Fair Value Gap — a price gap created by an aggressive move; tends to be retested.
GPS  —  The indicator’s trust dial. Reads STRONG / MODERATE / LOST.
GX  —  Globex (Asia) session — 18:00 ET previous day → 03:00 ET.
LD  —  London session — 03:00 → 12:00 ET.
MO  —  Monthly Open.
MTF  —  Multi-Timeframe — used in the Engine panel to compare three lanes.
N1, N5, N7, …  —  Key nodes in the 27-node cycle. Each has a recognisable character.
NY  —  New York session — 08:00 → 17:00 ET.
PDH  —  Previous-Day High.
PDL  —  Previous-Day Low.
PDM  —  Previous-Day Midpoint — (PDH + PDL) / 2.
Po3  —  Power of 3 — the cycle’s organising structure: 3 circles × 9 candles = 27.
Reclaim  —  The body of the sweep candle closing back on the original side of the level.
Sweep  —  A wick through a significant level that closes back inside it.
TDT  —  Time Distortion Theory — the methodology this indicator implements.
Type A / Gap / Type C  —  The three setup grades reported by the indicator.
Veto  —  When the indicator’s two-witness method disagrees, the read is shown as a veto rather than a confirmation.
WO  —  Weekly Open.

24. FAQ
Q. GPS says LOST but the chart looks normal. Why?
A. The chart can look “normal” while still violating cycle expectations. Maybe levels were broken without sweeps, or volume was off, or moves came at the wrong cycle position. GPS reads the cycle, not the chart’s surface appearance.
Q. I see a sweep visually, but the sweep flag did not fire. Why?
A. The flag has specific conditions — wick through the level AND close back inside. If the candle wicked but closed too close to the level (or beyond it), the flag holds. The flag is conservative on purpose; false positives cost more than missed signals.
Q. Can I use this on stocks?
A. Yes, but only on highly liquid names (SPY, QQQ, AAPL, MSFT, NVDA, TSLA, etc.) and only during regular trading hours. Pre-market and post-market break the session model.
Q. What if I trade an instrument that is not on the Best Instruments list?
A. The framework works on anything with session structure and meaningful liquidity. Thin or illiquid markets give false signals. If your instrument is not in the list, test in replay first — heavily.
Q. The cycle resets per session, but I trade across sessions. What do I do?
A. Use the active-session cycle for entries, and the multi-timeframe lanes for context. The session-level cycle is for timing; the HTF cycle is for direction.
Q. How long until GPS reacquires after LOST?
A. Typically a session of clean structure. Sometimes longer if the disruption was significant (news event, holiday, regime change). Don’t trade until GPS is at least MODERATE.
Q. Should I trail my stop bar-by-bar?
A. No. Trail behind cycle structure — the last node-confirmed swing — not every bar. Bar-by-bar trailing kills the runner.
Q. Can I take multiple trades per session?
A. Yes, but each subsequent trade is usually lower-quality. The framework’s edge concentrates in the first clean setup of the session. After two losses, stop trading the session.
Q. What if the indicator gives a setup but my discretion says no?
A. Trust your discretion if you have a specific reason. The indicator is decision-support, not a signal generator. The reverse also applies — discretion to take a trade without indicator confirmation is gambling.
Q. Can I automate this?
A. Mechanical execution of Type A setups is possible, but the framework’s edge depends heavily on the trader recognising when GPS LOST means stand aside and on managing trades with discretion. Pure automation usually under-performs the discretionary version.

25. Trade Journal Template
Log every trade. Review weekly. The pattern: Type A trades should be the dominant winner. If your Type C trades are outperforming your Type A trades, you are either lucky or wrong about what counts as an A-setup. Look harder.
Per-trade fields
Date and session (NY / LD / GX, with date).
Instrument and timeframe.
Pre-trade GPS state (STRONG / MODERATE — should never be LOST).
Pre-trade cycle position (active-session node + HTF node).
AMD phase at entry.
Level swept (PDH / PDL / PDM / DO / WO / MO).
Sweep + reclaim confirmed? Y/N.
Inside-candle confirmation? Y/N (and which node — N7 / N13 / N21).
MTF alignment? Y/N.
Setup grade: Type A / Gap / Type C.
Entry price and time.
Initial stop price.
Target 1 (PDM) — filled? When?
Target 2 (PDH or PDL) — filled? When?
Final exit price and reason: target / stop / discretionary / framework-flip.
R-multiple result (e.g., +2.4R, –1.0R).
What did I do well?
What would I do differently?
Weekly review fields
How many trades total? How many Type A vs Type C?
Win rate by grade (Type A win rate vs Type C win rate).
Average R-multiple by grade.
Were there any LOST-GPS sessions where I traded anyway? What was the result?
Were there any sessions I should have traded but stood aside? What was the read at the time?
Single biggest mistake of the week.
Single biggest win — was it a clean A-setup or luck?
One thing to do better next week.

26. Disclaimer
This guide is for education and analysis only. It is not financial advice, not a signal service, and not a guarantee of any outcome.
Trading carries risk. All trading decisions and their results are your own. Past patterns do not guarantee future results. Test thoroughly on your own markets and timeframes — in replay, then in simulation, then with conservative size — before relying on the indicator or any part of this guide.
The 10¢ ChronoMatrix indicator is an independent implementation of the Time Distortion Theory framework, developed for TradingView.
⧖   Time · Structure · Intelligence
