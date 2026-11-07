#!/usr/bin/env python3
"""AEGIS 3.0 — pre-registered directional defined-risk NIFTY option credit spread.

Research only. Never trades, fetches private credentials, or calls order APIs.
Core hypothesis: after a genuine morning directional break, a same-direction
deep OTM hedged short option has enough IV/Theta advantage to compensate
for risk, fees, intraday gaps and short Gamma/Vega.

SIGNAL: 10:00 completed NIFTY 5m, 09:46 -> 10:06 option OI/mark/Greeks,
and prior-session India VIX. Executable *proxy* entry: 10:16 option OHLC OPEN.
Hedged short vertical: sell 0.12-0.25 |Delta| and buy same-side 100-250
NIFTY points farther OTM; cap expiry max loss incl fee reserve < INR 10k.
Checkpoints use 11:10 -> 11:16, 12:10 -> 12:16, 13:10 -> 13:16,
14:40 -> 14:46, always exit before CAS. Stops/targets are approximations
with six minutes of detection/filled trade delay, NOT actual executable quotes.

Historical option volume/OI are observed; IV, Delta, Gamma, Theta and Vega
are model estimates using a constant interest/dividend proxy; not market
bid-ask Greeks, IV surface, queue, exchange margin or live returns.
"""
from __future__ import annotations
import argparse,collections,datetime as dt,json,math,pathlib
import duckdb,numpy as np,pandas as pd,pyarrow.parquet as pq
from aegis.aegis20_candidates import read_context
from aegis.backtest_v01 import estimate_greeks,lot_size,fees
from aegis.rolling_research_final import stats

CAPITAL=5_000_000
MAX_POSITION_RISK=10_000.
MAX_DAILY_RISK=25_000.
MAX_POSITIONS_PER_DAY=1
SHORT_DELTA_MIN=.12
SHORT_DELTA_MAX=.25
OI_MIN=5_000
MIN_CREDIT_WIDTH=.08
SPREAD_WIDTHS=(100,150,200,250)
CAS_START=dt.date(2026,8,3)
DEC_CAS_START=dt.date(2026,12,7)
FAMILY="DIRECTIONAL_CREDIT"
TIMES=("09:46","10:06","10:16","11:10","11:16","12:10","12:16",
       "13:10","13:16","14:40","14:46")
CHECKS=(("11:10","11:16"),("12:10","12:16"),
        ("13:10","13:16"),("14:40","14:46"))
EXIT_SIGNAL_CREDIT_RATIO=.50
STOP_SIGNAL_CREDIT_RATIO=2.0
FEE_RESERVE=500.
EXTRA_SLIPPAGE_SCENARIOS=(.0075,.015,.03)
SLIP_POINT_FLOOR=.75

def modeled_fill(px,side,slip_pct):
    return max(.05,float(px)+side*max(SLIP_POINT_FLOOR,abs(float(px))*slip_pct))

