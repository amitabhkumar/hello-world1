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

Status, GSM, LTASM, STASM and ESM field labels are decoded from the official SURV76993 annexure. REG1 codes differ from REG_IND composite indicators. Unknown codes remain Unknown. REG1 applies to the next eligible trading session, as explicitly stated in NSE/SURV/67801 page 81 (NSE/SURV/64924; corrigendum65097 retains this rule). All currently populated non-reserved fields are decoded. Reserved fillers are never silently interpreted as future fields. Unknown values remain Unknown. Effective REG1 status does not by itself establish permitted trading sessions; trading_access remains Unknown until all applicable notices and band evidence are reconciled. The forthcoming ETF field is not silently activated.

Tests: PYTHONPATH=. python tests/test_nse_session_selection.py. Optional NSE_ARTIFACT_DIR validates an existing artifact. Tests cover weekend, holiday, special sessions, publication gate, month transition and fail-closed year coverage. Live deployment acceptance remains separate from unit tests.

## Drive delivery
GitHub artifact creation and Drive delivery are separate stages. The scheduled TITAN consumer must fetch the artifact, independently verify bytes/manifest, check existing files by date/hash, upload missing files into its authorized Incoming folder and read them back. Append a receipt and daily tracker. No private folder IDs or Google credentials are stored in this public repository. Missing execution environment means delivery pending, never success.

## Failure handling
Preserve exact errors and prior decisions. No automatic download retries. An event timeout is not proof of an NSE server outage. A successful scheduled configuration is not evidence of future execution or Drive persistence.

## Verification revision 06 November 2026
Collector commit f60eb622fcebecb848cfb28fc1ff2d68cb2878f1 passed live run42145340389, artifact13469652564. Independent artifact digest and CSV hashes passed. All3227 REG1 records have effective date2026-11-06 and no unknown currently populated non-reserved codes. November6 report advances to November8 Muhurat; November9 advances past November10 holiday.

Workflow uses version-matched official Playwright Python container to avoid installing Chromium and OS packages every run, with regression tests before acquisition. This is not a guarantee of punctual GitHub schedule dispatch. Preserve actual timestamps. GitHub documents delayed/dropped scheduled jobs under load. Keep SOP crons unchanged; no download retry loop.

Open evidence: official historical price-band endpoint observed in the report page JavaScript returned an empty list for05–06Nov2026; no effective-date classification was inferred. The official GSM page states stages III/IV are weekly (Monday/first trading day), while the ESM FAQ specifies stageII periodic call auction on trading days. These framework facts require security-specific effective notices and overlapping restriction reconciliation before permission can be asserted. 2027 official equity calendar was not located in the reviewed sources; do not invent it.

## Append-only correction and implementation, 06 November 2026
The earlier empty historical response used the wrong date format. The official endpoint uses dd-mm-yyyy: /api/eqsurvactions?from_date=05-11-2026&to_date=06-11-2026 returned 14 dated records. All six November 5 and eight November 6 change rows matched symbol, From, To and explicit effectiveDate. This corrects the earlier empty-response limitation, without asserting complete snapshot effective dates.

Collector commit4569d7d3a98a42c10b6dc8123824c93268d2f2b5 verifies each change row against one historical request, saves raw history and per-file evidence, and leaves mismatches unknown. GSM III/IV weekly dates and ESM II periodic call auction constraints are recorded as PARTIAL_FRAMEWORK_RULES; they are not a complete trading-permission decision. Full sec_list and SME snapshot effective-date evidence and overlapping restrictions remain pending. Tests: PYTHONPATH=. python tests/test_nse_effective_rules.py.

Container setup failures42145567794 and42145688384 occurred before NSE acquisition (host Python path and missing ensurepip respectively). Commit1f41a906348f42b45b2a6bf76895e4248f4d39eb installs required venv support. Run42174992874 succeeded with artifact13482258766; all six CSV hashes/rows independently matched the earlier saved files. Prior failures remain in Actions history. Test-only commit58b55613 triggered an existing validation workflow before the new collector functions were committed; its import failure is retained, and the final collector tests pass locally. No exact cron-start guarantee is claimed.

## GSM/ESM session repair — 06 November 2026
The previous function omitted GSM I/II and ESM I and unconditionally returned Unknown even for known prohibitions. Collector9eb7b2012322d3ab89f075491e850d4fcfaa64d1 now covers GSM0/I/II/III/IV and ESM I/II for the effective REG1 snapshot date. Suspended/inactive status, exchange closure and an ineligible GSM weekly date produce Blocked; denial takes precedence over ESM auction eligibility. ESM I retains the T+2 margin activation condition and existing2% band instead of inferring an entry date. GSM VI/unknown codes remain explicit unknown rules, not generic permission.

