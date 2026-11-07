# AEGIS 3.0 (ADVC) — audited frozen NIFTY F&O credit-spread research

**Status at 7 November 2026: IMPLEMENTED; HISTORICAL SIMULATION EXECUTED; REJECTED AS A LIVE STRATEGY.**
The user's objective is a robust, high-probability, cost-adjusted NIFTY F&O strategy with effective India VIX / IV / Delta / Gamma / Theta / Vega / OI controls, robust to August 2026 CAS and possible sustained volatility after the new December CAS arrangements. The goal **was not achieved** in the tested design. Do not suggest otherwise.

## Actual delivered, verified evidence

- **Final complete research + trade and skip ledgers + 2024, 2025, 2026 execution evidence:** https://drive.google.com/file/d/1fG8qyUQio5U9_KgfhYq03nsSfkarCoSn/view
- **Detailed root-cause trade breakdown by exit, spread side and CAS cohort:** https://drive.google.com/file/d/13LYtBuTkNKtL2hO9ril_DtaA5mhhdnlK/view
- **Verified 2024–2025 original one-minute-option historical runs:** https://github.com/amitabhkumar/hello-world1/actions/runs/42349954112
- **Verified 2026 original + supplementary Upstox data, 209 completed prior-session India VIX days:** https://github.com/amitabhkumar/hello-world1/actions/runs/42350015517
- **Successful final 2024–26 arithmetic, no-lookahead, session risk and statistical reconciliation:** https://github.com/amitabhkumar/hello-world1/actions/runs/42350347322
- **Successful trade-level gross vs fees and stop-vs-target postmortem:** https://github.com/amitabhkumar/hello-world1/actions/runs/42350466641
- **Research code:** [aegis3_credit_spread.py](https://github.com/amitabhkumar/hello-world1/blob/aegis-nifty-backtest/aegis/aegis3_credit_spread.py) and [aegis3_final.py](https://github.com/amitabhkumar/hello-world1/blob/aegis-nifty-backtest/aegis/aegis3_final.py).

Historical input market ZIPs were transferred through encrypted temporary links to an isolated GitHub Actions runner; ephemeral link descriptors and public-key files were deleted after the 2026 run. No broker private Analytics token, order-trading API or account portfolio access was used.

## Frozen testable trading rules

*One strategy*, not an optimized multi-family comparison. Same rules in each historical year; no after-the-fact threshold adjustment.

- **Underlying:** NIFTY 50, standard NIFTY option contracts, expiry 4–12 calendar days away; date-effective actual 25/75/65-lot rule. **Position:** bullish = **short OTM put + longer OTM protective put**; bearish = **short OTM call + longer OTM protective call**. No unlimited short option exposure.
- **Signal information known before entry:** 09:15–09:40 index opening range, 09:55 and 10:00 completed NIFTY five-minute OHLC, 09:46 and 10:06 option-minute OPEN/OI; prior completed session India VIX and 10-day realized volatility. Trade selection does not use post-entry exit prices.
- **Directional filter:** Breakout, open-to-10:00 drift in breakout direction >=0.20%, sign confirmed against prior cash-index close.
- **India VIX:** Prior-day close 12–38, 20-session historical percentile >=20th, five-session VIX jump <=4 points; no unavailable/stale previous VIX.
- **IV:** Estimated Black–Scholes IV from 10:06 options OHLC OPEN, ATM implied annual volatility >=1.08x previous 10-session realized volatility and >=0.87x previous-day India VIX; both subject to bounds. Not exchange-quoted implied vol.
- **Greeks:** Delta short abs 0.12–0.25 (target 0.18), bullish net positive Delta / bearish net negative Delta, positive net Theta, negative net Gamma and Vega, all model-derived with constant 6.5% risk-free rate and 1.2% dividend-yield assumptions.
- **Observed options OI and volume:** Both short and hedge OI at least 5,000; short OI nondecreasing 09:46→10:06; hedge OI drawdown no worse than 15%; selected legs have positive historical minute traded volume; descriptive near-spot 350-point put/call OI ratio 0.35–3.0. This cannot identify actual buyer/seller initiation, queue depth or order-side disposition.
- **Risk and timing:** Hedge width 100/150/200/250 NIFTY points; initial one-lot maximum contractual expiry loss **including a ₹500 fee reserve ≤ ₹10,000**; maximum one modelled trade/day, daily cap ₹25,000 with no overlapping positions in this backtest. Trade OPEN proxy 10:16. Checkpoint signals at 11:10, 12:10, 13:10, 14:40; fills six minutes afterward at modelled option OPEN. Exit if buyback debit <=50% initially received credit (profit), >=200% (premium stop), otherwise exit at 14:46 before CAS. Both legs must have source price bars at entry; unpriceable terminal exits are penalised rather than discarded.
- **Costs:** Historical fees and sale taxes, adverse 0.75% or minimum ₹0.75 premium points PER LEG PER SIDE, plus 1.5% and 3% stress variants.
- **Greek shocks:** ±500/600 underlying points and ±10 IV percentage points (local quadratic sensitivity) checked at signal time; these are approximations and not executable shocks or tail guarantees.
- **CAS:** Historical August 3–Nov 5, 2026 evaluated separately. 7 December 2026 changes to derivatives expiry settlement and trading times are still in the future as of this analysis; the model excludes closing auction executions entirely.

## Actual historical results: 6 November 2024–5 November 2026

| Period | Trades | Winners | Modelled P&L |
|---|---:|---:|---:|
| Nov–Dec 2024 | 2 | 0 | **−₹200.80** |
| Full 2025 | 11 | 3 | **−₹3,537.24** |
| Jan–Nov 5, 2026 | 9 | 2 | **−₹3,475.18** |
| **Full tested period** | **22** | **5** | **−₹7,213.22** |

**Full period:** Win rate 22.73%, **profit factor 0.034**, median trade P&L −₹247.38, mean trade P&L −₹327.87, maximum closed-trade drawdown ₹7,213.22. Model assumes ₹50 lakh capital and 1 lot per position; −0.1443% of this capital, but this low total capital loss is due in part to **very few trades**. Historical result is negative, not a high-probability system.

- **Pre-CAS**: 21 trades, **−₹6,972.79**, 5 wins.
- **Post-CAS Aug03–Nov05**: **only 1 trade, −₹240.43, 0 wins**. Not statistically sufficient to evaluate a new regime.
- Bull put verticals: **12 trades, −₹3,943.41**, only **1 winner**.
- Bear call verticals: **10 trades, −₹3,269.81**, **4 winners**.
- **95% Wilson confidence interval for overall win rate:** **10.12%–43.44%**, far below the proposed 60% target.
- IID bootstrap 95% mean-trade interval **[−₹503.13, −₹175.72]**; monthly-block bootstrap **[−₹597.51, −₹149.08]**. Both entirely negative. These are **retrospective model uncertainty estimates**, not pristine prospective validation.

### Price, execution-fee and exit root cause

The independent postmortem audited the **same 22 trades**, without changing their selection:

| Exit | Count | Net modelled P&L |
|---|---:|---:|
| Mandatory exit before CAS | **20** | **−₹4,746.34** |
| Premium stop-loss | **2** | **−₹2,466.88** |
| 50% credit profit target | **0** | **₹0** |

- **Gross simulated trading P&L before fees: −₹4,855.47.**
- **Modelled brokerage, exchange and statutory fees: ₹2,357.75**, making the net −₹7,213.22.
- Median entry spread credit: **12.65 option-premium points**; median initial credit ≈**₹832** per position before fees. Median round-trip model charges ≈₹108.70.
- Exactly two gross-positive trades ended net-negative after fees. The losses are **not merely fees**; the average day-to-day mark of the narrow, short-dated vertical was negative and intraday Theta insufficient.
- No profit-taking trigger hit. This exposes a **structural mismatch** in this particular design: selling 4–12-day-expiry premium but forcing all spreads closed after only a few hours, during which expected Theta capture is small and directional/Gamma risks plus fees matter more. Under these tested conditions, a small short-Delta and high theoretical POP do **not** yield a high realised win rate.
- There were no missing terminal candles conservatively penalized in these 22 trades; missing-data elimination cannot explain the negative results.

### Slippage sensitivity — same frozen trade decisions

| Modeled per-leg/side adverse slippage | Net P&L |
|---|---:|
| 0.75% with ₹0.75 minimum (baseline) | **−₹7,213.22** |
| 1.50% | **−₹7,980.95** |
| 3.00% | **−₹11,911.98** |

Real bid/ask, broker execution price, market-impact, order queue, real-time India VIX reporting latency and complete historical options chain greeks not available. No live broker fills simulated.

## NIFTY and CAS regime context

The independently retrieved **reported one-minute NIFTY index OHLC** (not every unexecuted indicative closing auction mark) covered Jan1–Nov5 2026. Pre-CAS **143** sessions median high-low **229.0 points** (5 sessions ≥500, 2 ≥600), post-Aug03 CAS **66** sessions median **195.9 points** (zero ≥500 in reported regular 1m OHLC, maximum 474.2). Indicative auction price spikes seen on screens may be much larger but are not necessarily actual executable derivatives quotes.

The new CAS settlement treatment effective **7 December 2026** is unobserved. Model scenarios permit ±500/600 NIFTY and IV ±10 vol points; **persistent volatility after December should be treated as a stress hypothesis**, not assumed validated.

## Acceptance gates and disposition

| Gate | Result |
|---|---|
| Two-year net positive after costs | **FAIL** |
| Modelled net profit factor ≥1.30 | **FAIL** (0.034) |
| Observed win rate ≥60% | **FAIL** (22.73%) |
| 95% confidence lower bound on win rate ≥50% | **FAIL** (10.12%) |
| Defined initial per-spread risk ≤₹10,000 | **PASS**, based on model; execution may exceed |
| Net positive under 1.5% and 3% slippage | **FAIL** |
| At least 30 genuine prospectively observed trades | **FAIL** |
| Historical executable bid/ask and depth | **NOT AVAILABLE** |
| Revised December CAS actual observed performance | **NOT YET OBSERVED** |
| **Live-trading approval** | **REJECTED** |

**Decision: Retire this exact AEGIS3 design as a trading candidate.** Do not increase risk, extend holding periods, relax filters, or tune stops using the already-seen 2024–2026 results and then label that variant a tested institutional edge. A materially different risk-premium strategy would require a new, explicitly pre-registered economic hypothesis (such as multi-session Theta collection with overnight/gap/margin simulation and time-varying skew), a fresh code version, and truly unseen prospective validation. Under no circumstances claim a high-profit/high-probability system from these negative historical results.
