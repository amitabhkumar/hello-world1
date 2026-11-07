# AEGIS 4.0 — NIFTY 2024–2026 multi-session SWING options research

**As of 7 November 2026:** strategy implemented, historical backtest complete, trading-readiness **REJECTED**. This strategy was constructed in response to the user's explicit swing, not intraday, holding style. It was not adjusted after historical results to manufacture a positive result.

## 1. Final verified evidence (read-only, no live trades)

- **Full Drive results package:** https://drive.google.com/file/d/1SWqB6QN92wLe6adRsXH58H8hA0Rx8Hio/view
- **Successful verified all-year aggregation and trade/overnight/cost QA:** https://github.com/amitabhkumar/hello-world1/actions/runs/42352203783
- **2024 and 2025 actual long-hold candidate historical market replay:** https://github.com/amitabhkumar/hello-world1/actions/runs/42351784296
- **2026 actual Upstox original/active archive source and prior-day India VIX replay:** https://github.com/amitabhkumar/hello-world1/actions/runs/42351835082
- **Frozen strategy source:** https://github.com/amitabhkumar/hello-world1/blob/aegis-nifty-backtest/aegis/aegis4_swing.py
- **Confidence/robustness/expiry proxy and CAS report source:** https://github.com/amitabhkumar/hello-world1/blob/aegis-nifty-backtest/aegis/aegis4_final.py

Past encrypted temporary data handoffs and runner-public-key descriptors were deleted after the completed private-data run. This only used historical market-data ZIPs; no Upstox Analytics credential, broker account endpoint, portfolio or order-trading action.

## 2. What was actually built

**One single, multi-day, limited-risk option premium harvesting hypothesis**, not an intraday Theta strategy.

- **Weekly expiry:** real historical listed expiry (Thursday before September 2025 and Tuesday thereafter, with holiday adjustments from contract-source dates). Entry 3–9 calendar days before observed listed expiry. One active position and one entry per option expiry.
- **Bullish:** sell a 0.18–0.30 |Delta| OTM NIFTY put and buy a lower-strike protective put. **Bearish:** sell an OTM call and buy a higher-strike protective call. Strike separation 100/150/200 points.
- **Direction:** previous three trading sessions' 10 AM NIFTY signal-time price change >=0.55% in one direction, with gap/invalidation vetoes. No lookahead into later candle prices when selecting trade.
- **India VIX:** last completed day's VIX from verified India VIX history; level 11–45, historical 20-day percentile >=25th, five-session increase <=6 volatility points, prior day only. 10-day realized volatility from previous completed sessions.
- **IV:** inverted from actual 10:06 historical 1-minute option OPEN proxy (not exchange-quoted IV); must be >=1.08x prior realized vol and >=0.90x India VIX.
- **Greeks:** estimated option Delta, Gamma, Theta and Vega per 10:06 signal-time leg. Bullish spread net positive Delta, bearish negative Delta; net Gamma negative, Theta positive, Vega negative. Greek estimation uses constant risk-free/dividend proxies; actual market surface and bid/ask not present.
- **OI:** 09:46 and 10:06 actual OI snapshots. Short OI >=5,000 and nondecreasing, long wing OI >=5,000 and not dropping >20%. Near-spot OI put/call ratio 0.30–3.50. Historical option volume-positive. Note OI is not evidence of buy/sell initiation and may be posted with source latency.
- **Spread and sizing:** sufficient modeled premium >=11% of strike width at signal and >=10% at actual 10:16 entry after .75% modeled adverse slippage (minimum .75 premium points/leg/side). Max initial contractual spread risk, including a ₹500 fee reserve, <=₹10,000 on one historical NIFTY lot with date-effective 25/75/65 contract rules.
- **Multi-night management:** trade at 10:16 after observations known. Hold overnight, including across weekends if applicable, until credit profit capture of 60%, buyback premium reaching 2.3x original credit, strong prior-day VIX spike, short-strike threat, or expiry-session 14:46. Observe 10:06 / 14:40 option marks and model execution 10 minutes / 6 minutes later at 10:16 / 14:46. **No forced same-day close**; every executed historical trade held at least one night. No overlapping trades.
- **Expiry handling:** primary backtest closes by **14:46 on the expiry trading session**, avoiding unverified historical actual CAS settlement, exercise STT and assignment model. This allows expiry-day holding but **does not prove actual cash-settlement execution**. Separately recorded hypothetical spot-index CLOSE intrinsic payoffs are not NSE official settlements and exclude exit taxes; **do not treat these as strategy P&L**.
- **CAS:** August 3–November 5 2026 analyzed as a separate completed historical cohort. Revised December 7 CAS market/settlement rules are future/unobserved as of this report. ±500/600-point NIFTY and ±10 IV-vol-point local Greek stresses are included in final JSON and explicitly flagged as inaccurate for large repricing, not true executable option payoffs.

## 3. Executed historical outcomes

**Window:** 6 November 2024 to 5 November 2026. Modeled portfolio starting capital ₹50 lakh.

| Entry year | Trades | Wins | Win rate | Net modeled profit/loss |
|---|---:|---:|---:|---:|
| 6 Nov–Dec 2024 | 3 | 1 | 33.3% | **−₹1,302.44** |
| Jan–Dec 2025 | 19 | 14 | 73.7% | **−₹2,776.79** |
| Jan 1–Nov 5 2026 | 17 | 10 | 58.8% | **−₹5,565.04** |
| **All** | **39** | **25** | **64.10%** | **−₹9,644.27** |

