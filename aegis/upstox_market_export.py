#!/usr/bin/env python3
"""AEGIS: read-only Upstox historical NIFTY index/expired derivatives exporter.

The Analytics Token is entered via getpass and is NEVER saved in files.
All network calls are HTTP GET to https://api.upstox.com and only to:
  /v3/historical-candle/...
  /v2/expired-instruments/expiries
  /v2/expired-instruments/option/contract
  /v2/expired-instruments/future/contract
  /v2/expired-instruments/historical-candle/...
This program NEVER requests any portfolio, account, positions or order endpoints.

Usage (install Python 3.10+):
  python aegis/upstox_market_export.py probe
  python aegis/upstox_market_export.py export --start 2026-07-22 --end 2026-11-05 --max-contracts 12
  python aegis/upstox_market_export.py export --start 2026-07-22 --end 2026-11-05 --max-contracts 0

Full export may make many requests. Resumes already verified contract CSVs.
The numerical strike filter limits coverage to near-the-money option contracts.
No real bid/ask or depth is returned by candle APIs.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import getpass
import hashlib
import json
import math
import os
from pathlib import Path
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

HOST="https://api.upstox.com"
UNDERLYING="NSE_INDEX|Nifty 50"
VIX="NSE_INDEX|India VIX"
FIELDS=("timestamp","open","high","low","close","volume","oi")
MAX_VALID_DATE=dt.date.today()
ALLOWED_PREFIXES=(
 "/v3/historical-candle/",
 "/v2/expired-instruments/expiries",
 "/v2/expired-instruments/option/contract",
 "/v2/expired-instruments/future/contract",
 "/v2/expired-instruments/historical-candle/",
 "/v2/option/contract",
 "/v2/instruments/search",
)

def parse_date(text):
    return dt.date.fromisoformat(str(text))

def safe_name(text):
    return "".join(x if x.isalnum() or x in "-_." else "_" for x in str(text))[:130]

def date_windows(first,last,days=7):
    if last<first:return
    day=first
    while day<=last:
        end=min(last,day+dt.timedelta(days=days-1))
        yield day,end
        day=end+dt.timedelta(days=1)

def store_json(path, data):
    path.parent.mkdir(exist_ok=True,parents=True)
    tmp=path.with_suffix(path.suffix+".tmp")
    tmp.write_text(json.dumps(data,indent=2,default=str),encoding="utf-8")
    tmp.replace(path)

def put_candles(path,rows):
    if not rows:return
    path.parent.mkdir(exist_ok=True,parents=True)
    tmp=path.with_suffix(path.suffix+".tmp")
    with tmp.open("w",newline="",encoding="utf-8") as f:
        writer=csv.writer(f)
        writer.writerow(FIELDS)
        writer.writerows(rows)
    tmp.replace(path)

# Date-effective NSE market-session regime references:
#   NSE/FAOP/74467 (29-May-2026), effective 03-Aug-2026.
#   SEBI HO/47/11/11(3)2025-MRD-POD2/I/23843/2026 (15-Oct-2026)
#   effective 07-Dec-2026 (some unrelated provisions effective 08-Feb-2027).
#   https://www.nseindia.com/static/products-services/closing-auction-session
# October 2026 announcement is NOT retroactive for October trading days.
CAS_FO_START=dt.date(2026,8,3)
CAS_NEXT_PHASE=dt.date(2026,12,7)
IST_OFFSET=dt.timedelta(hours=5, minutes=30)

def session_last_minute(trade_date, *, expiry_date=None, segment="INDEX_FO"):
    """Last allowed one-minute candle OPEN for a regular NSE session.

    NSE NIFTY index F&O:
      pre-Aug03: 09:15–15:29 inclusive (close at 15:30).
      Aug03–Dec06: 09:15–15:39 inclusive (close at 15:40).
      from Dec07: 09:15–15:44 inclusive (close at 15:45);
        on expiry day expiring index contracts close at 15:30.
    This does NOT describe the cash-equity CAS auction or NIFTY spot index
    publication cadence, and special trading sessions must be added separately.
    """
    d=trade_date if isinstance(trade_date,dt.date) else dt.date.fromisoformat(str(trade_date))
    e=(expiry_date if isinstance(expiry_date,dt.date) else
       (dt.date.fromisoformat(str(expiry_date)) if expiry_date else None))
    if segment not in ("INDEX_FO","STOCK_FO"):
        raise ValueError("Unsupported session segment")
    if d<CAS_FO_START:
        return dt.time(15,29)
    if d<CAS_NEXT_PHASE:
        return dt.time(15,39)
    if segment=="INDEX_FO" and e is not None and d==e:
        return dt.time(15,29)
    return dt.time(15,44)

def regular_session_bar(timestamp, *, expiry_date=None, segment="INDEX_FO"):
    """Session-aware F&O candle check; does not discard raw data."""
    try:
        t=dt.datetime.fromisoformat(str(timestamp))
        if t.tzinfo is None or t.utcoffset()!=IST_OFFSET:
            return False
        d=t.date()
        cutoff=session_last_minute(d, expiry_date=expiry_date,segment=segment)
        return dt.time(9,15)<=t.timetz().replace(tzinfo=None)<=cutoff
    except (TypeError,ValueError):
        return False

def valid_cached_contract(path, meta):
    """Resume only when both file and a matching sha256 manifest are present."""
    if not path.is_file() or not meta.is_file():return False
    try:
        info=json.loads(meta.read_text(encoding="utf-8"))
        if not info.get("sha256_csv"):return False
        return hashlib.sha256(path.read_bytes()).hexdigest()==info["sha256_csv"]
    except (OSError,ValueError,KeyError):
        return False

def convert(rows):
    data=[]
    for raw in rows or []:
        if not isinstance(raw,list) or len(raw)<6:continue
        data.append(list(raw[:7])+([None] if len(raw)==6 else []))
    return data

class ReadOnlyClient:
    def __init__(self,token,min_delay=1.25):
        self.token=token
        self.last=0.0
        self.delay=max(1.1,float(min_delay))
        self.request_count=0

    def get(self,path,params=None):
        if not any(path.startswith(prefix) for prefix in ALLOWED_PREFIXES):
            raise ValueError("Blocked: this is not an approved historical market-data endpoint")
        query=("?"+urlencode(params)) if params else ""
        url=HOST+path+query
        for attempt in range(5):
            elapsed=time.monotonic()-self.last
            if elapsed<self.delay:time.sleep(self.delay-elapsed)
            self.last=time.monotonic()
            req=Request(url,headers={
                "Authorization":"Bearer "+self.token,
                "Accept":"application/json",
                "User-Agent":"AEGIS-HistoricalData/1.0"
            },method="GET")
            try:
                with urlopen(req,timeout=80) as res:
                    payload=json.loads(res.read().decode("utf-8"))
                self.request_count+=1
                if payload.get("status")=="error":
                    codes=[e.get("error_code") for e in payload.get("errors",[]) if isinstance(e,dict)]
                    raise RuntimeError("API returned error codes "+str(codes))
                return payload.get("data")
            except HTTPError as e:
                # Do not print raw response body or anything with account details.
                self.request_count+=1
                if e.code in (429,500,502,503,504) and attempt<4:
                    time.sleep(3*2**attempt)
                    continue
                raise RuntimeError(f"Market data GET returned HTTP {e.code}") from None
            except (URLError,TimeoutError) as e:
                if attempt<4:time.sleep(2**attempt+1);continue
                raise RuntimeError("Market data endpoint temporarily unreachable") from None
        raise RuntimeError("Exhausted GET retry budget")

    def active_options(self):
        """Discover currently listed NIFTY option contracts (no account endpoints)."""
        x=self.get("/v2/option/contract",{"instrument_key":UNDERLYING})
        if not isinstance(x,list):raise ValueError("Unexpected active option contract response")
        return x

    def current_nifty_futures(self):
        """Find listed NSE NIFTY futures through Upstox's read-only search."""
        results=[]
        for page in range(1,6):
            x=self.get("/v2/instruments/search",{
                "query":"NIFTY FUT","exchanges":"NSE","segments":"FO",
                "expiry":"current_month","page_number":page,"records":30})
            if not isinstance(x,list):raise ValueError("Unexpected instrument search response")
            results += [r for r in x
               if r.get("instrument_type")=="FUT"
               and r.get("segment")=="NSE_FO"
               and (r.get("underlying_key")==UNDERLYING
                    or r.get("underlying_symbol")=="NIFTY"
                    or r.get("trading_symbol","").startswith("NIFTY FUT"))]
            if len(x)<30:break
        # Deduplicate keys returned by the search pages.
        return list({r["instrument_key"]:r for r in results if r.get("instrument_key")}.values())

    def active_candles(self,key,first,last):
        """Standard historical V3; usable for currently listed derivative keys."""
        return self.index_candles(key,first,last)

    def expiries(self):
        x=self.get("/v2/expired-instruments/expiries",{"instrument_key":UNDERLYING})
        if not isinstance(x,list):raise ValueError("Unexpected expiry list structure")
        return sorted(set(parse_date(a) for a in x))

    def contracts(self,typ,expiry):
        if typ not in ("option","future"):raise ValueError("invalid contract type")
        x=self.get(f"/v2/expired-instruments/{typ}/contract",{
            "instrument_key":UNDERLYING,"expiry_date":expiry.isoformat()})
        return x if isinstance(x,list) else []

    def expired_candles(self,key,first,last):
        path="/v2/expired-instruments/historical-candle/"+quote(key,safe="")+"/1minute/"+last.isoformat()+"/"+first.isoformat()
        x=self.get(path)
        if not isinstance(x,dict) or "candles" not in x:
            raise ValueError("Unexpected expired-candle data structure")
        return convert(x["candles"])

    def index_candles(self,key,first,last):
        path="/v3/historical-candle/"+quote(key,safe="")+"/minutes/1/"+last.isoformat()+"/"+first.isoformat()
        x=self.get(path)
        if not isinstance(x,dict) or "candles" not in x:
            raise ValueError("Unexpected index-candle data structure")
        return convert(x["candles"])

