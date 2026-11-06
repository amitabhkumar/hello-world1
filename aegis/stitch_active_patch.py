#!/usr/bin/env python3
"""AEGIS: validate supplementary read-only active-contract ZIP and convert to Parquet.

Use ONLY after user uploads the small active-contract ZIP, never an access token.
Parquet is compatible with backtest_v01.py's semicolon-separated parquet sources.
No raw market file is modified. Original verified expired-contract archive remains
authoritative for earlier dates; active patch may overlap Nov02-03 but has a
distinct expiry (e.g. Nov10), so no expiry/strike/timestamp duplicate.
"""
from __future__ import annotations
import argparse,collections,csv,datetime as dt,hashlib,io,json,zipfile
from pathlib import Path
import pyarrow as pa
import pyarrow.parquet as pq
from aegis.stitch_upstox_2026 import ARROW_SCHEMA,timestamp,valid_ohlc,is_session
def convert_patch(archive,output):
    output.mkdir(exist_ok=True,parents=True)
    report={"archive":archive.name,"options":0,"futures":0,"option_rows":0,
          "futures_rows":0,"sidecar_checksums":0,"invalid_or_outside":0,
          "first_per_kind":{},"last_per_kind":{}}
    option_rows=[];future_rows=[]
    with zipfile.ZipFile(archive) as z:
        names=set(z.namelist())
        for name in sorted(names):
            if not name.endswith(".csv"):continue
            parts=name.replace("\\","/").split("/")
            kind="options" if "options" in parts else ("futures" if "futures" in parts else None)
            if not kind:continue
            sidecar=name[:-4]+".json"
            if sidecar not in names:raise ValueError("Missing sidecar "+name)
            meta=json.loads(z.read(sidecar))
            raw=z.read(name)
            if hashlib.sha256(raw).hexdigest()!=meta.get("sha256_csv"):
                raise ValueError("Bad CSV SHA256 "+name)
            report["sidecar_checksums"]+=1
            exp=dt.date.fromisoformat(str(meta["expiry"]))
            typ=meta["instrument_type"]
            lot=int(meta["lot_size"])
            k=int(meta["strike_price"]) if kind=="options" else None
            if kind=="options" and typ not in ("CE","PE"):raise ValueError("Bad option type")
            report[kind]+=1
            for row in csv.DictReader(io.StringIO(raw.decode("utf-8-sig"))):
                t=timestamp(row["timestamp"])
                d=t.date()
                o,h,l,c=(float(row[q]) for q in ("open","high","low","close"))
                if not valid_ohlc(o,h,l,c) or not is_session(t,"options") or d>exp:
                    report["invalid_or_outside"]+=1;continue
                common={"timestamp":t,"date":d,"expiry":exp,
                    "open":o,"high":h,"low":l,"close":c,"volume":float(row["volume"]),
                    "open_interest":float(row.get("oi") or 0),"lot_size":lot}
                if kind=="options":
                    option_rows.append({**common,"strike":k,"option_type":typ,
                         "source":"upstox_historical_v3_active_1m"})
                else:future_rows.append(common)
    if option_rows:
        pq.write_table(pa.Table.from_pylist(option_rows,schema=ARROW_SCHEMA),
               output/"NIFTY_2026_active_options_patch.parquet",compression="zstd")
    if future_rows:
        pq.write_table(pa.Table.from_pylist(future_rows),
               output/"NIFTY_2026_active_futures_patch.parquet",compression="zstd")
    report["option_rows"]=len(option_rows)
    report["futures_rows"]=len(future_rows)
    for key,data in (("options",option_rows),("futures",future_rows)):
        if data:
            report["first_per_kind"][key]=str(min(x["date"] for x in data))
            report["last_per_kind"][key]=str(max(x["date"] for x in data))
    (output/"active_patch_ingestion.json").write_text(json.dumps(report,indent=2))
    print("AEGIS_ACTIVE_PATCH_INTEGRATED",json.dumps(report))
    return report
def main():
    p=argparse.ArgumentParser()
    p.add_argument("--zip",required=True)
    p.add_argument("--output",default="AEGIS_STITCH")
    a=p.parse_args()
    convert_patch(Path(a.zip),Path(a.output))
if __name__=="__main__":main()
