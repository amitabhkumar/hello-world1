"""30-day EOD reference math & Research_Ledger reconciliation test audit.
Writes test outputs to Market_Data/Audit_30D_Test on Drive and local audit_30d_output/."""
from __future__ import annotations

import io
import json
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import requests

IST = timezone(timedelta(hours=5, minutes=30))
OUT_DIR = Path("audit_30d_output")
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


def find_or_create_folder(token: str, parent_id: str, folder_name: str) -> str:
    existing = find_folder(token, parent_id, folder_name)
    if existing:
        return existing
    r = requests.post(
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
    r.raise_for_status()
    return r.json()["id"]


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


def download_bytes(token: str, file_id: str) -> bytes:
    r = requests.get(
        f"https://www.googleapis.com/drive/v3/files/{file_id}",
        headers={"Authorization": f"Bearer {token}"},
        params={"alt": "media"},
        timeout=60,
    )
    r.raise_for_status()
    return r.content


def upload_or_update_file(
    token: str, folder_id: str, filename: str, content: bytes, mime_type: str
) -> str:
    existing_files = list_folder_files(token, folder_id)
    existing = next((f for f in existing_files if f["name"] == filename), None)

    metadata: dict[str, Any] = {"name": filename}
    if not existing:
        metadata["parents"] = [folder_id]

    boundary = "titan_audit_boundary_30d"
    body = (
        f"--{boundary}\r\n"
        "Content-Type: application/json; charset=UTF-8\r\n\r\n"
        f"{json.dumps(metadata)}\r\n"
        f"--{boundary}\r\n"
        f"Content-Type: {mime_type}\r\n\r\n"
    ).encode("utf-8") + content + f"\r\n--{boundary}--\r\n".encode("utf-8")

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": f"multipart/related; boundary={boundary}",
    }
    if existing:
        r = requests.patch(
            f"https://www.googleapis.com/upload/drive/v3/files/{existing['id']}",
            headers=headers,
            params={"uploadType": "multipart"},
            data=body,
            timeout=60,
        )
    else:
        r = requests.post(
            "https://www.googleapis.com/upload/drive/v3/files",
            headers=headers,
            params={"uploadType": "multipart"},
            data=body,
            timeout=60,
        )
    r.raise_for_status()
    return r.json()["id"]


def parse_eod_key(filename: str) -> tuple[str, str] | None:
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


def normalize_cols(df: pd.DataFrame) -> pd.DataFrame:
    df.columns = [re.sub(r"[^A-Z0-9]+", "_", str(c).strip().upper()).strip("_") for c in df.columns]
    return df


def pick_col(df: pd.DataFrame, candidates: list[str]) -> str | None:
    for c in candidates:
        if c in df.columns:
            return c
    return None


def compute_nse_30d_metrics(token: str, nse_files: list[dict[str, Any]]) -> pd.DataFrame:
    by_date: dict[str, dict[str, Any]] = {}
    for f in nse_files:
        key = parse_eod_key(f["name"])
        if key and key[0] == "nse_bhavcopy":
            by_date[key[1]] = f

    sorted_dates = sorted(by_date.keys())
    # Load up to 50 recent sessions so the final 30 trading days have rolling 20-day history
    selected_dates = sorted_dates[-50:]
    frames: list[pd.DataFrame] = []

    for dt in selected_dates:
        raw = download_bytes(token, by_date[dt]["id"])
        df = normalize_cols(pd.read_csv(io.BytesIO(raw)))

        sym_col = pick_col(df, ["SYMBOL", "TCKRSYMB", "SECURITY_SYMBOL"])
        ser_col = pick_col(df, ["SERIES", "SCTYSRS"])
        close_col = pick_col(df, ["CLOSE_PRICE", "CLSPRIC", "CLOSE"])
        vol_col = pick_col(df, ["TTL_TRD_QNTY", "TOTTRADQTY", "VOLUME"])
        deliv_qty_col = pick_col(df, ["DELIV_QTY", "DELIVQTY"])
        deliv_pct_col = pick_col(df, ["DELIV_PER", "DELIVPER"])
        high_col = pick_col(df, ["HIGH_PRICE", "HGHPRIC", "HIGH"])
        low_col = pick_col(df, ["LOW_PRICE", "LWPRIC", "LOW"])

        if not sym_col or not close_col or not vol_col:
            continue

        sub = df.copy()
        if ser_col:
            sub = sub[sub[ser_col].astype(str).str.strip().isin(["EQ", "BE"])]

        sub = pd.DataFrame(
            {
                "trading_date": dt,
                "symbol": sub[sym_col].astype(str).str.strip(),
                "close": pd.to_numeric(sub[close_col], errors="coerce"),
                "volume": pd.to_numeric(sub[vol_col], errors="coerce"),
                "high": pd.to_numeric(sub[high_col], errors="coerce") if high_col else pd.NA,
                "low": pd.to_numeric(sub[low_col], errors="coerce") if low_col else pd.NA,
                "deliv_qty": pd.to_numeric(sub[deliv_qty_col], errors="coerce") if deliv_qty_col else pd.NA,
                "deliv_pct": pd.to_numeric(sub[deliv_pct_col], errors="coerce") if deliv_pct_col else pd.NA,
            }
        ).dropna(subset=["symbol", "close", "volume"])
        frames.append(sub)

    if not frames:
        return pd.DataFrame()

    all_df = pd.concat(frames, ignore_index=True).sort_values(["symbol", "trading_date"])
    g = all_df.groupby("symbol", group_keys=False)

    all_df["vol_ma20"] = g["volume"].transform(lambda s: s.rolling(20, min_periods=5).mean())
    all_df["rvol20"] = (all_df["volume"] / all_df["vol_ma20"]).round(4)
    all_df["ma20"] = g["close"].transform(lambda s: s.rolling(20, min_periods=5).mean()).round(4)
    all_df["high_20d"] = g["high"].transform(lambda s: s.rolling(20, min_periods=5).max()).round(4)
    all_df["low_20d"] = g["low"].transform(lambda s: s.rolling(20, min_periods=5).min()).round(4)
    all_df["deliv_qty_ma20"] = g["deliv_qty"].transform(
        lambda s: s.rolling(20, min_periods=5).mean()
    ).round(2)
    all_df["deliv_pct_ma20"] = g["deliv_pct"].transform(
        lambda s: s.rolling(20, min_periods=5).mean()
    ).round(2)

    last_30_dates = set(sorted_dates[-30:])
    out = all_df[all_df["trading_date"].isin(last_30_dates)].sort_values(
        ["trading_date", "rvol20"], ascending=[True, False]
    )
    return out