def load_option_bars(paths,features):
    """Date/strike constrained scan with union of 2025 oi and 2026 open_interest."""
    spotref=pd.DataFrame([{"date":str(day),"spot":v["spot"]} for day,v in features.items()])
    if spotref.empty:return pd.DataFrame(),0
    paths=[str(pathlib.Path(x)) for x in paths]
    for p in paths:
        if not pathlib.Path(p).is_file():raise FileNotFoundError(p)
    columns=set()
    for p in paths:columns.update(pq.read_schema(p).names)
    field=("COALESCE(TRY_CAST(o.open_interest AS DOUBLE),TRY_CAST(o.oi AS DOUBLE))"
           if {"open_interest","oi"}<=columns else
           "TRY_CAST(o.open_interest AS DOUBLE)" if "open_interest" in columns else
           "TRY_CAST(o.oi AS DOUBLE)" if "oi" in columns else None)
    if field is None:raise RuntimeError("Actual OI field unavailable: do not invent OI")
    filenames="["+",".join("'"+p.replace("'","''")+"'" for p in paths)+"]"
    con=duckdb.connect()
    con.execute("SET TimeZone='Asia/Kolkata'")
    con.execute("SET memory_limit='4GB'")
    con.register("reference_spot",spotref)
    query=f"""
      SELECT CAST(o.date AS DATE) date,CAST(o.expiry AS DATE) expiry,
        CAST(o.strike AS INTEGER) strike,o.option_type typ,
        strftime(o.timestamp,'%H:%M') hm,
        CAST(o.open AS DOUBLE) px,
        TRY_CAST(o.volume AS DOUBLE) volume,
        {field} oi
      FROM read_parquet({filenames}, union_by_name=true) o
      JOIN reference_spot r ON CAST(o.date AS VARCHAR)=r.date
      WHERE DATE_DIFF('day',CAST(o.date AS DATE),CAST(o.expiry AS DATE)) BETWEEN 4 AND 12
        AND abs(CAST(o.strike AS DOUBLE)-r.spot)<=1000
        AND strftime(o.timestamp,'%H:%M') IN {TIMES}
        AND CAST(o.open AS DOUBLE)>.05
    """
    frame=con.execute(query).df()
    con.close()
    if frame.empty:return frame,0
    frame["date"]=pd.to_datetime(frame.date).dt.date
    frame["expiry"]=pd.to_datetime(frame.expiry).dt.date
    key=["date","expiry","strike","typ","hm"]
    dups=int(frame.duplicated(key).sum())
    if dups:
        frame=frame.sort_values(key+["volume"],ascending=[True]*5+[False]).drop_duplicates(key,keep="first")
    return frame,dups

def snapshot(allbars,spot):
    """Market data known by 10:07 only. Later execution marks not used for choice."""
    seen={}
    for r in allbars.itertuples():
        key=(r.expiry,int(r.strike),str(r.typ))
        if key not in seen:seen[key]={}
        seen[key][r.hm]={"px":float(r.px),"oi":float(r.oi) if pd.notna(r.oi) else None,
                         "vol":float(r.volume) if pd.notna(r.volume) else 0.}
    candidates=[]
    for key,marks in seen.items():
        early=marks.get("09:46")
        quote=marks.get("10:06")
        if early is None or quote is None:continue
        if not early["oi"] or not quote["oi"] or quote["oi"]<OI_MIN:continue
        if quote["vol"]<1 or early["vol"]<0:continue
        expiry,k,typ=key
        first_date=allbars.date.iloc[0]
        greeks=estimate_greeks(spot,k,(expiry-first_date).days,typ,quote["px"])
        if greeks is None or not .06<=greeks["iv"]<=.90:continue
        oi_change=(quote["oi"]-early["oi"])/max(1.,early["oi"])
        candidate={**greeks,"key":key,"expiry":expiry,"k":k,"typ":typ,
                   "marks":marks,"oi":quote["oi"],"oi_change":oi_change,
                   "signal_volume":quote["vol"],"signal_mark":quote["px"]}
        candidates.append(candidate)
    return candidates

