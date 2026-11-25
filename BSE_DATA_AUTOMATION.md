# BSE supplementary data workflow

This acquisition workflow supplements the existing BSE BhavCopy downloader. It does not change TITAN scoring or establish a complete research/risk model.

## Run and schedule

Open Actions → **BSE supplementary datasets** → **Run workflow**. Supply an optional `report_date` (YYYY-MM-DD) and `datasets` (`all` or comma-separated IDs from `titan/bse_data.py`).

Configured requests, in Asia/Kolkata:
- 08:30 and 16:30 Monday–Friday.
- 22:00 daily.
- 08:00 Saturday.

GitHub can delay or miss scheduled starts. Verify actual executions. Without an explicit date, trading-file datasets use the verified BSE calendar: before 19:00 IST the previous eligible session, at/after 19:00 the latest eligible session. Disclosure feeds retain the current calendar date. The manifest records both dates and calendar hashes. Missing calendar coverage fails explicitly; no older-file substitution is made for a missing required file.

For an authorized, reproducible push acceptance run, commit-message markers `[bse-data-date=YYYY-MM-DD]` and optional `[bse-data-sets=bulk_block,price_bands]` select the test date/sources. Explicit CLI/workflow inputs take precedence. Scheduled runs do not inherit old commit-message test selections.

## Evidence and output

The workflow uploads `bse-data-RUN_ID-ATTEMPT`, retained for **90 days**. Each source has a manifest, raw responses, rendered-page evidence and normalized exports or original downloads where supported. Root/per-source manifests preserve requested date, retrieval times, source URLs, code commit, row counts, byte counts and SHA-256 hashes.

CSV/JSON exports are reopened and checked. Large JSON exports are split into numbered parts without losing rows; a complete CSV is also retained. Original archives and responses remain unchanged. No Drive credentials or private project identifiers are stored in this public repository; project-storage transfer is separate.

## Acceptance results

For the 29 October 2026 acceptance date, using the full run and subsequent retries:
- **7 dated-record categories:** announcements (1,565), delivery (5,053), corporate actions (2,613), ASM (81 short-term + 249 long-term), GSM (626), equity calendar (16 holidays), breadth (one dated row).
- **6 schema-checked snapshot categories:** pledges (1,240), 52-week high/low (92/158), VaR groups (2,344/1,798), SCRIP/regulatory references, active Equity T+1 master (5,123), market quotes (4,633).
- **3 partial categories:** bulk/block reliability, underlying shareholding detail, price-band universe coverage.
- **1 future-mode category:** live pre-open verification.

These figures are frozen acceptance observations, not a current market report or guaranteed future availability.

