# NIFTY AEGIS — Executed Evidence, Dataset Coverage and Readiness (7 November 2026)

**Status: executable preliminary one-minute option-OHLC backtest completed through the available November 2026 records. NOT validated for deployment.**

This replaces the outdated initial register that said no backtest had executed.

## Authoritative execution evidence

- 2024–2026 original v0.1 execution: https://github.com/amitabhkumar/hello-world1/actions/runs/42185786356
- Original 2024–2026 report: https://drive.google.com/file/d/1UUN7EFBzJZvdSnwRPOfC-cJe_YWWbeN8/view
- Source Upstox 2026 contract ZIP: https://drive.google.com/file/d/1nRSNHsVlU9gmfKl5vd_-RoTXoKb1o2Cp/view
- Verified 2026 original ZIP checksum / archive audit: https://github.com/amitabhkumar/hello-world1/actions/runs/42247754833
- **Executed full 2026 stitched research replay:** https://github.com/amitabhkumar/hello-world1/actions/runs/42252130058
- Integrated source lineage, trade ledger, skips and summary: https://drive.google.com/file/d/1SdFsJEND_ZaJ0r9w0UdPjKpQnfjz3SUN/view
- **Executed 2026 bootstrap, tail-risk and cost stress:** https://github.com/amitabhkumar/hello-world1/actions/runs/42253307065
- **2026 active-November contract ZIP integrity, merge and replay:** https://github.com/amitabhkumar/hello-world1/actions/runs/42273407619
- **Current integrated evidence and robustness:** https://drive.google.com/file/d/1bD6Z0RmLBBVpNuuRnPNHJA35YhXqYv0w/view
- Full robustness report: https://drive.google.com/file/d/1UT-grbfp3VcSbSfeDK-89_MlsOMPn_A3/view
- Isolated repo branch: `aegis-nifty-backtest`; user Drive folder: https://drive.google.com/drive/folders/1QKdK4ZBp9vtN2aL_e-NMsI7V9i8MpZhv

## Input rows and temporal boundaries

| Data source | Records / files | Observed coverage | Integrity |
|---|---:|---|---|
| Public options 1-minute 2024 | 14,592,609 rows | Oct1–Dec31 2024 | Initial source and schema checks passed |
| Public options 1-minute 2025 | 69,687,860 rows | Jan1–Dec31 2025 | Initial source and schema checks passed |
| Public options 1-minute 2026 | 40,177,780 rows | Jan1–Jul21 2026 | Initial source and schema checks passed |
| **User Upstox Plus options 1-minute 2026** | **8,777,148 rows / 1,990 CSVs** | **Jul22–Nov03 2026** | **1,990 SHA-verified CSVs, no corrupt files** |
| **User Upstox Plus futures 1-minute 2026** | **34,520 rows / 4 CSVs** | **Jul22–Oct27 2026** | **4 SHA-verified CSVs** |
| User Upstox NIFTY 1-minute and India VIX 1-minute | 55,500 total rows / 12 CSVs | Jul22–Nov05 2026 | No invalid OHLC or out-of-session rows reported |
| Historical 5-minute NIFTY index | Independent mirror | 2024–Apr21 2026 | Original source with pinned ZIP digest |
| Additional public NIFTY 1-minute converted to 5-minute | 4 monthly files | Apr22–Jul21 2026 | Source URLs and SHA-256 in stitched ingestion report |

The original Upstox ZIP audit found 1,994 populated derivative CSVs, 1,994 matching SHA-256 hashes, no corrupt CSVs, no invalid OHLC observations and no out-of-session observations under the date-effective NSE derivatives session schedule. Its 52 empty API contract responses were not included as populated contract files.

The `aegis/stitch_upstox_2026.py` replay consumed **all 8,777,148 Upstox option candle rows without rejecting bad rows or timestamps** and converted the 34,520 futures rows to Parquet. It created a 2026 stitched NIFTY 5-minute index and daily VIX close series. The actual P&L engine consumes **option candles, spot data and VIX diagnostic regimes; it does not yet consume futures basis in signal selection or pricing**.

## Observed AEGIS performance (not historical fills)

### Original development

- 2024 (warmup eligible from October only) and 2025 development: **38 strategy trades, net −₹46,982.13**.
- First 2026 Jan–Apr21 truncated replay: **16 trades, net +₹29,435.22**. This earlier figure is superseded for full-2026 research by the stitched replay because some exit observations changed after extending the cash-index history.

