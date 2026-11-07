#!/usr/bin/env python3
"""AEGIS 2.0 candidate comparison: regime, India VIX, IV and per-leg Greeks/OI.

FROZEN exploratory candidate rules. NOT an optimized strategy or live system.
Inputs: 1m option OHLC+OI/volume, 5m spot, prior-day India VIX.
Data safety: 10:06 signal market option OPEN/OI observations can be used only
for execution >=10:16; 10:00 5m spot bar already complete before signal.
All legs must have actual 10:16 and 14:46 1m OPEN; no synthetic quotes.
No close auction matching or market impact, no actual bid/ask. Never short
unbounded options. Skip markets with absent IV/OI or missing any leg.
"""
from __future__ import annotations
import argparse,collections,datetime as dt,json,math,pathlib,statistics
import duckdb,numpy as np,pandas as pd,pyarrow.parquet as pq
from aegis.backtest_v01 import estimate_greeks,adverse,fees,lot_size
from aegis.exchange_rules import RESEARCH_START
from aegis.rolling_research_final import stats,uncertainty

CAPITAL=5000000.
MAX_POSITION_LOSS=12500.      # 0.25% x 50L
MAX_SESSION_LOSS=37500.       # 0.75% x 50L
MAX_DAILY_TRADES=1
SESSION_BARS=("10:06","10:16","14:46")
MIN_OPEN_INTEREST=5000
MIN_SIGNAL_VOLUME=1
MIN_ENTRY_VOLUME=1
END=dt.date(2026,11,5)
CAS_START=dt.date(2026,8,3)
DEC_CAS_CHANGE=dt.date(2026,12,7)
MODELS=("TREND_DEBIT","RANGE_CREDIT","VOL_EXPANSION")

def read_context(path,year):
    spotfile=path/"NIFTY_5min_2026_extended.csv" if year==2026 else path/"NIFTY_5min_5yr_2021_2026.csv"
    if not spotfile.exists():raise FileNotFoundError(spotfile)
    spot=pd.read_csv(spotfile,parse_dates=["timestamp"])
    spot=spot[(spot.timestamp.dt.year==year)&(spot.timestamp.dt.date<=END)].copy()
    spot["date"]=spot.timestamp.dt.date
    spot["hm"]=spot.timestamp.dt.strftime("%H:%M")
    spot=spot.sort_values("timestamp")
    day=spot.groupby("date").agg(
       dayopen=("open","first"), dayclose=("close","last"),
       dlow=("low","min"),dhigh=("high","max"),
       bars=("close","count")).reset_index()
    day["ret"]=day.dayclose.pct_change()
    day["rv10"]=day.ret.shift(1).rolling(10).std()*math.sqrt(252)*100
    day["last5_move"]=day.ret.abs().shift(1).rolling(5).mean()*100
    day["prevclose"]=day.dayclose.shift(1)
    # Session features: first 6 regular five-minute bars constitute 09:15–09:45.
    features={}
    prior_d=None
    for row in day.itertuples():
        d=row.date
        q=spot[spot.date==d]
        bars=q.set_index("hm")
        if (row.bars<68 or d<RESEARCH_START
            or not all(v in bars.index for v in ("09:15","09:40","09:55","10:00"))):
            prior_d=d;continue
        opening=bars[(bars.index>="09:15")&(bars.index<="09:40")]
        low=float(opening.low.min());hi=float(opening.high.max())
        spot_at_1005=float(bars.loc["10:00","close"])
        breakout=1 if (spot_at_1005>hi and float(bars.loc["09:55","close"])>hi) else \
                 -1 if (spot_at_1005<low and float(bars.loc["09:55","close"])<low) else 0
        mom=100*(spot_at_1005/float(row.dayopen)-1)
        features[d]={"date":str(d),"spot":spot_at_1005,
           "spot_close_prev":float(row.prevclose) if pd.notna(row.prevclose) else None,
           "open_move_pct":mom,
           "breakout":breakout,
           "rv10_pct":float(row.rv10) if pd.notna(row.rv10) else None,
           "prev_abs_change5_pct":float(row.last5_move) if pd.notna(row.last5_move) else None}
    vixfile=path/f"vix_{year}.csv"
    if not vixfile.exists():raise FileNotFoundError("VIX source missing: "+str(vixfile))
    vix=pd.read_csv(vixfile)
    vix.columns=[str(x).strip().lower() for x in vix.columns]
    if not set(("date","close")).issubset(vix.columns):raise ValueError("VIX missing date/close")
    daily={}
    for r in vix.itertuples():
        try:
            date=dt.datetime.strptime(str(r.date).strip(),"%d-%b-%Y").date()
            value=float(r.close)
            if value>0:daily[date]=value
        except (ValueError,TypeError):continue
    if not daily:raise ValueError("No valid prior session VIX observations")
    vixdays=sorted(daily)
    for d in features:
        past=[x for x in vixdays if x<d]
        latest=past[-1] if past else None
        if latest is None or (d-latest).days>7:continue
        past_values=[daily[x] for x in past[-21:]]
        features[d]["vix"]=daily[latest]
        features[d]["vix_prior_date"]=str(latest)
        features[d]["vix_percentile20"]=sum(x<=daily[latest] for x in past_values)/len(past_values)
        features[d]["vix_5session_move"]=daily[latest]-(past_values[-6] if len(past_values)>=6 else past_values[0])
    return features

