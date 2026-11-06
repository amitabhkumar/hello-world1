#!/usr/bin/env python3
"""Public 2026 NIFTY gap source check: 1-min spot + expiry options.
No secret, no account, no paid endpoints. New spot dataset is independently
validated against known NSE Nov-2026 closes.
"""
import csv, hashlib, io, json, pathlib, urllib.request, zipfile, datetime as dt, sys
root=pathlib.Path("AEGIS_NEW_2026_SOURCES")
root.mkdir(exist_ok=True)
def get(url,timeout=50):
    req=urllib.request.Request(url,headers={"User-Agent":"AEGIS-Reproducibility/0.1","Accept":"*/*"})
    with urllib.request.urlopen(req,timeout=timeout) as r:return r.read()

manifest={"created_utc":dt.datetime.now(dt.timezone.utc).isoformat(),"source":"technovusin/nifty50-historical-data","spot":{},"options_probes":{}}
spotfolder=root/"spot_1m";spotfolder.mkdir(exist_ok=True)
fullrows=[]
for month in range(1,12):
    path=f"1min/2026/NIFTY50_1min_2026-{month:02d}.csv"
    url=f"https://raw.githubusercontent.com/technovusin/nifty50-historical-data/main/{path}"
    data=get(url)
    f=spotfolder/pathlib.Path(path).name;f.write_bytes(data)
    text=data.decode("utf-8-sig")
    rows=list(csv.DictReader(io.StringIO(text)))
    rows=[x for x in rows if "Timestamp" in x and str(x["Timestamp"])[:10]<="2026-11-05"]
    if not rows:raise ValueError(f"No 2026 session rows {path}")
    for row in rows:
        a,b,c,d=(float(row[v]) for v in ("Open","High","Low","Close"))
        if a<=0 or b<max(a,d,c) or c>min(a,d,b):
            raise ValueError(f"OHLC invalid at {row.get('Timestamp')} in {path}")
    fullrows+=rows
    manifest["spot"][path]={"bytes":len(data),"sha256":hashlib.sha256(data).hexdigest(),
       "first":rows[0]["Timestamp"],"last":rows[-1]["Timestamp"],"rows_up_to_2026_11_05":len(rows)}
    print("SPOT",path,"bars",len(rows),"first",rows[0]["Timestamp"],"last",rows[-1]["Timestamp"],flush=True)
ordered=sorted(fullrows,key=lambda x:x["Timestamp"])
closes={x["Timestamp"][:10]:float(x["Close"]) for x in ordered}
ref={"2026-11-02":23440.80,"2026-11-05":24536.60}
for date,target in ref.items():
    observed=closes.get(date)
    manifest.setdefault("spot_reference_validation",{})[date]={"published_NSE_close":target,"spot_source_last_bar_close":observed,"diff":None if observed is None else round(observed-target,2)}
print("REFERENCE_VALIDATION",manifest.get("spot_reference_validation"),flush=True)
# Preserve all source files even if failed the independent price check. User can inspect.
probeurls={
 "HF_OPTIONS_NIFTY":"https://huggingface.co/api/datasets/thetrademarkk/india-index-options-1m/tree/main/options/NIFTY?limit=1000",
 "HF_INDEX_NIFTY":"https://huggingface.co/api/datasets/thetrademarkk/india-index-options-1m/tree/main/index?limit=1000"
}
for label,url in probeurls.items():
    try:
        payload=get(url,120);parsed=json.loads(payload)
        files=[x.get("path","") for x in parsed if x.get("type")=="file"]
        last=sorted(files)[-12:]
        future=[x for x in files if x.endswith(".parquet") and x.split("/")[-1].startswith("2026-") and x.split("/")[-1][:10]>"2026-07-21"]
        manifest["options_probes"][label]={"status":"ok","file_count_this_page":len(files),"recent_paths":last,"post_2026_07_21_paths":sorted(future)}
        print("DATASET",label,"file_count",len(files),"latest",last,"post_July21",len(future),flush=True)
    except Exception as e:
        manifest["options_probes"][label]={"status":"unavailable","error":str(e)}
        print("PROBE ERROR",label,repr(e),flush=True)
(root/"probe_manifest.json").write_text(json.dumps(manifest,indent=2))
with zipfile.ZipFile(root/"AEGIS_NIFTY_2026_SPOT_1M_JAN_NOV.zip","w",compression=zipfile.ZIP_DEFLATED) as z:
    for f in spotfolder.glob("*.csv"):z.write(f,f.name)
    z.write(root/"probe_manifest.json","probe_manifest.json")
print("BUNDLE",root/"AEGIS_NIFTY_2026_SPOT_1M_JAN_NOV.zip",flush=True)
