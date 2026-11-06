#!/usr/bin/env python3
"""AEGIS v0.1 – historical NIFTY option-candle strategy experiment.

This is NOT a bid/ask or fill-verified backtest. Trades use observed 1-minute
OPENs with conservative modelled spreads and explicit fees. No order-book data.
Rules fixed ex ante; 2026 data is held-out out-of-sample.
"""
from __future__ import annotations
import argparse,datetime as dt,json,math,os,pathlib,statistics,sys
import numpy as np
import pandas as pd
import duckdb

START=dt.date(2024,10,1)
END=dt.date(2026,4,30)  # public NIFTY 5-minute index reference ends around Apr 2026
COMMISSION_PER_ORDER=20.0
EXCH_RATE=0.0003503
GST_RATE=0.18
STAMP_BUY_RATE=0.00003
SEBI_RATE=0.000001
SLIP_PCT=float(os.environ.get("AEGIS_SLIP_PCT", "0.0075"))    # per side of option candle open
SLIP_FLOOR=float(os.environ.get("AEGIS_SLIP_FLOOR", "0.75"))    # option index points, each leg, each side
CAPITAL=5_000_000.0
RISK_CAP_PER_TRADE=0.01*CAPITAL
MODES={"A":{"take":0.40,"stop":0.35,"days":2},
       "B_UP":{"take":0.40,"stop":0.40,"days":2},
       "B_DN":{"take":0.40,"stop":0.40,"days":2},
       "C":{"take":0.40,"stop":0.45,"days":2},
       "BENCH_STRADDLE":{"take":999,"stop":999,"days":2}}

def lot_size(trade_date, expiry):
    # Exclude transitional expiry dates in late 2024 to avoid guessing sizes
    if dt.date(2024,11,20)<=trade_date<=dt.date(2024,12,31):
        return None
    if trade_date < dt.date(2025,1,1):
        return 25
    if trade_date < dt.date(2026,1,1):
        return 75
    return 65

def adverse(mid,side):  # side +1 = buy, -1 = sell
    s=max(SLIP_FLOOR, abs(mid)*SLIP_PCT)
    return max(0.05, mid+side*s)

def fees(trade_date,qty,legs,entries,exits):
    # STT charged on executed option sales, not buys.
    stt=0.0015 if trade_date>=dt.date(2026,4,1) else 0.0010
    brokerage=COMMISSION_PER_ORDER*len(legs)*2
    turnover=0.0; sells=0.0; buys=0.0
    for (typ,strike,sgn),p0,p1 in zip(legs,entries,exits):
        entry_cash=p0*qty; exit_cash=p1*qty
        turnover+=entry_cash+exit_cash
        if sgn==1:
            buys+=entry_cash; sells+=exit_cash
        else:
            sells+=entry_cash; buys+=exit_cash
    exchange=turnover*EXCH_RATE
    sebi=turnover*SEBI_RATE
    gst=GST_RATE*(brokerage+exchange+sebi)
    stamp=buys*STAMP_BUY_RATE
    return dict(brokerage=brokerage,stt=sells*stt,exchange=exchange,sebi=sebi,gst=gst,stamp=stamp,total=brokerage+sells*stt+exchange+sebi+gst+stamp)

