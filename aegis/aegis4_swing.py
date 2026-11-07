#!/usr/bin/env python3
"""AEGIS 4.0: PRE-REGISTERED NIFTY options swing-to-expiry credit vertical research.

Research only; never call account/order endpoints or claim live execution.
A single trend-aligned, theta-premium candidate:
  * entry 3–9 calendar days to verified listed expiry, at 10:16 after
    10:06 completed OI/IV/Greek and cash-index 10:00 snapshot.
  * up to multiple nights through expiry SESSION; 10:06 and 14:40
    risk checks, 10:16 / 14:46 modeled next-candle fills.
  * 60% credit captured take profit; 2.3x initial premium buyback risk
    stop; VIX jump / short strike breach veto; otherwise expire-session
    14:46 mandatory exit before auction/settlement; no overnight past expiry.
  * 1 one-lot risk-limited 100-200 wide bullish put or bearish call vertical
    per weekly expiry, no overlapping positions.
  * estimated IV/Delta/Gamma/Theta/Vega, observed historical OI/volume,
    prior-day India VIX, prior-10-day realized volatility and time-causal trend.
  * all source candles from previously verified market-data Parquet.
No historical actual bid/ask, depth, official settlement or true execution.
"""
from __future__ import annotations
import argparse,collections,datetime as dt,json,math,pathlib
import duckdb,numpy as np,pandas as pd,pyarrow.parquet as pq
from aegis.aegis20_candidates import read_context
from aegis.aegis3_credit_spread import snapshot,modeled_fill
from aegis.backtest_v01 import lot_size,fees
from aegis.rolling_research_final import stats

START=dt.date(2024,11,6)
END=dt.date(2026,11,5)
CAS=dt.date(2026,8,3)
MIN_OI=5_000.
MAX_LOSS=10_000.
FEE_RESERVE=500.
MAX_WIDTH=200
WIDTHS=(100,150,200)
ENTRY_MIN_DTE=3
ENTRY_MAX_DTE=9
SIGNALS=("09:46","10:06","10:16","14:40","14:46")
SLIP_STRESSES=(.0075,.015,.03)
INITIAL_TAKE_CREDIT_FRACTION=.40  # collect >=60% of initial short option credit
PREMIUM_STOP_FACTOR=2.3
MAX_OPEN_TRADES=1
STOP_VIX_JUMP=4.0
RISK_PERCENT_OF_CAPITAL=.20  # INR10k / INR50L
EARLY_EXIT_EXPIRY="14:46"

def load_marks(files,features):
    spotref=pd.DataFrame([{"date":str(d),"spot":f["spot"]} for d,f in features.items()])
    if spotref.empty:raise RuntimeError("No source index sessions with 10:00 spot")
    filenames=[str(pathlib.Path(p)) for p in files]
    for f in filenames:
        if not pathlib.Path(f).is_file():raise FileNotFoundError(f)
    cols=set()
    for f in filenames:cols.update(pq.read_schema(f).names)
    oi="COALESCE(TRY_CAST(o.open_interest AS DOUBLE),TRY_CAST(o.oi AS DOUBLE))" if {"open_interest","oi"}<=cols else (
       "TRY_CAST(o.open_interest AS DOUBLE)" if "open_interest" in cols else (
       "TRY_CAST(o.oi AS DOUBLE)" if "oi" in cols else None))
    if oi is None:raise RuntimeError("NO observed historical OI; cannot execute required filters")
    src="["+",".join("'"+p.replace("'","''")+"'" for p in filenames)+"]"
    con=duckdb.connect()
    con.execute("SET TimeZone='Asia/Kolkata'")
    con.execute("SET memory_limit='4GB'")
    con.register("indexref",spotref)
    stmt=f"""
      SELECT CAST(o.date AS DATE) date,CAST(o.expiry AS DATE) expiry,
        CAST(o.strike AS INTEGER) strike,o.option_type typ,
        strftime(o.timestamp,'%H:%M') hm,
        CAST(o.open AS DOUBLE) px,
        TRY_CAST(o.volume AS DOUBLE) volume, {oi} oi
      FROM read_parquet({src},union_by_name=true) o
      JOIN indexref r ON CAST(o.date AS VARCHAR)=r.date
      WHERE DATE_DIFF('day',CAST(o.date AS DATE),CAST(o.expiry AS DATE)) BETWEEN 0 AND 12
        AND abs(CAST(o.strike AS DOUBLE)-r.spot)<=1250
        AND strftime(o.timestamp,'%H:%M') IN {SIGNALS}
        AND CAST(o.open AS DOUBLE)>.05
    """
    data=con.execute(stmt).df();con.close()
    if data.empty:return {},0
    data["date"]=pd.to_datetime(data.date).dt.date
    data["expiry"]=pd.to_datetime(data.expiry).dt.date
    key=["date","expiry","strike","typ","hm"]
    duplicates=int(data.duplicated(key).sum())
    if duplicates:
        data=data.sort_values(key+["volume"],ascending=[True]*5+[False]).drop_duplicates(key,keep="first")
    by_day={day:g for day,g in data.groupby("date")}
    return by_day,duplicates

