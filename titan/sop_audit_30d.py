"""SOP V3.0 (Rev 1) 30-day Reference A Math Engine & Research Ledger Audit.
- Ingests ALL NSE Bhavcopy series (tagged, never dropped), BSE Bhavcopies, and NSE Index closes.
- Enforces exact Reference A formulas (prior 20 normal sessions excluding signal day for RVOL20/breakouts,
  min_periods=20, OHLC integrity checks, special-session exclusion, CA anomaly flags).
- Generates a compact latest-session JSON digest (Top-20 movers, Top-5 RVOL20 baseline, index returns)
  for low-token ChatGPT consumption.
- Writes ONLY to Market_Data/Audit_30D_Test on Drive and local audit_30d_output/."""
from __future__ import annotations

import io
import json
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import requests

IST = timezone(timedelta(hours=5, minutes=30))
OUT_DIR = Path("audit_30d_output")
OUT_DIR.mkdir(exist_ok=True)

# Shortened/special sessions excluded from normal 20-session baselines (Reference A)
SPECIAL_SESSIONS = {"2026-11-08"}
CA_ANOMALY_RET_PCT = 35.0  # Quarantine threshold for potential unadjusted split/bonus


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

    boundary = "titan_sop_v3_boundary"
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


def apply_reference_a_equity_math(df: pd.DataFrame, group_cols: list[str]) -> pd.DataFrame:
    """Apply exact SOP V3 Reference A calculations and integrity checks."""
    df = df.sort_values(group_cols + ["trading_date"]).copy()
    df["is_special_session"] = df["trading_date"].isin(SPECIAL_SESSIONS)

    # Reference A Data Checks: positive prices, L <= min(O,C) <= max(O,C) <= H, volume >= 0
    pos_prices = (
        (df["open"] > 0) & (df["high"] > 0) & (df["low"] > 0) & (df["close"] > 0) & (df["prev_close"] > 0)
    )
    min_oc = np.minimum(df["open"], df["close"])
    max_oc = np.maximum(df["open"], df["close"])
    range_ok = (df["low"] <= min_oc) & (max_oc <= df["high"])
    vol_ok = df["volume"] >= 0
    df["data_quality_ok"] = (pos_prices & range_ok & vol_ok).fillna(False)

    # Repricing / gap / post-open (raw)
    df["ret_1d_pct"] = np.where(df["prev_close"] > 0, 100.0 * (df["close"] / df["prev_close"] - 1.0), np.nan)
    df["gap_pct"] = np.where(df["prev_close"] > 0, 100.0 * (df["open"] / df["prev_close"] - 1.0), np.nan)
    df["open_to_close_pct"] = np.where(df["open"] > 0, 100.0 * (df["close"] / df["open"] - 1.0), np.nan)
    df["ca_anomaly_flag"] = df["ret_1d_pct"].abs() >= CA_ANOMALY_RET_PCT

    # Range / giveback / turnover
    hl_range = df["high"] - df["low"]
    df["close_location"] = np.where(hl_range > 0, (df["close"] - df["low"]) / hl_range, np.nan)
    df["high_to_close_giveback_pct"] = np.where(
        df["high"] > 0, 100.0 * (df["high"] - df["close"]) / df["high"], np.nan
    )
    df["turnover_proxy"] = (df["close"] * df["volume"]).round(2)

    # Normal-session-only series for prior 20-session baselines (excluding signal day)
    df["_vol_norm"] = np.where(~df["is_special_session"] & df["data_quality_ok"], df["volume"], np.nan)
    df["_high_norm"] = np.where(~df["is_special_session"] & df["data_quality_ok"], df["high"], np.nan)
    df["_low_norm"] = np.where(~df["is_special_session"] & df["data_quality_ok"], df["low"], np.nan)

    g = df.groupby(group_cols, group_keys=False)

    # Prior 20 normal sessions EXCLUDING signal day (min_periods=20 per Reference A)
    df["vol_ma20_prior"] = g["_vol_norm"].transform(lambda s: s.shift(1).rolling(20, min_periods=20).mean())
    df["rvol20"] = np.where(df["vol_ma20_prior"] > 0, df["volume"] / df["vol_ma20_prior"], np.nan)

    df["prior_high_20d"] = g["_high_norm"].transform(lambda s: s.shift(1).rolling(20, min_periods=20).max())
    df["prior_low_20d"] = g["_low_norm"].transform(lambda s: s.shift(1).rolling(20, min_periods=20).min())
    df["is_breakout_20d"] = (df["close"] > df["prior_high_20d"]).fillna(False)
    df["is_breakdown_20d"] = (df["close"] < df["prior_low_20d"]).fillna(False)

    # MA20: simple mean INCLUDING signal close (Reference A)
    df["ma20"] = g["close"].transform(lambda s: s.rolling(20, min_periods=20).mean())
    df["ma20_dist_pct"] = np.where(df["ma20"] > 0, 100.0 * (df["close"] / df["ma20"] - 1.0), np.nan)

    # Delivery prior 20-session mean (if available)
    if "deliv_qty" in df.columns:
        df["_deliv_norm"] = np.where(~df["is_special_session"] & df["data_quality_ok"], df["deliv_qty"], np.nan)
        df["deliv_qty_ma20_prior"] = g["_deliv_norm"].transform(
            lambda s: s.shift(1).rolling(20, min_periods=20).mean()
        )
        df["deliv_ratio20"] = np.where(
            df["deliv_qty_ma20_prior"] > 0, df["deliv_qty"] / df["deliv_qty_ma20_prior"], np.nan
        )
        df = df.drop(columns=["_deliv_norm"])

    # Round floats cleanly
    for col in [
        "ret_1d_pct", "gap_pct", "open_to_close_pct", "close_location",
        "high_to_close_giveback_pct", "vol_ma20_prior", "rvol20",
        "prior_high_20d", "prior_low_20d", "ma20", "ma20_dist_pct",
    ]:
        if col in df.columns:
            df[col] = df[col].round(4)

    return df.drop(columns=["_vol_norm", "_high_norm", "_low_norm"])