def choose(features,candidates,day):
    """Fully specified frozen rules, no optimization or future price access."""
    if not candidates:return None,"no_point_in_time_oi_iv_greek_candidates"
    rv=features.get("rv10_pct");vix=features.get("vix")
    if rv is None or not vix or not (9<=rv<=70) or not (12<=vix<=38):
        return None,"vix_or_realized_regime_outside_range"
    if features.get("vix_5session_move",100)>4:
        return None,"vix_acceleration_veto"
    if features.get("vix_percentile20",0)<.2:
        return None,"vix_low_percentile_veto"
    direction=features["breakout"]
    drift=features["open_move_pct"]
    if direction==0 or direction*drift<.20:
        return None,"trend_or_open_range_not_confirmed"
    if features["spot_close_prev"] is not None:
        if direction*(features["spot"]-features["spot_close_prev"])<=0:
            return None,"no_trend_confirmation_from_prior_close"
    expiry_groups=collections.defaultdict(set)
    for c in candidates:expiry_groups[c["expiry"]].add(c["typ"])
    expiries=sorted([x for x,s in expiry_groups.items() if s=={"CE","PE"}],
             key=lambda x:(abs((x-day).days-7),x))
    if not expiries:return None,"missing_two_sided_expiry"
    expiry=expiries[0]
    chain=[c for c in candidates if c["expiry"]==expiry]
    calls=sorted([x for x in chain if x["typ"]=="CE"],key=lambda x:x["k"])
    puts=sorted([x for x in chain if x["typ"]=="PE"],key=lambda x:x["k"])
    def nearest(array,delta):
        return min(array,key=lambda x:abs(x["delta"]-delta)) if array else None
    atm_c=nearest(calls,.50)
    atm_p=nearest(puts,-.50)
    if not atm_c or not atm_p:return None,"cannot_estimate_atm_iv"
    atm_iv=50*(atm_c["iv"]+atm_p["iv"])
    if not (10<=atm_iv<=60) or atm_iv<max(rv*1.08,vix*.87):
        return None,"not_enough_implied_premium_vs_rv_vix"
    typ="PE" if direction==1 else "CE"
    side=[x for x in chain if x["typ"]==typ]
    shorts=sorted([x for x in side
          if SHORT_DELTA_MIN<=abs(x["delta"])<=SHORT_DELTA_MAX and
          x["oi_change"]>=0 and x["signal_volume"]>=1],
         key=lambda x:(abs(abs(x["delta"])-.18),-x["oi"]))
    if not shorts:return None,"no_confirmed_short_delta_oi"
    qty=lot_size(day,expiry)
    if not qty:return None,"unknown_lot_size"
    # OI PCR is measured, not interpreted as who placed buy/sell orders.
    vicinity=[x for x in chain if abs(x["k"]-features["spot"])<=350]
    p_oi=sum(x["oi"] for x in vicinity if x["typ"]=="PE")
    c_oi=sum(x["oi"] for x in vicinity if x["typ"]=="CE")
    pcr=p_oi/max(1.,c_oi)
    if not .35<=pcr<=3.0:
        return None,"oi_concentration_unbalanced"
    # Pair vertical only from signal-time prices. NEVER choose winning exit.
    for short in shorts[:5]:
        for width in SPREAD_WIDTHS:
            strike=short["k"]-width if typ=="PE" else short["k"]+width
            hedges=[x for x in side if x["k"]==strike and x["oi"]>=OI_MIN
                 and x["signal_volume"]>=1 and
                 abs(x["delta"])<abs(short["delta"])]
            if not hedges:continue
            hedge=hedges[0]
            if not (-.15<=hedge["oi_change"] and hedge["oi"]>0):continue
            gross_mid=short["signal_mark"]-hedge["signal_mark"]
            if gross_mid<=width*MIN_CREDIT_WIDTH:continue
            # Conservative estimate based on future ENTRY marks not allowed
            # for strategy selection. Use known signal-time marks here.
            known_credit=(modeled_fill(short["signal_mark"],-1,.0075)-
                          modeled_fill(hedge["signal_mark"],1,.0075))
            if known_credit<=width*.06:continue
            signal_maxrisk=(width-known_credit)*qty+FEE_RESERVE
            if not 0<signal_maxrisk<=MAX_POSITION_RISK:continue
            delta=qty*(hedge["delta"]-short["delta"])
            gamma=qty*(hedge["gamma"]-short["gamma"])
            theta=qty*(hedge["theta_per_day"]-short["theta_per_day"])
            vega=qty*(hedge["vega_per_ivpt"]-short["vega_per_ivpt"])
            # For a put credit, hedged Delta is positive; for a call credit negative.
            if direction*delta<=0 or theta<=0 or gamma>=0 or vega>=0:
                continue
            # Approximate +/-600pt & +/-10 IVpt Mark-to-Model as early warning.
            # Contractual max loss still bounded by the strike width.
            shock=[]
            for move in (-600,-500,500,600):
                for volmove in (-10,0,10):
                    estimate=delta*move+.5*gamma*move*move+vega*volmove+theta/365.
                    shock.append(max(-signal_maxrisk,estimate))
            return {"family":FAMILY,"day":day,"direction":direction,"expiry":expiry,
                    "qty":qty,"short":short,"long":hedge,"width":width,
                    "vix":vix,"rv10":rv,"atm_iv_pct":atm_iv,
                    "pcr_350":pcr,"delta_units":delta,"gamma_units":gamma,
                    "theta_rs_day":theta,"vega_rs_ivpt":vega,
                    "short_oi_change":short["oi_change"],
                    "short_oi":short["oi"],"long_oi":hedge["oi"],
                    "signal_mid_credit":gross_mid,
                    "signal_estimate_maxrisk":signal_maxrisk,
                    "signal_taylor_shock_worst_rs":min(shock)},None
    return None,"spread_greeks_premium_or_defined_risk_not_met"

