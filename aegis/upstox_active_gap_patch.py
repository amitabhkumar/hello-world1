#!/usr/bin/env python3
"""Targeted, fully read-only Upstox November 2026 active-contract gap patch.

Requires the user's PRIVATE Analytics Token only on user's computer.
Reads NO portfolio, positions, funds or orders.
Saves only market OHLCV, OI, expiry/strike/lot metadata.
Does NOT repeat the previous 95MB expired-contract export.

Usage:
  python aegis/upstox_active_gap_patch.py
  python aegis/upstox_active_gap_patch.py --limit 4  # pilot
  python aegis/upstox_active_gap_patch.py --limit 0  # all selected market contracts

Only fetches option expiry 2026-11-06 to 2026-11-19 and
futures current November expiry. Data windows Nov02-Nov05 options and
Oct28-Nov05 futures. The user controls the token; never share token.
"""
from __future__ import annotations
import argparse,csv,datetime as dt,getpass,hashlib,json,pathlib,zipfile,os
try:
    from aegis.upstox_market_export import ReadOnlyClient,UNDERLYING,date_windows,\
      get_key,get_strike,put_candles,store_json,valid_cached_contract,regular_session_bar
except ModuleNotFoundError:
    from upstox_market_export import ReadOnlyClient,UNDERLYING,date_windows,\
      get_key,get_strike,put_candles,store_json,valid_cached_contract,regular_session_bar

FIRST_OPTIONS=dt.date(2026,11,2)
FIRST_FUTURES=dt.date(2026,10,28)
LAST=dt.date(2026,11,5)
def select_contracts(client,wing):
    opts=[x for x in client.active_options()
          if dt.date(2026,11,6)<=dt.date.fromisoformat(str(x.get("expiry","1900-01-01")))<=dt.date(2026,11,19)
          and x.get("instrument_type") in ("CE","PE") and x.get("instrument_key")
          and x.get("segment")=="NSE_FO"
          and (x.get("underlying_key")==UNDERLYING or x.get("underlying_symbol")=="NIFTY")]
    spot=client.index_candles(UNDERLYING,FIRST_OPTIONS,LAST)
    prices=[float(x[4]) for x in spot if len(x)>=5 and float(x[4])>0]
    if not prices:raise RuntimeError("No authenticated historical NIFTY index candles for Nov2-5; abort strike filtering")
    low=min(prices)-wing
    high=max(prices)+wing
    selected=[x for x in opts if get_strike(x) is not None and low<=get_strike(x)<=high]
    futures=[x for x in client.current_nifty_futures()
         if x.get("instrument_key") and dt.date.fromisoformat(str(x.get("expiry","1900-01-01")))>LAST]
    # Prefer earliest monthly active futures, not all future months.
    futures=sorted(futures,key=lambda x:x["expiry"])[:1]
    return sorted(selected,key=lambda x:(x["expiry"],float(x["strike_price"]),x["instrument_type"])),futures,{
        "NIFTY_spot_min":round(min(prices),2),
        "NIFTY_spot_max":round(max(prices),2),
        "strike_low":round(low,2),"strike_high":round(high,2)}
def run(client,out,limit=0,wing=1200):
    out.mkdir(parents=True,exist_ok=True)
    options,futures,spot_range=select_contracts(client,wing)
    manifest={"source":"Upstox current active contract + Historical Candle V3 read-only",
        "date_range":{"options":[str(FIRST_OPTIONS),str(LAST)],
                      "futures":[str(FIRST_FUTURES),str(LAST)]},
        "expiry_filter":["2026-11-06","2026-11-19"],"strike_selection":spot_range,
        "candidate_options":len(options),"candidate_futures":len(futures),
        "files_written":0,"files_reused":0,"empty":0,"errors":[],
        "token_saved":False,"portfolio_access":False,"order_access":False}
    selected=[("futures",x,FIRST_FUTURES) for x in futures]
    selected += [("options",x,FIRST_OPTIONS) for x in options]
    if not futures:
        manifest["warnings"]=["No active NIFTY future resolved: current-month instrument search may need manual specification"]
    processed=0
    for typ,contract,start in selected:
        if limit and processed>=limit:break
        key=contract["instrument_key"]
        expiry=dt.date.fromisoformat(str(contract["expiry"]))
        kind=contract.get("instrument_type","FUT")
        strike=get_strike(contract)
        ident=hashlib.sha256(key.encode()).hexdigest()[:12]
        name=(str(int(strike)) if strike is not None else "FUT")+"_"+kind+"_"+ident
        path=out/typ/str(expiry)/(name+".csv")
        meta=path.with_suffix(".json")
        if valid_cached_contract(path,meta):
            manifest["files_reused"]+=1
            continue
        processed+=1
        rows=[]
        try:
            for a,b in date_windows(start,LAST,days=7):
                rows += client.active_candles(key,a,b)
            rows={str(x[0]):x for x in rows if regular_session_bar(x[0],expiry_date=expiry)}
            data=[rows[t] for t in sorted(rows)]
            if not data:
                manifest["empty"]+=1
                print("EMPTY",typ,expiry,strike,flush=True)
                continue
            put_candles(path,data)
            store_json(meta,{"source":"upstox_historical_v3_active_1m",
                "expiry":str(expiry),"instrument_type":kind,"strike_price":strike,
                "lot_size":int(contract["lot_size"]),"instrument_key":key,
                "trading_symbol":contract.get("trading_symbol"),"rows":len(data),
                "first":str(data[0][0]),"last":str(data[-1][0]),
                "sha256_csv":hashlib.sha256(path.read_bytes()).hexdigest()})
            manifest["files_written"]+=1
            print("DOWNLOADED",typ,expiry,kind,strike,"bars",len(data),flush=True)
        except Exception as e:
            manifest["errors"].append({"kind":typ,"expiry":str(expiry),"strike":strike,"error_type":type(e).__name__,"message":str(e)})
            print("ERROR",typ,expiry,strike,str(e),flush=True)
        finally:
            manifest["api_requests"]=client.request_count
            store_json(out/"AEGIS_active_patch_manifest.json",manifest)
    manifest["contract_limit_reached"]=bool(limit and processed>=limit)
    manifest["api_requests"]=client.request_count
    store_json(out/"AEGIS_active_patch_manifest.json",manifest)
    bundle=out.parent/"AEGIS_Upstox_Active_Patch.zip"
    with zipfile.ZipFile(bundle,"w",zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for file in out.rglob("*"):
            if file.is_file() and file.suffix in (".csv",".json"):
                z.write(file,file.relative_to(out.parent))
    print("PATCH_FINISHED",json.dumps(manifest,indent=2))
    print("ARCHIVE",bundle,"BYTES",bundle.stat().st_size,flush=True)
def main():
    p=argparse.ArgumentParser()
    p.add_argument("--out",default="AEGIS_Upstox_Active_Patch")
    p.add_argument("--limit",type=int,default=0,help="0 means all selected contracts")
    p.add_argument("--wing",type=float,default=1200)
    a=p.parse_args()
    token=getpass.getpass("Read-only Upstox Analytics Token (hidden; never saved): ").strip()
    if not token:raise SystemExit("Missing token")
    client=ReadOnlyClient(token)
    run(client,pathlib.Path(a.out),limit=a.limit,wing=a.wing)
if __name__=="__main__":main()
