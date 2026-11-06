#!/usr/bin/env python3
"""Fetch one publicly published intraday NIFTY options parquet file and verify SHA-256."""
import argparse, hashlib, json, pathlib, sys, urllib.request, datetime
p=argparse.ArgumentParser()
p.add_argument("--year",type=int,required=True,choices=[2024,2025,2026])
a=p.parse_args()
expected={
2024:"573b6fa788dbe06cbb7f6c4a48ee2fcd259434ad05f70a1cca3e775bb5b9d934",
2025:"33c2525b57ba442cfabeaebfc63ace63d0292e8f69474d5ea1541b75c9546972",
2026:"bae9943b2fa99ee9c1214fb7c695b84f9f661a050a5cd04d9c5c2ffc7bc59f73"
}
url=f"https://huggingface.co/datasets/rissin/nse-options-intraday/resolve/main/upstox_intraday/NIFTY/NIFTY_{a.year}.parquet"
root=pathlib.Path(f"AEGIS_INTRADAY_{a.year}")
root.mkdir(exist_ok=True)
target=root/f"NIFTY_{a.year}.parquet"
h=hashlib.sha256()
with urllib.request.urlopen(urllib.request.Request(url,headers={"User-Agent":"Mozilla/5.0"}),timeout=180) as source,target.open("wb") as output:
    while True:
        chunk=source.read(4*1024*1024)
        if not chunk:break
        output.write(chunk);h.update(chunk)
actual=h.hexdigest()
record={"year":a.year,"url":url,"sha256_expected":expected[a.year],"sha256_actual":actual,"bytes":target.stat().st_size,
"verified":actual==expected[a.year],"retrieved_utc":datetime.datetime.now(datetime.timezone.utc).isoformat()}
(root/"ingest_manifest.json").write_text(json.dumps(record,indent=2))
print(json.dumps(record))
if not record["verified"]:sys.exit("checksum mismatch")