def marks(pair,clock,volume=False):
    short=pair["short"]["marks"].get(clock)
    hedge=pair["long"]["marks"].get(clock)
    if not short or not hedge:return None
    if volume and (short["vol"]<1 or hedge["vol"]<1):return None
    return short["px"],hedge["px"]

def exit_at(pair,entry_credit,slip_pct):
    """Causal checkpoint mark at 11:10, fill next available 11:16 etc."""
    for signal_clock,execution_clock in CHECKS:
        signal=marks(pair,signal_clock)
        if signal is None:continue
        signal_debit=signal[0]-signal[1]
        take_profit=signal_debit<=EXIT_SIGNAL_CREDIT_RATIO*entry_credit
        stop_loss=signal_debit>=STOP_SIGNAL_CREDIT_RATIO*entry_credit
        if not (take_profit or stop_loss or signal_clock=="14:40"):continue
        executable=marks(pair,execution_clock,volume=True)
        if executable:
            cause="profit_target" if take_profit else ("stop_loss" if stop_loss else "before_cas")
            return execution_clock,executable,cause
        # If a mandatory marked exit has no actual traded leg candle,
        # do NOT replace with favorable imaginary market price.
        if signal_clock=="14:40":break
    # Last chance at 14:46 without 14:40 signal:
    terminal=marks(pair,"14:46",volume=True)
    if terminal:return "14:46",terminal,"terminal_mark_no_signal"
    return "14:46",None,"unpriced_exit_assumed_max_loss"

def pnl_at(pair,entry,exit_quote,clock,slip_pct):
    a,b=entry
    qty=pair["qty"];width=pair["width"]
    short_entry=modeled_fill(a,-1,slip_pct)
    hedge_entry=modeled_fill(b,1,slip_pct)
    net_credit=short_entry-hedge_entry
    if net_credit<=0:return None
    max_expiry_loss=(width-net_credit)*qty+FEE_RESERVE
    if max_expiry_loss>MAX_POSITION_RISK:return None
    if exit_quote is None:
        # Mark absence is conservatively treated as full defined max loss
        # rather than discarding the entry from the P&L distribution.
        return {"pnl_rs":-round(max_expiry_loss,2),"charges_rs":FEE_RESERVE,
                "max_loss_rs":max_expiry_loss,"net_credit_pts":net_credit,
                "missing_exit_penalty":True}
    short_exit=modeled_fill(exit_quote[0],1,slip_pct)
    hedge_exit=modeled_fill(exit_quote[1],-1,slip_pct)
    legs=[(pair["short"]["typ"],pair["short"]["k"],-1),
          (pair["long"]["typ"],pair["long"]["k"],1)]
    charges=fees(pair["day"],qty,legs,
                 [short_entry,hedge_entry],[short_exit,hedge_exit],
                 exit_date=pair["day"])
    gross=qty*(net_credit-(short_exit-hedge_exit))
    # Contractual expiry bound is not an intraday mark guarantee. Model
    # permits excess losses at mark if crossed/missing execution.
    net=gross-charges["total"]
    return {"pnl_rs":round(net,2),"gross_rs":round(gross,2),
            "charges_rs":round(charges["total"],2),
            "max_loss_rs":round(max_expiry_loss,2),
            "net_credit_pts":round(net_credit,3),"missing_exit_penalty":False}