def load_option_marks(paths,year,features):
    df=pd.DataFrame([{"date":str(day),"refspot":v["spot"]} for day,v in features.items()])
    if df.empty:raise ValueError("No 5m cash-index sessions")
    filelist=[str(p) for p in paths]
    cols=set()
    for f in filelist:
        if not pathlib.Path(f).is_file():raise FileNotFoundError(f)
        cols.update(pq.read_schema(f).names)
    oi="COALESCE(TRY_CAST(o.open_interest AS DOUBLE),TRY_CAST(o.oi AS DOUBLE))" \
        if "open_interest" in cols and "oi" in cols else (
        "TRY_CAST(o.open_interest AS DOUBLE)" if "open_interest" in cols else
        "TRY_CAST(o.oi AS DOUBLE)" if "oi" in cols else "NULL::DOUBLE")
    if oi=="NULL::DOUBLE":raise RuntimeError("No actual OI source; cannot backtest OI gates")
    db=duckdb.connect()
    db.execute("SET TimeZone='Asia/Kolkata'")
    db.execute("SET memory_limit='4GB'")
    db.register("spot_ref",df)
    ar="["+",".join("'"+p.replace("'","''")+"'" for p in filelist)+"]"
    q=f"""
      SELECT CAST(o.date AS DATE) AS date, CAST(o.expiry AS DATE) AS expiry,
        CAST(o.strike AS INTEGER) strike, o.option_type typ,
        strftime(o.timestamp,'%H:%M') as hm, 
        CAST(o.open AS DOUBLE) px,
        CAST(o.volume AS DOUBLE) volume, {oi} as oi
      FROM read_parquet({ar},union_by_name=true) o
      JOIN spot_ref s ON CAST(o.date AS VARCHAR)=s.date
      WHERE DATE_DIFF('day',CAST(o.date AS DATE),CAST(o.expiry AS DATE)) BETWEEN 4 AND 12
        AND abs(CAST(o.strike AS DOUBLE)-s.refspot)<=750
        AND strftime(o.timestamp,'%H:%M') IN ('10:06','10:16','14:46')
        AND CAST(o.open AS DOUBLE)>.05
        AND COALESCE(CAST(o.volume AS DOUBLE),0)>=0
    """
    result=db.execute(q).df()
    db.close()
    result["date"]=pd.to_datetime(result.date).dt.date
    result["expiry"]=pd.to_datetime(result.expiry).dt.date
    # Reject duplicate identical market timestamp/contract across archive overlaps.
    key=["date","expiry","strike","typ","hm"]
    dup=int(result.duplicated(key).sum())
    if dup:
        result=result.sort_values(key+["volume"],ascending=[True]*5+[False]).drop_duplicates(key,keep="first")
    return result,dup

def build_snapshot(q,spot):
    """Use only 10:06 known market inputs to create candidate legs."""
    signal=q[q.hm=="10:06"].copy()
    actual_entry=q[q.hm=="10:16"]
    actual_exit=q[q.hm=="14:46"]
    # Must never price a leg from another day/expiry or missing bar.
    entries={ (r.expiry,int(r.strike),r.typ):(float(r.px),float(r.volume)) for r in actual_entry.itertuples()}
    exits={ (r.expiry,int(r.strike),r.typ):(float(r.px),float(r.volume)) for r in actual_exit.itertuples()}
    candidates=[]
    for r in signal.itertuples():
        exp=r.expiry;d=r.date
        if r.volume<MIN_SIGNAL_VOLUME or not pd.notna(r.oi) or float(r.oi)<MIN_OPEN_INTEREST:
            continue
        key=(exp,int(r.strike),r.typ)
        if key not in entries or key not in exits:continue
        if entries[key][1]<MIN_ENTRY_VOLUME or exits[key][1]<1:continue
        iv=estimate_greeks(spot,float(r.strike),(exp-d).days,r.typ,float(r.px))
        if not iv or not .04<=iv["iv"]<=1.5:continue
        candidates.append({"exp":exp,"k":int(r.strike),"typ":r.typ,
             "oi":float(r.oi),"vol_signal":float(r.volume),
             "signal_price":float(r.px),"iv":iv["iv"],
             "delta":float(iv["delta"]),"gamma":float(iv["gamma"]),
             "theta":float(iv["theta_per_day"]), "vega":float(iv["vega_per_ivpt"]),
             "entry":float(entries[key][0]),"exit":float(exits[key][0]),
             "vol_entry":entries[key][1],"vol_exit":exits[key][1]})
    return candidates

