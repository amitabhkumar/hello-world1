#!/usr/bin/env python3
"""AEGIS active-contract supplementary market ZIP forensic audit (read-only).

Verifies the *actual* 2026 Nov active 1-minute OHLCV+OI market CSVs against
SHA-256 sidecars. Option gaps are judged by market session days (not by naive
385-bar count: illiquid option contracts may have sparse candles).
Compares expected FUTURES trading days to the original ZIP's NIFTY 50 index
sessions, so exchange holidays are not silently counted as missing.

Outputs JSON that preserves only market data, no tokens/user account data.
"""
from __future__ import annotations
import argparse,collections,csv,datetime as dt,hashlib,io,json,pathlib,zipfile

FIRST_FUT=dt.date(2026,10,28)
FIRST_OPT=dt.date(2026,11,4)
LAST=dt.date(2026,11,5)
END_OPT_EXTRA=dt.date(2026,11,2)

def parse_time(x):
    t=dt.datetime.fromisoformat(str(x))
    if t.utcoffset()!=dt.timedelta(hours=5,minutes=30):
        raise ValueError("Invalid or non-IST timestamp")
    return t

def in_session(t):
    return dt.time(9,15)<=t.time().replace(tzinfo=None)<=dt.time(15,39)

def ohlc_valid(o,h,l,c):
    return all(v>0 for v in (o,h,l,c)) and h>=max(o,l,c) and l<=min(o,h,c)

def original_index_dates(path):
    if path is None:return None
    dates=set()
    with zipfile.ZipFile(path) as z:
        for name in z.namelist():
            if "/indices/NIFTY50/" not in name.replace("\\","/") or not name.endswith(".csv"):
                continue
            with io.TextIOWrapper(z.open(name),"utf-8-sig",newline="") as f:
                for r in csv.DictReader(f):
                    try:
                        t=parse_time(r["timestamp"])
                        if FIRST_FUT<=t.date()<=LAST:
                            dates.add(t.date())
                    except (ValueError,KeyError):continue
    return dates