Evidence:
- [Full collection](https://github.com/amitabhkumar/hello-world1/actions/runs/40932045471), commit `8454ee189ae06f2992f7bc90282e958f369599fe`.
- [Shareholding/pledge/price-band retry](https://github.com/amitabhkumar/hello-world1/actions/runs/40932970541), commit `fef6d7b9a2fa07d0f0d5d258c8dbc65d825efb25`.
- [Independent deal types and deduplicated price-band probe](https://github.com/amitabhkumar/hello-world1/actions/runs/40933554829), commit `850ae04c0cdf6bf623cf788151428934177fbf36`.
- [Earlier 62-record bulk response](https://github.com/amitabhkumar/hello-world1/actions/runs/40930706702) remains preserved; subsequent same-date responses were malformed empty objects.

All **21 automated tests** passed in the final code acceptance run. Independent verification reopened four retained archives, checked their digests/CRCs and 541 referenced files, reconciled final export row counts, and checked announcement dates/uniqueness and all 5,053 delivery records' dates/arithmetic.

## Status meanings

| Status | Meaning |
|---|---|
| VALIDATED_DATED_RECORDS | Dataset-specific schema/date checks passed; read the stated coverage/window. |
| VALIDATED_SNAPSHOT | Returned records pass schema checks; this is not complete historical point-in-time coverage or a live/executable quote guarantee. |
| DOWNLOADED_UNVALIDATED | File integrity checked; economic meaning/effective date still needs validation. |
| PARTIAL | Useful data or a tested route exists, but required reliability/scope remains incomplete. |
| CAPTURED_UNVALIDATED / SOURCE_ONLY / NO_DOWNLOAD_FOUND | Evidence only; no complete usable feed claimed. |
| NOT_APPLICABLE | Future phase/mode required; not proof the future feed works. |
| FAILED / ACCESS_BLOCKED | Explicit error; other sources continue. |

The collector intentionally exits nonzero while any requested category remains partial or unavailable. Artifacts are uploaded even after partial collection. A red workflow does not mean every download failed; it must not be relabelled green to hide coverage gaps.

## Historical remaining requirements at the October acceptance

1. **Bulk/block:** latest exact-date endpoints returned `{}` without the expected Table schema, despite an earlier 62-row bulk response. UI and explicit API requests were tested. Treat both deal types independently; obtain a valid dated official report or schema-bearing response before claiming reliable retrieval. Never treat malformed empty responses as zero deals.
2. **Shareholding:** the later retry downloaded 23,626 filing-index records. This is a relative last-year window at retrieval time, not a historical as-of database. Parse original issuer XBRL/filings for ownership conclusions; quarters and revisions may differ.
3. **Price bands:** one official page/API probe for security 532755 worked. The current source is explicitly a single-security probe, not an exchange-wide implementation. Extend to independently discovered research candidates and validate identifiers, units and effective dates before applying filters.
4. **Risk references:** raw REG_IND/REG1_IND flags are preserved. BSE's bundled SCRIP_STANDARDISED_FORMAT.docx marks many UDiFF columns, including TradToTradInd, as filler. Do not infer eligibility from column names. VaR grouping files are not numerical VaR rates and may apply to a later period.
5. **Pre-open/depth:** after-hours snapshots do not verify a live auction or order-book feed. Validate during the actual eligible phase; indicative orders are not executed trades.
6. **Calendar/cutoffs:** equity holiday tables retain a separate Muhurat-session notice; confirm its hours from the relevant circular. A default calendar date is not trading-session verification.

## Continuity

Preserve each artifact before expiry, verify exact file hashes/dates/row counts on readback, and append project-storage receipts. Reload the authoritative SOP and latest research ledger for every research run. Keep frozen forecasts, failed responses, and corrections separately. Missing data must remain missing; successful acquisition alone does not justify a high-conviction classification.


## 15 November 2026 repair

Commit c00cfb2b942a8d105a9bcb6d33f6520f422bd1d3, live run 43697474620, independently validated export hashes/bytes/counts and all delivery rows: 5,141 delivery rows, 51 bulk rows, schema-bearing empty block response, 1 breadth row, ASM 68/226, GSM 625, regulatory 20,910/7,960/5,870. Prior failures are retained. An empty BannedSecurities member no longer prevents parsing other reference members; it is preserved as EMPTY_SCHEMA_VALID and does not establish unrestricted trading.

The detail collector adds the entire active Equity T+1 master population for price-band snapshots and the latest original HTML ownership filing per issuer in the one-year index. Original response bytes and normalized ownership tables are retained. Eight in-flight requests maximum, no download retry loop, and access-denial/rate-limit responses stop further batches. Progress files retain counts and errors. The job budget is 60 minutes to accommodate declared coverage; existing cron times are unchanged. A timeout or incomplete population remains partial, never complete.

Price-band source dates, execution dates and target session remain distinct. Future-dated snapshots are not approved current-session risk filters. Shareholding submission time, index EndDate and stated quarter are retained separately. Parsed original tables do not themselves establish quarter-on-quarter ownership changes. Regulatory code/effective-session interpretation and actual pre-open validation remain separate research requirements.

### Completed detail acceptance and automatic reuse

Run 43733694031 (commit c9357111f2c5241fb693edd742142d54efe23a36) completed both requested categories: 5,147/5,147 active-equity band snapshots and 5,124/5,124 latest original ownership tables, zero detail errors. Independent validation checked all original/normalized hashes, row counts, issuer bindings, positive finite band limits and source dates. All band PBdate values were 14 November; this is a source date, not established effective-session permission for the 13 November target. 4,213 ownership originals were reused exactly and 911 fetched. Earlier run43697889839 hit60 minutes; its progress count4223 exceeded the actual4215 preserved originals. Only actual files receive credit.

Production now stops detail collection gracefully at45 minutes, before the60-minute runner limit, preserving receipts and exact remaining items. The immutable-original cache is restored automatically on scheduled runs. A cached filing is reused only when the current original URL and saved SHA256 match; changed originals are fetched once. Cached original retrieval times are preserved when known and remain null when unknown; validation time is separate. Cache failure or eviction must not be reported as successful reuse. The original raw documents remain in artifacts and authorized project storage.

Run43735297296 completed cache seeding. A separate no-explicit-resume acceptance is recorded in the project receipt; do not infer actual future scheduled delivery or punctuality from these push tests. All exchange cron schedules remain unchanged. Source acquisition success does not complete a TITAN research scan or establish security-specific trading permission.

Automatic-cache acceptance run43736045886 completed successfully with78 repository tests passing. It restored bse-originals-43735297296-1 without an explicit resume run ID and validated all5124 ownership filings withzero detail errors. The independently checked acceptance receipt records exact reuse and canonical saved files. These were push acceptances, not proof of punctual scheduled execution.


## 17 November 2026 targeted CSV repair

Announcements retain previous-eligible-session overlap on default runs. Exact-date acceptance inputs remain exact. The session warms up on https://bseindia.com; announcement requests use the browser context with explicit official Origin and Referer headers. Dates remain YYYYMMDD and pagination reconciles Table1 ROWCNT with unique records and a stable first-page recheck. Missing Table is an explicit failure, never zero announcements.

Pledges use the official visible Consolidated Pledge CSV control and Playwright expect_download. Nonempty bytes, security identifiers, pledge columns and positive record count are required. The raw download and normalized records are preserved with SHA256. The current snapshot as-on text is retained separately from requested report date; this does not reconstruct historical pledge holdings. A missing/ambiguous export control or invalid download fails explicitly without JSON fallback or retry loops.

Implementation commit 3d73d31bce30b2097b74c5c54880ff60d1374c4a; targeted live acceptance is recorded separately in project receipts. Initial run43997849237 failed before acquisition because an obsolete test asserted the retired JSON implementation. It is preserved; behavioral CSV tests replaced that assertion. No NSE, Bhavcopy source or cron definitions changed.

## 25 November 2026 — Section 6 delivery note

Full BSE archives over 100 MB exceed the ChatGPT Drive connector transfer cap.
For chat delivery, preserve the original archive and transfer a validated compact
subset with a receipt identifying its scope. The direct runner-to-Drive OAuth
path bypasses that connector and its 100 MB limit. Operational acceptance
requires a real self-test receipt verifying the downloaded bytes and parent.