def prior_trend(day,features,days):
    past=[d for d in days if d<day]
    if len(past)<4:return 0,0.
    # 3-trading-session trend from historical, already completed INDEX
    # 10:00 readings (no future-day close leakage).
    old=features[past[-3]]["spot"]
    now=features[day]["spot"]
    momentum=100*(now/old-1.)
    direction=1 if momentum>=.55 else (-1 if momentum<=-.55 else 0)
    return direction,momentum

def select(day,features,days,source):
    f=features[day];vix=f.get("vix");rv=f.get("rv10_pct")
    if vix is None or rv is None or not 11<=vix<=45 or not 5<=rv<=85:
        return None,"vix_or_realized_vol_unavailable_or_outside"
    if f.get("vix_5session_move",100)>6.:
        return None,"vix_accelerating_too_fast"
    if f.get("vix_percentile20",0)<.25:
        return None,"vix_premium_percentile_insufficient"
    direction,momentum=prior_trend(day,features,days)
    if not direction:return None,"no_prior_3_session_direction"
    # Avoid severe contradictory opening gap. No need for intraday ORB!
    if direction*f["open_move_pct"]<-.35:
        return None,"new_session_directional_invalidation"
    if f.get("spot_close_prev") is not None and direction*(f["spot"]/f["spot_close_prev"]-1)<-.007:
        return None,"opening_gap_opposes_prior_trend"
    chain=snapshot(source,f["spot"])
    if not chain:return None,"no_option_oi_iv_greeks"
    by_exp=collections.defaultdict(set)
    for c in chain:
        if ENTRY_MIN_DTE<=(c["expiry"]-day).days<=ENTRY_MAX_DTE:
            by_exp[c["expiry"]].add(c["typ"])
    possible=[exp for exp,types in by_exp.items() if types=={"CE","PE"}]
    if not possible:return None,"no_available_listed_weekly_expiry"
    # Freeze first option expiry of appropriate window, no knowledge of
    # future candle availability or outcome.
    expiry=min(possible,key=lambda x:((x-day).days,x))
    choices=[c for c in chain if c["expiry"]==expiry]
    calls=[c for c in choices if c["typ"]=="CE"]
    puts=[c for c in choices if c["typ"]=="PE"]
    if not calls or not puts:return None,"incomplete_two_sided_IV_chain"
    nearcall=min(calls,key=lambda c:abs(c["delta"]-.50))
    nearput=min(puts,key=lambda c:abs(c["delta"]+.50))
    iv=50*(nearcall["iv"]+nearput["iv"])
    if not 10<=iv<=70 or iv<rv*1.08 or iv<vix*.90:
        return None,"insufficient_implied_premium_against_realized_vol"
    nearby=[c for c in choices if abs(c["k"]-f["spot"])<=350]
    p_oi=sum(c["oi"] for c in nearby if c["typ"]=="PE")
    c_oi=sum(c["oi"] for c in nearby if c["typ"]=="CE")
    ratio=p_oi/max(c_oi,1.)
    if not .30<=ratio<=3.5:return None,"OI_put_call_concentration_veto"
    typ="PE" if direction==1 else "CE"
    short_options=sorted([c for c in choices if c["typ"]==typ and
       .18<=abs(c["delta"])<=.30 and c["oi"]>=MIN_OI and
       c["oi_change"]>=0 and c["signal_volume"]>=1],
       key=lambda c:(abs(abs(c["delta"])-.23),-c["oi"]))
    if not short_options:return None,"no_liquid_directional_short_delta"
    qty=lot_size(day,expiry)
    if qty is None:return None,"no_verified_lot_rule"
    for short in short_options[:7]:
        for width in WIDTHS:
            k=short["k"]-width if typ=="PE" else short["k"]+width
            hedge=next((c for c in choices if c["typ"]==typ and c["k"]==k and
                c["oi"]>=MIN_OI and c["oi_change"]>=-.20 and
                c["signal_volume"]>=1 and abs(c["delta"])<abs(short["delta"])),None)
            if hedge is None:continue
            sigcredit=(modeled_fill(short["signal_mark"],-1,.0075)-
                       modeled_fill(hedge["signal_mark"],1,.0075))
            if sigcredit<width*.11:continue
            risk=(width-sigcredit)*qty+FEE_RESERVE
            if not 0<risk<=MAX_LOSS:continue
            delta=qty*(hedge["delta"]-short["delta"])
            gamma=qty*(hedge["gamma"]-short["gamma"])
            theta=qty*(hedge["theta_per_day"]-short["theta_per_day"])
            vega=qty*(hedge["vega_per_ivpt"]-short["vega_per_ivpt"])
            if (direction*delta<=0 or gamma>=0 or theta<=0 or vega>=0):
                continue
            return {"direction":direction,"expiry":expiry,"qty":qty,"short":short,"hedge":hedge,
                    "width":width,"signal_credit":sigcredit,"signal_risk":risk,"trend3_pct":momentum,
                    "atm_iv":iv,"oi_pcr":ratio,"delta":delta,"gamma":gamma,"theta":theta,
                    "vega":vega,"entry_vix":vix,"entry_rv":rv},None
    return None,"no_credit_spread_passes_greeks_and_defined_risk"

