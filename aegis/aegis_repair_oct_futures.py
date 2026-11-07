#!/usr/bin/env python3
"""AEGIS: targeted 28-30 Oct 2026 NIFTY futures gap repair.

STANDALONE Python 3.10+ standard library; no external packages.
- Reads only the existing 4.59 MB AEGIS_Upstox_Active_Patch.zip (NOT the 95 MB ZIP).
- Extracts the *same* historical Nov-2026 NIFTY FUT instrument key from its
  local contract sidecar. No instrument rediscovery or options API calls.
- GETs only the three missing 2026-10-28/29/30 market-data dates.
- Uses one-month-compatible V3 1-minute historical candles, tries per-day
  V3 if necessary, then V2 historical 1-minute as a documented fallback.
- Preserves every existing options CSV + metadata and the original ZIP.
- Creates AEGIS_Upstox_Active_Patch_Repaired.zip and a token-free report.
- Requires a PRIVATE Upstox Analytics Token entered locally. NEVER stores,
  prints, exports or commits any token. No order or account endpoint.

Run locally from the same folder containing AEGIS_Upstox_Active_Patch.zip:
  python aegis_repair_oct_futures.py --self-test
  python aegis_repair_oct_futures.py
"""
from __future__ import annotations

import argparse
import collections
import csv
import datetime as dt
import getpass
import hashlib
import io
import json
from pathlib import Path
import time
import socket
import ssl
import urllib.request
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen
import zipfile

BASE_URL = "https://api.upstox.com"
OLD_ZIP = "AEGIS_Upstox_Active_Patch.zip"
NEW_ZIP = "AEGIS_Upstox_Active_Patch_Repaired.zip"
REPORT_FILE = "AEGIS_oct_futures_repair_report.json"
IST_OFFSET = dt.timedelta(hours=5, minutes=30)
COLUMNS = ("timestamp","open","high","low","close","volume","oi")
NEEDED = (dt.date(2026,10,28),dt.date(2026,10,29),dt.date(2026,10,30))
DAYS = (*NEEDED,dt.date(2026,11,2),dt.date(2026,11,3),dt.date(2026,11,4),dt.date(2026,11,5))
DAY_BARS = 385  # trading-session minute-bar starts from 09:15 through 15:39 inclusive.

def safe_error(error):
    """Redact server URLs, proxy credentials and token; retain failure category."""
    reason = error.reason if isinstance(error, URLError) else error
    result = {"error_class":type(error).__name__, "reason_class":type(reason).__name__}
    for key in ("errno", "winerror"):
        value=getattr(reason,key,None)
        if isinstance(value,int):
            result[key]=value
    if isinstance(reason,ssl.SSLError):
        code=getattr(reason,"reason",None)
        if isinstance(code,str) and code.replace("_","").isalnum():
            result["ssl_reason"]=code
    return result

class NetworkFailure(RuntimeError):
    def __init__(self,detail):
        self.detail=detail
        super().__init__("History connection unavailable ("+
                         detail["reason_class"]+
                         (", code "+str(detail.get("winerror") or detail.get("errno"))
                            if detail.get("winerror") or detail.get("errno") else "")+")")

def connection_probe():
    """One unauthenticated HTTPS request, no local proxy addresses or credentials logged."""
    report={"host":"api.upstox.com","token_used":False,
            "proxy_environment_present":bool(urllib.request.getproxies()),
            "https":"unknown","checked_at_utc":dt.datetime.now(dt.timezone.utc).isoformat()}
    request=Request(BASE_URL+"/v2/swagger-ui/index.html",method="GET",
        headers={"User-Agent":"AEGIS-Network-Diagnostic/1.0","Accept":"text/html"})
    try:
        with urlopen(request,timeout=12) as response:
            report["https"]="reachable"
            report["http_status"]=int(response.status)
    except HTTPError as error:
        # Any real HTTP status confirms DNS+TCP+TLS/HTTPS success, even 404/403.
        report["https"]="reachable"
        report["http_status"]=int(error.code)
    except (URLError,TimeoutError,OSError) as error:
        report["https"]="unreachable"
        report["error"]=safe_error(error)
    if report["https"]!="reachable":
        try:
            socket.getaddrinfo("api.upstox.com",443,type=socket.SOCK_STREAM)
            report["dns"]="resolved"
        except OSError as error:
            report["dns"]="failed"
            report["dns_error"]=safe_error(error)
        try:
            with socket.create_connection(("api.upstox.com",443),timeout=5) as raw:
                with ssl.create_default_context().wrap_socket(raw,server_hostname="api.upstox.com") as secured:
                    report["direct_tls"]="success" if secured.version() else "unknown"
        except (OSError,ssl.SSLError) as error:
            report["direct_tls"]="failed"
            report["direct_tls_error"]=safe_error(error)
    return report