def evaluate(year,paths,support,out):
    out=pathlib.Path(out);out.mkdir(parents=True,exist_ok=True)
    ctx=read_context(pathlib.Path(support),year)
    q,duplicate=load_option_bars(paths,ctx)
    by_date={day:frame for day,frame in q.groupby("date")} if len(q) else {}
    trades=[];rejected=[];vixseen=0;entryfail=0;missingexit=0
    for day,features in sorted(ctx.items()):
        if day not in by_date:
            rejected.append({"date":str(day),"reason":"missing_option_quote_day"});continue
        if features.get("vix") is not None:vixseen+=1
        candidates=snapshot(by_date[day],features["spot"])
        pair,why=choose(features,candidates,day)
        if pair is None:
            rejected.append({"date":str(day),"reason":why});continue
        observed_entry=marks(pair,"10:16",volume=True)
        if observed_entry is None:
            entryfail+=1
            rejected.append({"date":str(day),"reason":"untradeable_entry_no_both_legs"});continue
        signal_credit=pair["signal_mid_credit"]
        # One trade/day, 1 lot, defined-risk. Reject entry if fill cannot
        # satisfy the risk limit in every stress case, not based on exit.
        entrance_baseline=pnl_at(pair,observed_entry,(0.05,0.05),"10:16",.0075)
        if not entrance_baseline:
            rejected.append({"date":str(day),"reason":"actual_entry_credit_or_risk_invalid"});continue
        entry_credit=entrance_baseline["net_credit_pts"]
        finalclock,exitquote,reason=exit_at(pair,entry_credit,.0075)
        scenarios={}
        invalid=False
        for slip in EXTRA_SLIPPAGE_SCENARIOS:
            trade=pnl_at(pair,observed_entry,exitquote,finalclock,slip)
            if trade is None:
                invalid=True
                scenarios[f"{slip:.4f}"]={"pnl_rs":-round(pair["width"]*pair["qty"]+FEE_RESERVE,2),
                                        "risk_violation":True}
            else:scenarios[f"{slip:.4f}"]=trade
        if invalid:
            # Retain the baseline trade and stress failures, never silently drop
            # poor-fill scenarios. Baseline credit/risk was checked above.
            pass
        base=scenarios["0.0075"]
        if base["missing_exit_penalty"]:missingexit+=1
        record={
            "date":str(day),"expiry":str(pair["expiry"]),
            "regime":"post_CAS_AugNov2026" if day>=CAS_START else "pre_CAS",
            "side":"bull_put_credit" if pair["direction"]==1 else "bear_call_credit",
            "short_strike":pair["short"]["k"],"hedge_strike":pair["long"]["k"],
            "width":pair["width"],"qty":pair["qty"],
            "entry_time":"10:16","exit_time":finalclock,"exit_reason":reason,
            "net_pnl_rs":base["pnl_rs"],"charges_rs":base["charges_rs"],
            "contract_max_loss_est_rs":base["max_loss_rs"],
            "net_credit_pts":base["net_credit_pts"],
            "signal_credit_pts":round(signal_credit,3),
            "short_signal_iv_pct":round(pair["short"]["iv"]*100,2),
            "hedge_signal_iv_pct":round(pair["long"]["iv"]*100,2),
            "atm_signal_iv_pct":round(pair["atm_iv_pct"],2),
            "vix_prior":round(pair["vix"],2),
            "vix_prior_date":features["vix_prior_date"],
            "vix_prior_20pctile":round(features["vix_percentile20"],4),
            "vix_5session_delta":round(features["vix_5session_move"],2),
            "rv10_prior_pct":round(pair["rv10"],2),
            "breakout":pair["direction"],
            "open_movement_pct":round(features["open_move_pct"],3),
            "delta_units":round(pair["delta_units"],7),
            "gamma_units":round(pair["gamma_units"],9),
            "theta_rs_day":round(pair["theta_rs_day"],3),
            "vega_rs_ivpt":round(pair["vega_rs_ivpt"],3),
            "short_signal_OI":pair["short_oi"],
            "hedge_signal_OI":pair["long_oi"],
            "short_oi_pct_change":round(pair["short_oi_change"]*100,3),
            "oi_put_call_ratio_350pt":round(pair["pcr_350"],3),
            "short_signal_volume":pair["short"]["signal_volume"],
            "hedge_signal_volume":pair["long"]["signal_volume"],
            "signal_taylor_shock_worst_rs":round(pair["signal_taylor_shock_worst_rs"],2),
            "hypothetical_500_600_vol10_hard_loss_limit_rs":round(pair["signal_estimate_maxrisk"],2),
            "missing_exit_penalty":bool(base["missing_exit_penalty"]),
            "stress_1_5pct_net_rs":scenarios["0.0150"]["pnl_rs"],
            "stress_3pct_net_rs":scenarios["0.0300"]["pnl_rs"],
            "unmodeled_execution_risk":"OHLC proxies; no historical bid-ask/market-depth or real fill"}
        trades.append(record)
    ledger=pd.DataFrame(trades)
    if ledger.empty:
        ledger=pd.DataFrame(columns=["date","net_pnl_rs","regime","side",
              "stress_1_5pct_net_rs","stress_3pct_net_rs"])
    excluded=pd.DataFrame(rejected)
    if excluded.empty:excluded=pd.DataFrame(columns=["date","reason"])
    ledger.to_csv(out/f"AEGIS3_trades_{year}.csv",index=False)
    excluded.to_csv(out/f"AEGIS3_skips_{year}.csv",index=False)
    if len(ledger):
        assert (ledger.vix_prior_date.astype(str)<ledger.date.astype(str)).all()
        assert (ledger.contract_max_loss_est_rs<=MAX_POSITION_RISK+.01).all()
        assert (ledger.short_signal_OI>=OI_MIN).all()
        assert (ledger.hedge_signal_OI>=OI_MIN).all()
        assert (ledger.gamma_units<0).all()
        assert (ledger.theta_rs_day>0).all()
        assert (ledger.vega_rs_ivpt<0).all()
    summary={"year":year,"model":"AEGIS3 directional protective vertical credit",
      "tradability":"OHLC approximate marks, not executable bid/ask",
      "option_source_files":[str(x) for x in paths],
      "VIX_source":"prior-session India VIX close and 5-session trend",
      "sessions_with_spot_context":len(ctx),
      "option_quote_dates":len(by_date),"point_in_time_candidate_option_rows":len(q),
      "duplicate_raw_contract_minute_rows":duplicate,
      "sessions_with_prior_VIX":vixseen,"entry_missing_both_legs":entryfail,
      "conservatively_penalized_missing_exits":missingexit,
      "trading_decision_times":{"signals":"10:00 index;09:46->10:06 option OI/Greeks","entry":"10:16","exit_checkpoints":CHECKS},
      "strategy_results":stats(ledger),"by_regime":{k:stats(g) for k,g in ledger.groupby("regime")} if len(ledger) else {},
      "by_side":{k:stats(g) for k,g in ledger.groupby("side")} if len(ledger) else {},
      "skip_reasons":excluded.reason.value_counts().to_dict(),
      "model_risk_limit_rs":MAX_POSITION_RISK,
      "base_slippage_pct":.0075,"point_slippage_floor":SLIP_POINT_FLOOR,
      "prospective_unseen_holdout":False}
    (out/f"AEGIS3_summary_{year}.json").write_text(json.dumps(summary,indent=2,default=str))
    print("AEGIS3_YEAR_RESULT",json.dumps({
        "year":year,"source_days":len(by_date),"trades":len(ledger),
        "result":summary["strategy_results"],"regime":summary["by_regime"],
        "missing_exit_penalty":missingexit,
        "stress_net":{k:round(float(ledger[k].sum()),2) for k in
            ("stress_1_5pct_net_rs","stress_3pct_net_rs")},
        "skips":summary["skip_reasons"]},default=str),flush=True)
    return summary

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--year",type=int,required=True,choices=(2024,2025,2026))
    p.add_argument("--parquet",required=True)
    p.add_argument("--support",required=True)
    p.add_argument("--out",required=True)
    a=p.parse_args()
    evaluate(a.year,[pathlib.Path(x) for x in a.parquet.split(";")],
             pathlib.Path(a.support),a.out)
if __name__=="__main__":main()
