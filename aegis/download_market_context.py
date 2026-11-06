#!/usr/bin/env python3
"""Fetch public NIFTY spot 5-minute/futures daily archive and NSE VIX 2024-25 mirror.
Any external data is for research; origin and hashes retained for reproducibility.
"""
import hashlib,json,urllib.request,zipfile,io,pathlib,datetime,csv
root=pathlib.Path("AEGIS_SUPPORT");root.mkdir(exist_ok=True)
url="https://github.com/voletiramu/nse-fno-1min-data/releases/download/indices-v1.0.0/nifty_indices_5yr.zip"
req=urllib.request.Request(url,headers={"User-Agent":"Mozilla/5.0"})
data=urllib.request.urlopen(req,timeout=90).read()
assert hashlib.sha256(data).hexdigest()=="0c1f3de848a4e8c05e233c195685e7ae560d56d08df8baba8b2ffcfac699d3f8", "Cash/futures release changed SHA256"
(root/"nifty_indices_5yr.zip").write_bytes(data)
print("SOURCE:",url,"BYTES:",len(data),"SHA256:",hashlib.sha256(data).hexdigest())
with zipfile.ZipFile(io.BytesIO(data)) as z:
  for name in z.namelist():
    print("ZIP MEMBER",name,z.getinfo(name).file_size)
    if name.lower().endswith(".csv") and ("nifty" in name.lower()):
      target=root/pathlib.Path(name).name
      target.write_bytes(z.read(name))
      print("HEADER",target.name,target.read_text(errors="replace").splitlines()[:4])
for yr in [2024,2025]:
  vurl=f"https://raw.githubusercontent.com/Hareeshkesavan/Stock-Market-Dataset/main/hist_india_vix_-01-01-{yr}-to-31-12-{yr}.csv"
  try:
    payload=urllib.request.urlopen(urllib.request.Request(vurl,headers={"User-Agent":"Mozilla/5.0"}),timeout=30).read()
    expected_vix={2024:"9c9b6a2e6e261fff81d2738cd1a98162921d059d589beee3bbd284b70b7a2aae",2025:"ffc7cce46a8b81c4d242bb03e1afd81698574803b17b58918810b41426c0fe6c"}
    assert hashlib.sha256(payload).hexdigest()==expected_vix[yr], "India VIX mirror changed SHA256"
    (root/f"vix_{yr}.csv").write_bytes(payload)
    print("VIX",yr,len(payload),hashlib.sha256(payload).hexdigest(),payload[:90])
  except Exception as e:print("VIX FAILED",yr,repr(e))
