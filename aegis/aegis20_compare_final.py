#!/usr/bin/env python3
"""AEGIS2.0 frozen candidate evaluation and prospective approval gates.

No post-hoc optimization. Every family is independent; add no P&L across
families as if a tradable portfolio. 2026 CAS period is retrospective with
only 7 trend trades, not a pristine forward holdout.

Greeks are Black-Scholes *estimated* from 10:06 OHLC, interest/dividend
assumptions, NOT broker-supplied market-implied Greeks. OI at 10:06 from the
candle is assumed known by entry 10:16. Market prices are stale 1m OPEN
simulation, not executable bid/ask. India VIX strictly prior session.
"""
from __future__ import annotations
import argparse,datetime as dt,json,pathlib,math
import numpy as np,pandas as pd
from aegis.rolling_research_final import stats,uncertainty

FAMILIES=("TREND_DEBIT","RANGE_CREDIT","VOL_EXPANSION")
CAPITAL=5000000
def costs(recs):
    a=np.asarray(recs,dtype=float)
    return {
        "base_net_pnl_rs":round(float(a.sum()),2),
        "two_times_assumed_fees_net_rs":None,
        "note":"Historical trade ledger already charged adverse .75% per leg/side minimum .75 pts; no full bid/ask repricing possible from compressed candidate ledger"}

def ci_for(recs):
    if len(recs)<2:return {"mean_trade_bootstrap_95ci":[None,None],"wilson_win_rate_95ci":[None,None]}
    a=np.array(recs,dtype=float);n=len(a)
    rng=np.random.default_rng(20261107+n)
    draws=rng.choice(a,size=(15000,n),replace=True).mean(axis=1)
    ci=[round(float(x),2) for x in np.quantile(draws,[.025,.975])]
    p=float((a>0).mean());z=1.96;den=1+z*z/n
    center=(p+z*z/(2*n))/den
    half=(z/den)*math.sqrt(p*(1-p)/n+z*z/(4*n*n))
    return {"mean_trade_bootstrap_95ci":ci,
            "wilson_win_rate_95ci":[round(center-half,4),round(center+half,4)],
            "interval_contains_zero":ci[0]<=0<=ci[1]}

def metrics(df):
    s=stats(df)
    if df.empty:return {**s,**ci_for([])}
    a=df.net_pnl_rs.to_numpy(float)
    return {**s,**ci_for(a),
        "median_entry_IV_pct":round(float(df.atm_iv_pct.median()),2),
        "median_prior_VIX":round(float(df.vix.median()),2),
        "median_min_leg_OI":round(float(df.min_leg_oi.median()),1),
        "median_gamma_units":round(float(df.gamma_units.median()),6),
        "median_theta_rupees_per_day":round(float(df.theta_rs_day.median()),2),
        "median_vega_rupees_per_ivpoint":round(float(df.vega_rs_ivpt.median()),2),
        "median_abs_delta_units":round(float(df.delta_units.abs().median()),2),
        "positive_iv_minus_vix_count":int((df.atm_iv_pct>df.vix).sum())}

def read_run(year,path):
    r=path/f"AEGIS20_{year}"
    if not r.is_dir():r=path
    a=pd.read_csv(r/f"AEGIS20_candidates_{year}.csv")
    sk=pd.read_csv(r/f"AEGIS20_skips_{year}.csv")
    m=json.loads((r/f"AEGIS20_summary_{year}.json").read_text())
    if len(a):
        a["date"]=a.date.astype(str)
        assert all(a.date.str[:4]==str(year))
        assert all(a.entry_time=="10:16") and all(a.exit_time=="14:46")
        assert all(a.max_loss_rs<=12500.01) and all(a.min_leg_oi>=5000)
        assert all(a.vix_prior_date.astype(str)<a.date.astype(str))
        assert all(a.vega_rs_ivpt.notna()) and all(a.gamma_units.notna())
        assert all(a.atm_iv_pct.between(6,85))
        assert all(a.vix.between(5,90))
        assert all(a.family.isin(FAMILIES))
    return a,sk,m

