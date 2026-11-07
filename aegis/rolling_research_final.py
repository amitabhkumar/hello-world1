"""Research-only combined 2024-2026 AEGIS NIFTY evidence, no claims of live edge.

Reprices the *same* executed fixed-rule 2026 trade ledger with date-effective
2026 NSE fees, while 2024/25 ledgers are freshly executed from pinned parquet.
NEVER claims unobserved bid-ask or an untouched forward sample.
"""
from __future__ import annotations
import ast,collections,datetime as dt,json,math,pathlib,argparse
import numpy as np
import pandas as pd
from aegis import backtest_v01 as bt
from aegis.exchange_rules import RESEARCH_START,RESEARCH_END,CIRCULARS,model_scope

def trade_legs(x):
    out=ast.literal_eval(x)
    if not isinstance(out,list) or not all(isinstance(a,tuple) and len(a)==3 for a in out):
        raise ValueError("Invalid modeled trade-leg representation")
    return out

def reprice_trade(row,slip):
    # Use existing frozen strategy choices and recorded 1-minute option OPEN
    # prices; no new signal selection using the already examined 2026 records.
    legs=trade_legs(row["legs"])
    mid_entry=json.loads(row["entry_raw_open_prices"])
    mid_exit=json.loads(row["exit_raw_open_prices"])
    if len(legs)!=len(mid_entry) or len(legs)!=len(mid_exit):
        raise ValueError("Trade leg and market-price mismatch")
    def price(mid,sgn):
        p=float(mid)
        return max(.05,p+sgn*max(.75,abs(p)*slip))
    entry=[price(m,sgn) for m,(_,__,sgn) in zip(mid_entry,legs)]
    exit=[price(m,-sgn) for m,(_,__,sgn) in zip(mid_exit,legs)]
    date=dt.date.fromisoformat(str(row["date"])[:10])
    close_date=dt.date.fromisoformat(str(row["exit_timestamp"])[:10])
    qty=int(row["lot_size"])
    charge=bt.fees(date,qty,legs,entry,exit,exit_date=close_date)
    gross=sum(qty*sgn*(p1-p0) for (_,__,sgn),p0,p1 in zip(legs,entry,exit))
    return dict(net_pnl_rs=round(gross-charge["total"],2),
                gross_pnl_rs=round(gross,2),
                charges_rs=round(charge["total"],2),
                brokerage_rs=round(charge["brokerage"],2),
                stt_rs=round(charge["stt"],2),
                exchange_rs=round(charge["exchange"],2),
                gst_rs=round(charge["gst"],2))

def repriced_frame(df,slip):
    if df.empty:return df.copy()
    res=[]
    for _,row in df.iterrows():
        record=row.to_dict()
        record.update(reprice_trade(record,slip))
        res.append(record)
    return pd.DataFrame(res)

def stats(frame):
    if frame.empty:
        return {"trades":0,"net_pnl_rs":0.,"max_closed_trade_drawdown_rs":0.}
    a=frame["net_pnl_rs"].astype(float).to_numpy()
    curve=np.r_[0.,np.cumsum(a)]
    dd=np.maximum.accumulate(curve)-curve
    gains=a[a>0].sum();losses=-a[a<0].sum()
    results={"trades":int(len(a)),"net_pnl_rs":round(float(a.sum()),2),
       "mean_trade_rs":round(float(a.mean()),2),
       "median_trade_rs":round(float(np.median(a)),2),
       "wins":int((a>0).sum()),"win_rate":round(float((a>0).mean()),4),
       "profit_factor":round(float(gains/losses),3) if losses>0 else None,
       "max_closed_trade_drawdown_rs":round(float(dd.max()),2),
       "worst_trade_rs":round(float(a.min()),2),
       "worst_5pct_trade_average_rs":round(float(np.mean(np.sort(a)[:max(1,math.ceil(.05*len(a)))])),2),
       "net_return_on_assumed_50l_capital_pct":round(float(a.sum()/5000000*100),4),
       "net_without_best_one_rs":round(float(a.sum()-max(a)),2),
       "net_without_best_two_rs":round(float(a.sum()-sum(sorted(a,reverse=True)[:2])),2)}
    return results

