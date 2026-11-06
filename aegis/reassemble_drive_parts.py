#!/usr/bin/env python3
"""Reassemble Drive-stored AEGIS NIFTY parquet parts; verify every SHA-256.

Inputs:
  aegis-minute-2025-manifest.zip
  aegis-minute-2025-part-00.zip ... part-08.zip
  aegis-minute-2026-manifest.zip
  aegis-minute-2026-part-00.zip ... part-05.zip

Download the files from the dedicated AEGIS_NIFTY_OPTIONS_BACKTEST Drive folder.
This runs entirely offline; no Google authentication or external packages needed.
"""
import argparse
import hashlib
import json
from pathlib import Path
from zipfile import ZipFile

BUFFER=4 * 1024 * 1024

def reconstruct(year: int, root: Path, output: Path) -> None:
    manifest_zip=root / f"aegis-minute-{year}-manifest.zip"
    with ZipFile(manifest_zip) as z:
        member=next((n for n in z.namelist() if n.endswith(f"NIFTY_{year}_PARTS_MANIFEST.json")),None)
        if member is None: raise ValueError(f"No manifest in {manifest_zip}")
        manifest=json.loads(z.read(member))

    assert manifest["year"] == year
    output.mkdir(parents=True, exist_ok=True)
    target=output / manifest["original_file"]
    full_hash=hashlib.sha256()
    total=0
    with target.open("wb") as fout:
        for index,part in enumerate(manifest["parts"]):
            chunk_zip=root / f"aegis-minute-{year}-part-{index:02d}.zip"
            with ZipFile(chunk_zip) as z:
                members=[name for name in z.namelist() if name.endswith(part["file"])]
                if len(members)!=1: raise ValueError(f"{chunk_zip}: expected {part['file']}, got {members}")
                chunk_hash=hashlib.sha256()
                count=0
                with z.open(members[0]) as inp:
                    while True:
                        data=inp.read(BUFFER)
                        if not data: break
                        chunk_hash.update(data)
                        full_hash.update(data)
                        fout.write(data)
                        count+=len(data)
                        total+=len(data)
                if count!=part["size"] or chunk_hash.hexdigest()!=part["sha256"]:
                    raise ValueError(f"{chunk_zip}: part checksum or size failed")
                print(f"Verified chunk {index+1}/{len(manifest['parts'])} for {year}")
    if total!=manifest["original_size"] or full_hash.hexdigest()!=manifest["original_sha256"]:
        raise ValueError(f"NIFTY_{year}: reconstructed SHA256 or size failed")
    print(f"VERIFIED {target}: {total:,} bytes, sha256={full_hash.hexdigest()}")

if __name__ == "__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--folder",default=".",help="Folder with the part ZIPs and manifest ZIPs")
    p.add_argument("--out",default="reconstructed")
    p.add_argument("--year",type=int,choices=[2025,2026],help="Omit to reconstruct both years")
    a=p.parse_args()
    for year in ([a.year] if a.year else [2025,2026]):
        reconstruct(year,Path(a.folder),Path(a.out))
