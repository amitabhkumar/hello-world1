"""Backfill the last N NSE/BSE trading days into Google Drive: Market_Data/Historical."""
from __future__ import annotations

import json
import os
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import requests

IST = timezone(timedelta(hours=5, minutes=30))

# Official 2026 NSE/BSE Equity Trading Holidays (Sep-Dec 2026)
EXCHANGE_HOLIDAYS_2026 = {
    "2026-09-14",  # Ganesh Chaturthi
    "2026-10-02",  # Mahatma Gandhi Jayanti
    "2026-10-20",  # Dussehra
    "2026-11-10",  # Diwali-Balipratipada
    "2026-11-24",  # Prakash Gurpurb Sri Guru Nanak Dev
    "2026-12-25",  # Christmas
}

# Special/shortened sessions (valid trading day, flagged for SOP V3.0 Ref A baseline exclusion)
SPECIAL_SESSIONS_2026 = {
    "2026-11-08",  # Diwali Laxmi Pujan (Muhurat Trading)
}

NSE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "text/csv,text/plain,*/*",
    "Referer": "https://www.nseindia.com/",
}

BSE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "text/csv,text/plain,*/*",
    "Referer": "https://www.bseindia.com/",
}

OUT_DIR = Path("historical_output")
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
        raise RuntimeError("Could not resolve parent Market_Data folder from GDRIVE_INCOMING_FOLDER_ID.")
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


def list_existing_filenames(token: str, folder_id: str) -> dict[str, str]:
    existing: dict[str, str] = {}
    page_token = None
    while True:
        params: dict[str, Any] = {
            "q": f"'{folder_id}' in parents and trashed = false",
            "fields": "nextPageToken,files(id,name)",
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
        for f in data.get("files", []):
            existing[f["name"]] = f["id"]
        page_token = data.get("nextPageToken")
        if not page_token:
            break
    return existing


def upload_bytes_to_drive(
    token: str,
    folder_id: str,
    filename: str,
    content: bytes,
    mime_type: str = "text/csv",
    existing_file_id: str | None = None,
) -> str:
    boundary = "titan_historical_boundary_001"
    if existing_file_id:
        r = requests.patch(
            f"https://www.googleapis.com/upload/drive/v3/files/{existing_file_id}?uploadType=media",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": mime_type,
            },
            data=content,
            timeout=60,
        )
        r.raise_for_status()
        return r.json()["id"]

    metadata = json.dumps({"name": filename, "parents": [folder_id]}).encode("utf-8")
    body = (
        f"--{boundary}\r\n"
        "Content-Type: application/json; charset=UTF-8\r\n\r\n"
    ).encode("utf-8") + metadata + (
        f"\r\n--{boundary}\r\n"
        f"Content-Type: {mime_type}\r\n\r\n"
    ).encode("utf-8") + content + f"\r\n--{boundary}--\r\n".encode("utf-8")

    r = requests.post(
        "https://www.googleapis.com/upload/drive/v3/files?uploadType=multipart",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": f"multipart/related; boundary={boundary}",
        },
        data=body,
        timeout=60,
    )
    r.raise_for_status()
    return r.json()["id"]


def get_last_n_trading_days(n: int) -> list[date]:
    now_ist = datetime.now(IST)
    # Only include today if after 18:30 IST (EOD Bhavcopy publication window)
    cursor = now_ist.date() if (now_ist.hour > 18 or (now_ist.hour == 18 and now_ist.minute >= 30)) else (now_ist.date() - timedelta(days=1))
    days: list[date] = []
    while len(days) < n:
        iso = cursor.strftime("%Y-%m-%d")
        is_special = iso in SPECIAL_SESSIONS_2026
        is_weekday = cursor.weekday() < 5
        is_holiday = iso in EXCHANGE_HOLIDAYS_2026
        if is_special or (is_weekday and not is_holiday):
            days.append(cursor)
        cursor -= timedelta(days=1)
    return list(reversed(days))