def marks(by_day,day,spread,clock,require_volume=False):
    frame=by_day.get(day)
    if frame is None:return None
    legs=[]
    for c in (spread["short"],spread["hedge"]):
        r=frame[(frame.expiry==spread["expiry"]) &
                (frame.strike==c["k"]) &
                (frame.typ==c["typ"]) &
                (frame.hm==clock)]
        if len(r)!=1:return None
        x=r.iloc[0]
        if require_volume and (pd.isna(x.volume) or x.volume<1):return None
        legs.append((float(x.px),float(x.oi) if pd.notna(x.oi) else None))
    return legs

def valued_exit(spread,entry,exit_,exit_date,slip):
    qty=spread["qty"]
    shortin=modeled_fill(entry[0][0],-1,slip)
    longin=modeled_fill(entry[1][0],1,slip)
    credit=shortin-longin
    if credit<=0:return None
    worst=(spread["width"]-credit)*qty+FEE_RESERVE
    if worst<=0 or worst>MAX_LOSS:return None
    if exit_ is None:
        return {"net":-worst,"gross":-worst+FEE_RESERVE,"costs":FEE_RESERVE,
                "initial_credit":credit,"max_loss":worst,"missing_exit":True}
    shortout=modeled_fill(exit_[0][0],1,slip)
    longout=modeled_fill(exit_[1][0],-1,slip)
    legs=[(spread["short"]["typ"],spread["short"]["k"],-1),
          (spread["hedge"]["typ"],spread["hedge"]["k"],1)]
    charges=fees(spread["entry_date"],qty,legs,[shortin,longin],
                 [shortout,longout],exit_date=exit_date)
    gross=qty*(credit-(shortout-longout))
    return {"net":gross-charges["total"],"gross":gross,
            "costs":charges["total"],"initial_credit":credit,
            "max_loss":worst,"missing_exit":False}

def nearest_mark_after_event(by_day,day,spread,signal,execution):
    observed=marks(by_day,day,spread,signal)
    if observed is None:return None,None
    fill=marks(by_day,day,spread,execution,require_volume=True)
    return observed,fill

