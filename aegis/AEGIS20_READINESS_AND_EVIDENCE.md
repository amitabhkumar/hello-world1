# AEGIS 2.0 — Greeks, India VIX, OI, CAS adaptive research (7 Nov 2026)

**STATUS: historical candidate comparison EXECUTED; trading-readiness gate NOT PASSED.**
**No live orders, positions, credentials, or private-account operations were touched.**

## Authoritative execution and delivered evidence

- Final comprehensive 2024–2026 research archive (candidate ledgers, rejected entries, per-family annual summaries, modeled Greek shock scenarios and 2026 CAS index/VIX chronology):
  https://drive.google.com/file/d/1ZFpHmeKkUQsYJfnr65ZusTbnOp8Nn_ov/view
- 2024/25 three-family frozen strategy execution: https://github.com/amitabhkumar/hello-world1/actions/runs/42342400999
- 2026 retro-CAS source-verified replay using original 95 MB + active 4.59 MB market ZIPs and 209 India VIX sessions: https://github.com/amitabhkumar/hello-world1/actions/runs/42342521984
- Actual 2026 NIFTY reported 1-minute daily high-low index OHLC distribution before/after CAS: https://github.com/amitabhkumar/hello-world1/actions/runs/42342779596
- Full candidate comparison, confidence, and live-approval gates (successful): https://github.com/amitabhkumar/hello-world1/actions/runs/42342944804
- Source: `aegis/aegis20_candidates.py` (frozen three strategies), `aegis/aegis20_cas_index_audit.py` (source-based realized index range), `aegis/aegis20_compare_final.py` (risk/acceptance decision). Read-only private-market ZIP handoffs were ephemeral and deleted after completion.

## Core signal and risk inputs, point-in-time discipline

| Input | Role | Data source | Timing restriction |
|---|---|---|---|
| **India VIX** | Prior VIX level, rolling prior-20-session percentile, five-session change, regime veto | 2024/25 SHA-pinned India VIX mirror; 2026 public Upstox V3, **78,375** minute bars over **209** sessions | Last available completed *prior* trading session, stale beyond 7 calendar days excluded |
| **IV** | Implied-versus-realized premium comparisons; selective volatility expansion | Calculated by BSM inversion from **10:06 option 1-minute OHLC open** and NIFTY 10:00 5min spot | Mark at 10:06 used to decide later **10:16** entry; **NOT a quoted IV surface** |
| **Delta** | Select approximately 0.5/0.25 debit verticals or ±0.22 short condor / ±0.09 hedges; exposure sign | BSM model estimate per 10:06 option leg | Signed and multiplied by one actual lot per contract expiry |
| **Gamma** | Long convexity must be positive for long volatility, condor must have short convexity | BSM 10:06 model | Separate shock scenarios ±500/600 NIFTY pts, never guaranteed P&L |
| **Theta** | Long decay cost / positive credit theta | BSM 10:06 model per calendar day | Long volatility negative theta; credit positive theta required |
| **Vega** | Positive long vol sensitivity, IV±10 volatility-point scenario | BSM 10:06 model | Full vol surface skew and event repricing **not** observable |
| **OI** | Liquidity/concentration gate | **Observed historical** option minute-bar OI | 10:06 bar must be known before the 10:16 modeled entry; all legs OI >=5,000 |
| **Volume** | Ensures quoted bar had trades | Historical minute candle volume | Source minute 10:06 and entry 10:16 and exit 14:46 positive volume |
| **Spot/ORB/realized vol** | Market regime, trend vs range, last 10-session realized vol | Time-aligned NIFTY five-minute cash index | 09:15–10:00 observed bars only for 10:16 decision |
| **CAS** | Split retrospective before 03-Aug-2026 and 03-Aug–05-Nov-2026 | SEBI/NSE rules, index minute history | Same-day 14:46 strategy exits **before closing auction**, so no fake auction fills |

Historical charge model: ₹20 brokerage per option leg per transaction, date-effective NSE STT and other charges, adverse 0.75% option premium or min 0.75 points on every leg/side. **No historical executable bid/ask, order book, quotes, actual market depth, market impact or live paper execution.**

Risk policy for all candidate families: one lot, **₹12,500 maximum defined-risk at risk entry** (0.25% of assumed ₹50 lakh), no unlimited short positions, at most one candidate position per day *per independent model*, forced same-day exit at 14:46. Historical family trades **overlap**: no realized combined strategy or netting and no evidence that averaging losing families produces a positive portfolio.

