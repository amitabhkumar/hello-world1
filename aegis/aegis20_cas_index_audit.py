#!/usr/bin/env python3
"""AEGIS2.0 CAS-regime NIFTY index 1m observed daily range research.

2026 Jan1-Nov5 public Upstox V3, no token. Daily high/low is index
*reported* 1-minute OHLC, not guaranteed executable option/futures
market prices or actual auction indicative matched prices.
No claim CAS *causes* movements; cohorts are chronological attribution only.
"""
from __future__ import annotations
import collections,csv,datetime as dt,hashlib,json,pathlib,statistics,urllib.request
from urllib.parse import quote
import numpy as np

KEY="NSE_INDEX|Nifty 50"
START=dt.date(2026,1,1)
END=dt.date(2026,11,5)
CAS=dt.date(2026,8,3)
IST=dt.timedelta(hours=5,minutes=30)

def retrieve(first,last):
    url=("https://api.upstox.com/v3/historical-candle/"+
         quote(KEY,safe="")+"/minutes/1/"+str(last)+"/"+str(first))
    req=urllib.request.Request(url,headers={"Accept":"application/json",
      "User-Agent":"AEGIS20-Public-CAS-Movement-Research/1.0"},method="GET")
    with urllib.request.urlopen(req,timeout=90) as res:
        raw=res.read();body=json.loads(raw)
    bars=body.get("data",{}).get("candles")
    if body.get("status")!="success" or not isinstance(bars,list):
        raise RuntimeError("NIFTY V3 response status/shape invalid")
    return bars,hashlib.sha256(raw).hexdigest()

def summarize(rows):
    if not rows:return {"days":0}
    ranges=np.array([x["range_points"] for x in rows])
    return {"days":len(rows),
      "mean_range_points":round(float(ranges.mean()),1),
      "median_range_points":round(float(np.median(ranges)),1),
      "p90_range_points":round(float(np.quantile(ranges,.9)),1),
      "max_range_points":round(float(ranges.max()),1),
      "days_ge_500_points":int(np.sum(ranges>=500)),
      "days_ge_600_points":int(np.sum(ranges>=600)),
      "fraction_ge_500":round(float(np.mean(ranges>=500)),4),
      "fraction_ge_600":round(float(np.mean(ranges>=600)),4),
      "median_abs_open_close_points":round(float(np.median([abs(x["close_minus_open_points"]) for x in rows])),1)}

def run(out,vix_file=None):
    out=pathlib.Path(out);out.mkdir(parents=True,exist_ok=True)
    observed={};checks=[];invalid=0
    for month in range(1,12):
        first=max(START,dt.date(2026,month,1))
        last=min(END,dt.date(2026,month+1,1)-dt.timedelta(days=1) if month<12 else END)
        bars,digest=retrieve(first,last)
        valid=0
        for bar in bars:
            try:
                t=dt.datetime.fromisoformat(bar[0])
                if t.utcoffset()!=IST:raise ValueError("IST offset")
                if not first<=t.date()<=last:raise ValueError("out of period")
                if not dt.time(9,15)<=t.time().replace(tzinfo=None)<=dt.time(15,39):
                    raise ValueError("out of session")
                o,h,l,c=map(float,bar[1:5])
                if not 0<l<=min(o,c,h) or h<max(o,c,l):raise ValueError("OHLC")
                if t.isoformat() in observed:raise ValueError("duplicate minute")
                observed[t.isoformat()]=(t,o,h,l,c)
                valid+=1
            except (TypeError,ValueError,IndexError):
                invalid+=1
        checks.append({"month":month,"from":str(first),"to":str(last),
           "count":len(bars),"validated":valid,"response_sha256":digest})
        print("AEGIS20_NIFTY_INDEX_MONTH",month,"validated",valid,flush=True)
    if invalid:raise RuntimeError(f"NIFTY V3 invalid minute rows {invalid}")
    groups=collections.defaultdict(list)
    for t,o,h,l,c in observed.values():groups[t.date()].append((t,o,h,l,c))
    rows=[]
    for day,bars in sorted(groups.items()):
        bars=sorted(bars,key=lambda x:x[0])
        first,last=bars[0],bars[-1]
        h=max(x[2] for x in bars);l=min(x[3] for x in bars)
        row={"previous_session_vix":None,"previous_session_vix_date":None,
             "vix_regime":"unavailable",
             "date":str(day),"regime":"post_CAS_AugNov2026" if day>=CAS else "pre_CAS",
             "first_minute":first[0].strftime("%H:%M"),
             "last_minute":last[0].strftime("%H:%M"),
             "minute_rows":len(bars),
             "open":round(first[1],2),"high":round(h,2),
             "low":round(l,2),"close":round(last[4],2),
             "range_points":round(h-l,2),
             "close_minus_open_points":round(last[4]-first[1],2)}
        rows.append(row)
    if len(rows)<180:raise RuntimeError("Insufficient 2026 NIFTY minute sessions")
    prev_vix={}
    if vix_file is not None:
        with pathlib.Path(vix_file).open(newline="") as f:
            for x in csv.DictReader(f):
                prev_vix[dt.date.fromisoformat(x["market_date"])]=float(x["close"])
        days=sorted(prev_vix)
        for r in rows:
            date=dt.date.fromisoformat(r["date"])
            eligible=[d for d in days if d<date]
            if eligible and (date-eligible[-1]).days<=7:
                r["previous_session_vix"]=prev_vix[eligible[-1]]
                r["previous_session_vix_date"]=str(eligible[-1])
                r["vix_regime"]="vix_ge_20" if r["previous_session_vix"]>=20 else "vix_below_20"
            else:
                r["vix_regime"]="unavailable"
    result={"status":"verified_historical_reported_index_OHLC",
       "instrument":KEY,"source":"public Upstox one-minute index OHLC",
       "source_month_sha256":checks,"valid_minutes":len(observed),
       "distinct_sessions":len(rows),"invalid_rows":invalid,
       "pre_CAS_2026":summarize([r for r in rows if r["regime"]=="pre_CAS"]),
       "post_CAS_AugNov2026":summarize([r for r in rows if r["regime"]=="post_CAS_AugNov2026"]),
       "by_vix_regime":{reg:summarize([r for r in rows if r["vix_regime"]==reg])
                    for reg in ("vix_ge_20","vix_below_20","unavailable")} if vix_file else {},
       "critical_limitations":[
          "Index OHLC points are not executable option/futures fills or guaranteed executable CAS indicative prices",
          "Pre/post CAS difference is observational and confounded by simultaneous volatility regimes",
          "CAS revisions beginning 7 Dec 2026 have no observed market sessions as of Nov7 2026",
          "Stress-test 500–600-point swings as scenario rather than certainty"]}
    with (out/"AEGIS20_NIFTY_2026_DAILY_MOVEMENT.csv").open("w",newline="") as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0].keys()))
        writer.writeheader();writer.writerows(rows)
    (out/"AEGIS20_CAS_VOLATILITY_EVIDENCE.json").write_text(json.dumps(result,indent=2))
    print("AEGIS20_CAS_INDEX_EVIDENCE",json.dumps({
       "pre":result["pre_CAS_2026"],"post":result["post_CAS_AugNov2026"],
       "vix":result["by_vix_regime"],
       "verified_minutes":len(observed),"days":len(rows)}),flush=True)
def main():
    import argparse
    a=argparse.ArgumentParser()
    a.add_argument("--out",default="AEGIS20_CAS_INDEX")
    a.add_argument("--vix-file")
    args=a.parse_args()
    run(args.out,args.vix_file)
if __name__=="__main__":main()
