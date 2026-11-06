#!/usr/bin/env python3
"""Public data acquisition/verification only; NOT a NIFTY options backtest."""
import argparse, pathlib, hashlib, urllib.request, json, datetime, sys, time
BASE="https://huggingface.co/datasets/rissin/nse-options-intraday/resolve/main"
CHECKSUMS={
"historical_daily/NIFTY/NIFTY_2024.parquet":"245ff1a1a405c57d5bfbd9eba827fb248678c75fa18462065dd481b8598b5d67",
"historical_daily/NIFTY/NIFTY_2025.parquet":"6bbac1c7a52dd1a2d59e7d51873dd7efb6c8bc75e98579efc76d5e7b67f4dde8",
"historical_daily/NIFTY/NIFTY_2026.parquet":"2dc91094a78c50df7879fd5dbd596835f8c41889704e7e0be4b55b3068edae0b",
"upstox_intraday/NIFTY/NIFTY_2024.parquet":"573b6fa788dbe06cbb7f6c4a48ee2fcd259434ad05f70a1cca3e775bb5b9d934",
"upstox_intraday/NIFTY/NIFTY_2025.parquet":"33c2525b57ba442cfabeaebfc63ace63d0292e8f69474d5ea1541b75c9546972",
"upstox_intraday/NIFTY/NIFTY_2026.parquet":"bae9943b2fa99ee9c1214fb7c695b84f9f661a050a5cd04d9c5c2ffc7bc59f73",
}
p=argparse.ArgumentParser()
p.add_argument("--only",choices=("daily","intraday","all"),default="daily")
p.add_argument("--out",default="AEGIS_DATA")
a=p.parse_args()
root=pathlib.Path(a.out)
report={"download_utc":datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "source":"rissin/nse-options-intraday","complete":True,"data_is_backtest":False,"items":[]}
for key,sha in CHECKSUMS.items():
    if a.only=="daily" and not key.startswith("historical_daily/"):continue
    if a.only=="intraday" and not key.startswith("upstox_intraday/"):continue
    dst=root/key;dst.parent.mkdir(parents=True,exist_ok=True)
    item={"key":key,"expected_sha256":sha}
    try:
        req=urllib.request.Request(BASE+"/"+key,headers={"User-Agent":"Mozilla/5.0"})
        with urllib.request.urlopen(req,timeout=120) as resp,dst.open("wb") as fh:
            while True:
                b=resp.read(1024*1024)
                if not b:break
                fh.write(b)
        digest=hashlib.sha256(dst.read_bytes()).hexdigest()
        item.update({"bytes":dst.stat().st_size,"actual_sha256":digest,"status":"verified" if digest==sha else "checksum-mismatch"})
        if digest!=sha:raise RuntimeError("sha mismatch")
    except Exception as e:
        item.update({"status":"error","error":str(e)})
        report["complete"]=False
        print("FAILED",key,repr(e),file=sys.stderr)
    report["items"].append(item)
    print(json.dumps(item),flush=True)
root.mkdir(parents=True,exist_ok=True)
(root/"ingest_manifest.json").write_text(json.dumps(report,indent=2))
if not report["complete"]:sys.exit(1)