def load_market_context(root):
    spot=pd.read_csv(root/"NIFTY_5min_5yr_2021_2026.csv",parse_dates=["timestamp"])
    spot=spot[(spot.timestamp.dt.date>=START)&(spot.timestamp.dt.date<=END)].copy()
    spot["d"]=spot.timestamp.dt.date
    spot["hm"]=spot.timestamp.dt.strftime("%H:%M")
    spot=spot[(spot.hm>="09:15")&(spot.hm<="15:30")].sort_values("timestamp")
    daily=spot.groupby("d").agg(open=("open","first"),high=("high","max"),
        low=("low","min"),close=("close","last"),candles=("close","size")).reset_index()
    daily=daily.sort_values("d").reset_index(drop=True)
    daily["prev_close"]=daily.close.shift(1)
    daily["ret"]=daily.close.pct_change()
    daily["ret5"]=daily.close.pct_change(5)
    daily["ret3"]=daily.close.pct_change(3)
    daily["maxabs5"]=daily.ret.abs().shift(1).rolling(5).max()
    daily["meanabs2"]=daily.ret.abs().shift(1).rolling(2).mean()
    daily["retvol20"]=daily.ret.shift(1).rolling(20).std()*np.sqrt(252)*100
    daily["rng5"]=(daily.high.shift(1).rolling(5).max()-daily.low.shift(1).rolling(5).min())/daily.close.shift(1)
    vix={}
    for year in [2024,2025]:
        f=root/f"vix_{year}.csv"
        if not f.exists():continue
        vi=pd.read_csv(f,encoding="utf-8-sig")
        vi.columns=[str(x).strip().lower().replace(".","") for x in vi.columns]
        if "date" not in vi.columns or "close" not in vi.columns:continue
        for _,row in vi.iterrows():
            try:vix[dt.datetime.strptime(row["date"].strip(),"%d-%b-%Y").date()]=float(row["close"])
            except Exception: pass
    return spot,daily,vix

def signals(spot,daily):
    result=[]
    for i in range(21,len(daily)):
        row=daily.iloc[i]; d=row.d
        if d>END or d<START:continue
        if row.candles<68: continue  # reject incomplete regular-session spot data
        bars=spot[spot.d==d].set_index("hm")
        if not all(x in bars.index for x in ("09:15","09:40","09:55","10:00")):continue
        opening=bars.loc[(bars.index>="09:15") & (bars.index<="09:40")]
        orb_hi=opening.high.max();orb_lo=opening.low.min()
        last=bars.loc["10:00"];prev=bars.loc["09:55"]
        spot0=float(last["close"])
        mom3=float(daily.iloc[i-1].ret3) if pd.notna(daily.iloc[i-1].ret3) else 0
        direction=None
        if (last["close"]>orb_hi and prev["close"]>orb_hi and
            last["close"]>bars.loc["09:15"]["open"]*1.002 and mom3>0):
            direction="B_UP"
        elif (last["close"]<orb_lo and prev["close"]<orb_lo and
              last["close"]<bars.loc["09:15"]["open"]*0.998 and mom3<0):
            direction="B_DN"
        if direction: mode=direction
        elif d.weekday() in (0,1) and row.maxabs5>=0.012 and row.retvol20>=10:
            mode="A"
        elif d.weekday()==2 and row.meanabs2<0.004 and row.rng5>0.019:
            mode="C"
        else:mode=None
        result.append({"d":d,"spot":spot0,"mode":mode,"realized_vol":float(row.retvol20),
            "prior_day_ret":float(daily.iloc[i-1].ret) if pd.notna(daily.iloc[i-1].ret) else None,
            "opening_gap":float(row.open/row.prev_close-1) if row.prev_close else None,
            "next_day_gap":float(daily.iloc[i+1].open/row.close-1) if i+1<len(daily) else None})
    return result

