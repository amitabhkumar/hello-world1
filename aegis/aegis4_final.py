#!/usr/bin/env python3
"""AEGIS 4.0: fixed-rule two-year multi-session NIFTY premium swing assessment.

No optimization and no actual broker orders. 2026 is already inspected in
past AEGIS runs; therefore no claim of untouched OOS is permitted.
"""
from __future__ import annotations
import argparse,datetime as dt,json,math,pathlib
import numpy as np,pandas as pd
from aegis.rolling_research_final import stats

CAPITAL=5_000_000

def confidence(df):
    if len(df)<2:return {"n":len(df),"wilson95_win_rate":[None,None],
                         "iid95_mean_trade_rs":[None,None],
                         "month_block95_mean_trade_rs":[None,None]}
    p=np.asarray(df.net_pnl_rs,dtype=float)
    n=len(p);w=(p>0).sum()/n
    z=1.96;den=1+z*z/n
    mid=(w+z*z/(2*n))/den
    half=z/den*math.sqrt(w*(1-w)/n+z*z/(4*n*n))
    rng=np.random.default_rng(20261107+n)
    iid=rng.choice(p,size=(12_000,n),replace=True).mean(axis=1)
    month_blocks=[g.net_pnl_rs.to_numpy(float) for _,g in df.groupby(df.date.str[:7])]
    means=[]
    for _ in range(5000):
        sel=rng.integers(0,len(month_blocks),size=len(month_blocks))
        v=np.concatenate([month_blocks[i] for i in sel])
        means.append(float(v.mean()))
    return {"n":n,"wilson95_win_rate":[round(float(mid-half),4),round(float(mid+half),4)],
      "iid95_mean_trade_rs":[round(float(q),2) for q in np.quantile(iid,[.025,.975])],
      "month_block95_mean_trade_rs":[round(float(q),2) for q in np.quantile(means,[.025,.975])]}

def report(df):
    value=stats(df)
    value["uncertainty"]=confidence(df)
    if len(df)==0:return value
    p=df.net_pnl_rs.to_numpy(float)
    win=p[p>0];loss=p[p<0]
    value.update({
      "wins":int(len(win)),"losses":int(len(loss)),
      "avg_winning_trade_rs":round(float(win.mean()),2) if len(win) else None,
      "avg_losing_trade_rs":round(float(loss.mean()),2) if len(loss) else None,
      "average_winner_over_abs_average_loser":round(float(win.mean()/-loss.mean()),3) if len(win) and len(loss) else None,
      "total_gross_market_pnl_rs":round(float(df.gross_pnl_rs.sum()),2),
      "total_modelled_charges_rs":round(float(df.charges_rs.sum()),2),
      "median_initial_credit_points":round(float(df.credit_pts.median()),2),
      "median_calendar_nights_held":float(df.calendar_hold_days.median()),
      "mean_calendar_nights_held":round(float(df.calendar_hold_days.mean()),2),
      "overnight_trades":int(df.overnight.sum()),
      "exit_unpriced_penalty_trades":int(df.missing_exit_full_loss_penalty.sum()),
      "slippage_1_5pct_pnl_rs":round(float(df.stress_1_5pct_net_rs.sum()),2),
      "slippage_3pct_pnl_rs":round(float(df.stress_3pct_net_rs.sum()),2),
      "theoretical_expiry_gross_proxy_trade_count":int(df.hypothetical_gross_expiry_payoff_using_index_close_NOT_OFFICIAL_rs.notna().sum()),
      "theoretical_expiry_gross_proxy_sum_NOT_RESULT_rs":
         round(float(df.hypothetical_gross_expiry_payoff_using_index_close_NOT_OFFICIAL_rs.sum()),2),
      "max_single_contract_expiry_loss_rs":round(float(df.max_contract_risk_rs.max()),2)})
    return value

