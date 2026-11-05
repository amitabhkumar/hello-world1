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

## Calendar limit
This first acquisition version requests the exact IST calendar date. It does not declare a missing file a holiday, infer prior-session eligibility, or substitute an older file. Calendar-based closed-day reuse is NOT IMPLEMENTED and remains an explicit limitation. The research consumer must verify the official NSE calendar and applicable effective date before using a prior-session artifact.

## Drive delivery
GitHub artifact creation and Drive delivery are separate stages. The scheduled TITAN consumer must fetch the artifact, independently verify bytes/manifest, check existing files by date/hash, upload missing files into its authorized Incoming folder and read them back. Append a receipt and daily tracker. No private folder IDs or Google credentials are stored in this public repository. Missing execution environment means delivery pending, never success.

## Failure handling
Preserve exact errors and prior decisions. No automatic download retries. An event timeout is not proof of an NSE server outage. A successful scheduled configuration is not evidence of future execution or Drive persistence.