def compute_nse_all_series_30d(token: str, hist_files: list[dict[str, Any]]) -> pd.DataFrame:
    by_date: dict[str, dict[str, Any]] = {}
    for f in hist_files:
        key = parse_eod_key(f["name"])
        if key and key[0] == "nse_bhavcopy":
            by_date[key[1]] = f

    sorted_dates = sorted(by_date.keys())
    selected_dates = sorted_dates[-55:]  # Extra buffer so all 30 output dates have 20 prior normal sessions
    frames: list[pd.DataFrame] = []

    for dt in selected_dates:
        raw = download_bytes(token, by_date[dt]["id"])
        df = normalize_cols(pd.read_csv(io.BytesIO(raw)))

        sym_col = pick_col(df, ["SYMBOL", "TCKRSYMB", "SECURITY_SYMBOL"])
        ser_col = pick_col(df, ["SERIES", "SCTYSRS"])
        prev_col = pick_col(df, ["PREV_CLOSE", "PRVSCLSGPRIC"])
        open_col = pick_col(df, ["OPEN_PRICE", "OPNPRIC", "OPEN"])
        high_col = pick_col(df, ["HIGH_PRICE", "HGHPRIC", "HIGH"])
        low_col = pick_col(df, ["LOW_PRICE", "LWPRIC", "LOW"])
        close_col = pick_col(df, ["CLOSE_PRICE", "CLSPRIC", "CLOSE"])
        vol_col = pick_col(df, ["TTL_TRD_QNTY", "TOTTRADQTY", "VOLUME"])
        turn_col = pick_col(df, ["TURNOVER_LACS", "TTLTRFVAL", "TURNOVER"])
        deliv_qty_col = pick_col(df, ["DELIV_QTY", "DELIVQTY"])
        deliv_pct_col = pick_col(df, ["DELIV_PER", "DELIVPER"])

        if not sym_col or not close_col or not vol_col:
            continue

        series_vals = df[ser_col].astype(str).str.strip() if ser_col else "UNKNOWN"
        reported_turn = pd.to_numeric(df[turn_col], errors="coerce") if turn_col else np.nan
        if turn_col == "TURNOVER_LACS":
            reported_turn = reported_turn * 100000.0  # Convert Lacs to INR

        sub = pd.DataFrame(
            {
                "trading_date": dt,
                "exchange": "NSE",
                "symbol": df[sym_col].astype(str).str.strip(),
                "series": series_vals,
                "is_eq_be": series_vals.isin(["EQ", "BE"]) if ser_col else False,
                "prev_close": pd.to_numeric(df[prev_col], errors="coerce") if prev_col else np.nan,
                "open": pd.to_numeric(df[open_col], errors="coerce") if open_col else np.nan,
                "high": pd.to_numeric(df[high_col], errors="coerce") if high_col else np.nan,
                "low": pd.to_numeric(df[low_col], errors="coerce") if low_col else np.nan,
                "close": pd.to_numeric(df[close_col], errors="coerce"),
                "volume": pd.to_numeric(df[vol_col], errors="coerce"),
                "reported_turnover": reported_turn,
                "deliv_qty": pd.to_numeric(df[deliv_qty_col], errors="coerce") if deliv_qty_col else np.nan,
                "deliv_pct": pd.to_numeric(df[deliv_pct_col], errors="coerce") if deliv_pct_col else np.nan,
            }
        ).dropna(subset=["symbol", "close", "volume"])
        frames.append(sub)

    if not frames:
        return pd.DataFrame()

    all_df = apply_reference_a_equity_math(pd.concat(frames, ignore_index=True), ["symbol", "series"])
    last_30_dates = set(sorted_dates[-30:])
    return all_df[all_df["trading_date"].isin(last_30_dates)].sort_values(
        ["trading_date", "symbol", "series"]
    )


