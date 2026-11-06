#!/usr/bin/env python3
"""AEGIS source-data audit, NOT an options P&L backtest.

Reads each historical NIFTY options parquet file and reports physical schema,
records, nulls, timestamp boundaries, and price/volume/expiry field availability.
Does not invent spot, futures, bid/ask or Greeks where absent.
"""
import argparse, datetime, json, pathlib
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq
from collections import Counter

parser=argparse.ArgumentParser()
parser.add_argument("--file",required=True)
parser.add_argument("--kind",required=True)
parser.add_argument("--year",type=int,required=True)
parser.add_argument("--output",default="audit_results")
args=parser.parse_args()
file=pathlib.Path(args.file)
if not file.is_file(): raise SystemExit(f"Missing parquet file {file}")
pf=pq.ParquetFile(file)
schema=pf.schema_arrow
fields=[str(f.name) for f in schema]
rows=pf.metadata.num_rows
time_cols=[f.name for f in schema if any(k in f.name.lower() for k in ("timestamp","datetime","date","time","candle"))]
price_cols=[f.name for f in schema if f.name.lower() in ("open","high","low","close","volume","open_interest","oi","bid","ask","bid_price","ask_price","strike_price","strike","expiry","expiry_date","option_type","instrument_key")]
out={"source_file":str(file),"kind":args.kind,"nominal_year":args.year,"rows":rows,"row_groups":pf.num_row_groups,"column_names":fields,"schema":str(schema),"time_columns":time_cols,"candidate_price_columns":price_cols,"time_summary":{},"sample_rows":[]}
sample=pf.read_row_group(0).slice(0,3).to_pylist() if pf.num_row_groups else []
out["sample_rows"]=[{k:str(v) for k,v in row.items()} for row in sample]
for name in time_cols[:4]:
    c=schema.field(name)
    column_info={"type":str(c.type),"min":None,"max":None,"nulls":0,"sample_unique_dates":None}
    lo=None;hi=None; nulls=0; date_sample=set()
    try:
        # Column batches keep memory bounded even for large minute datasets.
        for batch in pf.iter_batches(batch_size=125000,columns=[name]):
            ar=batch.column(0);nulls+=ar.null_count
            if len(ar)==ar.null_count:continue
            mm=pc.min_max(ar,skip_nulls=True).as_py()
            mn=mm.get("min");mx=mm.get("max")
            if mn is not None:
                lo=mn if lo is None or mn<lo else lo
                hi=mx if hi is None or mx>hi else hi
            if len(date_sample)<2000 and (pa.types.is_timestamp(c.type) or pa.types.is_date(c.type)):
                date_arr=pc.cast(ar,pa.date32(),safe=False)
                for d in pc.unique(date_arr).to_pylist():
                    if d is not None:date_sample.add(str(d))
        column_info.update({"min":str(lo),"max":str(hi),"nulls":nulls})
        if date_sample:column_info["sample_unique_dates"]=len(date_sample)
    except Exception as e:
        column_info["audit_error"]=str(e)
    out["time_summary"][name]=column_info
out["audit_completed_utc"]=datetime.datetime.now(datetime.timezone.utc).isoformat()
dest=pathlib.Path(args.output);dest.mkdir(exist_ok=True,parents=True)
path=dest/f"nifty_{args.kind}_{args.year}_audit.json"
path.write_text(json.dumps(out,indent=2))
print(json.dumps({"year":args.year,"kind":args.kind,"rows":rows,"time_summary":out["time_summary"],"fields":fields,"result_file":str(path)},indent=2))