def preferred_exp(candidates,d):
    grouped=collections.defaultdict(set)
    for c in candidates:grouped[c["exp"]].add(c["typ"])
    available=[x for x,types in grouped.items() if types=={"CE","PE"}]
    return min(available,key=lambda x:(abs((x-d).days-7),x)) if available else None

def pick(candidates,typ,target_delta,min_k=None,max_k=None):
    items=[x for x in candidates if x["typ"]==typ and
           (min_k is None or x["k"]>=min_k) and
           (max_k is None or x["k"]<=max_k)]
    return min(items,key=lambda x:(abs(x["delta"]-target_delta),-x["oi"])) if items else None

def family_legs(family,features,legs,expiry):
    vix=features.get("vix");rv=features.get("rv10_pct")
    if not vix or rv is None or not 5<=vix<=90 or not 3<=rv<=150:
        return None,"missing_or_unusable_vix_rv"
    cs=[x for x in legs if x["typ"]=="CE"]
    ps=[x for x in legs if x["typ"]=="PE"]
    if not cs or not ps:return None,"no_two_sided_option_chain"
    atm_call=pick(cs,"CE",.50)
    atm_put=pick(ps,"PE",-.50)
    if not atm_call or not atm_put:return None,"no_atm_greeks"
    atm_iv_pct=50*(atm_call["iv"]+atm_put["iv"])
    if not 6<=atm_iv_pct<=85:return None,"invalid_atm_iv"
    trend=features["breakout"]
    move=features["open_move_pct"]
    if family=="TREND_DEBIT":
        if trend==0 or abs(move)<.25 or vix>50:
            return None,"trend_not_confirmed"
        if trend==1:
            buy=pick(cs,"CE",.52)
            sell=pick(cs,"CE",.25,min_k=buy["k"]+50) if buy else None
            if not buy or not sell:return None,"missing_bull_delta_legs"
            sel=[(buy,1),(sell,-1)]
        else:
            buy=pick(ps,"PE",-.52)
            sell=pick(ps,"PE",-.25,max_k=buy["k"]-50) if buy else None
            if not buy or not sell:return None,"missing_bear_delta_legs"
            sel=[(buy,1),(sell,-1)]
    elif family=="RANGE_CREDIT":
        if trend!=0 or abs(move)>.28:return None,"not_range_day"
        if vix<15 or features["vix_percentile20"]<.45:return None,"vix_insufficient_for_premium"
        if atm_iv_pct<max(rv*1.15, vix*.90):return None,"iv_insufficient_risk_premium"
        cshort=pick(cs,"CE",.22)
        pshort=pick(ps,"PE",-.22)
        if not cshort or not pshort:return None,"missing_short_wings"
        clong=pick(cs,"CE",.09,min_k=cshort["k"]+100,max_k=cshort["k"]+350)
        plong=pick(ps,"PE",-.09,min_k=pshort["k"]-350,max_k=pshort["k"]-100)
        if not clong or not plong:return None,"missing_hedge_wings"
        if clong["k"]<=cshort["k"] or plong["k"]>=pshort["k"]:
            return None,"bad_hedge_wing"
        sel=[(cshort,-1),(clong,1),(pshort,-1),(plong,1)]
    elif family=="VOL_EXPANSION":
        if features["vix_5session_move"]<1.0 and rv<atm_iv_pct*1.2:
            return None,"vol_forecast_not_expanding"
        if atm_iv_pct>vix*1.45:return None,"atm_iv_already_high"
        cbuy=pick(cs,"CE",.32)
        pbuy=pick(ps,"PE",-.32)
        if not cbuy or not pbuy:return None,"missing_otm_strangle_legs"
        sel=[(cbuy,1),(pbuy,1)]
    else:raise ValueError("Unknown family")
    # All Greeks calculated *before* 10:16 trade execution.
    delta=sum(s*a["delta"] for a,s in sel)
    gamma=sum(s*a["gamma"] for a,s in sel)
    theta=sum(s*a["theta"] for a,s in sel)
    vega=sum(s*a["vega"] for a,s in sel)
    if family=="TREND_DEBIT" and (delta*trend<.10 or theta>=0 or vega<-.1):
        return None,"greeks_inconsistent_trend_debit"
    if family=="RANGE_CREDIT" and (abs(delta)>.22 or theta<=0 or gamma>=0):
        return None,"greeks_inconsistent_credit"
    if family=="VOL_EXPANSION" and (gamma<=0 or vega<=0 or theta>=0 or abs(delta)>.2):
        return None,"greeks_inconsistent_long_vol"
    return {"legs":sel,"delta":delta,"gamma":gamma,"theta":theta,
            "vega":vega,"atm_iv_pct":atm_iv_pct,"vix":vix,"rv10":rv},None