The *future* revised closing auction and derivatives settlement regime starts **07-Dec-2026** (SEBI circular 15 Oct 2026). It has not yet been observed. The model treats 500/600 NIFTY-point moves and IV±10 vol points as theoretical Greek shocks; no true unseen future event data or fill execution is implied. Reference: https://zerodha.com/marketintel/bulletin/461085/changes-to-closing-auction-session-cas-from-december-7-2026 ; https://www.nseindia.com/static/products-services/closing-auction-session

## Fixed candidate families and executed historical results

Each family was defined **before running 2024/25/2026 comparative jobs**, rather than optimizing thresholds after seeing outcomes. Both prior work and 2026 have been examined previously; this is retrospective evidence, **not pristine OOS**.

| Candidate | 2024 trades/net | 2025 trades/net | 2026 trades/net | 2024–26 totals |
|---|---|---|---|---|
| **Trend debit vertical** (trend ORB, VIX volatility veto, long Delta, long Gamma) | 5 / −₹5,944.68 | 30 / −₹21,912.70 | 30 / −₹10,352.79 | **65 trades / −₹38,210.17** |
| **Range credit condor** (VIX percentile, IV above realized, positive Theta, negative Gamma, OI on 4 legs, bounded wings) | 0 | 3 / −₹825.56 | 2 / −₹821.71 | **5 trades / −₹1,647.27** |
| **Volatility expansion OTM strangle** (VIX 5-session rise or realized vol above IV, positive Gamma/Vega, negative Theta cost monitored) | 6 / +₹3,997.04 | 7 / −₹5,388.90 | 32 / −₹7,637.67 | **45 trades / −₹9,029.53** |

**All three lost money over the entire evaluated research window.** These are three competing experiments, not an aggregate portfolio. No 2024/25 development-period winner reliably forecast post-CAS success. The v0.1 historical 82-trade result remains archived separately and must not be described as this v2.0 replay.

### Current post-CAS retrospective sample (Aug 3–Nov 5 2026)

| Family | Eligible historical trades | Net modelled P&L | Wins / win rate |
|---|---:|---:|---:|
| Trend debit | **7** | **+₹6,250.25** | 5 / 71.43% |
| Range credit | 0 | ₹0 | none |
| Volatility expansion | 14 | −₹2,590.01 | 5 / 35.71% |

For the attractive seven-trade trend subset, the **Wilson 95% win-rate interval is 35.89%–91.78%**. An IID bootstrap over just seven already-observed outcomes gives a mean-trade interval roughly ₹22.63–₹1,852.80, but it cannot establish positive expected value out of sample; performance selection and structural CAS change are not statistically identified. **Do not claim verified 70%+ win rate from seven trades.**

### Actually observed 2026 NIFTY range data

From **78,375 2026 public one-minute index OHLC candles** in the Upstox V3 source, covering **209** sessions:

| Period | 1m index days | Median daily index high-low range | >=500-point range days | >=600-point range days |
|---|---:|---:|---:|---:|
| Pre-CAS Jan–Jul 2026 | 143 | **229.0 pts** | 5 | 2 |
| After CAS Aug–Nov 5 2026 | 66 | **195.9 pts** | **0** | **0** |

The post-CAS historical OHLC **maximum was 474.2 points**, which does not support saying that *regular reported 1-minute NIFTY ranges* exceeded 500–600 points in this specific sample. **Indicative auction marks on a trading terminal may have spiked more than the published regular index one-minute candles; those are not necessarily executable derivatives prices and should not be conflated.** The comparison is observational, not causal.

## Required institutional approval gates

- Full-window one-lot modelled net expectancy **positive after adverse costs**: **FAIL**, all three families negative.
- At least **30 genuinely prospective** post-CAS December-style trade observations before claiming 60%+ win probability: **FAIL** (trend subset only seven retrospective trades).
- Real historical bid/ask and depth, executable slippage and true option Greek/IV surface: **NOT AVAILABLE**.
- Correct post-Dec 7 CAS session/settlement model based on **actual future** trading sessions: **UNOBSERVED**.
- Genuine forward OOS performance: **NOT YET POSSIBLE** from historical replay; require new data after research freeze.
- Portfolio correlation, capital/margin lifecycle, crash gap risk, live hedge execution, real broker and liquidity failure tests: **NOT VALIDATED**.

### Decision

**Three strategies built and executed; none passes institutional production trading criteria.**

The 7-trade post-CAS trend debit pattern is a **PROSPECTIVE RESEARCH HYPOTHESIS ONLY**. Freeze its decision rules as-is before future paper-only monitoring. Do not retroactively add winning parameters to the already-inspected 2026 test and label it OOS. Any future upgrade must independently prove edge after executable costs and plausible stress events; if it cannot, reject it. No live trading permission granted.
