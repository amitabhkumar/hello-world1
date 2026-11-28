"""Read-only inventory & delta report: Market_Data/Incoming vs Market_Data/Historical."""
from __future__ import annotations

import csv
import json
import os
import re
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import requests

IST = timezone(timedelta(hours=5, minutes=30))
OUT_DIR = Path("inventory_output")
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


def find_folder(token: str, parent_id: str, folder_name: str) -> str | None:
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
    return files[0]["id"] if files else None


def list_folder_files(token: str, folder_id: str) -> list[dict[str, Any]]:
    files: list[dict[str, Any]] = []
    page_token = None
    while True:
        params: dict[str, Any] = {
            "q": f"'{folder_id}' in parents and trashed = false",
            "fields": "nextPageToken,files(id,name,mimeType,size,modifiedTime,md5Checksum)",
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


def parse_file_metadata(filename: str) -> tuple[str, str, str]:
    """Return (dataset_type, trading_date_iso, filename_hash_suffix)."""
    stem = Path(filename).stem
    hash_match = re.search(r"_([0-9a-fA-F]{8,64})$", stem)
    hash_suffix = hash_match.group(1) if hash_match else ""

    m = re.search(r"sec_bhavdata_full_(\d{2})(\d{2})(\d{4})", filename, re.IGNORECASE)
    if m:
        return ("nse_bhavcopy", f"{m.group(3)}-{m.group(2)}-{m.group(1)}", hash_suffix)

    m = re.search(r"ind_close_all_(\d{2})(\d{2})(\d{4})", filename, re.IGNORECASE)
    if m:
        return ("nse_indices", f"{m.group(3)}-{m.group(2)}-{m.group(1)}", hash_suffix)

    m = re.search(r"BhavCopy_BSE_CM_0_0_0_(\d{4})(\d{2})(\d{2})", filename, re.IGNORECASE)
    if m:
        return ("bse_bhavcopy", f"{m.group(1)}-{m.group(2)}-{m.group(3)}", hash_suffix)

    m_ts = re.search(r"(20\d{2})(\d{2})(\d{2})", filename)
    dt_iso = f"{m_ts.group(1)}-{m_ts.group(2)}-{m_ts.group(3)}" if m_ts else ""
    lower = filename.lower()
    if "announcement" in lower:
        dtype = "announcements"
    elif "price_band" in lower:
        dtype = "price_band"
    elif "shareholding" in lower:
        dtype = "shareholding"
    elif "ownership" in lower:
        dtype = "ownership"
    elif "manifest" in lower:
        dtype = "manifest"
    elif "nse_deals" in lower:
        dtype = "nse_deals_zip"
    else:
        dtype = "other"
    return (dtype, dt_iso, hash_suffix)


def build_inventory_rows(folder_label: str, files: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for f in sorted(files, key=lambda x: x["name"]):
        dtype, dt_iso, hash_suffix = parse_file_metadata(f["name"])
        rows.append(
            {
                "folder": folder_label,
                "filename": f["name"],
                "dataset_type": dtype,
                "trading_date": dt_iso,
                "filename_hash": hash_suffix,
                "md5_checksum": f.get("md5Checksum", ""),
                "size_bytes": f.get("size", ""),
                "modified_time": f.get("modifiedTime", ""),
            }
        )
    return rows


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, Any]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    token = get_drive_token()
    incoming_id = os.environ["GDRIVE_INCOMING_FOLDER_ID"]
    market_data_id = get_parent_folder_id(token, incoming_id)
    historical_id = find_folder(token, market_data_id, "Historical")
    if not historical_id:
        raise RuntimeError("Market_Data/Historical folder not found.")

    inc_rows = build_inventory_rows("Incoming", list_folder_files(token, incoming_id))
    hist_rows = build_inventory_rows("Historical", list_folder_files(token, historical_id))

    inv_fields = [
        "folder",
        "filename",
        "dataset_type",
        "trading_date",
        "filename_hash",
        "md5_checksum",
        "size_bytes",
        "modified_time",
    ]
    write_csv(OUT_DIR / "incoming_inventory.csv", inv_fields, inc_rows)
    write_csv(OUT_DIR / "historical_inventory.csv", inv_fields, hist_rows)

    eod_types = {"nse_bhavcopy", "nse_indices", "bse_bhavcopy"}
    inc_by_key: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for r in inc_rows:
        if r["dataset_type"] in eod_types and r["trading_date"]:
            inc_by_key[(r["dataset_type"], r["trading_date"])].append(r)

    comparison: list[dict[str, Any]] = []
    delta_missing: list[dict[str, Any]] = []
    status_counts: dict[str, int] = defaultdict(int)

    for h in hist_rows:
        if h["dataset_type"] not in eod_types or not h["trading_date"]:
            continue
        key = (h["dataset_type"], h["trading_date"])
        matches = inc_by_key.get(key, [])

        if not matches:
            status = "MISSING_IN_INCOMING"
        elif len(matches) > 1:
            status = "DUPLICATE_IN_INCOMING"
        elif matches[0]["md5_checksum"] == h["md5_checksum"]:
            status = "PRESENT_SAME_MD5"
        else:
            status = "PRESENT_DIFF_MD5"

        status_counts[status] += 1
        row = {
            "trading_date": h["trading_date"],
            "dataset_type": h["dataset_type"],
            "status": status,
            "historical_filename": h["filename"],
            "historical_md5": h["md5_checksum"],
            "incoming_filenames": " | ".join(m["filename"] for m in matches),
            "incoming_hashes": " | ".join(m["filename_hash"] for m in matches if m["filename_hash"]),
            "incoming_md5s": " | ".join(m["md5_checksum"] for m in matches),
        }
        comparison.append(row)
        if status == "MISSING_IN_INCOMING":
            delta_missing.append(row)

    comp_fields = [
        "trading_date",
        "dataset_type",
        "status",
        "historical_filename",
        "historical_md5",
        "incoming_filenames",
        "incoming_hashes",
        "incoming_md5s",
    ]
    write_csv(
        OUT_DIR / "comparison_by_date.csv",
        comp_fields,
        sorted(comparison, key=lambda x: (x["trading_date"], x["dataset_type"])),
    )
    write_csv(
        OUT_DIR / "delta_missing_files.csv",
        comp_fields,
        sorted(delta_missing, key=lambda x: (x["trading_date"], x["dataset_type"])),
    )

    summary = {
        "generated_at_ist": datetime.now(IST).isoformat(),
        "incoming_total_files": len(inc_rows),
        "historical_total_files": len(hist_rows),
        "delta_missing_count": len(delta_missing),
        "comparison_status_counts": dict(status_counts),
        "present_in_incoming_details": [c for c in comparison if c["status"] != "MISSING_IN_INCOMING"],
    }
    (OUT_DIR / "inventory_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