def choose_exit(spread,entry,session_days,features,by_day):
    day=spread["entry_date"];expiry=spread["expiry"]
    first_credit=(modeled_fill(entry[0][0],-1,.0075)-
                  modeled_fill(entry[1][0],1,.0075))
    # Any scheduled intervening weekday/market-index session with missing
    # historical quotes causes conservative max-loss fallback.
    seen=[]
    for current in session_days:
        if current<day:continue
        if current>expiry:break
        if current not in by_day:
            return current,None,"missing_option_session_assumed_max_loss",seen
        # Entry day: no pseudo exit at 10:06 (before the position existed).
        clocks=[("14:40","14:46")] if current==day else [
            ("10:06","10:16"),("14:40","14:46")]
        for signal_clock,execution_clock in clocks:
            quote,fill=nearest_mark_after_event(by_day,current,spread,signal_clock,execution_clock)
            if quote is None:
                if signal_clock=="10:06":continue
                return current,None,"missing_required_daily_close_assumed_max_loss",seen
            midbuyback=quote[0][0]-quote[1][0]
            # Requirement: only consider exit if 60% of initial credit
            # captured, stop if buyback >= 2.3x credit.
            profit=midbuyback<=first_credit*.40 and current>day
            stop=midbuyback>=first_credit*PREMIUM_STOP_FACTOR
            if current>day and signal_clock=="10:06":
                f=features.get(current,{})
                vix=f.get("vix")
                if vix and vix-spread["entry_vix"]>=STOP_VIX_JUMP:
                    stop=True
                spot=f.get("spot")
                if spot:
                    near_breach=(spot<=spread["short"]["k"]+40) if spread["direction"]>0 \
                                 else (spot>=spread["short"]["k"]-40)
                    if near_breach:stop=True
            expiry_close=current==expiry and signal_clock=="14:40"
            if profit or stop or expiry_close:
                label="swing_profit_take" if profit else ("swing_risk_stop" if stop else "expiry_day_close_before_settlement")
                if fill is None:
                    return current,None,"untradeable_exit_assumed_max_loss",seen
                return current,fill,label,seen
            seen.append({"date":str(current),"time":signal_clock,
                         "buyback_mid_pts":round(midbuyback,2)})
    # Expiry date unavailable in market index observations means unpriced:
    return min(expiry,session_days[-1] if session_days else expiry),None,"expiry_coverage_unverified_assumed_max_loss",seen

def expiry_payoff_proxy(spread,entry,index_close_by_day):
    """Counterfactual pure expiry payoff: **NOT** official settlement (CAS)."""
    exp=spread["expiry"]
    if exp not in index_close_by_day:return None
    spot=index_close_by_day[exp]
    typ=spread["short"]["typ"]
    intrinsic=lambda k:max(0.,spot-k) if typ=="CE" else max(0.,k-spot)
    credit=(modeled_fill(entry[0][0],-1,.0075)-
            modeled_fill(entry[1][0],1,.0075))
    pay=credit-intrinsic(spread["short"]["k"])+intrinsic(spread["hedge"]["k"])
    # Fee/tax on exercise/settlement depends on actual contract and settlement
    # and is NOT modeled. This is gross theoretical and must not be used
    # for claimed strategy profits or acceptance gates.
    return round(pay*spread["qty"],2)

def load_index_closes(support,year):
    root=pathlib.Path(support)
    f=(root/"NIFTY_5min_2026_extended.csv" if year==2026 else
       root/"NIFTY_5min_5yr_2021_2026.csv")
    x=pd.read_csv(f,parse_dates=["timestamp"])
    x=x[x.timestamp.dt.year==year].sort_values("timestamp")
    return dict(zip(x.timestamp.dt.date,x.groupby(x.timestamp.dt.date)["close"].transform("last")))