def compute_bse_30d(token: str, hist_files: list[dict[str, Any]]) -> pd.DataFrame:
    by_date: dict[str, dict[str, Any]] = {}
    for f in hist_files:
        key = parse_eod_key(f["name"])
        if key and key[0] == "bse_bhavcopy":
            by_date[key[1]] = f

    sorted_dates = sorted(by_date.keys())
    selected_dates = sorted_dates[-55:]
    frames: list[pd.DataFrame] = []

    for dt in selected_dates:
        raw = download_bytes(token, by_date[dt]["id"])
        df = normalize_cols(pd.read_csv(io.BytesIO(raw)))

        sym_col = pick_col(df, ["TCKRSYMB", "SYMBOL", "SC_NAME"])
        isin_col = pick_col(df, ["ISIN"])
        ser_col = pick_col(df, ["SCTYSRS", "SERIES", "SC_GROUP"])
        prev_col = pick_col(df, ["PRVSCLSGPRIC", "PREV_CLOSE", "PREVCLOSE"])
        open_col = pick_col(df, ["OPNPRIC", "OPEN"])
        high_col = pick_col(df, ["HGHPRIC", "HIGH"])
        low_col = pick_col(df, ["LWPRIC", "LOW"])
        close_col = pick_col(df, ["CLSPRIC", "CLOSE"])
        vol_col = pick_col(df, ["TTLTRADGVOL", "TOTTRADQTY", "NO_OF_SHRS"])
        turn_col = pick_col(df, ["TTLTRFVAL", "NET_TURNOV"])

        if not sym_col or not close_col or not vol_col:
            continue

        sub = pd.DataFrame(
            {
                "trading_date": dt,
                "exchange": "BSE",
                "symbol": df[sym_col].astype(str).str.strip(),
                "isin": df[isin_col].astype(str).str.strip() if isin_col else "",
                "series": df[ser_col].astype(str).str.strip() if ser_col else "UNKNOWN",
                "prev_close": pd.to_numeric(df[prev_col], errors="coerce") if prev_col else np.nan,
                "open": pd.to_numeric(df[open_col], errors="coerce") if open_col else np.nan,
                "high": pd.to_numeric(df[high_col], errors="coerce") if high_col else np.nan,
                "low": pd.to_numeric(df[low_col], errors="coerce") if low_col else np.nan,
                "close": pd.to_numeric(df[close_col], errors="coerce"),
                "volume": pd.to_numeric(df[vol_col], errors="coerce"),
                "reported_turnover": pd.to_numeric(df[turn_col], errors="coerce") if turn_col else np.nan,
            }
        ).dropna(subset=["symbol", "close", "volume"])
        frames.append(sub)

    if not frames:
        return pd.DataFrame()

    all_df = apply_reference_a_equity_math(pd.concat(frames, ignore_index=True), ["symbol", "series"])
    last_30_dates = set(sorted_dates[-30:])
    return all_df[all_df["trading_date"].isin(last_30_dates)].sort_values(
        ["trading_date", "symbol", "series"]
    )