def get_key(contract):
    return contract.get("expired_instrument_key") or contract.get("instrument_key") or ""

def get_strike(contract):
    try:return float(contract["strike_price"])
    except (ValueError,KeyError,TypeError):return None

def last_spot_from_index(client,expiry):
    start=expiry-dt.timedelta(days=7)
    bars=client.index_candles(UNDERLYING,start,expiry)
    # API often returns newest candles first; last valid chronologically.
    closes=sorted((str(r[0]),float(r[4])) for r in bars if r[4] is not None)
    return closes[-1][1] if closes else None

def probe(client,out,expiry):
    expiries=client.expiries()
    if expiry not in expiries:
        available=[str(x) for x in expiries if x<MAX_VALID_DATE]
        raise RuntimeError(f"Requested expiry {expiry} missing from API. Last available: {available[-8:]}")
    spot=last_spot_from_index(client,expiry)
    opts=client.contracts("option",expiry)
    futs=client.contracts("future",expiry)
    results={"mode":"probe","expiry":str(expiry),"spot_reference":spot,
        "contracts_seen":{"option":len(opts),"future":len(futs)},
        "expired_candles":[],"api_request_count":0}
    if not opts:raise RuntimeError("No expired option contracts returned")
    # Find up to two valid call/put contracts closest to observed spot.
    by_type={}
    for o in opts:
        t=o.get("instrument_type")
        k=get_strike(o)
        if t in ("CE","PE") and k is not None and get_key(o):
            by_type.setdefault(t,[]).append(o)
    selected=[]
    for typ in ("CE","PE"):
        group=by_type.get(typ,[])
        if group:
            ref=spot if spot is not None else sorted(get_strike(o) for o in group)[len(group)//2]
            selected.append(min(group,key=lambda o:abs(get_strike(o)-ref)))
    if futs:selected.append(futs[0])
    for contract in selected:
        kind=contract.get("instrument_type","?")
        key=get_key(contract)
        first=expiry-dt.timedelta(days=6)
        try:
            rows=client.expired_candles(key,first,expiry)
            status="success" if rows else "empty"
            samples={"earliest":min(str(x[0]) for x in rows),"latest":max(str(x[0]) for x in rows)} if rows else {}
            results["expired_candles"].append({
                "kind":kind,"strike":get_strike(contract),"status":status,
                "bars":len(rows),"lot_size":contract.get("lot_size"),
                "regular_session_bars":sum(regular_session_bar(x[0],expiry_date=expiry) for x in rows),
                "out_of_session_bars":sum(not regular_session_bar(x[0],expiry_date=expiry) for x in rows),
                **samples})
        except Exception as e:
            results["expired_candles"].append({"kind":kind,"strike":get_strike(contract),"status":"error","message":str(e)})
    results["api_request_count"]=client.request_count
    store_json(out/"AEGIS_upstox_expired_candle_probe.json",results)
    print(json.dumps(results,indent=2))
    print("Saved token-free report:",out/"AEGIS_upstox_expired_candle_probe.json")

def historical_indices(client,out,first,last):
    spots={}
    for key,name in ((UNDERLYING,"NIFTY50"),(VIX,"INDIA_VIX")):
        for a,b in date_windows(first,last,days=21):
            path=out/"indices"/name/f"{a}_{b}.csv"
            if path.exists() and path.stat().st_size>30:
                with path.open(newline="",encoding="utf-8") as f:
                    rows=[r for r in csv.DictReader(f)]
                    if name=="NIFTY50":
                        for r in rows:
                            try:spots.setdefault(str(r["timestamp"])[:10],[]).append(float(r["close"]))
                            except (ValueError,KeyError):pass
                continue
            rows=client.index_candles(key,a,b)
            if rows:
                put_candles(path,rows)
                if name=="NIFTY50":
                    for r in rows:
                        try:spots.setdefault(str(r[0])[:10],[]).append(float(r[4]))
                        except (ValueError,TypeError):pass
            print(name,a,b,"bars",len(rows),flush=True)
    return spots

def export(client,out,first,last,max_contracts,wing,lookback):
    if last>=MAX_VALID_DATE:
        # Avoid future or partial current-session output.
        last=min(last,MAX_VALID_DATE-dt.timedelta(days=1))
    if last<first:raise ValueError("end date precedes start date")
    spots=historical_indices(client,out,first,last)
    expiries=[x for x in client.expiries() if first<=x<=last]
    summary={"mode":"export","start":str(first),"end":str(last),
        "note":"Historical market candles only. No bid/ask, account or trading data.",
        "expiries_available":[str(x) for x in expiries],
        "downloaded_contract_files":0,"skipped_existing":0,"empty_contracts":0,
        "errors":[],"limits":{"wing_points":wing,"lookback_days":lookback,
           "max_contracts":max_contracts},"api_request_count":0}
    stored=0
    for expiry in expiries:
        options=client.contracts("option",expiry)
        futures=client.contracts("future",expiry)
        span_first=max(first,expiry-dt.timedelta(days=lookback))
        prices=[v for day,values in spots.items()
            if span_first<=parse_date(day)<=expiry for v in values]
        if prices:
            low=min(prices)-wing
            high=max(prices)+wing
        else:
            # No index reference = do not silently discard strikes.
            low=-float("inf");high=float("inf")
            print("WARNING: Missing spot reference for",expiry,": no strike filter",flush=True)
        # Fetch futures first so small pilot exports always validate this data class.
        selected=[x for x in futures if get_key(x)]
        selected+= [o for o in options if get_key(o) and get_strike(o) is not None and
             low<=get_strike(o)<=high and o.get("instrument_type") in ("CE","PE")]
        print("EXPIRY",expiry,"candidate contracts",len(selected),flush=True)
        for obj in selected:
            typ=obj.get("instrument_type","")
            strike=get_strike(obj)
            key=get_key(obj)
            if not key:continue
            kname=(safe_name(strike) if strike is not None else "FUT")+"_"+safe_name(typ)+"_"+hashlib.sha256(key.encode()).hexdigest()[:12]
            path=out/("options" if typ in ("CE","PE") else "futures")/str(expiry)/(kname+".csv")
            # Metadata contains public contract attributes only, not private user data.
            meta=path.with_suffix(".json")
            if valid_cached_contract(path,meta):
                summary["skipped_existing"]+=1
                continue
            if max_contracts and stored>=max_contracts:
                print("Contract limit reached",max_contracts,flush=True)
                summary["contract_limit_reached"]=True
                break
            contract_first=max(first,expiry-dt.timedelta(days=lookback if typ in ("CE","PE") else 45))
            allrows=[]
            try:
                for a,b in date_windows(contract_first,min(expiry,last),days=7):
                    allrows+=client.expired_candles(key,a,b)
                # De-duplicate timestamp within one contract and sort ascending.
                unique={str(r[0]):r for r in allrows}
                data=[unique[k] for k in sorted(unique)]
                if data:
                    put_candles(path,data)
                    store_json(meta,{"expiry":str(expiry),"instrument_type":typ,
                        "strike_price":strike,"lot_size":obj.get("lot_size"),
                        "instrument_key":key,"trading_symbol":obj.get("trading_symbol"),
                        "rows":len(data),"first":str(data[0][0]),"last":str(data[-1][0]),
                        "regular_session_rows":sum(regular_session_bar(x[0],expiry_date=expiry) for x in data),
                        "out_of_session_rows":sum(not regular_session_bar(x[0],expiry_date=expiry) for x in data),
                        "note":"Raw Upstox candles retained. Trading simulator must exclude timestamps outside normal NSE session.",
                        "sha256_csv":hashlib.sha256(path.read_bytes()).hexdigest()})
                    summary["downloaded_contract_files"]+=1
                    print("DOWNLOADED",str(expiry),typ,strike,"bars",len(data),flush=True)
                else:
                    summary["empty_contracts"]+=1
                    print("EMPTY",str(expiry),typ,strike,flush=True)
                stored+=1
            except Exception as e:
                summary["errors"].append({"expiry":str(expiry),"type":typ,
                     "strike":strike,"message":str(e)})
                print("ERROR",expiry,typ,strike,str(e),flush=True)
            finally:
                summary["api_request_count"]=client.request_count
                store_json(out/"AEGIS_upstox_export_manifest.json",summary)
        if max_contracts and stored>=max_contracts:break
    store_json(out/"AEGIS_upstox_export_manifest.json",summary)
    print("FINISHED",json.dumps({k:v for k,v in summary.items() if k!="expiries_available"},indent=2))

def main():
    p=argparse.ArgumentParser(description="Secure, market-only Upstox AEGIS historical exporter")
    p.add_argument("mode",choices=("probe","export"))
    p.add_argument("--expiry",default="2026-10-27",help="Probe expiry YYYY-MM-DD")
    p.add_argument("--start",default="2026-07-22",help="Export start")
    p.add_argument("--end",default="2026-11-05",help="Export end")
    p.add_argument("--out",default="AEGIS_Upstox_Export")
    p.add_argument("--max-contracts",type=int,default=12,
        help="Max option/futures contracts for export; 0 = all, potentially thousands")
    p.add_argument("--wing",type=int,default=1200,help="Extra points around spot range for option strikes")
    p.add_argument("--lookback",type=int,default=21,help="Option-contract days of history before expiry")
    args=p.parse_args()
    token=getpass.getpass("Upstox READ-ONLY Analytics Token (hidden, never saved): ").strip()
    if not token:raise SystemExit("No token supplied")
    client=ReadOnlyClient(token)
    out=Path(args.out);out.mkdir(exist_ok=True,parents=True)
    if args.mode=="probe":
        probe(client,out,parse_date(args.expiry))
    else:
        export(client,out,parse_date(args.start),parse_date(args.end),
               args.max_contracts,args.wing,args.lookback)
    print("Never upload your Analytics Token. Export folder contains market data only.")

if __name__=="__main__":main()