def digest(content):
    return hashlib.sha256(content).hexdigest()

def parse_stamp(value):
    ts=dt.datetime.fromisoformat(str(value))
    if ts.utcoffset()!=IST_OFFSET:
        raise ValueError("Invalid trading timestamp timezone")
    return ts

def valid_bar(vals, day=None):
    if len(vals)<6:
        return False
    try:
        ts=parse_stamp(vals[0])
        if day is not None and ts.date()!=day:
            return False
        if ts.date() not in DAYS:
            return False
        t=ts.time().replace(tzinfo=None)
        if not dt.time(9,15)<=t<=dt.time(15,39):
            return False
        if ts.second!=0 or ts.microsecond!=0:
            return False
        o,h,l,c=[float(v) for v in vals[1:5]]
        return o>0 and l>0 and c>0 and h>=max(o,l,c) and l<=min(o,c,h)
    except (ValueError,TypeError,IndexError):
        return False

def count_by_day(rows):
    totals=collections.Counter()
    minutes=collections.defaultdict(set)
    for stamp,r in rows.items():
        x=parse_stamp(stamp)
        totals[x.date()]+=1
        minutes[x.date()].add(x.strftime("%H:%M"))
    return {d.isoformat():{"bars":totals[d],"unique_minutes":len(minutes[d])} for d in DAYS}

def read_source_zip(path):
    if not path.is_file():
        raise FileNotFoundError(f"Cannot find {path}. Keep existing ZIP in the same folder.")
    with zipfile.ZipFile(path) as z:
        names=set(z.namelist())
        pairs=[x for x in names if "/futures/" in x.replace("\\","/")
               and x.lower().endswith(".json") and not x.endswith("manifest.json")]
        if len(pairs)!=1:
            raise ValueError(f"Expected exactly one November future sidecar, found {len(pairs)}")
        meta_name=pairs[0]
        csv_name=meta_name[:-5]+".csv"
        if csv_name not in names:
            raise ValueError("Missing futures contract CSV")
        meta=json.loads(z.read(meta_name))
        raw=z.read(csv_name)
        if digest(raw)!=meta.get("sha256_csv"):
            raise ValueError("Existing futures CSV SHA-256 failed; original ZIP untouched")
        if meta.get("instrument_type")!="FUT" or str(meta.get("expiry"))!="2026-11-23":
            raise ValueError("Unexpected futures contract identity: abort, no guessed replacement")
        key=meta.get("instrument_key")
        if not isinstance(key,str) or not key.startswith("NSE_FO|"):
            raise ValueError("Missing valid NSE_FO instrument key")
        records={}
        with io.StringIO(raw.decode("utf-8-sig"),newline="") as inp:
            reader=csv.DictReader(inp)
            if tuple(reader.fieldnames or [])!=COLUMNS:
                raise ValueError("Unexpected futures CSV schema")
            for row in reader:
                v=[row.get(c) for c in COLUMNS]
                if not valid_bar(v):
                    raise ValueError("Invalid existing futures candle; refusing to patch data")
                if v[0] in records:
                    raise ValueError("Duplicated futures timestamp in source ZIP")
                records[v[0]]=v
        if len(records)!=int(meta.get("rows",-1)):
            raise ValueError("Sidecar futures row-count mismatch")
        manifests=[x for x in names if x.endswith("/AEGIS_active_patch_manifest.json")]
        manifest_name=manifests[0] if len(manifests)==1 else None
        return {"csv_name":csv_name,"meta_name":meta_name,"manifest_name":manifest_name,
                "meta":meta,"key":key,"records":records}