def run(args):
    out=pathlib.Path(args.out);out.mkdir(parents=True,exist_ok=True)
    summaries={};ledgers=[];skips=[]
    for year,p in ((2024,args.y2024),(2025,args.y2025),(2026,args.y2026)):
        base=pathlib.Path(p)
        if (base/f"AEGIS4_{year}").exists():base=base/f"AEGIS4_{year}"
        s=json.loads((base/f"AEGIS4_swing_summary_{year}.json").read_text())
        t=pd.read_csv(base/f"AEGIS4_swing_trades_{year}.csv")
        r=pd.read_csv(base/f"AEGIS4_swing_skips_{year}.csv")
        summaries[str(year)]=s
        if len(t):
            t["date"]=t.date.astype(str)
            t["exit_date"]=t.exit_date.astype(str)
            assert (t.date.str[:4]==str(year)).all()
            assert (t.vix_prior_date.astype(str)<t.date).all()
            assert (t.exit_date>=t.date).all()
            assert (t.exit_date<=t.expiry.astype(str)).all()
            assert (t.max_contract_risk_rs<=10000.01).all()
            assert (t.Gamma_lot<0).all() and (t.Theta_rupees_day>0).all() and (t.Vega_rupees_ivpoint<0).all()
            assert (t.short_signal_oi>=5000).all() and (t.hedge_signal_oi>=5000).all()
            assert (t.entry_clock=="10:16").all()
            assert t.groupby("date").size().max()==1
        ledgers.append(t);skips.append(r)
    trades=pd.concat(ledgers,ignore_index=True).sort_values("date").reset_index(drop=True)
    if len(trades)==0:raise AssertionError("No completed historical swing trades")
    if (pd.to_datetime(trades.date)<pd.to_datetime("2024-11-06")).any():raise AssertionError("Before start")
    if (pd.to_datetime(trades.exit_date)>pd.to_datetime("2026-11-05")).any():raise AssertionError("After cutoff")
    if trades.duplicated("date").any():raise AssertionError("Overlapping opening trades")
    for prev,next_ in zip(trades.itertuples(),list(trades.itertuples())[1:]):
        assert str(prev.exit_date)<str(next_.date),("Overlapping open swing trades",prev,next_)
    # Independent post-execution, unchanged-trade Greek scenario audit.
    # A 500/600-point move makes a local Taylor model inaccurate once the
    # short and long strike are crossed; NEVER interpret these as actual
    # future option values, broker stop fills or hard expiry loss limits.
    greek_shocks={}
    for shift in (-600,-500,500,600):
        for iv_change in (-10,0,10):
            vals=(trades.Delta_lot*shift+
                  .5*trades.Gamma_lot*(shift**2)+
                  trades.Vega_rupees_ivpoint*iv_change)
            greek_shocks[f"spot_{shift:+}_IV_{iv_change:+}_volpts"]={
              "count":int(len(vals)),
              "median_local_Taylor_rs":round(float(vals.median()),2),
              "worst_local_Taylor_rs":round(float(vals.min()),2),
              "warning":"Local Greek approximation breaks down for 500/600-point moves; NOT executable option P&L"}
    all_=report(trades)
    per_year={str(y):report(trades[trades.date.str[:4]==str(y)]) for y in (2024,2025,2026)}
    cas={k:report(v) for k,v in trades.groupby("regime")}
    exits={k:report(v) for k,v in trades.groupby("exit_reason")}
    sides={k:report(v) for k,v in trades.groupby("side")}
    # Predeclared independent research gates; not retuned after outcome.
    low=all_["uncertainty"]["wilson95_win_rate"][0]
    gates={
      "net_profitable_after_costs":all_["net_pnl_rs"]>0,
      "profit_factor_at_least_1_30":all_.get("profit_factor") is not None and all_["profit_factor"]>=1.30,
      "win_rate_at_least_60pct":all_["win_rate"]>=.60,
      "win_rate_wilson_lower_95pct_at_least_50pct":low is not None and low>=.50,
      "strict_max_loss_defined_at_entry":bool((trades.max_contract_risk_rs<=10000.01).all()),
      "no_unbounded_short_options":True,
      "slippage_1_5pct_net_positive":all_["slippage_1_5pct_pnl_rs"]>0,
      "slippage_3pct_net_positive":all_["slippage_3pct_pnl_rs"]>0,
      "monthly_block_bootstrap_mean_lower_above_zero":
         all_["uncertainty"]["month_block95_mean_trade_rs"][0]>0,
      "historical_actual_bid_ask_and_depth":False,
      "historical_official_expiry_CAS_settlement_reconciled":False,
      "broker_margin_and_gap_liquidation_verified":False,
      "genuine_unseen_future_30_trades":False,
      "future_Dec_7_CAS_observed":False}
    gates["approved_for_live_trading"]=all(gates.values())
    q={
      "name":"AEGIS 4.0 — NIFTY SWING 3–9 DTE directional credit vertical",
      "research_status":"executed exploratory swing-to-expiry-session historical replay",
      "window":["2024-11-06","2026-11-05"],
      "user_trading_style":"swing / holding multiple sessions to expiry if the strategy allows",
      "data_provenance":{
         "2024_2025":"checksum-pinned public NIFTY one-minute derivatives and separate NIFTY index and India VIX context",
         "2026":"read-only user Upstox complete options ZIP, active contract supplement, public index/IndiaVIX and verified ancillary audit",
         "VIX":"previous completed market session, never current day's unknown finish",
         "OI":"observed historical OI at 09:46 and 10:06, not execution queue",
         "greeks":"Black-Scholes inferred IV, Delta, Gamma, Theta, Vega, not broker bid/ask greeks",
         "expiry_settlement":"not reconstructed from NSE official settlement files; primary exits pre-auction at 14:46 on expiry session"},
      "chronology":"trade selection before 10:16, risk observations at 10:06 or 14:40, executions at 10:16 or 14:46 on current/future sessions; no overlapping trades",
      "risk_policy":{
        "capital_rs":CAPITAL,"max_initial_contract_loss_including_500_fee_reserve_rs":10000,
        "single_active_trade":True,"per_expiry_entry_once":True,
        "short_option_delta_range":[.18,.30],
        "vix_prior_level_range":[11,45],
        "long_hedge_widths_points":[100,150,200],
        "expiry_days_at_entry":[3,9],
        "credit_capture_profit_target_pct":60,
        "credit_buyback_stop_multiple":2.3,
        "exit_on_expiry_session":"14:46 pre-CAS pre-settlement",
        "no_overnight_after_expiry":True,
        "no_rolling_or_adding_to_loss":True},
      "all":all_,"by_year":per_year,"by_CAS_regime":cas,
      "by_exit_reason":exits,"by_option_spread_type":sides,
      "annual_source_quality":summaries,
      "extreme_500_600_spot_IV_plus_minus_10pt_Greek_scenarios_NOT_REALIZED":greek_shocks,
      "all_skips":pd.concat(skips,ignore_index=True).reason.value_counts().to_dict(),
      "previous_AEGIS3_same_day_comparator":{
          "trades":22,"net_pnl_rs":-7213.22,
          "win_rate":.2273,"not_matched_trade_paired_comparison":True},
      "counterfactual_expiry_payoff_caveat":"Underlying 5m index CLOSE proxy, gross intrinsic only; NOT NSE final cash settlement or exercise tax. It is NOT added to primary P&L.",
      "trade_gates":gates,
      "prospective_sample_qualification":"FAIL; 2026 was inspected repeatedly under AEGIS 1–3; 7 December CAS not yet observed",
      "decision":"NOT APPROVED unless all gates pass; do not infer high odds from historical percentage alone"}
    (out/"AEGIS4_FULL_SWING_EVIDENCE.json").write_text(json.dumps(q,indent=2,default=str))
    trades.to_csv(out/"AEGIS4_2024_2026_ALL_SWING_TRADES.csv",index=False)
    pd.concat(skips,ignore_index=True).to_csv(out/"AEGIS4_2024_2026_ALL_REJECTED_SESSIONS.csv",index=False)
    md=[
      "# AEGIS 4.0 — executed NIFTY multi-day swing option credit spread research",
      "",
      "**Research decision: "+("APPROVED" if gates["approved_for_live_trading"] else "NOT APPROVED for live trading")+".**",
      "This is the first AEGIS version that allows actual **overnight multi-session holding through the expiry trading session**. It is NOT a same-day Theta strategy.",
      "",
      "## Actual historical results",
      "",
      "| Period | Trades | Wins | Win rate | Net modeled P&L INR | Profit factor | Max closed trade DD INR |",
      "|---|---:|---:|---:|---:|---:|---:|"]
    for key,val in [("2024",per_year["2024"]),("2025",per_year["2025"]),("2026",per_year["2026"]),("Total",all_)]+list(cas.items()):
        md.append(f"| {key} | {val['trades']} | {val.get('wins',0)} | {val.get('win_rate',0)*100:.1f}% | {val['net_pnl_rs']:,.2f} | {val.get('profit_factor')} | {val['max_closed_trade_drawdown_rs']:,.2f} |")
    md+=["",
        "## Premium capture and tail-loss decomposition",
        f"- Winning average modeled P&L: INR{all_.get('avg_winning_trade_rs')} vs losing average INR{all_.get('avg_losing_trade_rs')}.",
        f"- Median credit received {all_['median_initial_credit_points']} premium points; median nights held {all_['median_calendar_nights_held']}.",
        f"- Gross simulated P&L before charges: INR{all_['total_gross_market_pnl_rs']:,.2f}; modeled total charges: INR{all_['total_modelled_charges_rs']:,.2f}.",
        "- Profit targets are checked at future-session observed option prices. All risk-stop losses and unpriced full-loss penalties count in the ledger.",
        "",
        "## Robustness",
        f"- Base 0.75% adverse slippage model P&L INR{all_['net_pnl_rs']:,.2f}.",
        f"- 1.50% adverse slippage P&L INR{all_['slippage_1_5pct_pnl_rs']:,.2f}.",
        f"- 3.00% adverse slippage P&L INR{all_['slippage_3pct_pnl_rs']:,.2f}.",
        f"- IID 95% mean-trade bootstrap interval INR{all_['uncertainty']['iid95_mean_trade_rs']}.",
        f"- Month-block 95% mean-trade bootstrap interval INR{all_['uncertainty']['month_block95_mean_trade_rs']}.",
        f"- Wilson 95% winning-proportion interval {all_['uncertainty']['wilson95_win_rate']}.",
        "",
        "## Indicative +/-500/600-point and +/-10 IV-vol-point Greek shocks",
        "- The final evidence JSON includes per-scenario median/worst local Delta-Gamma-Vega projections for the recorded entries.",
        "- These are **NOT** actual executable P&L or even valid large-shock option prices: a short vertical's curvature changes nonlinearly across the strikes. Actual contractual expiry risk is bounded; pre-expiry liquidity/exit losses are not proven.",
        "",
        "## Data, Greeks, CAS and settlement discipline",
        "- India VIX prior-session level/trend/percentile; historical option OI growth and liquidity, estimated BS option IV, Delta, Gamma, Theta, Vega and 10-day realized volatility are required on every entry.",
        "- No naked short option; bounded spread contractual expiry loss. Intra-session stop fills and adverse gaps can still be worse than modeled.",
        "- Entries use only previous 09:46/10:06 and cash 10:00 known information; 10:16 execution, future risk checks at 10:06 and 14:40, executed option OHLC proxy at 10:16 and 14:46.",
        "- Expiry-day exit at 14:46 prevents counting unverified CAS final settlement pricing. Optional cash-intrinsic scenarios use an index close PROXY excluding exercise STT, NOT official NSE settlements.",
        "- The December 7 2026 revised CAS regime has not yet begun; do not assume actual observed 500–600 point price swings from historical indicative prints are executable.",
        "- Historical option bid/ask, market depth, broker margin calls, actual exchange settlement and order execution quality are unavailable; these block institutional live-readiness.",
        "",
        "## Historical acceptance gates"]
    for name,value in gates.items():md.append(f"- {name}: **{value}**")
    md+=["","**Do not change these observed outcomes to fit the user's desired win rate.** Strategy conditions and exit management were frozen before backtesting across 2024/25 and 2026."]
    (out/"AEGIS4_FULL_SWING_RESEARCH_REPORT.md").write_text("\n".join(md)+"\n")
    print("AEGIS4_FULL_HISTORICAL_RESULT",json.dumps({
      "total":all_,"year":{k:{"n":v["trades"],"pnl":v["net_pnl_rs"],"win":v.get("win_rate")} for k,v in per_year.items()},
      "CAS":{k:{"n":v["trades"],"pnl":v["net_pnl_rs"],"win":v.get("win_rate")} for k,v in cas.items()},
      "exits":{k:{"n":v["trades"],"pnl":v["net_pnl_rs"]} for k,v in exits.items()},
      "live_approved":gates["approved_for_live_trading"]},default=str),flush=True)

def main():
    p=argparse.ArgumentParser()
    for key in ("y2024","y2025","y2026","out"):
        p.add_argument("--"+key,required=True)
    run(p.parse_args())
if __name__=="__main__":main()