def audit_research_ledger(token: str, root_parent_id: str) -> dict[str, Any]:
    """Search Drive for Research_Ledger folder/files and summarize sizes & pending items."""
    q = "name contains 'Research_Ledger' and trashed = false"
    r = requests.get(
        "https://www.googleapis.com/drive/v3/files",
        headers={"Authorization": f"Bearer {token}"},
        params={
            "q": q,
            "fields": "files(id,name,mimeType,size,modifiedTime,parents)",
            "pageSize": 100,
        },
        timeout=30,
    )
    r.raise_for_status()
    matches = r.json().get("files", [])

    ledger_folder = next(
        (m for m in matches if m.get("mimeType") == "application/vnd.google-apps.folder"),
        None,
    )
    ledger_files: list[dict[str, Any]] = []
    if ledger_folder:
        ledger_files = list_folder_files(token, ledger_folder["id"])

    json_reports: list[dict[str, Any]] = []
    for f in ledger_files:
        if f["name"].lower().endswith(".json"):
            size_bytes = int(f.get("size") or 0)
            pending_count = None
            top_keys: list[str] = []
            try:
                raw = json.loads(download_bytes(token, f["id"]).decode("utf-8", errors="replace"))
                if isinstance(raw, dict):
                    top_keys = list(raw.keys())[:15]
                    if isinstance(raw.get("pending"), list):
                        pending_count = len(raw["pending"])
                    elif isinstance(raw.get("pending"), dict):
                        pending_count = len(raw["pending"])
            except Exception as exc:
                top_keys = [f"parse_error:{exc}"]

            json_reports.append(
                {
                    "name": f["name"],
                    "size_bytes": size_bytes,
                    "size_kb": round(size_bytes / 1024, 2),
                    "pending_count": pending_count,
                    "top_keys": top_keys,
                }
            )

    json_reports.sort(key=lambda x: x["size_bytes"], reverse=True)
    return {
        "root_parent_folder_id": root_parent_id,
        "ledger_folder_found": bool(ledger_folder),
        "ledger_folder_id": ledger_folder["id"] if ledger_folder else None,
        "ledger_total_files": len(ledger_files),
        "json_files_inspected": len(json_reports),
        "largest_json_files": json_reports[:15],
    }


def main() -> None:
    token = get_drive_token()
    incoming_id = os.environ["GDRIVE_INCOMING_FOLDER_ID"]
    market_data_id = get_parent_folder_id(token, incoming_id)
    historical_id = find_folder(token, market_data_id, "Historical")
    if not historical_id:
        raise RuntimeError("Market_Data/Historical folder not found.")

    test_folder_id = find_or_create_folder(token, market_data_id, "Audit_30D_Test")
    hist_files = list_folder_files(token, historical_id)
    metrics_df = compute_nse_30d_metrics(token, hist_files)
    ledger_audit = audit_research_ledger(token, market_data_id)

    metrics_csv_path = OUT_DIR / "ref_a_nse_30d_metrics.csv"
    metrics_csv_bytes = metrics_df.to_csv(index=False).encode("utf-8")
    metrics_csv_path.write_bytes(metrics_csv_bytes)

    summary = {
        "generated_at_ist": datetime.now(IST).isoformat(),
        "test_drive_folder": "Market_Data/Audit_30D_Test",
        "test_drive_folder_id": test_folder_id,
        "historical_files_available": len(hist_files),
        "metrics_30d_rows": int(len(metrics_df)),
        "metrics_30d_unique_dates": int(metrics_df["trading_date"].nunique()) if not metrics_df.empty else 0,
        "metrics_30d_unique_symbols": int(metrics_df["symbol"].nunique()) if not metrics_df.empty else 0,
        "metrics_30d_date_min": str(metrics_df["trading_date"].min()) if not metrics_df.empty else None,
        "metrics_30d_date_max": str(metrics_df["trading_date"].max()) if not metrics_df.empty else None,
        "research_ledger_audit": ledger_audit,
    }
    summary_bytes = json.dumps(summary, indent=2).encode("utf-8")
    (OUT_DIR / "sop_audit_30d_summary.json").write_bytes(summary_bytes)

    upload_or_update_file(
        token,
        test_folder_id,
        "sop_audit_30d_summary.json",
        summary_bytes,
        "application/json",
    )
    upload_or_update_file(
        token,
        test_folder_id,
        "ref_a_nse_30d_metrics.csv",
        metrics_csv_bytes,
        "text/csv",
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