class ReadOnlyHistory:
    def __init__(self,token):
        self._token=token
        self.request_count=0
        self.delay=1.25
        self.last=0.0

    def fetch(self,path):
        if not ((path.startswith("/v3/historical-candle/") and "/minutes/1/" in path)
                or (path.startswith("/v2/historical-candle/") and "/1minute/" in path)):
            raise ValueError("Non-historical or unsupported market-data endpoint blocked")
        for attempt in range(4):
            elapsed=time.monotonic()-self.last
            if elapsed<self.delay:
                time.sleep(self.delay-elapsed)
            self.last=time.monotonic()
            req=Request(BASE_URL+path,method="GET",headers={
                "Authorization":"Bearer "+self._token,"Accept":"application/json",
                "User-Agent":"AEGIS-Oct-Futures-Repair/1.0"})
            try:
                self.request_count+=1
                with urlopen(req,timeout=75) as result:
                    body=json.loads(result.read().decode("utf-8"))
                data=body.get("data",{})
                if body.get("status")=="error" or not isinstance(data,dict) or not isinstance(data.get("candles"),list):
                    raise RuntimeError("Upstox historical candle response invalid")
                return data["candles"]
            except HTTPError as e:
                if e.code in (429,500,502,503,504) and attempt<3:
                    time.sleep(2**attempt * 3)
                    continue
                raise RuntimeError("Upstox historical endpoint HTTP "+str(e.code)) from None
            except (URLError,TimeoutError,OSError) as error:
                detail=safe_error(error)
                # A DNS/TLS/proxy error is almost never solved by changing the
                # trading DATE or by retrying 7 different API paths 28 times.
                if attempt<1:
                    time.sleep(2)
                    continue
                raise NetworkFailure(detail) from None
        raise RuntimeError("Upstox request retry limit reached")

    def candles(self,key,first,last,version=3):
        if not isinstance(key,str) or not key.startswith("NSE_FO|"):
            raise ValueError("Only the NSE futures market instrument is allowed")
        enc=quote(key,safe="")
        if version==3:
            path=f"/v3/historical-candle/{enc}/minutes/1/{last}/{first}"
        elif version==2:
            path=f"/v2/historical-candle/{enc}/1minute/{last}/{first}"
        else:
            raise ValueError("Unsupported API version")
        return self.fetch(path)

def encode_csv(rows):
    buffer=io.StringIO(newline="")
    writer=csv.writer(buffer)
    writer.writerow(COLUMNS)
    for key in sorted(rows):
        writer.writerow(rows[key])
    return buffer.getvalue().encode("utf-8")

