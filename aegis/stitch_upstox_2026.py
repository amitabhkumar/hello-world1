#!/usr/bin/env python3
"""AEGIS v0.2: convert independently audited Upstox ZIP to replayable Parquet.

No Upstox token or API access. Preserves raw source ZIP. Produces:
  AEGIS_STITCH/NIFTY_upstox_2026_jul_nov.parquet
  AEGIS_SUPPORT/NIFTY_5min_2026_extended.csv
  AEGIS_SUPPORT/vix_2026.csv
  AEGIS_STITCH/ingestion_report.json

Cash index proxy uses original 5-min spot through 2026-04-21,
independent public one-minute source Apr22-Jul21, and user's Upstox
one-minute index bars Jul22-Nov05. Records all data-source boundaries.
Historical options 2026 Jul22-Nov03 are user-provided.
Backtest remains minute-OHLC MARK simulation, not bid/ask.
"""
from __future__ import annotations
import argparse, collections, csv, datetime as dt, hashlib, io, json
from pathlib import Path
import urllib.request
import zipfile
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

TIMEZONE=dt.timezone(dt.timedelta(hours=5,minutes=30))
CUTOVER=dt.date(2026,7,22)
END=dt.date(2026,11,5)
ARROW_SCHEMA=pa.schema([
    pa.field("timestamp",pa.timestamp("us",tz="+05:30")),
    pa.field("date",pa.date32()),
    pa.field("expiry",pa.date32()),
    pa.field("strike",pa.int32()),
    pa.field("option_type",pa.string()),
    pa.field("open",pa.float64()),
    pa.field("high",pa.float64()),
    pa.field("low",pa.float64()),
    pa.field("close",pa.float64()),
    pa.field("volume",pa.float64()),
    pa.field("open_interest",pa.float64()),
    pa.field("lot_size",pa.int32()),
    pa.field("source",pa.string())])
REQUIRED={"timestamp","open","high","low","close","volume"}
def sha256_bytes(b):return hashlib.sha256(b).hexdigest()
def timestamp(t):
    x=dt.datetime.fromisoformat(t)
    if x.utcoffset()!=dt.timedelta(hours=5,minutes=30):
        raise ValueError("Unexpected candle timestamp time zone "+str(t))
    return x
def valid_ohlc(o,h,l,c):return o>0 and c>0 and h>=max(o,c,l) and l>0 and l<=min(o,c,h)
def session_last(d,kind):
    if kind=="options":return dt.time(15,39) if d>=dt.date(2026,8,3) else dt.time(15,29)
    return dt.time(15,29)
def is_session(t,kind):
    return dt.time(9,15)<=t.time()<=session_last(t.date(),kind)