def load_quotes(path,spot,daily,year):
    # Load only minute bars we can potentially trade; restrict strikes using same
    # day's PRIOR session CLOSE so the selection does not use information after 10:05.
    spotdays=daily[daily.d.map(lambda x:x.year==year)].copy()
    spotdays["date"]=spotdays.d.astype(str)
    spotdays["reference_spot"]=spotdays.prev_close.fillna(spotdays.open)
    con=duckdb.connect(database=":memory:")
    con.execute("SET TimeZone='Asia/Kolkata'")
    con.execute("SET memory_limit='4GB'")
    con.register("spot_ref",spotdays[["date","reference_spot"]])
    parquet=str(path).replace("'","''")
    sql=f"""
    CREATE TABLE q AS
    SELECT CAST(o.date AS DATE) AS d, CAST(o.expiry AS DATE) AS exp,
      CAST(o.strike AS INTEGER) AS k, o.option_type AS typ,
      strftime(o.timestamp,'%Y-%m-%d %H:%M:%S') AS ts,
      strftime(o.timestamp,'%H:%M') AS hm,
      CAST(o.open AS DOUBLE) AS px, CAST(o.volume AS DOUBLE) AS vol
    FROM read_parquet('{parquet}') o
    JOIN spot_ref s ON o.date=s.date
    WHERE TRY_CAST(o.expiry AS DATE)>CAST(o.date AS DATE)+INTERVAL 2 DAY
      AND TRY_CAST(o.expiry AS DATE)<=CAST(o.date AS DATE)+INTERVAL 16 DAY
      AND ABS(o.strike-s.reference_spot)<=1400
      AND EXTRACT(HOUR FROM o.timestamp) BETWEEN 9 AND 15
      AND EXTRACT(MINUTE FROM o.timestamp) IN (6,16,21,36,46,51)
      AND CAST(o.open AS DOUBLE)>0
      AND COALESCE(CAST(o.volume AS DOUBLE),0)>0
    """
    con.execute(sql)
    con.execute("CREATE INDEX date_expiry ON q(d,exp)")
    count=con.execute("SELECT COUNT(*) FROM q").fetchone()[0]
    print("QUOTE_SAMPLE",year,count,flush=True)
    return con,count

def structure(mode,atm):
    if mode in ("A","BENCH_STRADDLE"):
        return [("CE",atm,1),("PE",atm,1)]
    if mode=="B_UP":
        return [("CE",atm,1),("CE",atm+350,-1)]
    if mode=="B_DN":
        return [("PE",atm,1),("PE",atm-350,-1)]
    if mode=="C":
        return [("PE",atm-200,1),("PE",atm-500,-1),
                ("CE",atm+200,1),("CE",atm+500,-1)]
    raise ValueError(mode)

