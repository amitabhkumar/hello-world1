#!/usr/bin/env python3
"""AEGIS targeted Upstox active-contract 1-minute supplement.

STANDALONE version: Python 3.10+ standard library ONLY.
Does NOT import upstox_market_export.py, so an old adjacent file cannot break it.
GET-only approved public MARKET DATA endpoints. NEVER calls order, portfolio,
holdings, positions, login, account, margin, or trading endpoints.
The Analytics Token is entered by getpass and never written or printed.

Run locally (not GitHub) with your private read-only Analytics Token:
  python upstox_active_gap_patch.py --self-test   # offline, no token
  python upstox_active_gap_patch.py --limit 4     # small API pilot
  python upstox_active_gap_patch.py --limit 0     # target all relevant contracts

Historical windows:
  Options:   2026-11-02 through 2026-11-05, expiries 2026-11-06..11-19
  NIFTY FUT: 2026-10-28 through 2026-11-05, nearest current-month future
No original files are modified; outputs are a small supplementary ZIP.
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
import urllib.error
import urllib.parse
import urllib.request
import zipfile

HOST = "https://api.upstox.com"
UNDERLYING = "NSE_INDEX|Nifty 50"
OPT_START = dt.date(2026, 11, 2)
FUT_START = dt.date(2026, 10, 28)
LAST = dt.date(2026, 11, 5)
MIN_OPTION_EXPIRY = dt.date(2026, 11, 6)
MAX_OPTION_EXPIRY = dt.date(2026, 11, 19)
IST = dt.timedelta(hours=5, minutes=30)
CANDLE_FIELDS = ("timestamp", "open", "high", "low", "close", "volume", "oi")
MARKET_ENDPOINTS = frozenset({
    "/v2/option/contract",
    "/v2/instruments/search",
})


def safe_date(value):
    try:
        return dt.date.fromisoformat(str(value)[:10])
    except (ValueError, TypeError):
        return None


def strike_of(contract):
    try:
        return float(contract["strike_price"])
    except (KeyError, TypeError, ValueError):
        return None


def is_nifty(contract):
    """Reject similarly named NIFTYBANK/FINNIFTY instruments."""
    if contract.get("segment") != "NSE_FO":
        return False
    if contract.get("underlying_key") == UNDERLYING:
        return True
    if str(contract.get("underlying_symbol", "")).upper() == "NIFTY":
        return True
    if str(contract.get("name", "")).upper() == "NIFTY":
        return True
    return str(contract.get("trading_symbol", "")).upper().startswith("NIFTY ")


def regular_fo_bar(ts, expiry=None):
    """3-Aug-2026 change: F&O 09:15–15:39 minute starts until December."""
    try:
        t = dt.datetime.fromisoformat(str(ts))
        return (
            t.utcoffset() == IST
            and OPT_START <= t.date() <= LAST
            and dt.time(9, 15) <= t.time().replace(tzinfo=None) <= dt.time(15, 39)
            and (expiry is None or t.date() <= expiry)
        )
    except (TypeError, ValueError):
        return False


def valid_candle(row):
    try:
        if not isinstance(row, (list, tuple)) or len(row) < 6:
            return False
        o, h, l, c = map(float, row[1:5])
        return o > 0 and l > 0 and c > 0 and h >= max(o, l, c) and l <= min(o, h, c)
    except (TypeError, ValueError):
        return False


def sha256_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verified_cache(path, meta):
    if not path.is_file() or not meta.is_file():
        return False
    try:
        saved = json.loads(meta.read_text(encoding="utf-8"))
        return bool(saved.get("sha256_csv")) and sha256_file(path) == saved["sha256_csv"]
    except (ValueError, OSError, KeyError):
        return False


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, indent=2, default=str), encoding="utf-8")
    temp.replace(path)


def write_csv(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    with temp.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(CANDLE_FIELDS)
        for row in rows:
            # V3: [timestamp, open, high, low, close, volume, OI].
            # Pad missing OI without guessing its economic value.
            writer.writerow(list(row[:7]) + [None] * max(0, 7 - len(row)))
    temp.replace(path)


class MarketOnlyClient:
    """No dependency on the earlier Upstox exporter; strict GET allowlist."""

    def __init__(self, token, delay=1.2):
        self.__token = token
        self.delay = max(1.1, float(delay))
        self.last_request = 0.0
        self.request_count = 0

    def get(self, path, params=None):
        # Hard deny all account, order and portfolio APIs.
        if path not in MARKET_ENDPOINTS and not path.startswith("/v3/historical-candle/"):
            raise ValueError("Blocked: not an approved market-data GET endpoint")
        if path.startswith("/v3/historical-candle/") and "/minutes/1/" not in path:
            raise ValueError("Blocked: unsupported historical candle interval")
        url = HOST + path
        if params:
            url += "?" + urllib.parse.urlencode(params)
        for attempt in range(5):
            elapsed = time.monotonic() - self.last_request
            if elapsed < self.delay:
                time.sleep(self.delay - elapsed)
            self.last_request = time.monotonic()
            request = urllib.request.Request(
                url,
                headers={
                    "Authorization": "Bearer " + self.__token,
                    "Accept": "application/json",
                    "User-Agent": "AEGIS-ReadOnly-Active-History/2.0",
                },
                method="GET",
            )
            try:
                self.request_count += 1
                with urllib.request.urlopen(request, timeout=60) as response:
                    payload = json.loads(response.read().decode("utf-8"))
                if payload.get("status") == "error":
                    codes = [
                        x.get("error_code") for x in payload.get("errors", [])
                        if isinstance(x, dict)
                    ]
                    raise RuntimeError("Upstox market-data API returned: " + str(codes))
                return payload
            except urllib.error.HTTPError as exc:
                if exc.code in (429, 500, 502, 503, 504) and attempt < 4:
                    time.sleep(3 * 2 ** attempt)
                    continue
                # Avoid printing raw broker/API response bodies and credentials.
                raise RuntimeError("Market-data API HTTP " + str(exc.code)) from None
            except (urllib.error.URLError, TimeoutError):
                if attempt < 4:
                    time.sleep(2 ** attempt + 1)
                    continue
                raise RuntimeError("Market-data API network request failed") from None
        raise RuntimeError("Market-data API retries exhausted")

    def active_options(self):
        data = self.get("/v2/option/contract", {"instrument_key": UNDERLYING}).get("data")
        if not isinstance(data, list):
            raise ValueError("Upstox option-contract API returned unexpected data")
        return data

    def current_nifty_futures(self):
        results = {}
        for page in range(1, 16):
            response = self.get(
                "/v2/instruments/search",
                {
                    "query": "NIFTY",
                    "exchanges": "NSE",
                    "segments": "FO",
                    "instrument_types": "FUT",
                    "expiry": "current_month",
                    "page_number": page,
                    "records": 30,
                },
            )
            records = response.get("data")
            if not isinstance(records, list):
                raise ValueError("Upstox instrument-search API returned unexpected data")
            for contract in records:
                if (contract.get("instrument_type") == "FUT"
                        and is_nifty(contract)
                        and contract.get("instrument_key")):
                    results[contract["instrument_key"]] = contract
            pagination = (response.get("meta_data") or {}).get("page") or {}
            total_pages = pagination.get("total_pages")
            if total_pages is not None and page >= int(total_pages):
                break
            if len(records) < 30:
                break
        return list(results.values())

    def candles(self, instrument_key, start, end):
        if not isinstance(instrument_key, str) or not instrument_key.startswith("NSE_FO|"):
            raise ValueError("Only NSE F&O instrument keys are permitted")
        path = (
            "/v3/historical-candle/"
            + urllib.parse.quote(instrument_key, safe="")
            + "/minutes/1/"
            + end.isoformat()
            + "/"
            + start.isoformat()
        )
        data = self.get(path).get("data")
        if not isinstance(data, dict) or not isinstance(data.get("candles"), list):
            raise ValueError("Upstox V3 candle API returned unexpected data")
        return data["candles"]

    def index_candles(self, start, end):
        path = (
            "/v3/historical-candle/"
            + urllib.parse.quote(UNDERLYING, safe="")
            + "/minutes/1/"
            + end.isoformat()
            + "/"
            + start.isoformat()
        )
        data = self.get(path).get("data")
        if not isinstance(data, dict) or not isinstance(data.get("candles"), list):
            raise ValueError("Upstox NIFTY index candle response unexpected")
        return data["candles"]


def select_contracts(client, wing):
    index = client.index_candles(OPT_START, LAST)
    spot = [float(c[4]) for c in index if valid_candle(c)]
    if not spot:
        raise RuntimeError("No 2026-Nov-02 to Nov-05 NIFTY index candles available")
    low = min(spot) - wing
    high = max(spot) + wing
    options = [
        c for c in client.active_options()
        if is_nifty(c)
        and c.get("instrument_type") in ("CE", "PE")
        and c.get("instrument_key")
        and (exp := safe_date(c.get("expiry"))) is not None
        and MIN_OPTION_EXPIRY <= exp <= MAX_OPTION_EXPIRY
        and (strike := strike_of(c)) is not None
        and low <= strike <= high
    ]
    futures = [
        c for c in client.current_nifty_futures()
        if safe_date(c.get("expiry")) is not None
        and safe_date(c["expiry"]) > LAST
        and c.get("lot_size")
    ]
    futures = sorted(futures, key=lambda c: c["expiry"])[:1]
    return (
        sorted(options, key=lambda c: (c["expiry"], float(c["strike_price"]),
                                       c["instrument_type"])),
        futures,
        {
            "spot_min": round(min(spot), 2),
            "spot_max": round(max(spot), 2),
            "selection_min": round(low, 2),
            "selection_max": round(high, 2),
        },
    )


def run(client, out, limit, wing):
    out.mkdir(parents=True, exist_ok=True)
    manifest_path = out / "AEGIS_active_patch_manifest.json"
    manifest = {
        "version": "standalone_v2",
        "source": "Upstox market-only active contract discovery + Historical Candle V3",
        "option_session_range": [str(OPT_START), str(LAST)],
        "future_session_range": [str(FUT_START), str(LAST)],
        "downloaded_contracts": 0,
        "reused_contracts": 0,
        "empty_contracts": 0,
        "errors": [],
        "warnings": [],
        "private_token_saved": False,
        "account_or_trading_endpoints_called": False,
    }
    try:
        options, futures, spot_range = select_contracts(client, wing)
        manifest["spot_selection"] = spot_range
        manifest["options_discovered"] = len(options)
        manifest["futures_discovered"] = len(futures)
        if not futures:
            manifest["warnings"].append(
                "No current NIFTY future found; inspect sanitized manifest, do not assume future gap closed"
            )
        if not options:
            manifest["warnings"].append(
                "No eligible listed NIFTY options found; check option expiry range and active contract availability"
            )
        selected = [("futures", c, FUT_START) for c in futures]
        selected += [("options", c, OPT_START) for c in options]
        processed = 0
        for kind, c, first in selected:
            if limit and processed >= limit:
                break
            expiry = safe_date(c.get("expiry"))
            typ = c.get("instrument_type", "FUT")
            key = c["instrument_key"]
            strike = strike_of(c)
            safe_id = hashlib.sha256(key.encode()).hexdigest()[:12]
            stem = (str(int(strike)) if kind == "options" else "FUT")
            path = out / kind / str(expiry) / f"{stem}_{typ}_{safe_id}.csv"
            sidecar = path.with_suffix(".json")
            if verified_cache(path, sidecar):
                manifest["reused_contracts"] += 1
                continue
            processed += 1
            try:
                raw = client.candles(key, first, LAST)
                dedup = {
                    str(row[0]): row
                    for row in raw
                    if valid_candle(row)
                    and regular_fo_bar(row[0], expiry=expiry)
                    and first <= safe_date(row[0]) <= LAST
                }
                rows = [dedup[t] for t in sorted(dedup)]
                if not rows:
                    manifest["empty_contracts"] += 1
                    print("EMPTY", kind, expiry, strike, flush=True)
                else:
                    write_csv(path, rows)
                    write_json(sidecar, {
                        "source": "upstox_historical_v3_active_1m",
                        "expiry": str(expiry),
                        "instrument_type": typ,
                        "strike_price": strike,
                        "lot_size": int(c["lot_size"]),
                        "instrument_key": key,
                        "trading_symbol": c.get("trading_symbol"),
                        "rows": len(rows),
                        "first": str(rows[0][0]),
                        "last": str(rows[-1][0]),
                        "sha256_csv": sha256_file(path),
                    })
                    manifest["downloaded_contracts"] += 1
                    print("DOWNLOADED", kind, expiry, typ, strike, "bars", len(rows), flush=True)
            except Exception as exc:
                manifest["errors"].append({
                    "kind": kind,
                    "expiry": str(expiry),
                    "strike": strike,
                    "error_type": type(exc).__name__,
                    "message": str(exc),
                })
                print("ERROR", kind, expiry, strike, type(exc).__name__, flush=True)
            finally:
                manifest["api_requests"] = client.request_count
                write_json(manifest_path, manifest)
        manifest["limit_reached"] = bool(limit and processed >= limit)
    except Exception as exc:
        manifest["fatal_error"] = {"type": type(exc).__name__, "message": str(exc)}
        print("DISCOVERY FAILED:", type(exc).__name__, str(exc), flush=True)
    finally:
        manifest["api_requests"] = client.request_count
        write_json(manifest_path, manifest)
        bundle = out.parent / "AEGIS_Upstox_Active_Patch.zip"
        with zipfile.ZipFile(bundle, "w", compression=zipfile.ZIP_DEFLATED) as z:
            for p in out.rglob("*"):
                if p.is_file() and p.suffix in (".csv", ".json"):
                    z.write(p, p.relative_to(out.parent))
        print("PATCH_MANIFEST", json.dumps(manifest, indent=2), flush=True)
        print("PATCH_ARCHIVE", str(bundle), "bytes", bundle.stat().st_size, flush=True)
    return manifest


def self_test():
    assert regular_fo_bar("2026-11-05T15:39:00+05:30")
    assert not regular_fo_bar("2026-11-05T15:40:00+05:30")
    assert not regular_fo_bar("2026-11-05T15:39:00+00:00")
    assert is_nifty({"segment": "NSE_FO", "underlying_symbol": "NIFTY"})
    assert not is_nifty({"segment": "NSE_FO", "underlying_symbol": "BANKNIFTY"})
    client = MarketOnlyClient("test-never-sent")
    for forbidden in ("/v2/order/place", "/v2/portfolio/short-term-positions", "/v2/user/profile"):
        try:
            client.get(forbidden)
        except ValueError:
            pass
        else:
            raise AssertionError("Forbidden account/trading endpoint passed allowlist")
    print("SELF-TEST PASSED: no external dependency, correct session cutoff, trading endpoints blocked")


def main():
    p = argparse.ArgumentParser(description="Standalone AEGIS Upstox active F&O historical supplement")
    p.add_argument("--limit", type=int, default=0, help="0 = all eligible contracts; 4 = small pilot")
    p.add_argument("--wing", type=float, default=1200)
    p.add_argument("--out", default="AEGIS_Upstox_Active_Patch")
    p.add_argument("--self-test", action="store_true", help="Offline safety test, does not ask for token")
    a = p.parse_args()
    if a.self_test:
        self_test()
        return
    if a.limit < 0 or a.wing <= 0:
        p.error("limit cannot be negative and wing must be positive")
    token = getpass.getpass("Upstox READ-ONLY Analytics Token (hidden; never saved): ").strip()
    if not token:
        p.error("No Analytics Token supplied")
    client = MarketOnlyClient(token)
    report = run(client, pathlib.Path(a.out), a.limit, a.wing)
    if report.get("fatal_error") or report.get("errors") or not report["downloaded_contracts"] + report["reused_contracts"]:
        raise SystemExit("Supplement not fully successful; inspect token-free patch manifest ZIP")
    print("No credential was saved. Upload only the generated market-data ZIP.")


if __name__ == "__main__":
    main()