def compute_nse_indices_30d(token: str, hist_files: list[dict[str, Any]]) -> pd.DataFrame:
    by_date: dict[str, dict[str, Any]] = {}
    for f in hist_files:
        key = parse_eod_key(f["name"])
        if key and key[0] == "nse_indices":
            by_date[key[1]] = f

    sorted_dates = sorted(by_date.keys())
    selected_dates = sorted_dates[-55:]
    frames: list[pd.DataFrame] = []

    for dt in selected_dates:
        raw = download_bytes(token, by_date[dt]["id"])
        df = normalize_cols(pd.read_csv(io.BytesIO(raw)))

        name_col = pick_col(df, ["INDEX_NAME", "INDEX"])
        open_col = pick_col(df, ["OPEN_INDEX_VALUE", "OPEN"])
        high_col = pick_col(df, ["HIGH_INDEX_VALUE", "HIGH"])
        low_col = pick_col(df, ["LOW_INDEX_VALUE", "LOW"])
        close_col = pick_col(df, ["CLOSING_INDEX_VALUE", "CLOSE"])
        chg_pct_col = pick_col(df, ["CHANGE_PERCENT", "CHANGE_IN_PERCENT", "CHANGE"])

        if not name_col or not close_col:
            continue

        sub = pd.DataFrame(
            {
                "trading_date": dt,
                "index_name": df[name_col].astype(str).str.strip(),
                "open": pd.to_numeric(df[open_col], errors="coerce") if open_col else np.nan,
                "high": pd.to_numeric(df[high_col], errors="coerce") if high_col else np.nan,
                "low": pd.to_numeric(df[low_col], errors="coerce") if low_col else np.nan,
                "close": pd.to_numeric(df[close_col], errors="coerce"),
                "reported_chg_pct": pd.to_numeric(df[chg_pct_col], errors="coerce") if chg_pct_col else np.nan,
            }
        ).dropna(subset=["index_name", "close"])
        frames.append(sub)

    if not frames:
        return pd.DataFrame()

    all_df = pd.concat(frames, ignore_index=True).sort_values(["index_name", "trading_date"])
    g = all_df.groupby("index_name", group_keys=False)
    all_df["ret_1d_pct"] = g["close"].pct_change(1).mul(100).round(4)
    all_df["ret_3d_pct"] = g["close"].pct_change(3).mul(100).round(4)
    all_df["ret_5d_pct"] = g["close"].pct_change(5).mul(100).round(4)
    all_df["ret_20d_pct"] = g["close"].pct_change(20).mul(100).round(4)
    all_df["ma20"] = g["close"].transform(lambda s: s.rolling(20, min_periods=20).mean()).round(4)
    all_df["is_special_session"] = all_df["trading_date"].isin(SPECIAL_SESSIONS)

    last_30_dates = set(sorted_dates[-30:])
    return all_df[all_df["trading_date"].isin(last_30_dates)].sort_values(
        ["trading_date", "index_name"]
    )


