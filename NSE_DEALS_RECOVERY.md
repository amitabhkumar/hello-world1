# NSE bulk/block recovery

This workflow acquires NSE bulk/block reports on the TITAN SOP schedule and supports explicit historical recovery. It does not replace or modify BSE or NSE restriction collectors.

## Official route discovery

NSE `/all-reports` links to `/report-detail/display-bulk-and-block-deals`. Its script `/dist/js/sections/bulk-block-deals-short-selling.js` constructs CSV downloads at:

`https://www.nseindia.com/api/historicalOR/bulk-block-short-deals?optionType=bulk_deals&from=04-11-2026&to=04-11-2026&csv=true`

Use `optionType=block_deals` for block deals. This is the website's published API CSV export, not a discovered static daily file store. Earlier `/api/historical/bulk-deals` and `/api/historical/block-deals` requests returned503; their exact server-side failure cause is unproven.

## Execution

Run `.github/workflows/nse_deals_recovery.yml` with optional `report_date` YYYY-MM-DD. Blank uses the shared official NSE calendar and date-selection helper. The fixed4November default was removed in commit937a0e5e0e92d51008ef44ed92ac44846a7ade61. Morning selects the prior eligible session; post-market selects today but records Pending publication before20:35 IST. Closed days select the latest eligible session. No unavailable required-date file is replaced with an older file. Calendar coverage beyond2026 fails explicitly. The browser establishes ordinary session state via the catalogue and reports page. No stealth, captcha bypass or automatic download retry loop is used.

The workflow uses Playwright1.56 Chromium in the official container. It checks HTTP200, rejects HTML, checks nonempty CSV and all-row dates, accepts case variation in month names, records hashes and preserves raw returned CSVs before validation. Empty data is not automatically declared no deals. Independent schema, quantity/price, identifiers and exact byte readback checks remain required after acquisition. Successful download does not establish full ownership coverage or trading permission.

Artifacts `nse-deals-RUN_ID-ATTEMPT` retain raw reports and manifest for90days. Preserve evidence externally before expiry. Never put credentials or private storage IDs here.

First test42215089840 returnedHTTP200 for both reports but failed date validation because `04-NOV-2026` was compared case-sensitively. Commit68bede5c1caa4b745501f067bfeeb4d3ebf74cfd corrects that comparison and preserves raw CSV before validation. Keep the original failed run for audit. No punctual scheduled delivery claim follows from a push test.

## Scheduled integration acceptance

Cron triggers:08:30 IST Monday-Friday;16:30 IST Monday-Friday;22:00 IST daily;08:00 IST Saturday. The16:30 run records pending publication without a download. The22:00 run makes one attempt for the selected date. No punctual execution guarantee follows from cron configuration.

Commit937a0e5e0e92d51008ef44ed92ac44846a7ade61 deployed the schedule, date selection and quantity/price/schema validation. Run42216188918 passed five acceptance test methods covering ten date/time cases, missing2027coverage, invalid explicit dates, schedule configuration, uppercase/mixed dates and malformed values. Its artifact13501990727 recorded PENDING_PUBLICATION_WINDOW for6November at17:45IST, with no requests. Historical download acceptance remains run42215275181 (133bulk rows,2block rows for4November).

GitHub artifacts are retained90days. Automatic GitHub-to-Drive transfer is not configured in this workflow; manifest explicitly reports NOT_TRANSFERRED. Session connector access is not a GitHub runner credential. External persistence/readback must be recorded separately. Existing research forecasts and prior failed runs remain unchanged.

## Connector-based delivery bridge

A separate TITAN artifact delivery task is configured at08:45,16:45 and22:45 IST to collect these GitHub artifacts using the user's existing connected GitHub and Drive tools. It validates reports, deduplicates date/hash, uploads to authorized private destinations and verifies exact hash plus parent readback. It does not install Google credentials inside GitHub or change exchange acquisition schedules.

This is a two-stage architecture: GitHub acquisition, followed by connector-based delivery. Task creation and an inline immediate test do not prove autonomous future execution or punctual cron acquisition. Keep those verification statuses separate. If an artifact is missing/running or transfer runtime unavailable, preserve delivery pending and reconcile the next transfer run. Never expose private destination identifiers or authentication tokens in repository files.