def repair(client,source_path,output_path,report_path):
    if source_path.resolve()==output_path.resolve():
        raise ValueError("Output ZIP must not overwrite original ZIP")
    info=read_source_zip(source_path)
    merged=dict(info["records"])
    initial=count_by_day(merged)
    report={"task":"AEGIS NIFTY November 2026 future 1-minute Oct28-Oct30 gap repair",
            "input":source_path.name,"output":output_path.name,"status":"incomplete",
            "original_rows":len(merged),"source_futures_expiry":info["meta"]["expiry"],
            "required_dates":[str(x) for x in DAYS],
            "target_missing_dates":[str(x) for x in NEEDED],
            "before":initial,"retrievals":[],"rejected_rows":0,
            "token_saved":False,"account_or_trading_endpoints_called":False}
    # Start with one efficient request. V3 documentation permits <=1 month.
    target_missing=[d for d in NEEDED if initial[str(d)]["bars"]!=DAY_BARS]
    if not target_missing:
        report["retrievals"].append({"note":"All required missing dates are already present"})
    else:
        queries=[(3,min(target_missing),max(target_missing),"v3-range")]
        queries += [(3,d,d,"v3-single") for d in target_missing]
        queries += [(2,d,d,"v2-single-fallback") for d in target_missing]
        for version,start,end,label in queries:
            unresolved=[d for d in NEEDED if len([1 for ts in merged if ts.startswith(d.isoformat())])<DAY_BARS]
            if not unresolved:
                break
            if start==end and start not in unresolved:
                continue
            try:
                rows=client.candles(info["key"],start,end,version=version)
                nvalid=0
                for row in rows:
                    if not valid_bar(row):
                        report["rejected_rows"]+=1
                        continue
                    d=parse_stamp(row[0]).date()
                    if d in NEEDED:
                        merged[str(row[0])]=list(row[:7])+[None]*max(0,7-len(row))
                        nvalid+=1
                report["retrievals"].append({"endpoint":label,"first":str(start),
                    "last":str(end),"returned":len(rows),"matching_rows":nvalid})
            except NetworkFailure as e:
                report["retrievals"].append({"endpoint":label,"first":str(start),
                    "last":str(end),"network_error":e.detail})
                report["network_blocked"]=True
                break
            except RuntimeError as e:
                report["retrievals"].append({"endpoint":label,"first":str(start),
                    "last":str(end),"error":str(e)})
    after=count_by_day(merged)
    report["after"]=after
    report["rows_after"]=len(merged)
    report["rows_recovered"]=len(merged)-len(info["records"])
    report["api_requests"]=getattr(client,"request_count",0)
    report["unresolved_dates"]=[str(d) for d in DAYS if after[str(d)]["bars"]!=DAY_BARS
      or after[str(d)]["unique_minutes"]!=DAY_BARS]
    report["status"]="complete" if not report["unresolved_dates"] else "incomplete"
    if len(merged) < len(info["records"]):
        raise AssertionError("Future records unexpectedly lost")
    if not all(key in merged and merged[key]==value for key,value in info["records"].items()):  # old ticks unchanged
        raise AssertionError("Some prior market candles changed")
    # Preserve prior 285 options and all original raw files, except FUT csv+sidecar and manifest.
    raw=encode_csv(merged)
    meta={**info["meta"],"rows":len(merged),
         "first":min(merged),"last":max(merged),
         "sha256_csv":digest(raw),
         "gap_repair_status":report["status"],
         "gap_repair_new_rows":report["rows_recovered"]}
    replacements={info["csv_name"]:raw,
        info["meta_name"]:json.dumps(meta,indent=2).encode("utf-8")}
    if info["manifest_name"]:
        with zipfile.ZipFile(source_path) as z:
            manifest=json.loads(z.read(info["manifest_name"]))
        manifest["futures_gap_repair"]={k:report[k] for k in (
            "status","before","after","unresolved_dates","rows_recovered","api_requests")}
        replacements[info["manifest_name"]]=json.dumps(manifest,indent=2).encode("utf-8")
    # Always publish a token-free diagnostic report independently, even for partial API responses.
    report_path.write_text(json.dumps(report,indent=2),encoding="utf-8")
    if report["status"]=="complete":
        tmp=output_path.with_suffix(".tmp")
        with zipfile.ZipFile(source_path) as zin, zipfile.ZipFile(tmp,"w") as zout:
            for item in zin.infolist():
                zout.writestr(item,replacements.get(item.filename,zin.read(item.filename)))
            # Place extra report in a known suffix, not in any futures directory.
            root=info["csv_name"].split("/futures/")[0]
            zout.writestr(root+"/AEGIS_oct_futures_repair_report.json",json.dumps(report,indent=2))
        tmp.replace(output_path)
        # Final archive/sidecar self-verification.
        verified=read_source_zip(output_path)
        if len(verified["records"])!=len(merged):
            raise AssertionError("Repacked market ZIP failed verification")
    print("AEGIS_FUTURES_GAP_REPAIR",json.dumps({
        "status":report["status"],"before":report["before"],
        "after":report["after"],"new_rows":report["rows_recovered"],
        "unresolved_dates":report["unresolved_dates"],
        "api_requests":report["api_requests"],
        "output":output_path.name if report["status"]=="complete" else None,
        "diagnostic_report":report_path.name},indent=2),flush=True)
    return report

