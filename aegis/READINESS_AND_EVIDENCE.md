# Current AEGIS status: AEGIS 4.0 NIFTY SWING (7 November 2026)

**Latest user trading style: swing; multi-session holding to weekly expiry.** Built and executed a new overnight, defined-risk spread with India VIX, IV, observed OI growth and modeled Delta/Gamma/Theta/Vega. This fixes the prior mistake of forcing all short-premium trades to close the same day.

**Executed full 2024–2026 result:** **39 overnight trades**, **25 wins (64.10%)**, **−₹9,644.27 modeled net**, **profit factor 0.643**, **maximum closed-trade drawdown ₹12,768.04**. Historical post-Aug CAS cohort **5/5 wins, +₹3,123.77**, but extremely small and NOT a verified edge. All 2026 periods have been inspected, not an untouched OOS evaluation.

- [Full latest AEGIS4 swing specification, exact P&L, VIX/Greeks/OI, negative expectancy root cause and risk gates](https://github.com/amitabhkumar/hello-world1/blob/aegis-nifty-backtest/aegis/AEGIS4_SWING_READINESS_AND_EVIDENCE.md)
- [Final AEGIS4 trade/skip ledger, research JSON, year source audit and report ZIP in Drive](https://drive.google.com/file/d/1SWqB6QN92wLe6adRsXH58H8hA0Rx8Hio/view)
- [AEGIS4 successful consolidated runner with 39-trade and CAS validation](https://github.com/amitabhkumar/hello-world1/actions/runs/42352203783)

**Readiness:** **REJECTED for live capital**. In-sample 64% winners still lost due average −₹1,930 loser vs +₹695 winner. The gross counterfactual expiry-settlement spot-close proxy (+₹2,360, pre-tax, not official) is **NOT** an executable verified alternative. Official NSE cash settlement, actual bid/ask and margin/overnight liquidations remain unverified.

---

# Latest experiment: AEGIS 3.0 — 7 November 2026

**Most recent requested strategy built and executed:** trend-aligned **defined-risk bullish put / bearish call credit vertical**, with historical India VIX, IV, Delta/Gamma/Theta/Vega, actual OI change and volume, max initial risk ₹10,000, early exit before CAS and 1.5–3% slippage stress. **Executed 22 simulated trades, 5 wins (22.73%), −₹7,213.22 net** on 6-Nov-2024–5-Nov-2026. **Rejected for live deployment**. The independent trade postmortem found 20 EOD exits without ever reaching the 50% credit target and 2 premium stops; trading marks were negative gross **before** fees. Do not modify the results to make them look profitable.

- [AEGIS3 complete current readiness and quantified loss attribution](https://github.com/amitabhkumar/hello-world1/blob/aegis-nifty-backtest/aegis/AEGIS3_READINESS_AND_EVIDENCE.md)
- [Complete third-generation research ZIP in user AEGIS Drive folder](https://drive.google.com/file/d/1fG8qyUQio5U9_KgfhYq03nsSfkarCoSn/view)
- [Verified final AEGIS3 GitHub historical replay](https://github.com/amitabhkumar/hello-world1/actions/runs/42350347322)
- [Detailed exit-price and fee postmortem](https://drive.google.com/file/d/13LYtBuTkNKtL2hO9ril_DtaA5mhhdnlK/view)

**Status:** The requested historical research run has completed, but **no 1.0, 2.0 or 3.0 design has been shown to achieve reliable high win rate or positive expectancy**. 2026 historical data have been reviewed repeatedly, not pristine OOS. Future CAS changes remain unobserved.

---

# Superseding research: AEGIS 2.0 (7 November 2026)

The original v0.1 research and its negative 82-trade results remain archived below, but the user's latest request requires **Delta, Gamma, Theta, Vega, IV, OI and India VIX** to be explicitly considered across multiple NIFTY F&O strategy families. That work has been implemented and executed as **AEGIS 2.0**, with three separately tested candidate families and an actual before/after CAS NIFTY 1-minute index range audit.

**Current 2.0 decision and links:** [AEGIS20_READINESS_AND_EVIDENCE.md](https://github.com/amitabhkumar/hello-world1/blob/aegis-nifty-backtest/aegis/AEGIS20_READINESS_AND_EVIDENCE.md). **Result: no strategy approved for live trading.** The post-CAS trend subset is +₹6,250.25 across **only seven** retrospective trades (5 wins); full-period trend results remain negative. All historical 2026 performance is repeatedly inspected, not untouched OOS.

**Final AEGIS 2.0 2024–2026 evidence ZIP:** https://drive.google.com/file/d/1ZFpHmeKkUQsYJfnr65ZusTbnOp8Nn_ov/view

---

# AEGIS NIFTY — Current research evidence and readiness decision

**Evidence cut-off: 7 November 2026 (India, IST).**

> **Research execution: COMPLETE within the available OHLC datasets and documented approximations.**
> **Institutional execution validation: NOT COMPLETE. Trading-readiness gate: FAILED.**
> 2024–2026 NIFTY 1-minute option-candle backtests show negative modeled performance. No positive verified edge; **do not deploy live capital** on the present model.

This file is the current canonical status. Previous reports and failed/retried GitHub Actions remain archived for traceability, but superseded older 2026 partial P&L figures should **not** be treated as final.

## 1. Final user-facing reports and independently verified runs

- **Final full rolling two-year research package** (all-year 2026 VIX, date-effective lots and costs, prior-day futures-basis diagnostic, trade ledgers, drawdown, bootstraps, fee stress, source manifests):
  https://drive.google.com/file/d/11qSOto9GjZg1GorQJU_Ctf1tkXidhB_q/view
- Full 2024–2026 fee-corrected historical replay (successful, 2024/25 rebuilt from checksum-pinned public Parquet sources; 2026 reused previously audited private Upstox trade ledger): https://github.com/amitabhkumar/hello-world1/actions/runs/42332081624
- All 2026 VIX data retrieved from public Upstox V3 without token (success): https://github.com/amitabhkumar/hello-world1/actions/runs/42332475921
- Final complete VIX prior-day attribution, 2026 all 39 trades labeled with no lookahead (success): https://github.com/amitabhkumar/hello-world1/actions/runs/42332677918
- Final limited available daily futures basis attribution (success): https://github.com/amitabhkumar/hello-world1/actions/runs/42332895008
- 2026 39-trade source Upstox active-contract option backtest and robustness (success): https://github.com/amitabhkumar/hello-world1/actions/runs/42273407619
- Fixed Nov 2026 futures Oct28–30 gaps via one token-free V3 request (success): https://github.com/amitabhkumar/hello-world1/actions/runs/42330977469
- Final repaired futures Parquet, 7/7 expected sessions ×385 one-minute bars (success): https://github.com/amitabhkumar/hello-world1/actions/runs/42331212071

Source-controlled research scripts: `aegis/backtest_v01.py`, `aegis/exchange_rules.py`, `aegis/rolling_research_final.py`, `aegis/relabel_2026_vix.py`, and `aegis/futures_basis_research.py`, all on the isolated branch `aegis-nifty-backtest`. GitHub Actions workflows and pinned SHA-256 source manifests provide reproducibility.

## 2. Executed rolling historical results

Research window **6 November 2024–5 November 2026**. Research strategy A/B/C is a **simplified, fixed-rule, one-lot long-convexity study**, not a documented reproduction of any unprovided institutional strategy specification. Observed 1-minute OHLC prices are modeled with adverse fill slippage and current/historical charges, not bid/ask or real order executions. Assumed capital ₹50,00,000.

| Entry year | Trades | Net modeled P&L |
|---|---:|---:|
| Nov 6–Dec 31 2024 | 6 | **−₹5,663.31** |
| Jan–Dec 2025 | 37 | **−₹42,676.13** |
| Jan 1–Nov 5 2026 | 39 | **+₹448.55** |
| **Rolling two-year total** | **82** | **−₹47,890.89** |

**Full period:** Win rate **36.59%** (30 wins), profit factor **0.783**, expectancy **−₹584.04 per trade**, median trade **−₹2,591.66**, max **closed-trade** drawdown **₹94,173.04**, worst trade **−₹12,379.92**, mean worst 5% of trades **−₹9,754.61**. Return on assumed ₹50 lakh capital −0.9578% before any unmodeled financing/opportunity cost.

- 2024–2025 chronological development segment: **43 trades, −₹48,339.44**.
- 2026 chronological retrospective evaluation segment: **39 trades, +₹448.55**. 2026 has been inspected repeatedly, so **it is NOT a pristine untouched out-of-sample validation**.
- Omitting the single best winner worsens the rolling result to **−₹77,094.55**; omitting the best two to **−₹99,676.12**.
- IID bootstrap mean-trade 95% interval **[−₹1,946.34, +₹873.55]**; calendar-month block bootstrap interval **[−₹1,748.57, +₹844.54]**. Intervals cross zero and do not establish positive expectation.

### Execution-cost sensitivity (same frozen trades, premium slippage each side, minimum 0.75 option points/leg/side)

| Adverse slippage | Two-year net modeled P&L |
|---|---:|
| 0.25% | −₹33,715.95 |
| **0.75% (baseline)** | **−₹47,890.89** |
| 1.50% | −₹75,425.74 |
| 3.00% | −₹133,074.40 |

The stress tests change price assumptions, not the trade-entry/exit decisions. A realistic market-impact and bid/ask backtest could differ further.

## 3. Reconciled data inventory and temporal provenance

| Data | Evidence status | Note |
|---|---|---|
| Public one-minute NIFTY option candles for Oct–Dec 2024, 2025, Jan–Jul 21 2026 | SHA-256-pinned Parquet source used in executed replays | From the independently published historical intraday dataset, exact SHA-256 manifests in runner artifacts |
| Private Upstox original Jul22–Nov03 2026 options | **1,990 contract CSV files, 8,777,148 1m candles** | ZIP audited (1,994/1,994 original option+future SHA checks passed); original unchanged |
| Original Upstox 2026 futures Jul22–Oct27 | **4 populated contract CSVs, 34,520 1m records** | Available but the AEGIS v0.1 trade rules do not consume futures basis |
| Active NIFTY option supplement Nov02–05 2026 | **285 contract CSVs, 376,301 1m records** | 286/286 active option+future SHA checks passed |
| November 23 NIFTY FUT, Oct28–Nov05 2026 | **2,695 1m candles across 7 sessions** | All 385 minute starts/session, recovered missing 1,155 Oct28–30 from public V3, no user token |
| India VIX 2026 Jan1–Nov05 | **78,375 minute candles, 209 complete sessions** | 375 candles/day, verified public V3, prior-day only for all 39 2026 trade labels |
| NIFTY index 5-minute source | 2024–21Apr2026 pinned public + 22Apr–21Jul2026 public 1m resampled + 22Jul–05Nov2026 Upstox 1m resampled | Source boundaries documented; exchange independent validation at both seams still needed |
| NIFTY daily front-month futures basis proxy | **359 daily spot/futures overlaps (Nov06 2024–Apr21 2026)** | **60 of 82 trades** labeled using strictly previous session; **22 trades unclassified** owing to absent continuous comparable futures reference through 2026 May–Nov |

The final futures-basis diagnostic is **observational only**; it does not drive signal selection, resolve intraday forward IV or constitute a forward-model ablation. No continuous two-year historical one-minute futures order book was available.

## 4. Exchange rules that were actually implemented

- NSE circular **NSE/FAOP/64625**: NIFTY lot 25 → 75, date-effective 2024–2025 contract transition. Existing weekly expiry 19-Dec-2024 and existing monthly expiry 30-Jan-2025 retain 25; weekly expiry 02-Jan-2025 and monthly 27-Feb-2025 first move to 75. The replay no longer silently excludes Nov20–Dec31 2024; model uses **contract expiry** to determine ordinary weekly/monthly lot.
  https://nsearchives.nseindia.com/content/circulars/FAOP64625.pdf
- NSE circular **NSE/FAOP/70616**: NIFTY 75 → 65 for 2026 new weekly/monthly expiry; first weekly 06-Jan-2026 and monthly 27-Jan-2026.
  https://nsearchives.nseindia.com/content/circulars/FAOP70616.pdf
- NSE circular **NSE/FAOP/68747**: regular NIFTY weekly/monthly expiry moves from Thursday to Tuesday for contracts expiring after August 2025; actual expiry read from contract market data, including holiday shifts. Full daily exchange contract-master validation remains unavailable.
  https://nsearchives.nseindia.com/content/circulars/FAOP68747.pdf
- NSE circular **NSE/FAOP/74467**: derivative market close extended 15:30 → 15:40 effective 03-Aug-2026. Candles are validated with date-effective 15:29/15:39 final minute starts. CAS equity-cash auction order matching is **not simulated**.
  https://nsearchives.nseindia.com/content/circulars/FAOP74467.pdf
- Option-sale **STT**: 0.10% until 31-Mar-2026, 0.15% from 01-Apr-2026 (NSE Finance Act 2026 schedule). Entry and exit charge dates handled separately for cross-boundary trades.
  https://www.nseindia.in/static/products-services/equity-derivatives-securities-transaction-tax
- NSE options premium exchange transaction charges: **0.03503%** through Feb 2026; **0.03553%** from Mar 2026 per Upstox published schedule. Brokerage, GST, SEBI fees and stamp duty are modeled using disclosed assumptions, **not audited broker contract notes**.
  https://upstox.com/brokerage-charges/

**Settlement:** Backtest forces square-off before option expiry to avoid exercise/settlement tax. Actual expiry settlement is not modeled. American/exercise assignment or actual bid/ask crosses are not simulated. The pre-expiry rule is a model restriction, not validation of exchange settlement mechanics.

## 5. Volatility, futures basis, and risk diagnostics

- All **39/39** modeled 2026 trades now have a prior-session India VIX label, with no same-day future information.
- Across both years, prior-day VIX >=20 labeled **8 trades, +₹19,397.81** net; normal VIX labeled **74 trades, −₹67,288.70**. Eight high-VIX observations is a very small sample; dropping the biggest winner reverses that subset's outcome.
- Daily prior-session front-month futures basis was available for **60 trades**, unavailable for **22**. Basis classification is correlation, **not** evidence that futures-basis filtering produces a profitable strategy. Missing near-month continuous 2026 May–Nov futures reference prevents a full-window future-input strategy evaluation.
- Research includes modeled holding-day, overnight/weekend, next-session gap, downside tail and rolling/period cohort diagnostics, but **does not** reconstruct continuous mark-to-market and intraday exchange margin calls.

## 6. Scope of completion and hard validation gates

| Requirement | Final status |
|---|---|
| Retrieve and verify original and active 2026 derivative ZIPs | **COMPLETE** |
| Resolve 2026 Nov options and Oct28–30 futures session gaps | **COMPLETE** |
| Export source derivatives to validated Parquet | **COMPLETE** |
| Fill India VIX 2026 Jan–Nov source and prior-day labels | **COMPLETE** |
| Correct 2024–2026 NIFTY lot transitions, expiry and time/fee rules | **Implemented and regression tested for ordinary weekly/monthly contracts**; daily exchange master audit still pending |
| Run rolling Nov2024–Nov2026 OHLC backtest | **COMPLETE** (82 trades, negative) |
| Analyze costs, drawdowns, tail risk, regimes, gap/overnight sensitivity | **COMPLETE on modeled trade ledgers** |
| Integrate *available* historical daily futures basis for diagnostic purposes | **COMPLETE for 60/82 trades**; full intraday coverage not available |
| Verify historical bid/ask and market depth at entry/exit | **BLOCKED: not in supplied historical API data** |
| Full NSE daily contract-master and settlement replay | **BLOCKED: original historical daily master/settlement data not verified** |
| Full original institutional strategy fidelity | **NOT ESTABLISHED: original detailed executable AEGIS specification not present in repo** |
| Genuinely untouched future holdout | **NOT POSSIBLE as of this evidence cut-off; 2026 repeatedly observed** |
| Profitable, execution-robust, deployable strategy | **FAILED** |

### Decision

**Stop treating AEGIS v0.1 as a validated trading strategy.** The rolling historical evidence is negative and worsens under adverse execution assumptions. This is a **completed and reproducible negative research result** for the documented simplified A/B/C model, not a reason to invent a profitable result or claim live-readiness.

Future research, if pursued, should be defined as a **new, pre-registered strategy version** with real quote/depth and contract-master provenance, controlled risk/entry logic, and *future unseen* sessions. No retrospective rule changes to these inspected years should be represented as out-of-sample proof.

## Archived context

Older research/audit reports, logs and incremental missing-data corrections remain on this branch, but this register and the final ZIP linked above supersede their preliminary readiness claims.