**Full sample:** Profit factor **0.643**, average net trade **−₹247.29**, median net trade **+₹518.35**, maximum closed-trade drawdown **₹12,768.04**, worst single trade **−₹4,002.66**.

The attractive **64.1% win rate is not positive expectancy**. The net win/loss asymmetry is the main structural weakness:

- **25 profit-taking exits** totaled **+₹17,384.13**.
- **14 stop-risk exits** totaled **−₹27,028.40**.
- Average winner **+₹695.37** versus average loser **−₹1,930.60** (mean winner/absolute mean loser **0.36**).
- Gross modeled option price P&L before fees **−₹5,414.77**; modelled brokerage, STT/other charges **₹4,229.49**; net **−₹9,644.27**.
- Median entry credit **17.25 NIFTY option premium points**; **all 39 trades held overnight**, median **three calendar days**.
- All 39 had a priced exit (no fallback full-loss penalties).
- Historical 25/39 Wilson 95% win-rate interval **48.42%–77.26%**, too wide to support a dependable 60%+ winning probability.
- IID mean-trade bootstrap 95% interval **−₹717.05 to +₹181.60**; calendar-month-block mean-trade interval **−₹754.49 to +₹160.58**. Both include zero (not evidence of positive expectancy).

### Slippage sensitivity (same historical trades and exit choices)

| Modeled option-leg adverse slippage | Net P&L |
|---|---:|
| 0.75% (minimum .75 premium points per leg/side) | **−₹9,644.27** |
| 1.5% | **−₹12,178.75** |
| 3% | **−₹19,623.89** |

Higher fill friction makes outcomes worse. Without historical actual bid/ask, this remains a favorable, **not institutionally verified**, market execution abstraction.

## 4. CAS comparison

- **Pre-Aug-3-2026:** 34 swing trades, **−₹12,768.04**, 20 winners (58.8%).
- **Aug-3–Nov-5-2026 post-CAS subset:** **5 swing trades, all five winners, +₹3,123.77 modeled** (average +₹624.75). **Wilson 95% win-rate interval 56.55%–100%**, too few trades to establish a persistent edge. 2026 was extensively reviewed in preceding AEGIS versions and is not pristine OOS.
- The user raised 500–600 NIFTY-point CAS-linked moves and expects continued volatility. The index historical 1-minute reported OHLC sample does not capture every indicative auction-price display or prove execution. Treat 500/600 points as risk shocks; do **not** assume their persistence after 7 December 2026.

### What about literal hold to NSE cash settlement?

For the same 39 entries, a separate *counterfactual gross expiry intrinsic* calculation using available **cash-index 5-minute CLOSE proxy**, no early stop and no taxes, summed **+₹2,360.15**. **This is NOT a verified backtest return**: the underlying price is not source-confirmed NSE option final settlement (especially the Aug–Nov CAS period), exercised option STT/charges and real clearing processes are not applied, and the path would expose positions to large overnight and expiry Gamma events. It must **not** be compared to net early-exit strategy results as if equally executable.

That distinction is especially important given the user's permission to hold positions through expiry.

## 5. Actual completion and unresolved institutional requirements

| Item | Outcome |
|---|---|
| Implement non-intraday swing with up to expiry-session holding | **Executed**, 39 overnight trades |
| Use actual price OHLC, OI, OI change, option volume | **Executed from source** |
| Compute IV and Delta, Gamma, Theta, Vega | **Executed, Black–Scholes estimated** |
| Use India VIX level, percentile and momentum | **Executed from previous market session** |
| NSE 2024–26 historical lots and expiry selection | **Executed with documented source heuristic; daily historical contract master audit remains** |
| Compare pre-CAS and post-Aug-CAS | **Executed: 5/5 post-CAS wins but very small sample** |
| Cost, 500/600-point shocks, bootstrap and drawdown | **Executed as modeled scenarios; no true quote/market-depth validation** |
| Official NSE expiry cash settlement with CAS and tax | **NOT VALIDATED** |
| Overnight gap execution/margin and risk liquidation | **NOT VALIDATED** |
| Bid/ask, depth, true Greek surface and real option order fills | **NOT AVAILABLE from these historical minute OHLC files** |
| December 7 2026 new CAS market regime | **FUTURE: cannot validate yet** |
| Independent untouched prospective win-rate/edge evidence | **NOT AVAILABLE: past periods repeatedly examined** |
| Profitable production-grade strategy | **FAIL — no live deployment** |

### Decision and recommended scope

**AEGIS4 is a completed swing-oriented and reproducible historical research experiment, but it still fails profitability and risk-adjusted approval criteria.** The source data are valuable; a high winner percentage alone did not solve the low-premium/high-loss problem. This system should not be introduced to a live account without positive evidence on genuinely unseen prospective sessions, official settlement/strike price and actual executable quotes.

**No more announcing a winning institutional strategy based on retrospective adjustments to 2024–2026.** A new proposed swing experiment should prioritize legitimate multi-session volatility risk premia *with tail-loss distribution and realistic settlement* rather than tuning an already-seen 60% credit-profit target/stop multiple until it looks profitable.