def risk_and_cash(family,structures,qty,trade_day):
    selected=structures["legs"]
    raw_entry=[a["entry"] for a,s in selected]
    entries=[adverse(a["entry"],s) for a,s in selected]
    exits=[adverse(a["exit"],-s) for a,s in selected]
    debit=sum(s*p for (a,s),p in zip(selected,entries))
    gross=qty*sum(s*(p1-p0) for (a,s),p0,p1 in zip(selected,entries,exits))
    credit=-debit
    if family=="RANGE_CREDIT":
        # Butterfly/condor worst-case max loss is wider of put/call wings - net credit.
        short_ce=next(a for a,s in selected if a["typ"]=="CE" and s==-1)
        long_ce=next(a for a,s in selected if a["typ"]=="CE" and s==1)
        short_pe=next(a for a,s in selected if a["typ"]=="PE" and s==-1)
        long_pe=next(a for a,s in selected if a["typ"]=="PE" and s==1)
        width=max(long_ce["k"]-short_ce["k"],short_pe["k"]-long_pe["k"])
        worst=max(0.,width-credit)*qty
        if credit<=2 or width<=0 or credit>=width:return None,"credit_outside_wings"
    else:
        worst=debit*qty
        if debit<=2:return None,"nonpositive_debit"
    if worst<=0 or worst>MAX_POSITION_LOSS:
        return None,"risk_cap_exceeded"
    if family=="VOL_EXPANSION" and worst>MAX_POSITION_LOSS*.95:
        return None,"long_vol_risk_buffer"
    leg_triples=[(a["typ"],a["k"],s) for a,s in selected]
    charge=fees(trade_day,qty,leg_triples,entries,exits,exit_date=trade_day)
    net=gross-charge["total"]
    return {"gross":gross,"net":net,"fees":charge,"max_loss":worst,
            "initial_debit":debit,"entry_prices":entries,"exit_prices":exits,
            "leg_triples":leg_triples},None

