# Optional verified Drive handoff
Operational delivery only. Existing acquisition results and schedules are unchanged.
Configure repository secrets GDRIVE_SERVICE_ACCOUNT_JSON, GDRIVE_INCOMING_FOLDER_ID,
and GDRIVE_LOGS_FOLDER_ID. Grant that service account write access to the designated
folders; connector access from a chat does not authenticate a GitHub runner.
Use a Drive location where the service account has storage/creation permission
(normally a shared drive). No credentials or private destination IDs belong here.
Missing configuration records NOT_TRANSFERRED without failing acquisition.

Each workflow invokes titan.drive_sync after acquisition and before artifact upload,
even after acquisition failure. Only explicitly validated CSV/JSON exports with
matching local hash, bytes and row count are eligible. Source dates and effective
dates remain separate. Failed and partial datasets remain in the compact summary.
The uploader does not establish trading permission or full research coverage.

Uploads are append-only, date/hash duplicates are reused after exact byte and parent
readback. Revisions have date/hash/run/time names. A compact per-run
sop_v3_manifest_summary.json and readback receipt accompany the data. Failed delivery
remains in drive_sync_receipt.json in the GitHub artifact. No automatic retry loop.

Announcement repair: the current BSE UI exposes #idnext (Next), not a numbered
1–5 window. Real Submit/Next clicks are captured using expect_response, including
page 6 and subsequent boundaries; no synthetic fetch URL or retry is used.
Visible Prev clicks return to Page 1 for its stability check (Submit on the final page was observed to request the old page number). Raw responses and before/after
DOM snapshots are preserved. Historical HTTP 400 remains a historical failure.