A separate gsm_esm_session_result distinguishes a known block, auction requirement, matched weekly date and absence of a GSM/ESM session prohibition. This is not global trading clearance or an intraday order-window decision. Other frameworks, complete bands and subsequent notices remain separate checks. No current observed stage is unmapped in the5November REG1 snapshot effective6November.

Live run42180201515, artifact13484638222, passed. Independent validation:3227records;16Blocked,19PeriodicCallAuctionRequired,3192NoGSMESMSessionProhibition; six CSVs unchanged from verified earlier hashes. New17regression tests and existing5effective tests pass; hosted test discovery job127767801662 also passed. Sources: NSE GSM FAQ12June2026 and SURV69315 (25July2025, actions retained in consolidatedSURV74008). Prior partial outputs remain valid historical records and are not overwritten.

## Security-master evidence repair — 15 November 2026
The NSE-listed MII security master (NSE_CM_security_ddmmyyyy.csv.gz) is now collected once for the exact selected report date. This is distinct from the NSE/BSE interop variant. GZIP integrity, decompression limits, schema, nonempty rows, token/ISIN identifiers and unique symbol-series keys are checked. Both compressed and decompressed SHA256/bytes are recorded.

Security status, normal-market eligibility, daily rupee range, call-auction indicator and closing-auction eligibility are decoded from CMTR73927 Part D Annexures 1/10, CMTR74466 Annexure A and CMTR74969 (effective September 7). These are master-snapshot values, not an intraday permission or a fill. The international ETF caution field is decoded from SURV76993; unknown future values stay Unknown.

security_access_evidence.json joins REG1, the master and band rows by symbol AND series. A confirmed effective-date band change proves that row only; it never dates the entire complete list. Conflicting bands, absent records, unsupported codes, master applicability and subsequent-notice gaps remain explicit. Master local update time is not publication time. No future file is relabelled current. No historical forecast is changed.

Observed scheduled run43639735482 rejected all six report downloads at source-host validation. The prior error omitted its actual URL. The collector now records download and page URLs before validation and accepts only enumerated HTTPS NSE hosts, including the official website's observed nseindia.in redirect. Blob URLs remain unapproved; an official-looking blob origin alone is not proof of upstream bytes. This must be verified in the new live artifact, not assumed from unit tests.

The workflow runs all test_nse_*.py tests before acquisition. Schedules, publication gate, no-retry policy and BSE workflows are unchanged. COMPLETE price-band applicability and comprehensive target-session clearance are NOT claimed by this repair: use the per-security pending checks. Reference sources:
- https://nsearchives.nseindia.com/content/circulars/CMTR73927.zip
- https://nsearchives.nseindia.com/content/circulars/CMTR74466.zip
- https://nsearchives.nseindia.com/content/circulars/CMTR74969.zip
- https://nsearchives.nseindia.com/content/circulars/SURV76993.zip


### 15 November 2026 acceptance and reconciliation correction
- Run 43670166789 preserved the actual rejected download URLs: official All Reports links used nsearchives.nseindia.in. The explicit HTTPS host allowlist now includes this observed archive host; arbitrary subdomains, non-HTTPS and blob URLs remain rejected.
- Run 43670676638 (push, commit b00ed9cc35cacd927e2cbdebdfaa50a63883943f) acquired all seven selected reports successfully. Artifact 14144132346 SHA256 be1a2be647dffdf8d9f893c9ac5e4d111aeb047d4ec66cfabad376ca148b0a2c. This is push acceptance, not proof of scheduled delivery.
- Separate band_snapshot_status and regulatory_snapshot_status from target-date applicability and trading_access. Explicit 'No Band' means NO_FIXED_BAND_REPORTED; blanks remain UNKNOWN. It does not by itself certify F&O membership.
- Coverage reports active REG1 rows, exact symbol/series master matches and active rows with band classifications. REG1-population coverage is not an exchange-wide completeness claim.
- resolve_band_timeline implements date-normalized, latest-applicable changes over an externally verified baseline and continuous change coverage. It rejects missing coverage, identity ambiguity and conflicting same-date revisions, retains unaffected rows and separates future changes. It is NOT used to fabricate baseline applicability: current complete-list applicability is still unverified. Its tests are diagnostic implementation tests, not exchange evidence.
- Original record 20261114_EVENING_R001 is unchanged. Observed remaining requirements: complete-band and MII snapshot applicability for target 16 November; subsequent security notices; live session status when that mode starts. Known dated suspension remains blocking.
