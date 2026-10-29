# BSE supplementary data acquisition

This workflow supplements the existing BhavCopy collector; it does not change scoring or establish research coverage by itself.

## Run
Use Actions → BSE supplementary datasets → Run workflow. Optional report_date is YYYY-MM-DD; datasets is all or comma-separated IDs from titan/bse_data.py.
Scheduled requests are 08:30 and 16:30 IST Monday–Friday, 22:00 IST daily, and 08:00 IST Saturday. GitHub can delay scheduled runs; requested times are not guaranteed delivery times. At present report_date defaults to the current IST calendar date, not an inferred trading session. Holidays and pre-release periods can produce missing dated data, which must not be replaced with stale data silently.

## Evidence
Each run uploads bse-data-RUN_ID-ATTEMPT. Each source has a manifest, raw responses, rendered page evidence, and normalized exports or downloaded files where supported. Exported CSV/JSON files are reopened and checked; files carry byte counts and SHA-256 hashes. The root manifest records run ID, attempt, commit, requested date, retrieval time, and individual outcomes. Preserve each artifact before the 90-day retention period expires. No Drive credentials are installed in this public repository; transfer to project storage is a separate operation.

## Status meanings
- VALIDATED_DATED_RECORDS: schema and explicit date/count checks passed; see dataset-specific coverage.
- VALIDATED_SNAPSHOT: schema-checked records retrieved now, with source dates retained. This does not imply complete coverage, historical point-in-time data, or a live/executable quote.
- DOWNLOADED_UNVALIDATED: actual files downloaded and integrity checked; date or economic meaning still requires validation.
- PARTIAL: useful records exist but required scope or consistency checks are incomplete.
- CAPTURED_UNVALIDATED / SOURCE_ONLY / NO_DOWNLOAD_FOUND: evidence only; no claim of usable complete data.
- NOT_APPLICABLE: mode or time trigger is not active; a later live check is still required.
- FAILED / ACCESS_BLOCKED: explicit error; other sources continue. Access denials are not bypassed.

The workflow deliberately exits nonzero when any required category remains partial or unavailable, while uploading successful outputs and diagnostics. A red workflow is therefore not proof that every download failed. Always read per-dataset manifests.

## Data limitations
Announcement metadata and attachment links are not full filing-content research. Shareholding defaults are recent filings, not an exchange-wide ownership database. Corporate-action defaults are not a historical adjusted-price series. Pledges retain mixed reporting periods. Market quotes are snapshots, not depth or same-time RVOL baselines. Pre-open indicative orders are not executed trades. Reference files must be matched to their effective dates before applying ASM/GSM/ESM/TFT/price-band restrictions. Missing data must remain missing.

## Reproducibility and continuity
Use the script at the artifact's exact commit, preserve original inputs, and append later runs/corrections rather than overwriting frozen outputs. Use the original BhavCopy workflow for OHLCV. The supplementary workflow is an acquisition layer; a successful export does not satisfy all SOP discovery, source-trace, or risk checks.
