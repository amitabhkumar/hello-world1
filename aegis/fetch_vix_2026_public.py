#!/usr/bin/env python3
"""Collect and verify public, token-free Upstox India VIX 1m 2026 history.

No account or order API; no user's token. Only GET /v3/historical-candle.
Creates historical daily VIX close aligned to NSE trading sessions from Jan1
to Nov5 2026, for use in prior-DAY-only AEGIS regime diagnostics.
VIX is NOT a strategy selection input in current AEGIS v0.1.
"""
from __future__ import annotations
import collections,csv,datetime as dt,hashlib,json,pathlib,urllib.request
from urllib.parse import quote

START=dt.date(2026,1,1)
END=dt.date(2026,11,5)
KEY="NSE_INDEX|India VIX"
IST=dt.timedelta(hours=5,minutes=30)
def expected(dt0):
    return dt.time(9,15)<=dt0.time().replace(tzinfo=None)<=dt.time(15,29)
def valid_bar(bar):
    if not isinstance(bar,list) or len(bar)<5:return False
    try:
        stamp=dt.datetime.fromisoformat(bar[0])
        o,h,l,c=[float(x) for x in bar[1:5]]
        return stamp.utcoffset()==IST and expected(stamp) and \
                o>0 and c>0 and h>=max(o,l,c) and l>0 and l<=min(o,h,c)
    except (TypeError,ValueError):
        return False
def fetch_period(first,last):
    url=("https://api.upstox.com/v3/historical-candle/"+quote(KEY,safe="")
        +"/minutes/1/"+last.isoformat()+"/"+first.isoformat())
    req=urllib.request.Request(url,method="GET",headers={
        "Accept":"application/json","User-Agent":"AEGIS-public-VIX-validation/1.0"})
    with urllib.request.urlopen(req,timeout=90) as response:
        raw=response.read()
        result=json.loads(raw)
    if result.get("status")!="success" or not isinstance(result.get("data",{}).get("candles"),list):
        raise RuntimeError(f"Unexpected India VIX response for {first} to {last}")
    return result["data"]["candles"],hashlib.sha256(raw).hexdigest()
def run(out):
    out.mkdir(parents=True,exist_ok=True)
    overall={};month_checks=[];anomalies=[]
    for month in range(1,12):
        first=max(START,dt.date(2026,month,1))
        last=min(END,dt.date(2026,month+1,1)-dt.timedelta(days=1) if month<12 else END)
        bars,h=fetch_period(first,last)
        ok=0
        for bar in bars:
            if not valid_bar(bar):
                if len(anomalies)<10:anomalies.append({"month":month,"timestamp":str(bar[0])[:25]})
                continue
            stamp=dt.datetime.fromisoformat(bar[0])
            day=stamp.date()
            if not first<=day<=last:
                if len(anomalies)<10:anomalies.append({"month":month,"outside":str(day)})
                continue
            key=stamp.isoformat()
            if key in overall:raise ValueError("Repeated VIX timestamp across month boundaries")
            overall[key]=bar
            ok+=1
        month_checks.append({"month":month,"range":[str(first),str(last)],"returned":len(bars),
                             "valid":ok,"response_sha256":h})
        print("AEGIS_VIX_2026_PERIOD",month,"returned",len(bars),"valid",ok,flush=True)
    dates=collections.defaultdict(list)
    for ts,bar in overall.items():
        stamp=dt.datetime.fromisoformat(ts)
        dates[stamp.date()].append((stamp,float(bar[4])))
    rows=[];counts={}
    for d,points in sorted(dates.items()):
        points=sorted(points)
        counts[str(d)]=len(points)
        rows.append({"date":d.strftime("%d-%b-%Y").upper(),"close":points[-1][1],
             "market_date":str(d),"bars":len(points),"last_candle":points[-1][0].isoformat()})
    if not rows:raise RuntimeError("No valid 2026 India VIX history")
    if anomalies:raise RuntimeError("Invalid VIX candle/period data present: "+str(anomalies[:3]))
    with (out/"vix_2026.csv").open("w",newline="",encoding="utf-8") as f:
        writer=csv.DictWriter(f,fieldnames=["date","close","market_date","bars","last_candle"])
        writer.writeheader();writer.writerows(rows)
    result={
       "status":"public_upstox_vix_2026_1min_verified",
       "instrument":KEY,
       "window":[str(START),str(END)],
       "first_session":min(counts),"last_session":max(counts),
       "valid_minute_records":len(overall),
       "distinct_sessions":len(counts),
       "daily_bars_distribution":dict(sorted(collections.Counter(counts.values()).items())),
       "non375_sessions":{k:v for k,v in counts.items() if v!=375},
       "month_checks":month_checks,
       "anomalies":anomalies,
       "token_used":False,
       "future_lookahead_in_source":False,
       "method":"Use latest CLOSE of date D as historical VIX available to strategy on date D+1; never current-day future value"}
    (out/"AEGIS_VIX_2026_DATA_QUALITY.json").write_text(json.dumps(result,indent=2))
    print("AEGIS_VIX_2026_COMPLETED",json.dumps({k:result[k] for k in (
         "status","valid_minute_records","distinct_sessions","first_session","last_session",
         "non375_sessions","token_used")},indent=2),flush=True)
def main():
    import argparse
    p=argparse.ArgumentParser()
    p.add_argument("--out",default="AEGIS_VIX_2026_COMPLETE")
    a=p.parse_args()
    run(pathlib.Path(a.out))
if __name__=="__main__":main()