def run_one(con,candidates,days,year,benchmark=False):
    trades=[];skips=[];busy_until=dt.date(2000,1,1)
    available_days=sorted(d for d in days if d.year==year)
    for c in candidates:
        d=c["d"]
        if d.year!=year:continue
        mode="BENCH_STRADDLE" if benchmark else c["mode"]
        if benchmark and d.weekday()!=0:continue
        if not mode:continue
        if d<=busy_until: continue
        atm=int(math.floor((c["spot"]+25)/50)*50)
        expiries=con.execute("""
          SELECT DISTINCT exp FROM q
          WHERE d=? AND hm='10:06' AND k BETWEEN ? AND ?
          AND DATE_DIFF('day',d,exp) BETWEEN 3 AND 13 ORDER BY exp
          """,[d,atm-550,atm+550]).fetchall()
        expiries=[r[0] for r in expiries if 4 <= (r[0]-d).days <=13]
        if not expiries:
            skips.append({"date":str(d),"mode":mode,"reason":"no_eligible_expiry"});continue
        exp=expiries[0]
        lots=lot_size(d,exp)
        if lots is None:
            skips.append({"date":str(d),"mode":mode,"reason":"transitional_2024_lot_size_excluded"});continue
        legs=structure(mode,atm)
        maxhold=MODES[mode]["days"]
        if d not in available_days:continue
        di=available_days.index(d)
        end=available_days[min(di+maxhold,len(available_days)-1)]
        # Must exit strictly before expiry to avoid settlement & exercise tax assumptions.
        if end>=exp:
            prev=[z for z in available_days if d<=z<exp]
            if len(prev)==0:continue
            end=prev[-1]
        params=[d,end,exp]
        strikes=sorted(set(k for typ,k,sgn in legs))
        marks=con.execute(f"""SELECT d,ts,hm,k,typ,px
            FROM q WHERE d>=? AND d<=? AND exp=?
            AND k IN ({','.join('?'*len(strikes))}) ORDER BY ts""",
            params+strikes).fetchall()
        at={}
        for date,ts,hm,k,typ,px in marks:
            key=(str(ts),str(date))
            at.setdefault(key,{})[(typ,int(k))]=float(px)
        entries=[(ts,dic) for (ts,z),dic in at.items() if z==str(d) and ts.endswith("10:06:00")]
        if len(entries)!=1:
            skips.append({"date":str(d),"mode":mode,"reason":"missing_10_06_quote"});continue
        entrykey,entryq=entries[0]
        if not all((t,k) in entryq for t,k,s in legs):
            skips.append({"date":str(d),"mode":mode,"reason":"missing_entry_leg"});continue
        entmid=[entryq[(t,k)] for t,k,s in legs]
        ent=[adverse(m,s) for m,(_,__,s) in zip(entmid,legs)]
        initial_debit=sum(s*p for (_,__,s),p in zip(legs,ent))
        if initial_debit<=0.05 or initial_debit*lots>RISK_CAP_PER_TRADE:
            skips.append({"date":str(d),"mode":mode,"reason":"bad_or_oversized_debit",
                          "debit_rupees":round(initial_debit*lots,2)});continue
        exitkey=None;exitq=None;gross=0
        eligible=[]
        for (ts,z),q in sorted(at.items(),key=lambda x:x[0][0]):
            trade_day=dt.date.fromisoformat(z)
            if (trade_day==d and ts<=entrykey) or trade_day>end:continue
            if not all((t,k) in q for t,k,s in legs):continue
            grossmark=sum(s*q[(t,k)] for t,k,s in legs)
            ret=(grossmark-initial_debit)/initial_debit
            eligible.append((ts,q,ret))
        if not eligible:
            skips.append({"date":str(d),"mode":mode,"reason":"missing_exit_quote"});continue
        take=MODES[mode]["take"];stop=MODES[mode]["stop"]
        exitkey,exitq,ret=eligible[-1];reason="time_limit"
        for ts,q,r in eligible:
            if r>=take:
                exitkey,exitq,ret=ts,q,r;reason="profit_target";break
            if r<=-stop:
                exitkey,exitq,ret=ts,q,r;reason="stop_mark";break
        exitmid=[exitq[(t,k)] for t,k,s in legs]
        exits=[adverse(m,-s) for m,(_,__,s) in zip(exitmid,legs)]
        gross_pnl=lots*sum(s*(out-en) for (_,__,s),en,out in zip(legs,ent,exits))
        charged=fees(d,lots,legs,ent,exits)
        net=gross_pnl-charged["total"]
        trade={**c,"date":str(d),"expiry":str(exp),"exit_timestamp":exitkey,
           "mode":mode,"exit_reason":reason,"atm":atm,"legs":str(legs),
           "lot_size":lots,"entry_debit_points":initial_debit,"entry_debit_rs":round(lots*initial_debit,2),
           "exit_value_points":round(sum(s*p for (_,__,s),p in zip(legs,exits)),3),
           "gross_pnl_rs":round(gross_pnl,2),"charges_rs":round(charged["total"],2),
           "net_pnl_rs":round(net,2),"return_on_debit":round(net/(initial_debit*lots),6),
           "brokerage_rs":round(charged["brokerage"],2),"stt_rs":round(charged["stt"],2),
           "exchange_rs":round(charged["exchange"],2),"gst_rs":round(charged["gst"],2),
           "slippage_policy":f"{SLIP_PCT:.3%} open or {SLIP_FLOOR:.2f} pts per leg per side whichever higher"}
        trades.append(trade)
        busy_until=dt.datetime.strptime(exitkey[:10],"%Y-%m-%d").date()
    return trades,skips