def uncertainty(data):
    if data.empty:return {"status":"no_trades"}
    a=data["net_pnl_rs"].to_numpy(float);rng=np.random.default_rng(20261107)
    samples=rng.choice(a,size=(12000,len(a)),replace=True).mean(axis=1)
    months=data.assign(month=data.date.astype(str).str.slice(0,7))
    blocks=[r.net_pnl_rs.to_numpy(float) for _,r in months.groupby("month",sort=True)]
    # Block resampling with replacement, retaining within-month sequences.
    blockmeans=[]
    for _ in range(4000):
        draw=rng.integers(0,len(blocks),size=len(blocks))
        values=np.concatenate([blocks[i] for i in draw])
        blockmeans.append(float(values.mean()))
    return {
       "iid_bootstrap_95pct_mean_trade_rs":[round(float(x),2) for x in np.quantile(samples,[.025,.975])],
       "calendar_month_block_bootstrap_95pct_mean_trade_rs":[round(float(x),2) for x in np.quantile(blockmeans,[.025,.975])],
       "note":"Both bootstrap procedures are retrospective uncertainty diagnostics, not unseen-data proof."}

def analyze(root2024,root2025,root2026,out):
    out.mkdir(parents=True,exist_ok=True)
    frames={};baselines={};skips={};source_summary={}
    for year,root in ((2024,root2024),(2025,root2025),(2026,root2026)):
        name="AEGIS_2026_WITH_ACTIVE_PATCH" if year==2026 else f"AEGIS_BACKTEST_{year}"
        # Direct roots can also point to outputs; avoid path guessing silently.
        source=root/name if (root/name).exists() else root
        t=pd.read_csv(source/f"trades_{year}.csv")
        b=pd.read_csv(source/f"baseline_{year}.csv")
        try:
            skp=pd.read_csv(source/f"skips_{year}.csv")
        except pd.errors.EmptyDataError:
            skp=pd.DataFrame(columns=["reason"])
        summ=json.loads((source/f"summary_{year}.json").read_text())
        t["date"]=t["date"].astype(str);b["date"]=b["date"].astype(str)
        if year==2024:
            t=t[t.date>=str(RESEARCH_START)].copy()
            b=b[b.date>=str(RESEARCH_START)].copy()
        if year==2026:
            # Existing 2026 original labels from prior run are now re-costed;
            # core strategy has not changed for 2026.
            t=repriced_frame(t,.0075)
            b=repriced_frame(b,.0075)
        frames[year]=t;baselines[year]=b
        skips[year]=skp["reason"].value_counts().to_dict() if "reason" in skp else {}
        source_summary[year]={"previous_run_year":summ["year"],
              "pinned_input_quote_sample_rows":summ["quote_sample_rows"],
              "spot_sessions":summ["spot_sessions"],
              "source_model":summ["model"]}
    all_=pd.concat(list(frames.values()),ignore_index=True)
    all_=all_.sort_values(["date","exit_timestamp"]).reset_index(drop=True)
    all_bench=pd.concat(list(baselines.values()),ignore_index=True)
    all_bench=all_bench.sort_values(["date","exit_timestamp"]).reset_index(drop=True)
    if not all( RESEARCH_START<=dt.date.fromisoformat(x)<=RESEARCH_END
                for x in all_.date):
        raise AssertionError("Out-of-research-window trades detected")
    # All 2024/25 trades must match current exchange-rule expiry-based lot.
    problems=[]
    for _,r in all_.iterrows():
        d=dt.date.fromisoformat(r.date)
        exp=dt.date.fromisoformat(r.expiry)
        expect=bt.lot_size(d,exp)
        if int(r.lot_size)!=expect:
            problems.append({"date":r.date,"expiry":r.expiry,
                             "observed":int(r.lot_size),"expected":expect})
    if problems:
        raise AssertionError("Date-effective lot mismatch: "+str(problems[:4]))
    result={
        "title":"AEGIS NIFTY 06-Nov-2024 to 05-Nov-2026 fixed-rule historical research",
        "status":"COMPLETED historical-candle exploratory simulation; NOT an institutional-grade verified edge",
        "range":[str(RESEARCH_START),str(RESEARCH_END)],
        "data_sources":source_summary,
        "rule_sources":CIRCULARS,
        "brokerage_price_fees":"time-aligned modeled premium STT and exchange charges, not actual broker fills",
        "equity_model":"one lot per trade; starts at INR 50,00,000 assumed capital",
        "active_futures":"October28-November05 2026 385 each (2,695 total) verified; NOT in this v0.1 option signal model",
        "chronological_partition":{
           "development":"2024-11-06 to 2025-12-31",
           "historical_retro_eval":"2026-01-01 to 2026-11-05; repeatedly examined so NOT untouched OOS"},
        "all":stats(all_),
        "by_year":{str(k):stats(v) for k,v in frames.items()},
        "by_mode":{str(k):stats(v) for k,v in all_.groupby("mode")},
        "by_vix_regime":{str(k):stats(v) for k,v in all_.groupby("vix_regime")},
        "chronological_development":stats(all_[all_.date<"2026-01-01"]),
        "chronological_previously_seen_2026":stats(all_[all_.date>="2026-01-01"]),
        "simple_monday_straddle_benchmark":stats(all_bench),
        "bootstrap":uncertainty(all_),
        "month_bucket":{},
        "cost_stress":{},
        "near_expiry_and_gaps":{},
        "skips_by_year":skips,
        "validation_gates":{
            "raw_minute_bar_integrity":"passed for user 2026 Upstox ZIPs",
            "2026_oct_futures_gaps":"closed",
            "late_2024_lot_transition":"expiry-based NSE circular heuristic implemented; daily contract master confirmation NOT available",
            "nse_cas_2026":"F&O 15:40 closure documented from Aug03; options index and clearing auction not reconstructible",
            "expiry_calendar":"contract expiries read from source data; expiry shifted for holidays; daily exchange contract files NOT available",
            "margins":"one lot and per-trade initial debit cap; no intraday margin engine",
            "real_bid_ask":"not available",
            "orderbook_depth":"not available",
            "exchange_execution":"NOT validated",
            "prospective_oos":"NOT conducted as 2026 already used for analysis",
            "strategy_spec":"A/B/C are simplified code-defined research hypotheses, not full original institutional specification",
            "live_readiness":"FAIL—do not deploy as verified trading strategy"}}
    month=all_.assign(month=all_.date.str.slice(0,7))
    result["month_bucket"]={str(k):stats(v) for k,v in month.groupby("month")}
    costframes={}
    for slip in (.0025,.0075,.015,.03):
        repriced=repriced_frame(all_,slip)
        key=f"{slip:.4f}"
        costframes[key]=repriced
        result["cost_stress"][key]=stats(repriced)
    # Entry-to-exit session gaps and capped tail sensitivity
    all_["entry_date_dt"]=pd.to_datetime(all_.date)
    all_["exit_date_dt"]=pd.to_datetime(all_.exit_timestamp.str.slice(0,10))
    all_["calendar_holding_days"]=(all_.exit_date_dt-all_.entry_date_dt).dt.days
    result["near_expiry_and_gaps"]={
       "overnight_trades":stats(all_[all_.calendar_holding_days>=1]),
       "same_day_trades":stats(all_[all_.calendar_holding_days==0]),
       "holding_over_weekend":stats(all_[all_.calendar_holding_days>=3]),
       "reported_next_session_gap_ge_0_75pct":stats(all_[pd.to_numeric(all_["next_day_gap"],errors="coerce").abs()>=.0075]),
       "winner_count":int((all_.net_pnl_rs>0).sum())}
    all_.drop(columns=["entry_date_dt","exit_date_dt","calendar_holding_days"]).to_csv(out/"AEGIS_full_rolling_research_trade_ledger.csv",index=False)
    all_bench.to_csv(out/"AEGIS_full_rolling_research_simple_benchmark.csv",index=False)
    rows=[]
    for k,v in costframes.items():
        for _,r in v.iterrows():rows.append({"date":r["date"],"mode":r["mode"],"slip_fraction":k,"net_pnl_rs":r["net_pnl_rs"]})
    pd.DataFrame(rows).to_csv(out/"AEGIS_rolling_2024_2026_cost_stress.csv",index=False)
    (out/"AEGIS_FULL_TWO_YEAR_RESEARCH_EVIDENCE.json").write_text(json.dumps(result,indent=2,default=str))
    document=["# AEGIS NIFTY: Executed historical research, 6 Nov 2024–5 Nov 2026","",
       "**Research status:** Historical-candle modeling complete within documented limits; **no demonstrated deployable trading edge**.",
       "",
       "## Historical results after NSE contract lots and date-specific costs","",
       "| Period | Trades | Net ₹ | Win rate | Profit factor | Closed trade max drawdown ₹ |",
       "|---|---:|---:|---:|---:|---:|"]
    for k,v in [("Complete rolling window",result["all"]),*[(str(y),result["by_year"][str(y)]) for y in (2024,2025,2026)],("Chronological development 2024–25",result["chronological_development"]),("Previously-seen 2026",result["chronological_previously_seen_2026"]),("Monday straddle comparator",result["simple_monday_straddle_benchmark"])]:
        document.append(f"| {k} | {v['trades']} | {v['net_pnl_rs']:,.2f} | {v.get('win_rate',0)*100:.1f}% | {v.get('profit_factor')} | {v['max_closed_trade_drawdown_rs']:,.2f} |")
    document+=["","## Costs: fixed trades, adverse modeled execution (minimum 0.75 option pts per side)","",
       "| Slippage % of option premium per side | Net P&L ₹ |",
       "|---|---:|"]
    for k,v in result["cost_stress"].items():
        document.append(f"| {float(k)*100:.2f}% | {v['net_pnl_rs']:,.2f} |")
    document+=["","## Uncertainty and sensitivity",
        "- IID mean-trade bootstrap 95% CI: ₹"+str(result["bootstrap"]["iid_bootstrap_95pct_mean_trade_rs"])+".",
        "- Calendar-month block bootstrap mean-trade 95% CI: ₹"+str(result["bootstrap"]["calendar_month_block_bootstrap_95pct_mean_trade_rs"])+".",
        f"- Net excluding best winner: ₹{result['all']['net_without_best_one_rs']:,.2f}; excluding two best: ₹{result['all']['net_without_best_two_rs']:,.2f}.",
        "",
        "## Data and methodology gates",""]
    document.extend(f"- **{k}**: {v}" for k,v in result["validation_gates"].items())
    document+=["","## NSE rule sources",""]
    document.extend(f"- {k}: {v}" for k,v in CIRCULARS.items())
    document+=["","## Conclusions","",
        "- The results are simulated from minute OHLC, not proof of executable trades.",
        "- Contract transition 2024–2025 now uses NSE expiry-based 25/75-lot handling. Further daily contract-master review is an external data prerequisite.",
        "- 2026 previously inspected; do not call the chronological 2026 split pristine out of sample.",
        "- No actual bid/ask, order book, broker impact, CAS auction implementation or forward unseen period.",
        "- Do not deploy live until an independently positive, cost-robust prospective test and order execution quality evidence are obtained."]
    (out/"AEGIS_FULL_TWO_YEAR_RESEARCH_REPORT.md").write_text("\n".join(document)+"\n")
    print("AEGIS_FULL_TWO_YEAR_RESEARCH",json.dumps({
       "all":result["all"],"by_year":result["by_year"],
       "dev":result["chronological_development"],
       "2026":result["chronological_previously_seen_2026"],
       "cost_net":{k:v["net_pnl_rs"] for k,v in result["cost_stress"].items()},
       "bootstrap":result["bootstrap"],"late2024":result["by_year"]["2024"]},default=str),flush=True)

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--y2024",required=True)
    p.add_argument("--y2025",required=True)
    p.add_argument("--y2026",required=True)
    p.add_argument("--out",default="AEGIS_2024_2026_COMPLETE")
    args=p.parse_args()
    analyze(pathlib.Path(args.y2024),pathlib.Path(args.y2025),
            pathlib.Path(args.y2026),pathlib.Path(args.out))
if __name__=="__main__":main()
