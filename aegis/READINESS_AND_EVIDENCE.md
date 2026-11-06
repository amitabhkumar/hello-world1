# NIFTY AEGIS — Executed Evidence, Dataset Coverage and Readiness (6 November 2026)

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

The Upstox ZIP audit found 1,994 populated derivative CSVs, 1,994 matching SHA-256 hashes, no corrupt CSVs, no invalid OHLC observations and no out-of-session observations under the date-effective NSE derivatives session schedule. Its 52 empty API contract responses were not included as populated contract files.

The `aegis/stitch_upstox_2026.py` replay consumed **all 8,777,148 Upstox option candle rows without rejecting bad rows or timestamps** and converted the 34,520 futures rows to Parquet. It created a 2026 stitched NIFTY 5-minute index and daily VIX close series. The actual P&L engine consumes **option candles, spot data and VIX diagnostic regimes; it does not yet consume futures basis in signal selection or pricing**.

## Observed AEGIS performance (not historical fills)

### Original development

- 2024 (warmup eligible from October only) and 2025 development: **38 strategy trades, net −₹46,982.13**.
- First 2026 Jan–Apr21 truncated replay: **16 trades, net +₹29,435.22**. This earlier figure is superseded for full-2026 research by the stitched replay because some exit observations changed after extending the cash-index history.

### New stitched 2026 replay

| Entry-date cohort | Strategy trades | Net P&L |
|---|---:|---:|
| Jan1–Apr21 2026 | 16 | +₹23,595.14 |
| Apr22–Jul21 2026 | 11 | −₹42,262.89 |
| Jul22–Nov03 2026 | 11 | −₹3,456.04 |
| **2026 total** | **38** | **−₹22,123.79** |

2026 win rate 34.21% (13 winning), mean P&L −₹582.20 per trade, profit factor 0.802, maximum closed-trade drawdown ₹74,032.93, worst trade −₹8,715.07, IID bootstrap mean-trade 95% interval ₹[−2,723.37,+1,910.13]. Removing best winner gives −₹51,327.45; removing best two gives −₹71,770.30. A naïve Monday-straddle benchmark lost ₹92,941.65 over 36 2026 trades.

Matched-trade adverse slippage (minimum 0.75 option points per side) at 0.25%, 0.75%, 1.50% and 3.00% returned **−₹15,224.11, −₹22,123.79, −₹35,372.02 and −₹62,918.57**, respectively. Matched-trade cost tests change fills only, not the entry and exit decisions.

**Classification:** the 2026 extension is *exploratory*, not a pristine untouched out-of-sample holdout; previous 2026 results were already inspected. A negative historical experiment does not imply the strategy is profitable or ready to trade.

## Explicit outstanding work and limits

| Component | Status | What remains |
|---|---|---|
| Import and validate supplied 95MB Upstox ZIP | **Complete** | Retain source and SHA audit |
| Export actual option and future 1-minute bars as usable Parquet | **Complete** | Use source lineage with dates and contracts |
| Historical index plus VIX stitching | **Complete for July–November**, partial older 2026 VIX | NSE daily cross-verification and 2026 Jan–Jul VIX still needed |
| Run AEGIS v0.1 candle backtest through available Nov2026 | **Executed; negative result** | Need stronger fill and strategy fidelity |
| Historical contract calendars, expiry settlement and lot changes | **Partially modeled** | Full date-effective exchange-circular and daily calendar QA |
| NSE CAS derivative sessions | **Date-effective session flags implemented** | Exchange event-by-event auction/settlement execution simulation is not implemented |
| Options on Nov04–Nov05 | **Missing** | Retrieve then-active Nov10 expiry contracts with read-only active Historical Candle V3 |
| Futures on Oct28–Nov05 | **Missing** | Retrieve then-active November monthly futures contract |
| Fully aligned futures basis/forward IV | **Not in AEGIS v0.1 strategy logic** | Build separately and run controlled ablation |
| Historical executable bid/ask, market depth | **Missing** | Licensed quotes or an explicit proxy; current results have modeled adverse spreads |
| Complete rolling two-year Nov06 2024–Nov05 2026 window | **Not yet demonstrated** | The source includes Nov–Dec 2024, but the simulator excludes 2024 Nov20–Dec31 due contract lot-size transitions; November 2026 active contracts also missing |
| Institutional AEGIS original specification fidelity | **Not established** | Current A/B/C is simplified, uses 350-pt verticals, 15m exit checks |
| Untouched prospective walk-forward | **Not established** | Freeze new rules then test genuinely unseen future sessions |
| Production live trading readiness | **NO** | Data, quality, fills, net edge and drawdown gates not passed |

The existing read-only supplement: `aegis/upstox_active_gap_patch.py` (private local Analytics Token, never stored) generates a small `AEGIS_Upstox_Active_Patch.zip`. `aegis/stitch_active_patch.py` validates source hashes and produces compatible active-derivative Parquet. Safety and smoke tests run on the isolated branch.

**Next milestone:** integrate the small Nov04–05 active option / Oct28–Nov05 futures patch if accessible, rerun the same frozen rule set; resolve the late-2024 contract lot-size transition (rolling two-year window begins in Nov2024, so Jan–Sep2024 is not required); then complete NSE daily cross-validation and make an independent decision on further methodological investment. Do not tune these observed 2026 outcomes and call them OOS.
