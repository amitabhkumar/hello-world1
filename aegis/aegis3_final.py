#!/usr/bin/env python3
"""AEGIS 3.0 final fixed-rule NIFTY defined-risk credit-spread evaluation.

Reject unproven high-win marketing. No parameter fitting after outcomes.
2026 has been inspected under AEGIS 1/2, so not pristine OOS.
Any small CAS-subset profit is a research observation only.
"""
from __future__ import annotations
import argparse,collections,datetime as dt,json,math,pathlib
import numpy as np,pandas as pd
from aegis.rolling_research_final import stats

THRESHOLDS={
  "profit_factor_min":1.30,
  "net_expectancy_positive":True,
  "win_rate_target":.60,
  "wilson_lower_bound_wins_at_least":.50,
  "drawdown_cap_pct_capital":5.,
  "position_max_risk_rs":10000.,
  "daily_risk_cap_rs":25000.,
  "min_genuinely_future_prospective_trades":30,
  "high_slippage_1_5_percent_net_positive":True,
  "high_slippage_3_percent_net_positive":True,
}

def bootstrap(values,seed=20261107):
    v=np.asarray(values,dtype=float);n=len(v)
    if n<2:return {"n":n,"win_rate_wilson_95":[None,None],
                     "mean_trade_bootstrap_95":[None,None],
                     "mean_trade_month_block_bootstrap_95":[None,None]}
    p=float((v>0).mean());z=1.96
    den=1+z*z/n
    mid=(p+z*z/(2*n))/den
    d=z/den*math.sqrt(p*(1-p)/n+z*z/(4*n*n))
    rng=np.random.default_rng(seed+n)
    samples=rng.choice(v,size=(15000,n),replace=True).mean(axis=1)
    return {"n":n,"win_rate_wilson_95":[round(mid-d,4),round(mid+d,4)],
            "mean_trade_bootstrap_95":[round(float(x),2) for x in np.quantile(samples,[.025,.975])]}

def evaluated(frame):
    a=stats(frame)
    if len(frame):
        a.update(bootstrap(frame.net_pnl_rs))
        a["stress_slippage_1_5pct_net_rs"]=round(float(frame.stress_1_5pct_net_rs.sum()),2)
        a["stress_slippage_3pct_net_rs"]=round(float(frame.stress_3pct_net_rs.sum()),2)
        a["bull_put_trades"]=int((frame.side=="bull_put_credit").sum())
        a["bear_call_trades"]=int((frame.side=="bear_call_credit").sum())
        a["win_proportion"]=round(float((frame.net_pnl_rs>0).mean()),4)
        a["min_oi_per_leg"]=round(float(np.minimum(frame.short_signal_OI,frame.hedge_signal_OI).min()),1)
        a["median_prior_vix"]=round(float(frame.vix_prior.median()),1)
        a["median_short_iv_pct"]=round(float(frame.short_signal_iv_pct.median()),1)
        a["median_net_credit_pts"]=round(float(frame.net_credit_pts.median()),2)
        a["stale_or_missing_exits_assigned_full_loss"]=int(frame.missing_exit_penalty.sum())
    return a