### Prior stitched 2026 replay before active November patch (superseded)

| Entry-date cohort | Strategy trades | Net P&L |
|---|---:|---:|
| Jan1–Apr21 2026 | 16 | +₹23,595.14 |
| Apr22–Jul21 2026 | 11 | −₹42,262.89 |
| Jul22–Nov03 2026 | 11 | −₹3,456.04 |
| **2026 total** | **38** | **−₹22,123.79** |

2026 win rate 34.21% (13 winning), mean P&L −₹582.20 per trade, profit factor 0.802, maximum closed-trade drawdown ₹74,032.93, worst trade −₹8,715.07, IID bootstrap mean-trade 95% interval ₹[−2,723.37,+1,910.13]. Removing best winner gives −₹51,327.45; removing best two gives −₹71,770.30. A naïve Monday-straddle benchmark lost ₹92,941.65 over 36 2026 trades.

Matched-trade adverse slippage (minimum 0.75 option points per side) at 0.25%, 0.75%, 1.50% and 3.00% returned **−₹15,224.11, −₹22,123.79, −₹35,372.02 and −₹62,918.57**, respectively. Matched-trade cost tests change fills only, not the entry and exit decisions.

**Classification:** the 2026 extension is *exploratory*, not a pristine untouched out-of-sample holdout; previous 2026 results were already inspected. A negative historical experiment does not imply the strategy is profitable or ready to trade.

## Current stitched 2026 run **after** active November patch

- User supplied `AEGIS_Upstox_Active_Patch.zip` from Nov06: **286 populated contract CSVs (285 options, 1 November futures) with 286 matching SHA-256 checks and no invalid session/ohlc rows**. Contains **376,301** option minute bars (November 02–05) plus **1,540** futures bars (November 02–05, 385 each). Separately 15 empty contract responses, not checksum failures.
- NIFTY options **November 04: 102,159 bars across 270 contracts**; **November 05: 104,328 across 278 contracts**. Both days covered, with Nov09 and Nov17 option expiries.
- Futures benchmarked to NIFTY cash index: **missing October 28, October 29 and October 30**, present November 02–05; the v0.1 options signal engine currently does not use futures basis.
- Run: https://github.com/amitabhkumar/hello-world1/actions/runs/42273407619
- Integrated report: `AEGIS_2026_ACTIVE_PATCH_FULL_INTEGRATED_EVIDENCE` archived under the above workflow, additionally saved to the user's AEGIS Drive folder.

| Metric | Before active option patch | After active option patch |
|---|---:|---:|
| 2026 strategy trades | 38 | **39** |
| 2026 modelled net P&L | −₹22,123.79 | **+₹458.21** |
| Win rate | 34.21% | **35.90%** |
| Profit factor | 0.802 | **1.004** |
| Closed-trade max drawdown | ₹74,032.93 | **₹74,032.93** |
| Naive Monday straddle baseline P&L | −₹92,941.65 | −₹76,633.14 |

The active-contract patch enabled **one additional strategy trade worth +₹22,582.00 net**, creating the complete change. Its entry was **3 November 2026**, expiry **9 November 2026**, mode **A (long 23,600 CE + long 23,600 PE)**; the candle-based exit was **5 November 2026 at 09:16 IST** on a simulated profit target. Modelled gross P&L +₹22,778.23, charges ₹196.23. Exact trade provenance: https://github.com/amitabhkumar/hello-world1/actions/runs/42274283691. No new strategy positions were entered on 4–5 November; new active-series prices instead enabled this prior-day trade to be evaluated. There is no evidence of stable positive expectancy: **IID bootstrap 95% mean-trade interval −₹2,323.03 to +₹2,764.83**, P&L without the best winning trade **−₹28,745.45**, and higher-slippage stress at **1.5%: −₹13,326.70** and **3.0%: −₹41,946.61**. The matched-trade 0.25%, 0.75%, 1.5%, 3% stress shows ₹7,679.39, ₹458.21, −₹13,326.70 and −₹41,946.61.

**Do not treat +₹458.21 as proof of trading edge or a finished two-year institutional replay.** The April–July 2026 cohort alone lost ₹42,262.89, 2024 transition periods remain excluded, no historical executable bid/ask was supplied and 2026 has already been analyzed repeatedly.

## Explicit outstanding work and limits