def audit(patch,original=None):
    expected=original_index_dates(original)
    summary={
        "status":"pending","patch_zip":patch.name,"original_zip":original.name if original else None,
        "patch_bytes":patch.stat().st_size,
        "sha256_csv_passed":0,"sha256_csv_failed":0,
        "file_errors":[],"invalid_ohlc":0,"invalid_timestamp_or_session":0,
        "duplicate_time_bars":0,
        "options":{"files":0,"rows":0,"by_expiry":{},"by_day":{},"empty_contract_responses_reported":None},
        "futures":{"files":0,"rows":0,"by_expiry":{},"by_day":{}},
        "index_trading_dates_2026_oct28_nov05":[],
        "futures_missing_dates_vs_original_index":[],
        "options_missing_dates_nov04_nov05":[],
        "comments":["An empty API response does not necessarily mean missing trading activity at an illiquid strike.",
                    "No order book or historical bid/ask prices are present."],
    }
    counts={"options":collections.Counter(),"futures":collections.Counter()}
    exp_counts={"options":collections.Counter(),"futures":collections.Counter()}
    contractday={"options":collections.defaultdict(set),"futures":collections.defaultdict(set)}
    strike_map=collections.defaultdict(lambda:{"CE":set(),"PE":set()})
    with zipfile.ZipFile(patch) as z:
        summary["zip_members"]=len(z.namelist())
        if len(z.namelist())!=len(set(z.namelist())):
            summary["file_errors"].append("Duplicate ZIP path names")
        names=set(z.namelist())
        for name in sorted(names):
            if not name.lower().endswith(".csv"):continue
            kind="options" if "/options/" in name else ("futures" if "/futures/" in name else None)
            if not kind:continue
            sidecar=name[:-4]+".json"
            if sidecar not in names:
                summary["file_errors"].append(f"Missing sidecar: {name}");continue
            try:
                meta=json.loads(z.read(sidecar))
                raw=z.read(name)  # ZIP CRC check performed
                got=hashlib.sha256(raw).hexdigest()
                if got!=meta.get("sha256_csv"):
                    summary["sha256_csv_failed"]+=1
                    summary["file_errors"].append(f"Bad SHA-256: {name}")
                    continue
                summary["sha256_csv_passed"]+=1
                exp=dt.date.fromisoformat(str(meta["expiry"]))
                assert int(meta["lot_size"])>0
                typ=meta["instrument_type"]
                strike=float(meta["strike_price"]) if kind=="options" else None
                if kind=="options" and typ not in ("CE","PE"):
                    raise ValueError("Unexpected option type")
                summary[kind]["files"]+=1
                exp_counts[kind][str(exp)]+=1
                with io.TextIOWrapper(io.BytesIO(raw),"utf-8-sig",newline="") as f:
                    reader=csv.DictReader(f)
                    if not set(["timestamp","open","high","low","close","volume"]).issubset(reader.fieldnames or []):
                        raise ValueError("Invalid CSV header")
                    seen=set()
                    n=0
                    for row in reader:
                        n+=1
                        try:
                            t=parse_time(row["timestamp"])
                            d=t.date()
                            if not in_session(t) or d>exp:
                                summary["invalid_timestamp_or_session"]+=1
                                continue
                            if t.isoformat() in seen:
                                summary["duplicate_time_bars"]+=1
                            seen.add(t.isoformat())
                            o,h,l,c=(float(row[k]) for k in ("open","high","low","close"))
                            if not ohlc_valid(o,h,l,c):
                                summary["invalid_ohlc"]+=1
                            counts[kind][str(d)]+=1
                            contractday[kind][str(d)].add(name)
                            if kind=="options":strike_map[str(d)][typ].add(strike)
                        except (ValueError,TypeError,KeyError):
                            summary["invalid_timestamp_or_session"]+=1
                    if int(meta.get("rows",-1))!=n:
                        summary["file_errors"].append(f"Metadata row mismatch: {name}")
                    summary[kind]["rows"]+=n
            except (ValueError,KeyError,TypeError,AssertionError,zipfile.BadZipFile) as error:
                summary["file_errors"].append(f"{name}: {error}")
    for kind in ("options","futures"):
        summary[kind]["by_day"]={
            date:{"bars":cnt,"contracts_with_bars":len(contractday[kind][date]),
                **({"CE_distinct_strikes":len(strike_map[date]["CE"]),"PE_distinct_strikes":len(strike_map[date]["PE"])} if kind=="options" else {})}
            for date,cnt in sorted(counts[kind].items())
        }
        summary[kind]["by_expiry"]=dict(sorted(exp_counts[kind].items()))
        summary[kind]["first_session"]=min(counts[kind]) if counts[kind] else None
        summary[kind]["last_session"]=max(counts[kind]) if counts[kind] else None
    # Cross-check index sessions rather than assuming weekday implies exchange-open.
    if expected is not None:
        summary["index_trading_dates_2026_oct28_nov05"]=[str(d) for d in sorted(expected)]
        summary["futures_missing_dates_vs_original_index"]=[
            str(d) for d in sorted(expected) if str(d) not in counts["futures"]]
        summary["options_missing_dates_nov04_nov05"]=[
            str(d) for d in sorted(expected) if FIRST_OPT<=d<=LAST
            and str(d) not in counts["options"]]
    manifestpaths=[name for name in names if name.endswith("AEGIS_active_patch_manifest.json")]
    if manifestpaths:
        with zipfile.ZipFile(patch) as manifest_archive:
            data=json.loads(manifest_archive.read(sorted(manifestpaths)[0]))
        summary["embedded_manifest"]={k:data.get(k) for k in (
            "version","downloaded_contracts","files_written","reused_contracts",
            "empty_contracts","errors","warnings","api_requests","limit_reached")}
        summary["options"]["empty_contract_responses_reported"]=data.get("empty_contracts")
    summary["status"]="integrity_pass" if not (
       summary["sha256_csv_failed"] or summary["file_errors"]
       or summary["invalid_ohlc"] or summary["invalid_timestamp_or_session"]
       or summary["duplicate_time_bars"]) else "integrity_failure"
    return summary

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--patch",required=True)
    p.add_argument("--original")
    p.add_argument("--out",default="AEGIS_active_patch_audit.json")
    a=p.parse_args()
    x=audit(pathlib.Path(a.patch),pathlib.Path(a.original) if a.original else None)
    pathlib.Path(a.out).write_text(json.dumps(x,indent=2))
    print("AEGIS_ACTIVE_PATCH_FORENSIC_AUDIT",json.dumps({
        "status":x["status"],"sha_verified":x["sha256_csv_passed"],
        "file_errors":x["file_errors"][:3],
        "options":x["options"],"futures":x["futures"],
        "missing_futures_index_sessions":x["futures_missing_dates_vs_original_index"],
        "missing_options_last2_sessions":x["options_missing_dates_nov04_nov05"]
    },indent=2),flush=True)
    if x["status"]!="integrity_pass":raise SystemExit(2)
if __name__=="__main__":main()