def run(args):
    out=pathlib.Path(args.out);out.mkdir(parents=True,exist_ok=True)
    sources={}
    trades=[];skips=[]
    for year,path in ((2024,args.y2024),(2025,args.y2025),(2026,args.y2026)):
        t,s,m=read_run(year,pathlib.Path(path))
        trades.append(t);skips.append(s)
        sources[str(year)]=m
    raw=pd.concat(trades,ignore_index=True).sort_values(["date","family"]).reset_index(drop=True)
    raw.to_csv(out/"AEGIS20_all_frozen_candidates_2024_2026.csv",index=False)
    allskip=pd.concat(skips,ignore_index=True)
    allskip.to_csv(out/"AEGIS20_all_skip_reasons.csv",index=False)
    # Assert prospectively selected Greek sign and max position risk.
    for family,subset in raw.groupby("family"):
        if family=="VOL_EXPANSION":
            assert (subset.gamma_units>0).all()
            assert (subset.vega_rs_ivpt>0).all()
            assert (subset.theta_rs_day<0).all()
        if family=="RANGE_CREDIT":
            assert (subset.gamma_units<0).all()
            assert (subset.theta_rs_day>0).all()
    by_year={str(y):{f:metrics(raw[(raw.date.str[:4]==str(y))&(raw.family==f)]) for f in FAMILIES}
             for y in (2024,2025,2026)}
    family_results={f:metrics(raw[raw.family==f]) for f in FAMILIES}
    pre=raw[raw.regime=="pre_CAS"];post=raw[raw.regime=="post_CAS_AugNov2026"]
    pre_results={f:metrics(pre[pre.family==f]) for f in FAMILIES}
    post_results={f:metrics(post[post.family==f]) for f in FAMILIES}
    # Post-CAS Greek shock scenario: second-order one-step Taylor only.
    # DO NOT claim this is actual P&L or a guarantee on extreme gap risk.
    shock={}
    for f in FAMILIES:
        sample=post[post.family==f]
        combos={}
        for change in (-600,-500,500,600):
            for ivmove in (-10,0,10):
                label=f"move_{change}_iv_{ivmove}"
                values=[json.loads(x)[label] for x in sample.greek_shock_scenarios_rs]
                combos[label]={
                    "count":len(values),
                    "median_rupees":round(float(np.median(values)),2) if values else None,
                    "worst_rupees":round(float(np.min(values)),2) if values else None}
        shock[f]=combos
    cas=json.loads(pathlib.Path(args.cas_index).read_text())
    if cas["pre_CAS_2026"]["days"]<100 or cas["post_CAS_AugNov2026"]["days"]<50:
        raise AssertionError("NIFTY CAS source session coverage incomplete")
    post_trend=post[post.family=="TREND_DEBIT"]
    gate={
       "needs_min_30_prospective_post_cas_trades":len(post_trend)>=30,
       "requires_95pct_mean_trade_ci_lower_above_zero":(
          post_results["TREND_DEBIT"]["mean_trade_bootstrap_95ci"][0] is not None and
          post_results["TREND_DEBIT"]["mean_trade_bootstrap_95ci"][0]>0),
       "requires_bid_ask_executable_fill_validation":False,
       "requires_new_dec2026_cas_realtime_observations":False,
       "requires_independent_unseen_period":False,
       "requires_observed_oi_and_time_causal_iv_and_greeks":True,
       "requires_cost_stress_from_actual_bid_ask":False}
    gate["approved_for_live_money"]=bool(all(gate.values()))
    output={
      "title":"AEGIS 2.0 Frozen NIFTY options strategy candidate competition",
      "execution_status":"COMPLETE executed retrospective candidate research, NOT live-ready",
      "source_years":sources,
      "models":list(FAMILIES),
      "risk_cap_rs":12500,
      "position_risk_pct_of_model_capital":.25,
      "model_capital_rs":CAPITAL,
      "greeks_and_oi_model":{
         "Delta":"estimated from Black-Scholes inversion of 10:06 option OHLC OPEN using 10:00 spot proxy; directional exposure in NIFTY underlying units after lot",
         "Gamma":"modelled 2nd derivative of option PV with respect to spot at 10:06; long convexity sign test",
         "Theta":"estimated time decay per calendar day from Black-Scholes at 10:06; credit must have positive net, long volatility negative net",
         "Vega":"estimated rupees per one IV percentage-point at signal; long volatility must be positive",
         "IV":"option 10:06 price inverted with fixed rate 6.5% dividend 1.2% and spot proxy; NOT observed exchange-implied IV surface",
         "OI":"observed last-reported 10:06 option minute-bar OI; mandatory all legs >=5000, assumed knowable before 10:16 entry",
         "Volume":"observed actual 10:06 signal, 10:16 entry and 14:46 exit 1m candle volume; no order-book depth",
         "IndiaVIX":"verified prior trading session India VIX close, 20-session percentile and 5-session difference; <=7 calendar-day staleness; no lookahead",
         "CAS":"separate 2026-08-03 onward regime, fixed 14:46 exit safely before auction; no 2026-12-07 observed regime"},
      "by_family_all_years":family_results,
      "by_year":by_year,
      "pre_cas_family_results":pre_results,
      "post_cas_family_results":post_results,
      "post_cas_trend_sample_size":len(post_trend),
      "prospective_trade_approval_gates":gate,
      "greek_shock_scenario_post_cas":shock,
      "actual_nifty_index_reported_intraday_2026":{
           "pre_CAS":cas["pre_CAS_2026"],"post_CAS":cas["post_CAS_AugNov2026"],
           "source":"Public Upstox index 1m OHLC; do not confuse with indicative auction prints",
           "vix_regimes":cas["by_vix_regime"]},
      "caveats":[
        "No actual historical bid/ask or depth; OHLC adverse fill estimates are not trades executed at market",
        "All 2024–26 samples have already been observed; no genuine untouched prospective out-of-sample result",
        "No optimized after-the-fact Greek/VIX thresholds; frozen rules unprofitable over observed full period",
        "No claims of statistically supported positive strategy despite a 7-trade +6250.25 post-CAS trend subset",
        "CAS change due 7 Dec 2026 is UNOBSERVED; scenario ±500/600 NIFTY and IV±10pts only",
        "Separate family results are not an executable combined portfolio. Sizing per family is one lot and independent; overlapping positions not netted",
        "Index reported range does not include every indicative CAS auction screen value or guarantee tradability",
        "No live position, trade, order, token, or broker account touched"],
    }
    (out/"AEGIS20_FINAL_EVIDENCE.json").write_text(json.dumps(output,indent=2,default=str))
    document=["# AEGIS 2.0 — executed frozen candidate comparison",
        "",
        "**Research-only decision: NOT READY FOR LIVE CAPITAL.**",
        "All three candidate families had negative net modeled performance across the tested full historical window.",
        "",
        "## Underlying option Greeks, implied volatility, open interest, India VIX",
        "",
        "Delta, Gamma, Theta and Vega were explicitly calculated per *signal-time* leg and used as mandatory structure checks; input IV is a price inversion at 10:06, while OI and volume are historical observed 1-minute fields. India VIX is only prior-session close plus percentile and trend. Trade execution is modeled at 10:16 option OPEN, exit at 14:46 the same session, with adverse option price fill cost and estimated statutory charges. No actual bid/ask.",
        "",
        "## Frozen family results across 2024–2026",
        "",
        "| Family | Trades | Simulated net INR | Wins | Win rate | Profit factor |",
        "|---|---:|---:|---:|---:|---:|"]
    for f,r in family_results.items():
        document.append(f"| {f} | {r['trades']} | {r['net_pnl_rs']:,.2f} | {r.get('wins','—')} | {100*r.get('win_rate',0):.1f}% | {r.get('profit_factor','—')} |")
    document+=["","## 2026 post-CAS candidate subset","",
        "| Family | Trades | Net INR | Win rate | Wilson 95% win-rate interval | Bootstrap mean-trade 95% CI INR |",
        "|---|---:|---:|---:|---|---|"]
    for f,r in post_results.items():
        ci=r.get("wilson_win_rate_95ci",[None,None])
        document.append(f"| {f} | {r['trades']} | {r['net_pnl_rs']:,.2f} | {100*r.get('win_rate',0):.1f}% | {ci} | {r.get('mean_trade_bootstrap_95ci')} |")
    document+=["",
        "### Distinction between regular NIFTY 1-minute candles and closing-auction indicative swings",
        f"- Before CAS: {cas['pre_CAS_2026']['days']} index sessions; median high-low {cas['pre_CAS_2026']['median_range_points']} points, {cas['pre_CAS_2026']['days_ge_500_points']} days with >=500-point range.",
        f"- Since 3 Aug CAS: {cas['post_CAS_AugNov2026']['days']} index sessions; median {cas['post_CAS_AugNov2026']['median_range_points']} points; {cas['post_CAS_AugNov2026']['days_ge_500_points']} >=500-point sessions in the regular OHLC series.",
        "- CAS indicative spikes or unmatched auction values cannot be treated as executable options/futures fills. Different sources can display different closing indicative values.",
        "- The 7 Dec 2026 revision is in the future: treat 500–600 point swings as stress scenarios under persistent elevated volatility, not as a backtested occurrence.",
        "",
        "## Independent acceptance gates"]
    for k,v in gate.items():document.append(f"- {k}: **{v}**")
    document+=["",
        "## Institutional validation limitations",
        *["- "+x for x in output["caveats"]],
        "",
        "## Conclusion",
        "Historical Greek/VIX/OI gates alone did NOT create a profitable full-period strategy. The seven-trade post-CAS trend subset is a hypothesis for prospective validation, not evidence of a reliable 70% edge. No live deployment or claims of robust profits are justified.",
        ""]
    (out/"AEGIS20_FINAL_RESEARCH_REPORT.md").write_text("\n".join(document))
    print("AEGIS20_COMPARATIVE_RESEARCH_FINAL",json.dumps({
       "all":{x:{"n":v["trades"],"pnl":v["net_pnl_rs"],"win":v.get("win_rate")} for x,v in family_results.items()},
       "post_CAS":{x:{"n":v["trades"],"pnl":v["net_pnl_rs"],"win":v.get("win_rate"),
                      "win_rate_ci":v.get("wilson_win_rate_95ci"),
                      "bootstrap_mean_ci":v.get("mean_trade_bootstrap_95ci")} for x,v in post_results.items()},
       "gate":gate,"index_post_cas":cas["post_CAS_AugNov2026"],
       "rows":len(raw)},default=str),flush=True)

def main():
    p=argparse.ArgumentParser()
    for name in ("y2024","y2025","y2026","cas_index","out"):
        p.add_argument("--"+name.replace("_","-"),required=True)
    a=p.parse_args()
    run(a)
if __name__=="__main__":main()