| Component | Status | What remains |
|---|---|---|
| Import and validate supplied 95MB Upstox ZIP | **Complete** | Retain source and SHA audit |
| Export actual option and future 1-minute bars as usable Parquet | **Complete** | Use source lineage with dates and contracts |
| Historical index plus VIX stitching | **Complete for July–November**, partial older 2026 VIX | NSE daily cross-verification and 2026 Jan–Jul VIX still needed |
| Run AEGIS v0.1 candle backtest through Nov05 2026 | **Executed; near flat (+₹458.21 net)** | Need stronger fill and strategy fidelity |
| Historical contract calendars, expiry settlement and lot changes | **Partially modeled** | Full date-effective exchange-circular and daily calendar QA |
| NSE CAS derivative sessions | **Date-effective session flags implemented** | Exchange event-by-event auction/settlement execution simulation is not implemented |
| Options on Nov04–Nov05 | **Recovered and verified** | Date-level 1m coverage and 285 active-option contracts acquired; sparse strikes are not necessarily corruption |
| Futures on Oct28–Nov05 | **Partially recovered** | Nov02–05 has 385 bars each; **Oct28, Oct29, Oct30 remain missing** compared with original NIFTY index sessions |
| Fully aligned futures basis/forward IV | **Not in AEGIS v0.1 strategy logic** | Build separately and run controlled ablation |
| Historical executable bid/ask, market depth | **Missing** | Licensed quotes or an explicit proxy; current results have modeled adverse spreads |
| Complete rolling two-year Nov06 2024–Nov05 2026 window | **Not yet demonstrated** | Historical lot-size transition Nov20–Dec31 2024 excluded, NSE session rules and 2026 futures October 28–30 still pending; executable bid/ask absent |
| Institutional AEGIS original specification fidelity | **Not established** | Current A/B/C is simplified, uses 350-pt verticals, 15m exit checks |
| Untouched prospective walk-forward | **Not established** | Freeze new rules then test genuinely unseen future sessions |
| Production live trading readiness | **NO** | Data, quality, fills, net edge and drawdown gates not passed |

The existing read-only supplement: `aegis/upstox_active_gap_patch.py` (private local Analytics Token, never stored) generates a small `AEGIS_Upstox_Active_Patch.zip`. `aegis/stitch_active_patch.py` validates source hashes and produces compatible active-derivative Parquet. Safety and smoke tests run on the isolated branch.

**Next milestone:** audit options data availability beyond simple presence, recover Oct28–30 futures separately if intraday futures basis is required, resolve the late-2024 contract lot-size transition, NSE session/cost validation and genuine untouched future holdout. **Do not optimize on these already-observed 2026 results and describe them as out-of-sample.**


### 7 November 2026 — root-cause fix for the remaining NIFTY futures gap

**Confirmed code defect:** In `upstox_active_gap_patch.py`, `regular_fo_bar()` compared every candle against the *options* start date (2026-11-02), including the November futures contract whose requested start date was 2026-10-28. The Oct28–30 futures candles were therefore excluded by local post-download filtering, regardless of whether Upstox returned them. The export reported success because it checked API errors and nonempty CSV files but not per-day completeness.

- Corrected code passes the individual contract start date into the session validator, with an explicit Oct28/Oct30 futures regression test (commit d983919d52b058deb6f541492f1a904aa5929b7e).
- Added `aegis/aegis_repair_oct_futures.py`, standalone Python read-only script. It opens the existing small active-market-data ZIP, identifies the exact Nov23 NIFTY future key from the checksum-verified sidecar, retrieves only Oct28–30 1-minute candles, merges without altering earlier records or options CSVs, verifies exactly 385 timestamp-distinct minute bars on every required trading date Oct28–Nov05, and saves a new `AEGIS_Upstox_Active_Patch_Repaired.zip`. On an incomplete response it produces a token-free diagnostic report and DOES NOT claim completion.
- Offline integration/regression/standalone tests passed: https://github.com/amitabhkumar/hello-world1/actions/runs/42277113892
- **Status:** script validated on synthetic market-data responses; the three real trading-day rows must still be authenticated through the user's private local Upstox Analytics Token. Do not claim the gap filled until the repaired archive is uploaded and audited.
- There is no need to re-export 285 options or the previous 95 MB archive. Futures do not enter the current v0.1 option-candle engine; this patch improves dataset completeness for later futures/basis studies.