def build_latest_session_digest(
    nse_df: pd.DataFrame, idx_df: pd.DataFrame
) -> dict[str, Any]:
    """Build compact SOP V3 digest for the latest session (Section 4 & 6)."""
    if nse_df.empty:
        return {}

    latest_dt = str(nse_df["trading_date"].max())
    day = nse_df[(nse_df["trading_date"] == latest_dt) & (nse_df["data_quality_ok"])].copy()
    eq_day = day[day["is_eq_be"] & (~day["ca_anomaly_flag"])].copy()

    cols = [
        "symbol", "series", "close", "ret_1d_pct", "gap_pct", "open_to_close_pct",
        "volume", "rvol20", "deliv_pct", "reported_turnover", "is_breakout_20d", "is_breakdown_20d",
    ]
    top20_gainers = eq_day.sort_values("ret_1d_pct", ascending=False).head(20)[cols].to_dict("records")
    top20_losers = eq_day.sort_values("ret_1d_pct", ascending=True).head(20)[cols].to_dict("records")

    # Section 6 Fixed-Budget Baseline: Top 5 RVOL20 positive/negative movers, ties by turnover then symbol
    pos_base = (
        eq_day[(eq_day["ret_1d_pct"] > 0) & eq_day["rvol20"].notna()]
        .sort_values(["rvol20", "reported_turnover", "symbol"], ascending=[False, False, True])
        .head(5)[cols]
        .to_dict("records")
    )
    neg_base = (
        eq_day[(eq_day["ret_1d_pct"] < 0) & eq_day["rvol20"].notna()]
        .sort_values(["rvol20", "reported_turnover", "symbol"], ascending=[False, False, True])
        .head(5)[cols]
        .to_dict("records")
    )

    ca_anomalies = day[day["ca_anomaly_flag"]][["symbol", "series", "prev_close", "close", "ret_1d_pct"]].to_dict("records")

    idx_latest = []
    if not idx_df.empty:
        idx_latest = (
            idx_df[idx_df["trading_date"] == latest_dt][
                ["index_name", "close", "ret_1d_pct", "ret_3d_pct", "ret_5d_pct", "ret_20d_pct"]
            ]
            .dropna(subset=["ret_1d_pct"])
            .to_dict("records")
        )

    return {
        "latest_trading_date": latest_dt,
        "valid_all_series_rows": int(len(day)),
        "valid_eq_be_non_ca_rows": int(len(eq_day)),
        "abs_ret_ge_5pct_count": int((eq_day["ret_1d_pct"].abs() >= 5.0).sum()),
        "rvol20_ge_3_count": int((eq_day["rvol20"] >= 3.0).sum()),
        "ca_anomalies_quarantined": ca_anomalies,
        "baseline_top5_rvol20_positive": pos_base,
        "baseline_top5_rvol20_negative": neg_base,
        "top20_gainers_eq_be": top20_gainers,
        "top20_losers_eq_be": top20_losers,
        "nse_indices_latest": idx_latest[:40],
    }