def summarize(trades):
    if not trades:return {"n":0,"net_pnl_rs":0,"win_rate":None,"expectancy_rs":None,"profit_factor":None,"max_drawdown_rs":None}
    vals=np.array([x["net_pnl_rs"] for x in trades])
    eq=vals.cumsum()
    drawdown=np.maximum.accumulate(np.concatenate([[0],eq]))[1:]-eq
    gains=vals[vals>0].sum(); losses=abs(vals[vals<0].sum())
    sortedvals=np.sort(vals)
    tailn=max(1,math.ceil(.05*len(vals)))
    return {"n":int(len(vals)),"net_pnl_rs":round(float(vals.sum()),2),
      "win_rate":round(float(np.mean(vals>0)),4),
      "expectancy_rs":round(float(vals.mean()),2),
      "median_trade_rs":round(float(np.median(vals)),2),
      "profit_factor":round(float(gains/losses),4) if losses else None,
      "max_drawdown_rs":round(float(drawdown.max()),2),
      "worst_trade_rs":round(float(vals.min()),2),
      "cvar_worst_5pct_rs":round(float(sortedvals[:tailn].mean()),2),
      "net_on_50L_capital_pct":round(float(vals.sum()/CAPITAL*100),4),
      "gross_profit_rs":round(float(gains),2),
      "gross_loss_rs":round(float(losses),2)}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--year",required=True,type=int,choices=[2024,2025,2026])
    p.add_argument("--parquet",required=True)
    p.add_argument("--support",required=True)
    p.add_argument("--out",default="AEGIS_BACKTEST")
    a=p.parse_args()
    support=pathlib.Path(a.support)
    spot,daily,vix=load_market_context(support)
    cs=signals(spot,daily)
    for c in cs:
        # Critically, prior available VIX close only; no same-day future info.
        prior=[(date,number) for date,number in vix.items() if date<c["d"]]
        latest=max(prior) if prior else None
        c["vix_prior"]=latest[1] if latest and (c["d"]-latest[0]).days<=7 else None
        c["vix_regime"]="high" if c["vix_prior"] is not None and c["vix_prior"]>=20 else ("normal" if c["vix_prior"] is not None else "unknown")
    db,nq=load_quotes(a.parquet,spot,daily,a.year)
    days=list(daily.d)
    aegis,skips=run_one(db,cs,days,a.year)
    baseline,bskips=run_one(db,cs,days,a.year,benchmark=True)
    out=pathlib.Path(a.out);out.mkdir(exist_ok=True,parents=True)
    pd.DataFrame(aegis).to_csv(out/f"trades_{a.year}.csv",index=False)
    pd.DataFrame(baseline).to_csv(out/f"baseline_{a.year}.csv",index=False)
    pd.DataFrame(skips).to_csv(out/f"skips_{a.year}.csv",index=False)
    pd.DataFrame(cs).query("d.dt.year == @a.year") if False else None
    dates=[c for c in cs if c["d"].year==a.year]
    stats={"year":a.year,"range":[str(min(x["d"] for x in dates)),str(max(x["d"] for x in dates))],
      "spot_sessions":len(dates),"quote_sample_rows":nq,
      "aegis":summarize(aegis),"baseline_fixed_monday_straddle":summarize(baseline),
      "aegis_by_mode":{m:summarize([x for x in aegis if x["mode"]==m]) for m in ("A","B_UP","B_DN","C")},
      "aegis_vix_regime":{k:summarize([x for x in aegis if x["vix_regime"]==k]) for k in ("high","normal","unknown")},
      "aegis_gap_next_session_big":summarize([x for x in aegis if x.get("next_day_gap") is not None and abs(x["next_day_gap"])>=.0075]),
      "skips":pd.DataFrame(skips).reason.value_counts().to_dict() if skips else {},
      "source":"NIFTY traded 1m option OHLC, 5m cash index, 2024-25 prior-day VIX",
      "model":f"one lot, {SLIP_PCT:.3%} premium or {SLIP_FLOOR:.2f} pt each execution leg, 20 rupees commission/leg/order, estimated taxes; no bid/ask",
      "lookahead":"Signal at 10:05, enter using 10:06 1-minute OPEN, 15m open-price monitoring; not an orderbook simulation",
      "held_out":a.year==2026,"limitations":["No real bid/ask or historical intraday futures","2026 VIX source missing","NIFTY index spot reference ends Apr 2026","2024 Nov20-Dec31 excluded due contract-size transition","no genuine intraminute stop execution"]}
    (out/f"summary_{a.year}.json").write_text(json.dumps(stats,indent=2,default=str))
    print("AEGIS_RESULT",json.dumps(stats,default=str),flush=True)

if __name__=="__main__":main()