def self_test():
    import tempfile
    with tempfile.TemporaryDirectory() as folder:
        root=Path(folder)
        csv_path="AEGIS_Upstox_Active_Patch/futures/2026-11-23/FUT_FUT_test.csv"
        old={}
        def candles_for(day):
            for j in range(DAY_BARS):
                t=dt.datetime.combine(day,dt.time(9,15),dt.timezone(IST_OFFSET))+dt.timedelta(minutes=j)
                ts=t.isoformat()
                old[ts]=[ts,100,101,99,100.5,100,20]
        for d in DAYS[3:]:
            candles_for(d)
        orig=encode_csv(old)
        meta={"expiry":"2026-11-23","instrument_type":"FUT",
            "instrument_key":"NSE_FO|FAKE_PUBLIC_TEST","lot_size":65,
            "sha256_csv":digest(orig),"rows":len(old)}
        old_path=root/OLD_ZIP
        with zipfile.ZipFile(old_path,"w") as z:
            z.writestr(csv_path,orig)
            z.writestr(csv_path[:-4]+".json",json.dumps(meta))
            z.writestr("AEGIS_Upstox_Active_Patch/options/2026-11-09/sample.csv","dummy,content\n")
            z.writestr("AEGIS_Upstox_Active_Patch/AEGIS_active_patch_manifest.json",
                json.dumps({"downloaded_contracts":2,"errors":[]}))
        class Fake:
            request_count=0
            def candles(self,key,first,last,version=3):
                self.request_count+=1
                data=[]
                for d in NEEDED:
                    if first<=d<=last:
                        for j in range(DAY_BARS):
                            t=dt.datetime.combine(d,dt.time(9,15),dt.timezone(IST_OFFSET))+dt.timedelta(minutes=j)
                            data.append([t.isoformat(),100,101,99,100.5,100,20])
                return data
        result=repair(Fake(),old_path,root/NEW_ZIP,root/REPORT_FILE)
        assert result["status"]=="complete",result
        assert result["rows_recovered"]==3*385,result
        assert safe_error(URLError(socket.gaierror(-2,"test")))["reason_class"]=="gaierror"
        assert safe_error(TimeoutError())["reason_class"]=="TimeoutError"
        with zipfile.ZipFile(root/NEW_ZIP) as z:
            assert z.read("AEGIS_Upstox_Active_Patch/options/2026-11-09/sample.csv")==b"dummy,content\n"
        with zipfile.ZipFile(old_path) as z:
            assert z.read(csv_path)==orig
    print("SELF_TEST_PASSED: Oct28-30 accepted; prior futures and options preserved; token never requested")

def main():
    p=argparse.ArgumentParser(description="Fix exactly three missing Oct2026 NIFTY future 1-minute sessions")
    p.add_argument("--archive",default=OLD_ZIP)
    p.add_argument("--out",default=NEW_ZIP)
    p.add_argument("--report",default=REPORT_FILE)
    p.add_argument("--self-test",action="store_true")
    p.add_argument("--diagnose",action="store_true",
        help="One unauthenticated HTTPS connectivity check; NO token requested")
    args=p.parse_args()
    if args.self_test:
        self_test()
        return
    if args.diagnose:
        diagnosis=connection_probe()
        Path("AEGIS_upstox_connectivity_diagnostic.json").write_text(
            json.dumps(diagnosis,indent=2),encoding="utf-8")
        print("AEGIS_CONNECTION_DIAGNOSTIC",json.dumps(diagnosis,indent=2),flush=True)
        if diagnosis["https"]!="reachable":
            raise SystemExit("Upstox HTTPS is not reachable; no token requested or candle API calls made")
        print("HTTPS transport reachable; this does not prove historical data API eligibility.")
        return
    preflight=connection_probe()
    if preflight["https"]!="reachable":
        Path("AEGIS_upstox_connectivity_diagnostic.json").write_text(
            json.dumps(preflight,indent=2),encoding="utf-8")
        print("AEGIS_CONNECTION_DIAGNOSTIC",json.dumps(preflight,indent=2))
        raise SystemExit("Preflight connection failed; no token requested and no data requests attempted")
    token=getpass.getpass("Read-only Upstox Analytics Token (hidden, never saved): ").strip()
    if not token:
        raise SystemExit("Missing private read-only token")
    client=ReadOnlyHistory(token)
    outcome=repair(client,Path(args.archive),Path(args.out),Path(args.report))
    if outcome["status"]!="complete":
        raise SystemExit("Not complete: share only the token-free AEGIS_oct_futures_repair_report.json")
    print("REPAIR_COMPLETE: Upload only "+args.out+" to your existing AEGIS Drive folder.")

if __name__=="__main__":
    main()
