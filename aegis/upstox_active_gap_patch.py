#!/usr/bin/env python3
"""AEGIS Nov-2026 ACTIVE derivatives missing-data patch (standalone, read-only).

Download this ONE Python file. It does not import upstox_market_export.py
and does not require third-party Python packages. It does not access account,
holdings, positions, orders, funds, or trading endpoints.

Requires the user's Upstox Analytics Token, entered privately via getpass.
Token never stored. Reads only authenticated Upstox market-data endpoints:
    /v2/option/contract
    /v2/instruments/search
    /v3/historical-candle/
Output AEGIS_Upstox_Active_Patch.zip + token-free manifest.

Date windows: option candles Nov 02–05, futures candles Oct 28–Nov 05.
Contracts: selected current Nov-2026 options and November future.
Run: python upstox_active_gap_patch.py --limit 0
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import getpass
import hashlib
import json
import pathlib
import time
import zipfile
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

API = "https://api.upstox.com"
UNDERLYING = "NSE_INDEX|Nifty 50"
FIRST_OPTIONS = dt.date(2026, 11, 2)
FIRST_FUTURES = dt.date(2026, 10, 28)
LAST = dt.date(2026, 11, 5)
EXPS_FIRST = dt.date(2026, 11, 6)
EXPS_LAST = dt.date(2026, 11, 19)
COLUMNS = ("timestamp", "open", "high", "low", "close", "volume", "oi")
SAFE_PREFIXES = (
    "/v2/option/contract",
    "/v2/instruments/search",
    "/v3/historical-candle/",
)

def parse_date(x):
    return dt.date.fromisoformat(str(x))

def get_strike(contract):
    try:
        return float(contract["strike_price"])
    except (KeyError, ValueError, TypeError):
        return None

def regular_session_bar(value):
    """Date-effective NSE index F&O bar-OPEN schedule, August 2026 onward."""
    try:
        t = dt.datetime.fromisoformat(str(value))
        if t.utcoffset() != dt.timedelta(hours=5, minutes=30):
            return False
        latest = dt.time(15, 39) if t.date() >= dt.date(2026, 8, 3) else dt.time(15, 29)
        return dt.time(9, 15) <= t.time().replace(tzinfo=None) <= latest
    except (ValueError, TypeError):
        return False

def store_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    tmp.replace(path)

def store_csv(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(COLUMNS)
        for r in rows:
            writer.writerow(list(r[:7]) + [None] * max(0, 7-len(r)))
    tmp.replace(path)

def valid_cache(csv_path, meta_path):
    if not csv_path.is_file() or not meta_path.is_file():
        return False
    try:
        details = json.loads(meta_path.read_text(encoding="utf-8"))
        if not details.get("sha256_csv"):
            return False
        return hashlib.sha256(csv_path.read_bytes()).hexdigest() == details["sha256_csv"]
    except (OSError, ValueError, KeyError):
        return False

class MarketOnlyClient:
    def __init__(self, token, minimum_delay=1.25):
        self.token = token
        self.minimum_delay = minimum_delay
        self.last_request = 0.0
        self.request_count = 0

    def get_payload(self, path, params=None):
        if not any(path.startswith(p) for p in SAFE_PREFIXES):
            raise ValueError("Disallowed non-market-data API path")
        url = API + path + ("?" + urlencode(params) if params else "")
        for attempt in range(5):
            remaining = self.minimum_delay - (time.monotonic() - self.last_request)
            if remaining > 0:
                time.sleep(remaining)
            self.last_request = time.monotonic()
            req = Request(url, headers={
                "Authorization": "Bearer " + self.token,
                "Accept": "application/json",
                "User-Agent": "AEGIS-Historical-Market-Only/2.0"
            }, method="GET")
            try:
                with urlopen(req, timeout=75) as response:
                    body = json.loads(response.read().decode("utf-8"))
                self.request_count += 1
                if body.get("status") != "success":
                    codes = [str(e.get("error_code")) for e in body.get("errors", [])
                             if isinstance(e, dict)]
                    raise RuntimeError(f"Upstox API status error (codes: {codes})")
                return body
            except HTTPError as err:
                self.request_count += 1
                if err.code in (429, 500, 502, 503, 504) and attempt < 4:
                    time.sleep(3 * (2 ** attempt))
                    continue
                # Avoid logging full request URLs (and any private API details).
                raise RuntimeError(f"Upstox market-data API returned HTTP {err.code}") from None
            except (URLError, TimeoutError):
                if attempt < 4:
                    time.sleep(2 ** attempt)
                    continue
                raise RuntimeError("Upstox market-data endpoint unavailable after retries") from None
        raise RuntimeError("Upstox retry limit reached")

    def active_options(self):
        response = self.get_payload("/v2/option/contract", {"instrument_key": UNDERLYING})
        result = response.get("data")
        if not isinstance(result, list):
            raise ValueError("Unexpected option contracts API response (expected data array)")
        return result

    def current_nifty_futures(self):
        """Search NSE_FO FUT with documented pagination and exact underlying."""
        seen = {}
        for query in ("NIFTY", "NIFTY FUT"):
            for page in range(1, 21):
                response = self.get_payload("/v2/instruments/search", {
                    "query": query,
                    "exchanges": "NSE",
                    "segments": "FO",
                    "instrument_types": "FUT",
                    "expiry": "current_month",
                    "page_number": page,
                    "records": 30,
                })
                data = response.get("data")
                if not isinstance(data, list):
                    raise ValueError("Unexpected instrument search response")
                for contract in data:
                    if (contract.get("segment") == "NSE_FO"
                        and contract.get("instrument_type") == "FUT"
                        and (contract.get("underlying_key") == UNDERLYING
                             or contract.get("underlying_symbol") == "NIFTY")
                        and contract.get("instrument_key")):
                        seen[contract["instrument_key"]] = contract
                metadata = response.get("meta_data") or {}
                pages = (metadata.get("page") or {}).get("total_pages")
                if pages is not None:
                    if page >= int(pages):
                        break
                elif len(data) < 30:
                    break
            if seen:
                break
        return list(seen.values())

    def index_candles(self, key, first, last):
        return self.active_candles(key, first, last)

    def active_candles(self, key, first, last):
        path = ("/v3/historical-candle/" + quote(key, safe="") +
                "/minutes/1/" + last.isoformat() + "/" + first.isoformat())
        response = self.get_payload(path)
        data = response.get("data")
        if not isinstance(data, dict) or not isinstance(data.get("candles"), list):
            raise ValueError("Unexpected historical V3 candle response")
        return data["candles"]

def select_contracts(client, wing):
    candidates = []
    for item in client.active_options():
        try:
            expiry = parse_date(item["expiry"])
        except (ValueError, KeyError, TypeError):
            continue
        if not EXPS_FIRST <= expiry <= EXPS_LAST:
            continue
        if (item.get("instrument_type") not in ("CE", "PE")
            or not item.get("instrument_key") or item.get("segment") != "NSE_FO"):
            continue
        if not (item.get("underlying_key") == UNDERLYING
                or item.get("underlying_symbol") == "NIFTY"):
            continue
        candidates.append(item)
    spot = client.index_candles(UNDERLYING, FIRST_OPTIONS, LAST)
    prices = [float(row[4]) for row in spot
              if isinstance(row, list) and len(row) >= 5 and row[4] is not None
              and float(row[4]) > 0]
    if not prices:
        raise RuntimeError("No NIFTY index historical candles for Nov 2-5: cannot safely select strikes")
    low, high = min(prices) - wing, max(prices) + wing
    selected = [x for x in candidates
                if get_strike(x) is not None and low <= get_strike(x) <= high]
    futures = [x for x in client.current_nifty_futures()
               if x.get("instrument_key")
               and parse_date(x.get("expiry", "1900-01-01")) > LAST]
    futures = sorted(futures, key=lambda x: x["expiry"])[:1]
    selected.sort(key=lambda x: (x["expiry"], float(x["strike_price"]), x["instrument_type"]))
    return selected, futures, {
        "NIFTY_spot_min": round(min(prices), 2),
        "NIFTY_spot_max": round(max(prices), 2),
        "strike_low": round(low, 2),
        "strike_high": round(high, 2),
    }

def run(client, out, limit=0, wing=1200):
    out.mkdir(parents=True, exist_ok=True)
    options, futures, spot_range = select_contracts(client, wing)
    manifest = {
        "source": "Upstox Option Contracts + Instrument Search + Historical Candle V3",
        "date_range": {
            "options": [str(FIRST_OPTIONS), str(LAST)],
            "futures": [str(FIRST_FUTURES), str(LAST)]
        },
        "strike_selection": spot_range,
        "candidate_options": len(options),
        "candidate_futures": len(futures),
        "files_written": 0, "files_reused": 0,
        "empty": 0, "errors": [], "warnings": [],
        "token_saved": False, "portfolio_access": False, "order_access": False,
        "api_requests": client.request_count,
    }
    if not options:
        manifest["warnings"].append("No active Nov 6-19 NIFTY options found")
    if not futures:
        manifest["warnings"].append("No current-month NIFTY future found")
    contracts = ([("futures", x, FIRST_FUTURES) for x in futures] +
                 [("options", x, FIRST_OPTIONS) for x in options])
    processed = 0
    print("DISCOVERY", "options", len(options),
          "futures", len(futures), "selected", len(contracts), flush=True)
    for kind, contract, start in contracts:
        if limit and processed >= limit:
            break
        key = contract["instrument_key"]
        expiry = parse_date(contract["expiry"])
        typ = contract.get("instrument_type", "FUT")
        strike = get_strike(contract) if kind == "options" else None
        hashed_key = hashlib.sha256(key.encode()).hexdigest()[:12]
        stem = (str(int(strike)) if strike is not None else "FUT") + "_" + typ + "_" + hashed_key
        csv_path = out / kind / str(expiry) / (stem + ".csv")
        sidecar = csv_path.with_suffix(".json")
        if valid_cache(csv_path, sidecar):
            manifest["files_reused"] += 1
            continue
        processed += 1
        try:
            rows = client.active_candles(key, start, LAST)
            de_duped = {
                str(x[0]): x for x in rows
                if isinstance(x, list) and len(x) >= 6
                and regular_session_bar(x[0])
                and start <= parse_date(str(x[0])[:10]) <= LAST
            }
            data = [de_duped[t] for t in sorted(de_duped)]
            if not data:
                manifest["empty"] += 1
                print("EMPTY", kind, str(expiry), strike, flush=True)
                continue
            store_csv(csv_path, data)
            store_json(sidecar, {
                "source": "upstox_historical_v3_active_1m",
                "expiry": str(expiry),
                "instrument_type": typ,
                "strike_price": strike,
                "lot_size": int(contract["lot_size"]),
                "instrument_key": key,
                "trading_symbol": contract.get("trading_symbol"),
                "rows": len(data),
                "first": str(data[0][0]),
                "last": str(data[-1][0]),
                "sha256_csv": hashlib.sha256(csv_path.read_bytes()).hexdigest(),
            })
            manifest["files_written"] += 1
            print("DOWNLOADED", kind, expiry, typ, strike, "bars", len(data), flush=True)
        except Exception as err:
            manifest["errors"].append({
                "kind": kind, "expiry": str(expiry), "strike": strike,
                "error_type": type(err).__name__, "message": str(err),
            })
            print("ERROR", kind, expiry, strike, str(err), flush=True)
        finally:
            manifest["api_requests"] = client.request_count
            store_json(out / "AEGIS_active_patch_manifest.json", manifest)
    manifest["contract_limit_reached"] = bool(limit and processed >= limit)
    manifest["api_requests"] = client.request_count
    store_json(out / "AEGIS_active_patch_manifest.json", manifest)
    bundle = out.parent / "AEGIS_Upstox_Active_Patch.zip"
    with zipfile.ZipFile(bundle, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for file in sorted(out.rglob("*")):
            if file.is_file() and file.suffix in (".csv", ".json"):
                archive.write(file, file.relative_to(out.parent))
    print("PATCH_FINISHED", json.dumps(manifest, indent=2))
    print("ARCHIVE", bundle, "BYTES", bundle.stat().st_size, flush=True)
    return manifest

def main():
    parser = argparse.ArgumentParser(description="Standalone read-only Upstox active NIFTY patch")
    parser.add_argument("--out", default="AEGIS_Upstox_Active_Patch")
    parser.add_argument("--limit", type=int, default=0,
                        help="0 = all selected contracts; >0 for pilot")
    parser.add_argument("--wing", type=float, default=1200)
    args = parser.parse_args()
    if args.limit < 0 or args.wing <= 0:
        parser.error("limit must be >= 0 and wing must be > 0")
    token = getpass.getpass("Read-only Upstox Analytics Token (hidden): ").strip()
    if not token:
        raise SystemExit("No token provided")
    client = MarketOnlyClient(token)
    try:
        run(client, pathlib.Path(args.out), limit=args.limit, wing=args.wing)
    except (ValueError, RuntimeError) as err:
        print("MARKET_DATA_ERROR", str(err))
        print("No Upstox token or account information was saved.")
        raise SystemExit(2) from None

if __name__ == "__main__":
    main()
