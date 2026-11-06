#!/usr/bin/env python3
"""AEGIS offline quality audit for user-exported Upstox market-data ZIP.

Runs entirely offline; reads only market-data ZIP and optional manifest JSON.
Never opens any brokerage endpoints or needs an access token.
Audit outputs derived aggregate findings, not account information.
"""
from __future__ import annotations

import argparse
import collections
import csv
import datetime as dt
import hashlib
import io
import json
import pathlib
import zipfile

START=dt.date(2026,7,22)
END=dt.date(2026,11,5)

def kind_of(path):
    parts=path.lower().replace("\\","/").split("/")
    for k in ("options","futures","indices"):
        if k in parts:return k
    return None

def session_last(date,kind):
    if kind=="indices":return dt.time(15,29)  # Separate cash-index/VIX bar audit.
    return dt.time(15,39) if date>=dt.date(2026,8,3) else dt.time(15,29)

def parse_stamp(x):
    return dt.datetime.fromisoformat(x.strip())

def main():
    parser=argparse.ArgumentParser(description="Offline audit of AEGIS Upstox 2026 historical data ZIP")
    parser.add_argument("archive",help="Path to AEGIS_Upstox_Export.zip")
    parser.add_argument("--manifest",help="Optional downloaded AEGIS_upstox_export_manifest.json")
    parser.add_argument("--output",default="AEGIS_upstox_archive_audit.json")
    a=parser.parse_args()
    arc=pathlib.Path(a.archive)
    if not arc.exists():raise SystemExit(f"ZIP not found: {arc}")
    expected=json.loads(pathlib.Path(a.manifest).read_text(encoding="utf-8")) if a.manifest else None
    summary={"source_archive":arc.name,"zip_bytes":arc.stat().st_size,
        "requested_start":str(START),"requested_end":str(END),
        "archive_valid_directory":False,
        "csv_counts":{},"session_dates_by_kind":{},
        "derivative_last_two_sessions":{},"expiry_dates_seen":[],
        "sha_metadata_verified":0,"sha_metadata_mismatch":0,
        "csv_corrupted_or_unreadable":[],"sample_invalid_ohlc":[],
        "out_of_session_samples":[],"duplicate_timestamp_files":[],
        "metadata_missing_or_corrupt":0,"contract_files_without_metadata":0,
        "note":"Session classification varies with 03-Aug-2026 F&O rule; index close separate. Sparse option candles may be normal illiquidity."}
    if expected:summary["provided_manifest"]={k:expected.get(k) for k in (
       "start","end","expiries_available","downloaded_contract_files","skipped_existing",
       "empty_contracts","errors","limits","api_request_count"
    )}
    totals={k:collections.Counter() for k in ("options","futures","indices")}
    dates={k:set() for k in totals}
    expiries=set()
    session_4_5={k:collections.Counter() for k in totals}
    zip_hash=hashlib.sha256()
    with arc.open("rb") as fi:
        for chunk in iter(lambda:fi.read(1024*1024),b""):zip_hash.update(chunk)
    summary["zip_sha256"]=zip_hash.hexdigest()
    with zipfile.ZipFile(arc) as z:
        members=z.namelist()
        summary["archive_valid_directory"]=True
        summary["zip_members"]=len(members)
        member_set=set(members)
        summary["zip_duplicate_member_names"]=len(members)-len(member_set)
        for name in members:
            if not name.lower().endswith(".csv"):continue
            kind=kind_of(name)
            if not kind:continue
            totals[kind]["files"]+=1
            sidecar=name[:-4]+".json"
            if kind in ("options","futures"):
                segments=name.split("/")
                if "options" in segments:
                    kindex=segments.index("options")
                elif "futures" in segments:
                    kindex=segments.index("futures")
                else:kindex=None
                if kindex is not None and kindex+1<len(segments):
                    try:expiries.add(dt.date.fromisoformat(segments[kindex+1]))
                    except ValueError:pass
            try:
                raw=z.read(name)  # Forces ZIP CRC verification.
                if sidecar in member_set:
                    try:
                        meta=json.loads(z.read(sidecar).decode("utf-8"))
                        wanted=meta.get("sha256_csv")
                        if wanted and hashlib.sha256(raw).hexdigest()==wanted:
                            summary["sha_metadata_verified"]+=1
                        elif wanted:
                            summary["sha_metadata_mismatch"]+=1
                            summary["csv_corrupted_or_unreadable"].append({"file":name,"error":"sha256 mismatch"})
                        else:
                            summary["metadata_missing_or_corrupt"]+=1
                    except Exception as e:
                        summary["metadata_missing_or_corrupt"]+=1
                elif kind!="indices":
                    summary["contract_files_without_metadata"]+=1
                text=io.StringIO(raw.decode("utf-8-sig"))
                reader=csv.DictReader(text)
                if not {"timestamp","open","high","low","close"}.issubset(set(reader.fieldnames or [])):
                    summary["csv_corrupted_or_unreadable"].append({"file":name,"error":"missing expected headers"})
                    continue
                stamps=set()
                dup=0
                for row in reader:
                    totals[kind]["rows"]+=1
                    stamp=row.get("timestamp") or ""
                    try:
                        t=parse_stamp(stamp)
                        d=t.date()
                        vals=[float(row[x]) for x in ("open","high","low","close")]
                        o,h,l,c=vals
                        if not all(x>0 for x in vals) or h<max(o,l,c) or l>min(o,h,c):
                            totals[kind]["invalid_ohlc"]+=1
                            if len(summary["sample_invalid_ohlc"])<10:summary["sample_invalid_ohlc"].append({"file":name,"timestamp":stamp,"OHLC":vals})
                        if stamp in stamps:dup+=1
                        stamps.add(stamp)
                        if START<=d<=END:
                            dates[kind].add(d)
                            totals[kind]["rows_in_requested_period"]+=1
                            if d in (dt.date(2026,11,4),dt.date(2026,11,5)):
                                session_4_5[kind][str(d)]+=1
                            clock=t.time().replace(tzinfo=None)
                            if clock<dt.time(9,15) or clock>session_last(d,kind):
                                totals[kind]["outside_reference_session"]+=1
                                if len(summary["out_of_session_samples"])<15:
                                    summary["out_of_session_samples"].append({"file":name,"timestamp":stamp})
                    except (ValueError,TypeError,KeyError):
                        totals[kind]["invalid_rows"]+=1
                if dup:
                    totals[kind]["duplicate_timestamps"]+=dup
                    if len(summary["duplicate_timestamp_files"])<15:
                        summary["duplicate_timestamp_files"].append({"file":name,"duplicates":dup})
            except Exception as e:
                summary["csv_corrupted_or_unreadable"].append({"file":name,"error":type(e).__name__})
    for k in totals:
        summary["csv_counts"][k]=dict(totals[k])
        summary["session_dates_by_kind"][k]={
          "distinct_trading_dates":len(dates[k]),
          "first":str(min(dates[k])) if dates[k] else None,
          "last":str(max(dates[k])) if dates[k] else None}
        summary["derivative_last_two_sessions"][k]=dict(session_4_5[k])
    summary["expiry_dates_seen"]=[str(d) for d in sorted(expiries)]
    summary["coverage_alerts"]=[]
    for k in ("options","futures"):
        for d in ("2026-11-04","2026-11-05"):
            if summary["derivative_last_two_sessions"][k].get(d,0)==0:
                summary["coverage_alerts"].append(f"No {k} candles observed for {d}; likely expired-contract selection boundary")
    if expected:
        actual=totals["options"]["files"]+totals["futures"]["files"]
        listed=int(expected.get("downloaded_contract_files",0))+int(expected.get("skipped_existing",0))
        summary["contract_file_count_vs_manifest"]={"observed":actual,"expected":listed,"match":actual==listed}
    out=pathlib.Path(a.output)
    out.write_text(json.dumps(summary,indent=2,default=str),encoding="utf-8")
    print(json.dumps({
        "zip_sha256":summary["zip_sha256"],
        "csv_counts":summary["csv_counts"],
        "session_dates_by_kind":summary["session_dates_by_kind"],
        "expiries":summary["expiry_dates_seen"],
        "contract_file_count_vs_manifest":summary.get("contract_file_count_vs_manifest"),
        "sha_verified":summary["sha_metadata_verified"],
        "corrupt_files":len(summary["csv_corrupted_or_unreadable"]),
        "coverage_alerts":summary["coverage_alerts"],
        "report":str(out)
    },indent=2))
if __name__=="__main__":main()
