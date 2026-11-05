# NSE REG1 and price-band acquisition

This independent workflow follows NSE All Reports, selects actual displayed report cards, and downloads through a normal Chromium browser on a GitHub-hosted runner. It requires no personal computer or interactive browser session. Existing BSE code is unchanged.

## Schedule and invocation
Runs at 08:30 IST weekdays (03:00 UTC), 16:30 IST weekdays (11:00 UTC), 22:00 IST daily (16:30 UTC), and Saturday 08:00 IST (02:30 UTC), plus workflow_dispatch with an optional exact YYYY-MM-DD date. Pushes touching the NSE collector/workflow execute a live acceptance test. Do not submit duplicate runs while one is active. GitHub schedules can be delayed or missed.

No repeated download loop, guessed URL probing, access-control bypass, or older-date substitution. Requests for today's file before 20:35 IST are publication-pending. The window is a user-selected operating configuration, not an exchange publication guarantee.

## Artifacts
nse-restrictions-RUN_ID-ATTEMPT contains manifest.json, observed report inventory, page screenshot, and successfully validated CSV files. Retention is 90 days. Partial successes remain available even when the job fails.

Required current-date files: REG1_INDddmmyy.csv and sec_list_ddmmyyyy.csv.
Also collect displayed same-date band changes/SME bands and separately identified future-dated band changes/SME bands. Never label a future-dated reference as today's effective restriction.

Validation checks official HTTPS source, exact selected/downloaded filename, CSV structure, required column families, nonempty consistent rows, byte count, SHA256. Acquisition validation does not interpret surveillance codes or establish effective trading dates.

## Calendar selection (2026-11-05 revision)
The collector uses the official 2026 NSE equity holiday snapshot, the January 15 amendment, February 1 Budget session and November 8 Muhurat session. Sources are in CALENDAR_SOURCES. Morning selects the preceding eligible session; 16:30 selects today but records publication pending until the configured 20:35 window; closed days select the latest eligible session. Missing required files never cause an older-date fallback. Dates outside 2026 fail explicitly, including a year rollover needing adjacent-year coverage. This snapshot must be revised for new exchange notices and the next year; it is not a live calendar subscription.

Status, GSM, LTASM, STASM and ESM field labels are decoded from the official SURV76993 annexure. REG1 codes differ from REG_IND composite indicators. Unknown codes remain Unknown. This partial interpretation does not establish effective dates or permitted trading sessions; trading_access remains Unknown. The forthcoming ETF field is not silently activated.

Tests: PYTHONPATH=. python tests/test_nse_session_selection.py. Optional NSE_ARTIFACT_DIR validates an existing artifact. Tests cover weekend, holiday, special sessions, publication gate, month transition and fail-closed year coverage. Live deployment acceptance remains separate from unit tests.

## Drive delivery
GitHub artifact creation and Drive delivery are separate stages. The scheduled TITAN consumer must fetch the artifact, independently verify bytes/manifest, check existing files by date/hash, upload missing files into its authorized Incoming folder and read them back. Append a receipt and daily tracker. No private folder IDs or Google credentials are stored in this public repository. Missing execution environment means delivery pending, never success.

## Failure handling
Preserve exact errors and prior decisions. No automatic download retries. An event timeout is not proof of an NSE server outage. A successful scheduled configuration is not evidence of future execution or Drive persistence.