def extract(zip_path, output, old_support):
    output.mkdir(exist_ok=True,parents=True)
    support=old_support
    support.mkdir(exist_ok=True,parents=True)
    opt_file=output/"NIFTY_upstox_2026_jul_nov.parquet"
    reports={"input_zip":str(zip_path.name),"zip_bytes":zip_path.stat().st_size,
       "source_sha256":None,"option_csv_count":0,"option_rows_total":0,
       "option_rows_written":0,"option_rows_discarded_bad":0,
       "option_rows_discarded_session":0,
       "option_rows_discarded_dates":0,"futures_csv_count":0,"futures_rows":0,
       "options_dates":{},"index":{},"metadata_sha_verified":0,
       "metadata_sha_errors":[],"derived_spot_sources":{},
       "source_limits":["No bid/ask","No post-2026-11-03 options","No post-2026-10-27 futures",
                        "Public 1-minute spot for April22-July21 requires independent exchange check"]}
    h=hashlib.sha256()
    with zip_path.open("rb") as f:
        for chunk in iter(lambda:f.read(4*1024*1024),b""):h.update(chunk)
    reports["source_sha256"]=h.hexdigest()
    buffer=[]
    writer=None
    idx_bars={"NIFTY50":[],"INDIA_VIX":[]}
    futures_rows=[]
    per_day=collections.Counter()
    bad_examples=[]
    def flush():
        nonlocal buffer,writer
        if not buffer:return
        table=pa.Table.from_pylist(buffer,schema=ARROW_SCHEMA)
        if writer is None:writer=pq.ParquetWriter(str(opt_file),ARROW_SCHEMA,compression="zstd")
        writer.write_table(table,row_group_size=min(100000,len(buffer)))
        reports["option_rows_written"]+=len(buffer)
        buffer=[]
    with zipfile.ZipFile(zip_path) as z:
        names=set(z.namelist())
        for name in sorted(names):
            lower=name.lower().replace("\\","/")
            if not lower.endswith(".csv"):continue
            parts=lower.split("/")
            if "options" in parts:kind="options"
            elif "futures" in parts:kind="futures"
            elif "indices" in parts:kind="indices"
            else:continue
            raw=z.read(name)  # CRC tested; audit previously also compared SHA
            sidecar=name[:-4]+".json"
            metadata={}
            if kind in ("options","futures"):
                if sidecar not in names:raise ValueError(f"Missing contract sidecar: {name}")
                metadata=json.loads(z.read(sidecar))
                wanted=metadata.get("sha256_csv")
                if wanted!=sha256_bytes(raw):
                    reports["metadata_sha_errors"].append(name)
                    raise ValueError(f"Contract SHA mismatch: {name}")
                reports["metadata_sha_verified"]+=1
                exp=dt.date.fromisoformat(str(metadata["expiry"]))
                if kind=="options":
                    k=float(metadata["strike_price"])
                    if k!=int(k):raise ValueError("Nonintegral option strike "+name)
                    strike=int(k)
                    typ=str(metadata["instrument_type"])
                    if typ not in ("CE","PE"):raise ValueError("Bad type "+name)
                    lot=int(metadata["lot_size"])
                    reports["option_csv_count"]+=1
                else:
                    reports["futures_csv_count"]+=1
                    lot=int(metadata["lot_size"])
            if kind=="indices":
                if "/NIFTY50/" in name.upper():key="NIFTY50"
                elif "/INDIA_VIX/" in name.upper():key="INDIA_VIX"
                else:continue
            with io.TextIOWrapper(z.open(name),"utf-8-sig",newline="") as stream:
                rows=csv.DictReader(stream)
                if not REQUIRED.issubset(set(rows.fieldnames or [])):raise ValueError("Unexpected CSV header "+name)
                for row in rows:
                    if kind=="options":reports["option_rows_total"]+=1
                    elif kind=="futures":reports["futures_rows"]+=1
                    try:
                        ts=timestamp(row["timestamp"])
                        d=ts.date()
                        o,h,l,c=(float(row[x]) for x in ("open","high","low","close"))
                        if not valid_ohlc(o,h,l,c):raise ValueError("Invalid OHLC")
                    except Exception as e:
                        if len(bad_examples)<5:bad_examples.append({"csv":name,"error":str(e)})
                        if kind=="options":reports["option_rows_discarded_bad"]+=1
                        continue
                    if kind=="options":
                        if d<CUTOVER or d>END or d>exp:
                            reports["option_rows_discarded_dates"]+=1
                            continue
                        if not is_session(ts,"options"):
                            reports["option_rows_discarded_session"]+=1
                            continue
                        buffer.append({"timestamp":ts,"date":d,"expiry":exp,"strike":strike,
                          "option_type":typ,"open":o,"high":h,"low":l,"close":c,
                          "volume":float(row.get("volume") or 0),
                          "open_interest":float(row.get("oi") or 0),
                          "lot_size":lot,"source":"upstox_expired_contract_1m"})
                        per_day[str(d)]+=1
                        if len(buffer)>=75000:flush()
                    elif kind=="futures":
                        if CUTOVER<=d<=END and d<=exp and is_session(ts,"options"):
                            futures_rows.append({"timestamp":ts,"date":d,"expiry":exp,
                                 "open":o,"high":h,"low":l,"close":c,
                                 "volume":float(row.get("volume") or 0),
                                 "open_interest":float(row.get("oi") or 0),"lot_size":lot})
                    elif kind=="indices":
                        if CUTOVER<=d<=END:
                            if is_session(ts,"indices"):
                                idx_bars[key].append({"timestamp":ts,"open":o,"high":h,"low":l,"close":c,
                                    "volume":float(row.get("volume") or 0)})
            if (reports["option_csv_count"]%300)==0 and kind=="options":
                print("OPTIONS_CSV_PROCESSED",reports["option_csv_count"],flush=True)
        flush()
    if writer is not None:writer.close()
    else:raise ValueError("No valid option candle data produced")
    reports["options_dates"]=dict(sorted(per_day.items()))
    if futures_rows:
        future_table=pa.Table.from_pylist(futures_rows)
        pq.write_table(future_table,output/"NIFTY_futures_upstox_2026.parquet",
             compression="zstd")
    reports["futures_rows_written"]=len(futures_rows)
    reports["futures_observed_last"]=str(max((x["date"] for x in futures_rows),default="none"))
    reports["bad_examples"]=bad_examples
    spot_base_file=support/"NIFTY_5min_5yr_2021_2026.csv"
    if not spot_base_file.exists():raise FileNotFoundError(spot_base_file)
    base=pd.read_csv(spot_base_file)
    base.columns=[str(c).lower() for c in base.columns]
    if not {"timestamp","open","high","low","close"}.issubset(base):raise ValueError("Unexpected spot support schema")
    base["timestamp"]=pd.to_datetime(base["timestamp"]).dt.tz_localize(None)
    base=base[(base.timestamp.dt.date<dt.date(2026,4,22))]
    base=base[["timestamp","open","high","low","close","volume"]].copy()
    base["source"]="voletiramu_5m_mirror"
    public=[]
    for month in (4,5,6,7):
        url=("https://raw.githubusercontent.com/technovusin/nifty50-historical-data/main/"
             f"1min/2026/NIFTY50_1min_2026-{month:02d}.csv")
        request=urllib.request.Request(url,headers={"User-Agent":"AEGIS-2026-Historical-Replay/1.0"})
        with urllib.request.urlopen(request,timeout=75) as r:raw=r.read()
        reports["derived_spot_sources"][f"2026-{month:02d}"]={
             "url":url,"sha256":sha256_bytes(raw),"bytes":len(raw)}
        for row in csv.DictReader(io.StringIO(raw.decode("utf-8-sig"))):
            try:
                t=dt.datetime.fromisoformat(row["Timestamp"])
                d=t.date()
                if not (dt.date(2026,4,22)<=d<CUTOVER):continue
                if not (dt.time(9,15)<=t.time()<=dt.time(15,29)):continue
                o,h,l,c=(float(row[x]) for x in ("Open","High","Low","Close"))
                if valid_ohlc(o,h,l,c):
                    public.append({"timestamp":t,"open":o,"high":h,"low":l,"close":c,
                         "volume":float(row.get("Volume") or 0)})
            except (ValueError,KeyError,TypeError):
                continue
    def aggregate_5minute(records,source):
        if not records:return pd.DataFrame(columns=base.columns)
        df=pd.DataFrame(records)
        df["timestamp"]=pd.to_datetime(df["timestamp"]).dt.tz_localize(None)
        df=df.sort_values("timestamp")
        df=df.set_index("timestamp")
        agg=df.resample("5min",closed="left",label="left").agg(
            {"open":"first","high":"max","low":"min","close":"last","volume":"sum"})
        agg=agg.dropna(subset=["open","high","low","close"]).reset_index()
        agg["source"]=source
        return agg
    source_github=aggregate_5minute(public,"technovusin_1m_to_5m")
    source_upstox=aggregate_5minute(idx_bars["NIFTY50"],"upstox_index_1m_to_5m")
    combined=pd.concat([base,source_github,source_upstox],ignore_index=True)
    combined=combined.sort_values("timestamp").drop_duplicates("timestamp",keep="last")
    combined.to_csv(support/"NIFTY_5min_2026_extended.csv",index=False)
    reports["index"]["spot_source_counts"]={
       str(k):int(v) for k,v in combined.groupby("source").size().items()}
    reports["index"]["spot_new_last_timestamp"]=str(combined.timestamp.max())
    vix=idx_bars["INDIA_VIX"]
    vixdf=pd.DataFrame(vix).sort_values("timestamp")
    vixdf["date"]=pd.to_datetime(vixdf["timestamp"]).dt.date
    vixlast=vixdf.groupby("date").tail(1)
    vixlast["date"]=vixlast["date"].map(lambda x:x.strftime("%d-%b-%Y"))
    vixlast[["date","close"]].to_csv(support/"vix_2026.csv",index=False)
    reports["index"]["vix_days"]=len(vixlast)
    reports["index"]["vix_last_date"]=str(vixdf.timestamp.max().date())
    (output/"ingestion_report.json").write_text(json.dumps(reports,indent=2))
    print("AEGIS_STITCH_INGEST",json.dumps({
       k:reports[k] for k in ("option_csv_count","option_rows_total","option_rows_written",
         "option_rows_discarded_bad","option_rows_discarded_session",
         "metadata_sha_verified","futures_csv_count","futures_rows","index")
       },default=str),flush=True)

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--zip",required=True)
    p.add_argument("--support",default="AEGIS_SUPPORT")
    p.add_argument("--output",default="AEGIS_STITCH")
    a=p.parse_args()
    extract(Path(a.zip),Path(a.output),Path(a.support))
if __name__=="__main__":main()
