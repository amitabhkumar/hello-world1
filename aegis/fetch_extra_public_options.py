#!/usr/bin/env python3
"""Retrieve publicly listed HF NIFTY 2026 expiries after previous data's July21 cutoff.
Only authentic HTTP GET of published Parquet files. No claims of quote/bid/ask data.
"""
import pathlib,urllib.request,json,hashlib,datetime as dt
import pyarrow.parquet as pq
ROOT=pathlib.Path("AEGIS_EXTRA_PUBLIC_OPTIONS");ROOT.mkdir(exist_ok=True)
ROOT_URL="https://huggingface.co/datasets/thetrademarkk/india-index-options-1m/resolve/main/options/NIFTY"
expiries=["2026-07-28","2026-08-04"]
manifest={"source":"thetrademarkk/india-index-options-1m","acquired_utc":dt.datetime.now(dt.timezone.utc).isoformat(),"files":[]}
for expiry in expiries:
    url=ROOT_URL+"/"+expiry+".parquet"
    req=urllib.request.Request(url,headers={"User-Agent":"AEGIS Research/1.0"})
    target=ROOT/(expiry+".parquet")
    h=hashlib.sha256()
    try:
        with urllib.request.urlopen(req,timeout=90) as r, target.open("wb") as f:
            while True:
                chunk=r.read(1024*1024)
                if not chunk:break
                h.update(chunk);f.write(chunk)
        pf=pq.ParquetFile(target)
        sample=pf.read_row_group(0).slice(0,2).to_pylist() if pf.num_row_groups else []
        info={"expiry":expiry,"status":"downloaded","bytes":target.stat().st_size,
          "sha256":h.hexdigest(),"row_count":pf.metadata.num_rows,
          "fields":pf.schema_arrow.names,"sample":json.loads(json.dumps(sample,default=str))}
        manifest["files"].append(info);print("FILE",json.dumps(info),flush=True)
    except Exception as e:
        manifest["files"].append({"expiry":expiry,"status":"error","error":str(e)})
        print("FAILED",expiry,repr(e),flush=True)
(ROOT/"manifest.json").write_text(json.dumps(manifest,indent=2))