def audit_research_ledger(token: str, root_parent_id: str) -> dict[str, Any]:
    q = "name contains 'Research_Ledger' and trashed = false"
    r = requests.get(
        "https://www.googleapis.com/drive/v3/files",
        headers={"Authorization": f"Bearer {token}"},
        params={"q": q, "fields": "files(id,name,mimeType,size,modifiedTime,parents)", "pageSize": 100},
        timeout=30,
    )
    r.raise_for_status()
    matches = r.json().get("files", [])
    ledger_folder = next(
        (m for m in matches if m.get("mimeType") == "application/vnd.google-apps.folder"), None
    )
    ledger_files = list_folder_files(token, ledger_folder["id"]) if ledger_folder else []

    json_reports: list[dict[str, Any]] = []
    for f in ledger_files:
        if f["name"].lower().endswith(".json"):
            size_bytes = int(f.get("size") or 0)
            pending_count = None
            try:
                raw = json.loads(download_bytes(token, f["id"]).decode("utf-8", errors="replace"))
                if isinstance(raw, dict) and isinstance(raw.get("pending"), (list, dict)):
                    pending_count = len(raw["pending"])
            except Exception:
                pass
            json_reports.append(
                {
                    "name": f["name"],
                    "size_kb": round(size_bytes / 1024, 2),
                    "pending_count": pending_count,
                }
            )

    json_reports.sort(key=lambda x: x["size_kb"], reverse=True)
    return {
        "ledger_folder_found": bool(ledger_folder),
        "ledger_total_files": len(ledger_files),
        "json_files_inspected": len(json_reports),
        "largest_json_files": json_reports[:10],
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

    nse_df = compute_nse_all_series_30d(token, hist_files)
    bse_df = compute_bse_30d(token, hist_files)
    idx_df = compute_nse_indices_30d(token, hist_files)
    digest = build_latest_session_digest(nse_df, idx_df)
    ledger_audit = audit_research_ledger(token, market_data_id)

    for fname, df in [
        ("ref_a_nse_30d_metrics.csv", nse_df),
        ("ref_a_bse_30d_metrics.csv", bse_df),
        ("ref_a_nse_indices_30d.csv", idx_df),
    ]:
        raw_csv = df.to_csv(index=False).encode("utf-8")
        (OUT_DIR / fname).write_bytes(raw_csv)
        upload_or_update_file(token, test_folder_id, fname, raw_csv, "text/csv")

    digest_bytes = json.dumps(digest, indent=2, default=str).encode("utf-8")
    (OUT_DIR / "sop_v3_latest_session_digest.json").write_bytes(digest_bytes)
    upload_or_update_file(
        token, test_folder_id, "sop_v3_latest_session_digest.json", digest_bytes, "application/json"
    )

    summary = {
        "generated_at_ist": datetime.now(IST).isoformat(),
        "sop_version": "TITAN_V3.0_Rev1_ReferenceA",
        "test_drive_folder": "Market_Data/Audit_30D_Test",
        "nse_all_series_30d": {
            "rows": int(len(nse_df)),
            "unique_dates": int(nse_df["trading_date"].nunique()) if not nse_df.empty else 0,
            "unique_symbols": int(nse_df["symbol"].nunique()) if not nse_df.empty else 0,
            "data_quality_failed_rows": int((~nse_df["data_quality_ok"]).sum()) if not nse_df.empty else 0,
            "ca_anomaly_rows": int(nse_df["ca_anomaly_flag"].sum()) if not nse_df.empty else 0,
            "series_counts": nse_df["series"].value_counts().head(15).to_dict() if not nse_df.empty else {},
        },
        "bse_30d": {
            "rows": int(len(bse_df)),
            "unique_dates": int(bse_df["trading_date"].nunique()) if not bse_df.empty else 0,
            "unique_symbols": int(bse_df["symbol"].nunique()) if not bse_df.empty else 0,
            "data_quality_failed_rows": int((~bse_df["data_quality_ok"]).sum()) if not bse_df.empty else 0,
            "ca_anomaly_rows": int(bse_df["ca_anomaly_flag"].sum()) if not bse_df.empty else 0,
        },
        "nse_indices_30d": {
            "rows": int(len(idx_df)),
            "unique_dates": int(idx_df["trading_date"].nunique()) if not idx_df.empty else 0,
            "unique_indices": int(idx_df["index_name"].nunique()) if not idx_df.empty else 0,
        },
        "research_ledger_audit": ledger_audit,
    }
    summary_bytes = json.dumps(summary, indent=2).encode("utf-8")
    (OUT_DIR / "sop_audit_30d_summary.json").write_bytes(summary_bytes)
    upload_or_update_file(
        token, test_folder_id, "sop_audit_30d_summary.json", summary_bytes, "application/json"
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