def run(year,files,support,out):
    out=pathlib.Path(out);out.mkdir(parents=True,exist_ok=True)
    features=read_context(pathlib.Path(support),year)
    dates=sorted(features)
    by_day,duplicates=load_marks(files,features)
    latest_index_day=max(dates) if dates else None
    index_close=load_index_closes(support,year)
    trades=[];skips=[];open_until=None;used_expiries=set()
    for day in dates:
        if day<START or day>END:continue
        if open_until is not None and day<=open_until:
            skips.append({"date":str(day),"reason":"existing_swing_position_open"})
            continue
        raw=by_day.get(day)
        if raw is None:
            skips.append({"date":str(day),"reason":"option_session_unavailable"});continue
        spread,reason=select(day,features,dates,raw)
        if spread is None:
            skips.append({"date":str(day),"reason":reason});continue
        if spread["expiry"]>latest_index_day:
            # Avoid right-censoring: future trading sessions and expiry payoff
            # have not occurred in the pinned historical data.
            skips.append({"date":str(day),"reason":"unobserved_expiry_after_historical_cutoff"});continue
        if spread["expiry"] in used_expiries:
            skips.append({"date":str(day),"reason":"one_trade_per_option_expiry"});continue
        # Causality: no future entry prices until candidate frozen above.
        spread["entry_date"]=day
        entry=marks(by_day,day,spread,"10:16",require_volume=True)
        if entry is None:
            skips.append({"date":str(day),"reason":"entry_leg_not_traded_at_10_16"});continue
        credit=(modeled_fill(entry[0][0],-1,.0075)-
                modeled_fill(entry[1][0],1,.0075))
        maxrisk=(spread["width"]-credit)*spread["qty"]+FEE_RESERVE
        if credit<spread["width"]*.10 or maxrisk>MAX_LOSS or maxrisk<=0:
            skips.append({"date":str(day),"reason":"actual_entry_credit_or_risk_below_threshold"});continue
        # Determine the complete next-session risk schedule from cash index,
        # but never choose an entry based on the *future option* availability.
        subsequent=[d for d in dates if day<=d<=spread["expiry"]]
        exit_day,exitmark,reason,checks=choose_exit(spread,entry,subsequent,features,by_day)
        results={};stressfail=0
        for slip in SLIP_STRESSES:
            val=valued_exit(spread,entry,exitmark,exit_day,slip)
            if val is None:
                stressfail+=1
                # Stress scenario cannot be silently dropped.
                val={"net":-MAX_LOSS,"gross":-MAX_LOSS+FEE_RESERVE,
                     "costs":FEE_RESERVE,"initial_credit":0.,
                     "max_loss":MAX_LOSS,"missing_exit":True,"stress_untradable":True}
            results[f"{slip:.4f}"]=val
        default=results["0.0075"]
        if default.get("stress_untradable"):
            # All selected entries must contribute to P&L, even if strict
            # historical source cannot price later mandatory exit.
            reason="conservative_full_loss_entry_or_exit_incomplete"
        exp_counter=expiry_payoff_proxy(spread,entry,index_close)
        record={
            "date":str(day),"expiry":str(spread["expiry"]),
            "expiry_days_at_entry":(spread["expiry"]-day).days,
            "exit_date":str(exit_day),"calendar_hold_days":(exit_day-day).days,
            "overnight":exit_day>day,"exit_reason":reason,
            "regime":"post_CAS_AugNov2026" if day>=CAS else "pre_CAS",
            "side":"bull_put_credit" if spread["direction"]>0 else "bear_call_credit",
            "short_strike":spread["short"]["k"],
            "long_hedge_strike":spread["hedge"]["k"],"width":spread["width"],
            "lot_qty":spread["qty"],"entry_clock":"10:16",
            "net_pnl_rs":round(float(default["net"]),2),
            "gross_pnl_rs":round(float(default["gross"]),2),
            "charges_rs":round(float(default["costs"]),2),
            "credit_pts":round(float(default["initial_credit"]),3),
            "max_contract_risk_rs":round(float(default["max_loss"]),2),
            "missing_exit_full_loss_penalty":bool(default.get("missing_exit",False)),
            "prior_india_vix":round(float(spread["entry_vix"]),2),
            "vix_prior_date":features[day]["vix_prior_date"],
            "vix_5session_change":round(float(features[day]["vix_5session_move"]),2),
            "IV_atm_pct":round(float(spread["atm_iv"]),2),
            "IV_short_pct":round(float(spread["short"]["iv"]*100),2),
            "IV_hedge_pct":round(float(spread["hedge"]["iv"]*100),2),
            "rv10_prior_pct":round(float(spread["entry_rv"]),2),
            "Delta_lot":round(float(spread["delta"]),4),
            "Gamma_lot":round(float(spread["gamma"]),7),
            "Theta_rupees_day":round(float(spread["theta"]),3),
            "Vega_rupees_ivpoint":round(float(spread["vega"]),3),
            "short_signal_oi":float(spread["short"]["oi"]),
            "hedge_signal_oi":float(spread["hedge"]["oi"]),
            "short_oi_change_pct":round(float(spread["short"]["oi_change"]*100),3),
            "put_call_oi_ratio":round(float(spread["oi_pcr"]),3),
            "trend_three_session_pct":round(float(spread["trend3_pct"]),3),
            "hypothetical_gross_expiry_payoff_using_index_close_NOT_OFFICIAL_rs":exp_counter,
            "stress_1_5pct_net_rs":round(float(results["0.0150"]["net"]),2),
            "stress_3pct_net_rs":round(float(results["0.0300"]["net"]),2),
            "stress_untradeable_scenarios":stressfail,
            "risk_check_events":len(checks),
            "note":"Swing option candles OHLC, not executable bid/ask; expiry payoff proxy excludes settlement fees"}
        trades.append(record)
        used_expiries.add(spread["expiry"])
        # No overlap permitted even if the strategy closes at expiry day.
        open_until=exit_day
    ledger=pd.DataFrame(trades)
    if ledger.empty:
        ledger=pd.DataFrame(columns=["date","expiry","exit_date","net_pnl_rs","regime","overnight",
          "stress_1_5pct_net_rs","stress_3pct_net_rs"])
    rej=pd.DataFrame(skips)
    if rej.empty:rej=pd.DataFrame(columns=["date","reason"])
    ledger.to_csv(out/f"AEGIS4_swing_trades_{year}.csv",index=False)
    rej.to_csv(out/f"AEGIS4_swing_skips_{year}.csv",index=False)
    summary={
      "strategy":"AEGIS4_NIFTY_swing_defined_risk_theta_premium",
      "year":year,"input_files":[str(p) for p in files],
      "market_signal_sessions":len(dates),"option_session_days":len(by_day),
      "source_option_mark_rows":int(sum(len(g) for g in by_day.values())),
      "overlap_deduplicated":duplicates,
      "risk_cap_rs":MAX_LOSS,"open_position_limit":MAX_OPEN_TRADES,
      "single_entry_per_expiry":True,
      "model_months":"multi-session hold to expiry session or earlier stop/credit profit, no forced same-day close",
      "cas":"all modeled trades exit before auction/settlement, new Dec7 2026 regime not observed",
      "vix":"prior complete session only, no future VIX",
      "greeks":"BSM IV, Delta, Gamma, Theta, Vega estimates at 10:06; observed OI, NOT executable broker quotes",
      "same_day_source_lookahead":False,
      "prospective_oos":False,
      "results":stats(ledger),
      "overnight":stats(ledger[ledger.overnight]) if len(ledger) else {"trades":0},
      "regime":{name:stats(x) for name,x in ledger.groupby("regime")} if len(ledger) else {},
      "skip_reasons":rej.reason.value_counts().to_dict(),
      "actual_exits":ledger.exit_reason.value_counts().to_dict() if len(ledger) else {},
      "unpriced_exits_penalized":int(ledger.missing_exit_full_loss_penalty.sum()) if len(ledger) else 0,
      "stresses":{key:round(float(ledger[key].sum()),2) if len(ledger) else 0.
                   for key in ("stress_1_5pct_net_rs","stress_3pct_net_rs")},
      "counterfactual_expiry_proxy_excludes_fees_and_is_NOT_OFFICIAL":True}
    (out/f"AEGIS4_swing_summary_{year}.json").write_text(json.dumps(summary,indent=2,default=str))
    print("AEGIS4_YEAR_REPLAY",json.dumps({"year":year,
      "n":summary["results"]["trades"],"net":summary["results"]["net_pnl_rs"],
      "win":summary["results"].get("win_rate"),
      "regime":summary["regime"],
      "stress":summary["stresses"],"overnight":summary["overnight"],
      "skip":summary["skip_reasons"],"close":summary["actual_exits"],
      "penalized":summary["unpriced_exits_penalized"]},default=str),flush=True)

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--year",type=int,required=True,choices=(2024,2025,2026))
    p.add_argument("--parquet",required=True)
    p.add_argument("--support",required=True)
    p.add_argument("--out",required=True)
    a=p.parse_args()
    run(a.year,[pathlib.Path(x) for x in a.parquet.split(";")],
        pathlib.Path(a.support),a.out)
if __name__=="__main__":main()
