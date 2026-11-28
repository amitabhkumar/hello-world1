"""Compare Market_Data/Historical vs Market_Data/Incoming by (dataset, date)
and copy only missing files into Market_Data/Delta."""
from __future__ import annotations

import json
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import requests

IST = timezone(timedelta(hours=5, minutes=30))
OUT_DIR = Path("delta_output")
OUT_DIR.mkdir(exist_ok=True)


def get_drive_token() -> str:
    resp = requests.post(
        "https://oauth2.googleapis.com/token",
        data={
            "client_id": os.environ["GDRIVE_CLIENT_ID"],
            "client_secret": os.environ["GDRIVE_CLIENT_SECRET"],
            "refresh_token": os.environ["GDRIVE_REFRESH_TOKEN"],
            "grant_type": "refresh_token",
        },
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


def get_parent_folder_id(token: str, folder_id: str) -> str:
    r = requests.get(
        f"https://www.googleapis.com/drive/v3/files/{folder_id}",
        headers={"Authorization": f"Bearer {token}"},
        params={"fields": "id,name,parents"},
        timeout=30,
    )
    r.raise_for_status()
    parents = r.json().get("parents", [])
    if not parents:
        raise RuntimeError("Could not resolve parent Market_Data folder.")
    return parents[0]


def find_or_create_folder(token: str, parent_id: str, folder_name: str) -> str:
    q = (
        f"'{parent_id}' in parents and name = '{folder_name}' "
        "and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
    )
    r = requests.get(
        "https://www.googleapis.com/drive/v3/files",
        headers={"Authorization": f"Bearer {token}"},
        params={"q": q, "fields": "files(id,name)", "pageSize": 10},
        timeout=30,
    )
    r.raise_for_status()
    files = r.json().get("files", [])
    if files:
        return files[0]["id"]

    create_resp = requests.post(
        "https://www.googleapis.com/drive/v3/files",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        json={
            "name": folder_name,
            "mimeType": "application/vnd.google-apps.folder",
            "parents": [parent_id],
        },
        timeout=30,
    )
    create_resp.raise_for_status()
    return create_resp.json()["id"]


def list_folder_files(token: str, folder_id: str) -> list[dict[str, Any]]:
    files: list[dict[str, Any]] = []
    page_token = None
    while True:
        params: dict[str, Any] = {
            "q": f"'{folder_id}' in parents and trashed = false",
            "fields": "nextPageToken,files(id,name,mimeType)",
            "pageSize": 1000,
        }
        if page_token:
            params["pageToken"] = page_token
        r = requests.get(
            "https://www.googleapis.com/drive/v3/files",
            headers={"Authorization": f"Bearer {token}"},
            params=params,
            timeout=30,
        )
        r.raise_for_status()
        data = r.json()
        files.extend(data.get("files", []))
        page_token = data.get("nextPageToken")
        if not page_token:
            break
    return files


def extract_key(filename: str) -> tuple[str, str] | None:
    """Return (dataset_type, YYYY-MM-DD) for supported EOD files, else None."""
    m = re.search(r"sec_bhavdata_full_(\d{2})(\d{2})(\d{4})", filename, re.IGNORECASE)
    if m:
        return ("nse_bhavcopy", f"{m.group(3)}-{m.group(2)}-{m.group(1)}")

    m = re.search(r"ind_close_all_(\d{2})(\d{2})(\d{4})", filename, re.IGNORECASE)
    if m:
        return ("nse_indices", f"{m.group(3)}-{m.group(2)}-{m.group(1)}")

    m = re.search(r"BhavCopy_BSE_CM_0_0_0_(\d{4})(\d{2})(\d{2})", filename, re.IGNORECASE)
    if m:
        return ("bse_bhavcopy", f"{m.group(1)}-{m.group(2)}-{m.group(3)}")

    return None


def copy_drive_file(token: str, file_id: str, dest_folder_id: str, name: str) -> str:
    r = requests.post(
        f"https://www.googleapis.com/drive/v3/files/{file_id}/copy",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        json={"name": name, "parents": [dest_folder_id]},
        timeout=30,
    )
    r.raise_for_status()
    return r.json()["id"]


def main() -> None:
    token = get_drive_token()
    incoming_id = os.environ["GDRIVE_INCOMING_FOLDER_ID"]
    market_data_id = get_parent_folder_id(token, incoming_id)
    historical_id = find_or_create_folder(token, market_data_id, "Historical")
    delta_id = find_or_create_folder(token, market_data_id, "Delta")

    incoming_files = list_folder_files(token, incoming_id)
    historical_files = list_folder_files(token, historical_id)
    delta_existing_names = {f["name"] for f in list_folder_files(token, delta_id)}

    incoming_keys: set[tuple[str, str]] = set()
    for f in incoming_files:
        k = extract_key(f["name"])
        if k:
            incoming_keys.add(k)

    copied: list[str] = []
    skipped_in_incoming: list[str] = []
    skipped_in_delta: list[str] = []

    for f in sorted(historical_files, key=lambda x: x["name"]):
        key = extract_key(f["name"])
        if not key:
            continue
        if key in incoming_keys:
            skipped_in_incoming.append(f["name"])
            continue
        if f["name"] in delta_existing_names:
            skipped_in_delta.append(f["name"])
            continue

        copy_drive_file(token, f["id"], delta_id, f["name"])
        copied.append(f["name"])

    summary = {
        "generated_at_ist": datetime.now(IST).isoformat(),
        "incoming_matched_dates_count": len(incoming_keys),
        "copied_to_delta": len(copied),
        "skipped_already_in_incoming": len(skipped_in_incoming),
        "skipped_already_in_delta": len(skipped_in_delta),
        "skipped_in_incoming_files": skipped_in_incoming,
    }
    (OUT_DIR / "delta_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
