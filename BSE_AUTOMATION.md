# BSE daily bhavcopy automation

This repository contains a normal-browser adaptation of the supplied working downloader. It does not include fingerprint hiding, proxy rotation, CAPTCHA handling or access-control bypasses. A 401/403/429 or challenge stops the run. A successful unit test is not proof of live BSE access.

## Operation

The BSE Bhavcopy GitHub Actions workflow runs at 08:30 IST weekdays, 16:30 IST weekdays, 22:00 IST daily, and 08:00 IST Saturday. Pushes run offline tests only. Actions → BSE Bhavcopy → Run workflow starts a live run; optionally supply YYYY-MM-DD. Public-repository standard GitHub runners require no paid data subscription. No paid service or new billing plan is configured.

Before 16:30 IST it checks up to 14 prior calendar dates for a published report, including special weekend sessions. At/after 16:30 it requires the current date. An explicit date overrides this. Missing reports are never relabelled, and publication history is not treated as a verified holiday calendar. The SOP task must separately verify the official trading calendar, missing sessions, and report freshness. A layout timeout is a failure, not proof of a holiday. Selectors follow the user-supplied navigation and remain subject to BSE UI changes.

Every run produces output/manifest.json. Only a validated download adds a CSV. Validation checks the exact date-bearing CM filename, official HTTPS hostname, ZIP integrity and size, required fields, every row's TradDt/Src/Sgmt, instrument IDs and nonzero rows. It records SHA-256, byte count and row count. Invalid downloads are removed. An empty output directory prevents accidental reuse of an old file.

Exit codes: 0 VALIDATED_DOWNLOAD; 2 NOT_PUBLISHED_OR_NO_SESSION; 3 ACCESS_BLOCKED; 1 FAILED. Download success does not mean Drive delivery: drive_status stays NOT_TRANSFERRED.

## Drive handoff

The existing authorized SOP tasks retrieve `bse-RUN_ID-ATTEMPT` artifacts through the connected GitHub tool, validate their manifest and bytes independently, and upload the CSV to the existing authorized Market_Data/Incoming folder through the Google Drive connector. Private folder IDs, account details, credentials and the SOP itself are deliberately absent from this public repository. GitHub does not receive Google OAuth tokens.

The handoff is a scheduled agent operation, not a native GitHub-to-Drive service. If the current workflow is still running at SOP start, the task must wait within its execution budget or explicitly mark delivery pending and reconcile at the next run. It must not claim immediate synchronization. Artifacts expire after seven days. Check existing Drive files by date and SHA-256 first: identical files are reused; conflicting bytes are retained as separately identified revisions. After upload, read bytes back and compare SHA-256 and parent folder. Save the receipt in the authorized Logs folder.

## Limits and monitoring

GitHub schedules can be delayed or dropped under load. Public-repository schedules can be disabled after 60 days without repository activity. The weekly SOP review must verify the workflow state, recent executions, artifact retention and Drive receipts, and report missed sessions. This is not an exact-minute uptime guarantee.

A denied scheduled runner must not be treated as fixed simply because the original script worked on another computer. Preserve the error and seek BSE's supported access process. There is no automatic network rotation or aggressive retry. End-to-end acceptance requires a real dated BSE CSV plus a matching Drive readback receipt.

## Local execution

Python 3.12 recommended. Install `pip install -r requirements-bse.txt` and `python -m playwright install chromium`. Run `python -m titan.bse --date YYYY-MM-DD --output new-run-folder`. Linux without a display needs Xvfb (`xvfb-run --auto-servernum python -m titan.bse`). Run offline tests with `python -m unittest discover -s tests -v`.

Official references:
- https://playwright.dev/python/docs/downloads
- https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows
- https://docs.github.com/en/actions/tutorials/store-and-share-data
