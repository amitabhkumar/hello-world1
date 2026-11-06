# NSE bulk/block recovery

This workflow recovers an explicitly requested historical date. It does not replace the BSE or NSE restriction collectors and adds no cron schedule.

## Official route discovery

NSE `/all-reports` links to `/report-detail/display-bulk-and-block-deals`. Its script `/dist/js/sections/bulk-block-deals-short-selling.js` constructs CSV downloads at:

`https://www.nseindia.com/api/historicalOR/bulk-block-short-deals?optionType=bulk_deals&from=04-11-2026&to=04-11-2026&csv=true`

Use `optionType=block_deals` for block deals. This is the website's published API CSV export, not a discovered static daily file store. Earlier `/api/historical/bulk-deals` and `/api/historical/block-deals` requests returned503; their exact server-side failure cause is unproven.

## Execution

Run `.github/workflows/nse_deals_recovery.yml` with explicit `report_date` YYYY-MM-DD. The push acceptance default is fixed4November2026 and must not be treated as a latest-date collector. Use a verified eligible historical session. The browser establishes ordinary session state via the catalogue and reports page. No stealth, captcha bypass or automatic download retry loop is used.

The workflow uses Playwright1.56 Chromium in the official container. It checks HTTP200, rejects HTML, checks nonempty CSV and all-row dates, accepts case variation in month names, records hashes and preserves raw returned CSVs before validation. Empty data is not automatically declared no deals. Independent schema, quantity/price, identifiers and exact byte readback checks remain required after acquisition. Successful download does not establish full ownership coverage or trading permission.

Artifacts `nse-deals-RUN_ID-ATTEMPT` retain raw reports and manifest for90days. Preserve evidence externally before expiry. Never put credentials or private storage IDs here.

First test42215089840 returnedHTTP200 for both reports but failed date validation because `04-NOV-2026` was compared case-sensitively. Commit68bede5c1caa4b745501f067bfeeb4d3ebf74cfd corrects that comparison and preserves raw CSV before validation. Keep the original failed run for audit. No punctual scheduled delivery claim follows from a push test.