def run(args):
    out=pathlib.Path(args.out);out.mkdir(parents=True,exist_ok=True)
    records=[];years={};rawskips=[]
    for yr,path in ((2024,args.y2024),(2025,args.y2025),(2026,args.y2026)):
        directory=pathlib.Path(path)
        if (directory/f"AEGIS3_{yr}").exists():directory=directory/f"AEGIS3_{yr}"
        ledger=pd.read_csv(directory/f"AEGIS3_trades_{yr}.csv")
        skips=pd.read_csv(directory/f"AEGIS3_skips_{yr}.csv")
        report=json.loads((directory/f"AEGIS3_summary_{yr}.json").read_text())
        if len(ledger):
            ledger["date"]=ledger.date.astype(str)
            assert (ledger.date.str[:4]==str(yr)).all()
            assert (ledger.vix_prior_date.astype(str)<ledger.date).all()
            assert (ledger.contract_max_loss_est_rs<=10000.01).all()
            assert (ledger.short_signal_OI>=5000).all() and (ledger.hedge_signal_OI>=5000).all()
            assert (ledger.gamma_units<0).all() and (ledger.theta_rs_day>0).all()
            assert (ledger.vega_rs_ivpt<0).all()
            assert (ledger.entry_time=="10:16").all()
            assert ledger.groupby("date").size().max()<=1
        records.append(ledger);rawskips.append(skips)
        years[str(yr)]=report
    trades=pd.concat(records,ignore_index=True).sort_values("date").reset_index(drop=True)
    if not len(trades):raise AssertionError("No executed historical trades; cannot report performance")
    assert not trades.duplicated(["date","side"]).any()
    assert not (trades.date<"2024-11-06").any()
    assert not (trades.date>"2026-11-05").any()
    families={"all":evaluated(trades),
         "pre_CAS":evaluated(trades[trades.regime=="pre_CAS"]),
         "post_CAS_AugNov2026":evaluated(trades[trades.regime=="post_CAS_AugNov2026"])}
    by_year={str(y):evaluated(trades[trades.date.str[:4]==str(y)])
             for y in (2024,2025,2026)}
    by_side={side:evaluated(frame) for side,frame in trades.groupby("side")}
    # IID bootstrap not enough when sessions correlated. Block-sample by
    # month, preserving all trade P&Ls and their chronological order.
    months=[grp.net_pnl_rs.to_numpy(float) for _,grp in
            trades.groupby(trades.date.str[:7],sort=True)]
    rng=np.random.default_rng(20261107)
    blockmean=[]
    for _ in range(5000):
        s=rng.integers(0,len(months),len(months))
        values=np.concatenate([months[i] for i in s])
        blockmean.append(float(values.mean()))
    families["all"]["monthly_block_bootstrap_95_mean_trade_rs"]=[
       round(float(x),2) for x in np.quantile(blockmean,[.025,.975])]
    # Actual pre/post CAS historical index OHLC and VIX separately verified.
    index=json.loads(pathlib.Path(args.cas_index).read_text())
    if index["post_CAS_AugNov2026"]["days"]<60 or index["pre_CAS_2026"]["days"]<140:
        raise AssertionError("CAS index reference coverage too small")
    # Decisions: strictly no live trading on investigated historical data.
    main=families["all"]
    wins=main.get("win_rate_wilson_95",[None,None])
    pass_metrics={
        "positive_net_after_costs":main["net_pnl_rs"]>0,
        "profit_factor_ge_1_30":main.get("profit_factor") is not None and main["profit_factor"]>=1.3,
        "observed_win_rate_ge_60pct":main["win_rate"]>=.60,
        "win_rate_95pct_lower_bound_ge_50pct":wins[0] is not None and wins[0]>=.50,
        "max_closed_trade_drawdown_le_5pct_capital":main["max_closed_trade_drawdown_rs"]<=250000,
        "net_after_1_5pct_slippage_positive":main["stress_slippage_1_5pct_net_rs"]>0,
        "net_after_3pct_slippage_positive":main["stress_slippage_3pct_net_rs"]>0,
        "at_least_30_pristine_future_trades":False,
        "actual_executable_bid_ask_depth":False,
        "CAS_regime_from_07Dec2026_observed":False}
    # No validity claims even if all historical metrics pass on known data.
    pass_metrics["institutional_live_approved"]=all(pass_metrics.values())
    q={
      "name":"AEGIS3 trend-aligned bounded credit vertical",
      "result_status":"EXECUTED exploratory historic backtest (research-only)",
      "research_window":["2024-11-06","2026-11-05"],
      "user_goal":"High probability NIFTY F&O risk-defined and positive expectancy through CAS and high volatility",
      "capital_assumed_rs":5000000,
      "risk_policy":{"max_spread_risk_at_entry_including_fee_reserve_rs":10000,
                     "daily_aggregate_risk_ceiling_rs":25000,"positions_per_day":1,
                     "expiry_days_to_eligibility":[4,12],"exit_before_CAS":"14:46 IST",
                     "no_overnight_exposure":True},
      "source_years":years,
      "metrics":families,
      "by_year":by_year,"by_side":by_side,
      "full_period_skips":pd.concat(rawskips,ignore_index=True).reason.value_counts().to_dict(),
      "cash_index_CAS_evidence":{"pre_2026":index["pre_CAS_2026"],
         "post_AugNov2026":index["post_CAS_AugNov2026"],
         "caveat":"OHLC regular index candles; CAS indicative swings are not necessarily executable"},
      "uncertainty_note":"IID and month-block bootstrap are descriptive retrospective, not untouched forward OOS",
      "acceptance_thresholds":THRESHOLDS,
      "approval_gates":pass_metrics,
      "required_live_evidence_missing":[
        "historical executable bid-ask, order-book depths and contract notes",
        "actual 1m options price-quality / OI update latency exchange reconciliation",
        "broker order queue, slippage and margin liquidation simulations",
        "unseen real Dec-2026+ CAS settlement regime with prospective paper-only performance",
        "genuine untouched prospective holdout, not 2026 previously examined multiple times",
        "static BSM implied vols used instead of executable skew term structure"],
      "declaration":"The engine is a new frozen candidate, not an institutional-grade, positive expected-return strategy unless gates pass."}
    (out/"AEGIS3_FINAL_RESEARCH_EVIDENCE.json").write_text(json.dumps(q,indent=2,default=str))
    trades.to_csv(out/"AEGIS3_REPRODUCIBLE_TRADE_LEDGER_2024_2026.csv",index=False)
    pd.concat(rawskips,ignore_index=True).to_csv(out/"AEGIS3_ALL_REJECTED_SESSIONS.csv",index=False)
    sections=[
      "# AEGIS 3.0 — Executed NIFTY directional defined-risk credit research",
      "",
      "**No claims of a winning strategy before validated evidence.** No live orders were placed.",
      "",
      "## Frozen rules",
      "",
      "- Direction: 09:15–09:40 NIFTY opening range, 09:55 and 10:00 index closes, same-direction drift >=0.20%, confirmed prior-day direction.",
      "- India VIX: only previous full trading day's close, >=12 and <=38, historical 20-session percentile >=20%, 5-session increase <=4 volatility points.",
      "- Volatility premium: 10:06 option ATM IV model inversion >=1.08x prior 10-session realized vol and >=0.87x prior India VIX.",
      "- Directional option: bullish put or bearish call sold at 0.12–0.25 modeled absolute delta (~0.18 target), same-side long further-OTM hedge at one of 100/150/200/250 strike-width points.",
      "- Short option OI >=5,000 and nondecreasing between 09:46 and 10:06; hedge OI >=5,000 and not collapsing >15%.",
      "- OI PE/CE ratio across 350 NIFTY spot points must be 0.35–3.0. Historical OI is not order-side attribution.",
      "- Greeks pre-entry: net positive Theta, negative Gamma and Vega, directional signed Delta. All Greek values modelled via Black–Scholes using 10:06 option OHLC OPEN, not exchange-quoted IV.",
      "- Minimum modeled signal premium credit 8% of spread width; risk <=INR10,000 including estimated INR500 closing cost reserve; <=1 trade/day.",
      "- Execute proxy entry at 10:16 OPEN. Observe 11:10/12:10/13:10/14:40 signals, execute 6min later: profit target when buyback <=50% original credit, stop at >=2x credit, otherwise forced exit 14:46.",
      "- Slippage per option leg/side min INR0.75 premium or .75%; enhanced adverse slippage 1.5% and 3% sensitivity. Actual executable bid/ask unavailable.",
      "",
      "## Executed model outcomes",
      "",
      "| Cohort | Trades | Simulated net P&L INR | Win rate | Profit factor | Max closed-trade drawdown INR |",
      "|---|---:|---:|---:|---:|---:|"]
    for label,values in [(str(y),v) for y,v in by_year.items()]+[(k,v) for k,v in families.items()]:
        sections.append(f"| {label} | {values['trades']} | {values['net_pnl_rs']:,.2f} | {100*values.get('win_rate',0):.1f}% | {values.get('profit_factor','—')} | {values['max_closed_trade_drawdown_rs']:,.2f} |")
    sections+=["","### Costs and uncertainty",
      f"- Baseline 0.75% slippage net: **INR{main['net_pnl_rs']:,.2f}**.",
      f"- Higher 1.5% slippage net: **INR{main['stress_slippage_1_5pct_net_rs']:,.2f}**.",
      f"- Higher 3.0% slippage net: **INR{main['stress_slippage_3pct_net_rs']:,.2f}**.",
      f"- IID bootstrap mean P&L 95%: **INR{main['mean_trade_bootstrap_95']}**.",
      f"- Month-block bootstrap mean P&L 95%: **INR{main['monthly_block_bootstrap_95_mean_trade_rs']}**.",
      "",
      "### CAS and large NIFTY movements",
      f"- Index historical regular-minute pre-Aug-2026 median 1m daily high–low **{index['pre_CAS_2026']['median_range_points']} points**, versus Aug–Nov **{index['post_CAS_AugNov2026']['median_range_points']} points**.",
      "- Hypothetical ±500/600 NIFTY-point spot shocks and ±10 IV percentage-point Taylor approximations are stress assumptions, not claims of actual option-price execution.",
      "- Future 7-Dec-2026 CAS settlement changes cannot be backtested from sessions that have not yet occurred; no trades run through the closing auction.",
      "",
      "## Institutional go/no-go criteria",
      ""]
    sections.extend(f"- {k}: **{'PASS' if v else 'FAIL'}**" for k,v in pass_metrics.items())
    sections+=["","**Decision:** " + ("APPROVED" if pass_metrics["institutional_live_approved"] else "NOT APPROVED for live trading."),
                "No parameter changes were made to make earlier-year losses disappear.",
                "Historical one-minute price bars are not a substitute for executable bid-ask, order-book or broker contract notes."]
    (out/"AEGIS3_FINAL_REPORT.md").write_text("\n".join(sections)+"\n")
    print("AEGIS3_FULL_HISTORICAL_RESULT",json.dumps({
       "all":main,
       "annual":{k:{"trades":v["trades"],"net_pnl_rs":v["net_pnl_rs"]} for k,v in by_year.items()},
       "post_CAS":families["post_CAS_AugNov2026"],
       "gates":pass_metrics,
       "count":len(trades)},default=str),flush=True)

def main():
    p=argparse.ArgumentParser()
    for k in ("y2024","y2025","y2026","cas_index","out"):
        p.add_argument("--"+k.replace("_","-"),required=True)
    run(p.parse_args())
if __name__=="__main__":main()