def fetch_csv(url: str, headers: dict[str, str], expected_token: str) -> bytes | None:
    for attempt in range(3):
        try:
            r = requests.get(url, headers=headers, timeout=25)
            if r.status_code == 200 and expected_token in r.text[:300]:
                return r.content
            if r.status_code == 404:
                return None
        except requests.RequestException:
            pass
        time.sleep(1.5 * (attempt + 1))
    return None


def main() -> None:
    target_days = int(os.environ.get("TRADING_DAYS", "45"))
    token = get_drive_token()
    incoming_id = os.environ["GDRIVE_INCOMING_FOLDER_ID"]
    market_data_id = get_parent_folder_id(token, incoming_id)
    historical_id = find_or_create_folder(token, market_data_id, "Historical")
    existing = list_existing_filenames(token, historical_id)

    trading_days = get_last_n_trading_days(target_days)
    manifest: list[dict[str, Any]] = []
    counts = {"uploaded": 0, "skipped_existing": 0, "missing": 0}

    for d in trading_days:
        iso = d.strftime("%Y-%m-%d")
        ddmmyyyy = d.strftime("%d%m%Y")
        yyyymmdd = d.strftime("%Y%m%d")

        datasets = [
            (
                "nse_bhavcopy",
                f"sec_bhavdata_full_{ddmmyyyy}.csv",
                f"https://nsearchives.nseindia.com/products/content/sec_bhavdata_full_{ddmmyyyy}.csv",
                NSE_HEADERS,
                "SYMBOL",
            ),
            (
                "nse_indices",
                f"ind_close_all_{ddmmyyyy}.csv",
                f"https://nsearchives.nseindia.com/content/indices/ind_close_all_{ddmmyyyy}.csv",
                NSE_HEADERS,
                "Index Name",
            ),
            (
                "bse_bhavcopy",
                f"BhavCopy_BSE_CM_0_0_0_{yyyymmdd}_F_0000.CSV",
                f"https://www.bseindia.com/download/BhavCopy/Equity/BhavCopy_BSE_CM_0_0_0_{yyyymmdd}_F_0000.CSV",
                BSE_HEADERS,
                "TradDt",
            ),
        ]

        day_status: dict[str, Any] = {
            "date": iso,
            "is_special_session": iso in SPECIAL_SESSIONS_2026,
            "files": {},
        }

        for key, filename, url, headers, check_token in datasets:
            if filename in existing:
                day_status["files"][key] = "SKIPPED_EXISTING"
                counts["skipped_existing"] += 1
                continue

            raw = fetch_csv(url, headers, check_token)
            if raw:
                upload_bytes_to_drive(token, historical_id, filename, raw, "text/csv")
                existing[filename] = "uploaded"
                day_status["files"][key] = "UPLOADED"
                counts["uploaded"] += 1
            else:
                day_status["files"][key] = "MISSING_ON_EXCHANGE"
                counts["missing"] += 1
            time.sleep(0.4)

        manifest.append(day_status)
        print(f"{iso} | {day_status['files']}")

    summary = {
        "generated_at_ist": datetime.now(IST).isoformat(),
        "trading_days_requested": target_days,
        "date_range": [trading_days[0].strftime("%Y-%m-%d"), trading_days[-1].strftime("%Y-%m-%d")],
        "counts": counts,
        "sessions": manifest,
    }
    summary_bytes = json.dumps(summary, indent=2).encode("utf-8")
    (OUT_DIR / "historical_manifest.json").write_bytes(summary_bytes)
    upload_bytes_to_drive(
        token,
        historical_id,
        "historical_manifest.json",
        summary_bytes,
        "application/json",
        existing_file_id=existing.get("historical_manifest.json"),
    )
    print(json.dumps({"date_range": summary["date_range"], "counts": counts}, indent=2))


if __name__ == "__main__":
    main()