def evaluate(year,paths,support,output):
    output.mkdir(parents=True,exist_ok=True)
    ctx=read_context(support,year)
    q,duplicates=load_option_marks(paths,year,ctx)
    attempts=[];executed=[];quote_days=set(q.date)
    # One independently modeled position/session/family (NOT actual portfolio overlap).
    for d,features in sorted(ctx.items()):
        if d not in quote_days:
            for family in MODELS:attempts.append({"date":str(d),"family":family,"reason":"no_option_quotes"})
            continue
        current=q[q.date==d]
        # Evaluate expiry from signal legs; choose one without looking at future close.
        candidate=build_snapshot(current,features["spot"])
        expiry=preferred_exp(candidate,d)
        for family in MODELS:
            if not expiry:
                attempts.append({"date":str(d),"family":family,"reason":"no_liquid_expiry_and_greeks"})
                continue
            options=[a for a in candidate if a["exp"]==expiry]
            chosen,err=family_legs(family,features,options,expiry)
            if err:
                attempts.append({"date":str(d),"family":family,"reason":err});continue
            qty=lot_size(d,expiry)
            if not qty:
                attempts.append({"date":str(d),"family":family,"reason":"unsupported_contract_lot"})
                continue
            cash,err=risk_and_cash(family,chosen,qty,d)
            if err:
                attempts.append({"date":str(d),"family":family,"reason":err});continue
            legs=chosen["legs"]
            # Greeks at signal-time 10:06 derived from OHLC, not brokerage IV.
            delta=qty*chosen["delta"]
            gamma=qty*chosen["gamma"]
            theta=qty*chosen["theta"]
            vega=qty*chosen["vega"]
            # Hypothetical $500, $600 point shock scenarios, IV +/- 10 vol-points.
            # This is a Taylor approximation, NOT a historical executable path.
            shock={}
            for change in (-600,-500,500,600):
                for ivchange in (-10,0,10):
                    rough=(delta*change+.5*gamma*change*change+vega*ivchange
                            +theta*(1/252))
                    shock[f"move_{change}_iv_{ivchange}"]=round(float(max(-cash["max_loss"],rough)),2)
            post=d>=CAS_START
            rec={**features,"family":family,"expiry":str(expiry),
                 "regime":"post_CAS_AugNov2026" if post else "pre_CAS",
                 "entry_time":"10:16","exit_time":"14:46","lot_size":qty,
                 "max_loss_rs":round(cash["max_loss"],2),
                 "net_pnl_rs":round(cash["net"],2),"gross_pnl_rs":round(cash["gross"],2),
                 "charges_rs":round(cash["fees"]["total"],2),
                 "initial_debit_points":round(cash["initial_debit"],3),
                 "atm_iv_pct":round(chosen["atm_iv_pct"],2),
                 "delta_units":round(delta,7),"gamma_units":round(gamma,9),
                 "theta_rs_day":round(theta,3),"vega_rs_ivpt":round(vega,3),
                 "sum_oi":sum(a["oi"] for a,s in legs),
                 "min_leg_oi":min(a["oi"] for a,s in legs),
                 "sum_signal_volume":sum(a["vol_signal"] for a,s in legs),
                 "min_entry_volume":min(a["vol_entry"] for a,s in legs),
                 "leg_definition":json.dumps([(a["typ"],a["k"],s) for a,s in legs]),
                 "signal_leg_iv":json.dumps([round(a["iv"],4) for a,s in legs]),
                 "signal_leg_oi":json.dumps([a["oi"] for a,s in legs]),
                 "greek_shock_scenarios_rs":json.dumps(shock),
                 "pricing_warning":"OHLC simulated fills; 10:06 signal -> 10:16 entry -> 14:46 exit; no bid/ask"}
            executed.append(rec)
    led=pd.DataFrame(executed)
    skip=pd.DataFrame(attempts)
    if led.empty:
        # Preserve schema for aggregate analysis and explicit zero-trade status.
        led=pd.DataFrame(columns=["date","family","regime","net_pnl_rs","vix","atm_iv_pct",
                                  "delta_units","gamma_units","theta_rs_day","vega_rs_ivpt"])
    if skip.empty:skip=pd.DataFrame(columns=["date","family","reason"])
    led.to_csv(output/f"AEGIS20_candidates_{year}.csv",index=False)
    skip.to_csv(output/f"AEGIS20_skips_{year}.csv",index=False)
    summary={"year":year,"sessions_with_spot_features":len(ctx),
             "option_quote_dates":len(quote_days),"sample_option_rows":len(q),
             "deduplicated_source_rows":duplicates,
             "input_source_paths":[p.name for p in paths],
             "source_required":"OHLC 1m, contemporaneous OI+volume at 10:06, same-leg 10:16+14:46 marks",
             "vix_required":"prior session (up to 7 calendar days), known at signal 10:06",
             "post_CAS_range":["2026-08-03","2026-11-05"],
             "dec_2026_future_CAS":"not observed; only shock scenario, never backtest claim",
             "family_results":{f:stats(led[led.family==f]) for f in MODELS},
             "family_by_regime":{f:{r:stats(df) for r,df in led[led.family==f].groupby("regime")} for f in MODELS},
             "skip_reasons":skip.groupby(["family","reason"]).size().to_dict() if False else
                 {f:skip[skip.family==f].reason.value_counts().to_dict() for f in MODELS},
             "one_day_rule":"Each candidate is same-day, all legs closed 14:46 before any CAS or expiry. No margin, queue, bid-ask or close auction fills",
             "not_an_optimization":True,
             "out_of_sample":False,
             "research":True}
    (output/f"AEGIS20_summary_{year}.json").write_text(json.dumps(summary,indent=2))
    print("AEGIS20_YEAR_RESULT",json.dumps({
        "year":year,"option_rows":len(q),"option_dates":len(quote_days),
        "families":summary["family_results"],
        "cas":summary["family_by_regime"],
        "skips":summary["skip_reasons"],
        "oos":False},default=str),flush=True)
    return summary

def main():
    a=argparse.ArgumentParser()
    a.add_argument("--year",required=True,type=int,choices=(2024,2025,2026))
    a.add_argument("--parquet",required=True,help="Semicolon separated Parquet paths")
    a.add_argument("--support",required=True)
    a.add_argument("--out",required=True)
    x=a.parse_args()
    paths=[pathlib.Path(p) for p in x.parquet.split(";")]
    evaluate(x.year,paths,pathlib.Path(x.support),pathlib.Path(x.out))
if __name__=="__main__":main()
