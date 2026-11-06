#!/usr/bin/env python3
"""AEGIS 2026 stitched candle replay robustness report.

This is a static ledger postprocessor, NOT strategy optimization.
All output explicitly labels the non-pristine 2026 exploratory data and the
missing active November derivatives sessions. No bid/ask data or actual fills.
"""
from __future__ import annotations
import argparse,ast,datetime as dt,json,math,pathlib
import numpy as np,pandas as pd
from aegis.backtest_v01 import fees

def stats(trades):
    if trades.empty:return {"n":0,"net_pnl_rs":0}
    a=trades.net_pnl_rs.to_numpy(dtype=float)
    n=len(a);net=float(a.sum())
    eq=a.cumsum();dd=(np.maximum.accumulate(np.r_[0.0,eq])[1:]-eq).max()
    pos=a[a>0].sum();neg=-a[a<0].sum()
    rng=np.random.default_rng(20261106+n)
    boot=rng.choice(a,size=(10000,n),replace=True).mean(axis=1)
    ci=[round(float(v),2) for v in np.quantile(boot,[.025,.975])]
    p=float((a>0).mean());z=1.96;den=1+z*z/n
    center=(p+z*z/(2*n))/den
    half=(z/den)*np.sqrt(p*(1-p)/n+z*z/(4*n*n))
    desc=np.sort(a)[::-1]
    return {
      "n":n,"wins":int((a>0).sum()),"win_rate":round(p,4),
      "net_pnl_rs":round(net,2),"expectancy_rs":round(net/n,2),
      "median_trade_rs":round(float(np.median(a)),2),
      "profit_factor":round(float(pos/neg),3) if neg else None,
      "drawdown_closed_trade_rs":round(float(dd),2),
      "worst_trade_rs":round(float(a.min()),2),
      "cvar_worst_5pct_rs":round(float(np.sort(a)[:max(1,math.ceil(.05*n))].mean()),2),
      "bootstrap_iid_mean_trade_95ci_rs":ci,
      "wilson_win_rate_95ci":[round(float(center-half),4),round(float(center+half),4)],
      "net_without_best_trade_rs":round(float(net-desc[0]),2),
      "net_without_best_two_trades_rs":round(float(net-desc[:2].sum()),2),
      "net_on_50l_capital_pct":round(net/5000000*100,4)}
def net_repriced(row,slippage_pct):
    legs=ast.literal_eval(row.legs)
    first=json.loads(row.entry_raw_open_prices)
    last=json.loads(row.exit_raw_open_prices)
    size=int(row.lot_size)
    def fill(mid,sgn):
        mid=float(mid)
        return max(.05,mid+sgn*max(.75,mid*slippage_pct))
    buys=[fill(x,sgn) for x,(_,__,sgn) in zip(first,legs)]
    sells=[fill(x,-sgn) for x,(_,__,sgn) in zip(last,legs)]
    f=fees(dt.date.fromisoformat(row.date),size,legs,buys,sells)
    return size*sum(sgn*(end-start)
        for (_,__,sgn),start,end in zip(legs,buys,sells))-f["total"]
def main():
    p=argparse.ArgumentParser()
    p.add_argument("--input",default="INPUT/AEGIS_2026_EXTENSION")
    p.add_argument("--out",default="AEGIS_2026_ROBUSTNESS")
    a=p.parse_args()
    root=pathlib.Path(a.input);out=pathlib.Path(a.out)
    out.mkdir(parents=True,exist_ok=True)
    t=pd.read_csv(root/"trades_2026.csv")
    b=pd.read_csv(root/"baseline_2026.csv")
    periods={
      "2026_jan01_apr21":t[t.date<="2026-04-21"],
      "2026_apr22_jul21":t[(t.date>="2026-04-22")&(t.date<="2026-07-22")],
      "2026_jul22_nov03":t[(t.date>="2026-07-21")&(t.date<="2026-11-04")]
    }
    report={
      "title":"AEGIS NIFTY 2026 extended options-candle research",
      "classification":"exploratory, previously reviewed 2026, NOT untouched OOS",
      "strategy_model":"AEGIS v0.1 approximated mode rules, 1-min candle opens and 15m monitoring, one lot",
      "source":"Verified Upstox 2026 July22-Nov03 options; public Jan-Jul21 options; stitched spot 2026; partial VIX",
      "missing":"Nov04-Nov05 option candles and Oct28-Nov05 futures; no bid-ask or depth",
      "all_2026":stats(t),
      "fixed_monday_straddle_benchmark":stats(b),
      "by_period":{k:stats(v) for k,v in periods.items()},
      "by_mode":{k:stats(t[t["mode"]==k]) for k in sorted(t["mode"].dropna().unique())},
      "cost_model":"Reprice SAME exact trades at alternative adverse premium slippage; does not reoptimize signals/exits.",
      "cost_sensitivity":{},
      "limitations":[
        "No historical executable bid/ask; OHLC marking only",
        "A, B and C simplified v0.1 strategy, not fully institutional specification",
        "Missing November 4-5 options and October 28-November 5 futures",
        "2026 is no longer pristine OOS after analysis in earlier runs",
        "2024 options Jan-Sep missing from prior coverage",
        "Different NIFTY spot sources near April22 and July22 data seams",
        "Greeks approximated under fixed interest rate and dividend assumptions",
        "IID bootstrap may understate calendar/regime dependence"]}
    stressrows=[]
    for pct in (0.0025,0.0075,0.015,0.03):
        vals=[]
        for _,row in t.iterrows():
            new=round(float(net_repriced(row,pct)),2)
            vals.append(new)
            stressrows.append({"date":row.date,"mode":row["mode"],"slippage_pct":pct,"net_pnl_rs":new})
        temp=t.copy();temp["net_pnl_rs"]=vals
        report["cost_sensitivity"][str(pct)]={"all_2026":stats(temp)}
        report["cost_sensitivity"][str(pct)]["by_period"]={
            k:stats(temp.loc[v.index]) for k,v in periods.items()}
    pd.DataFrame(stressrows).to_csv(out/"AEGIS_2026_matched_cost_stress.csv",index=False)
    (out/"AEGIS_2026_ROBUSTNESS.json").write_text(json.dumps(report,indent=2))
    lines=[
      "# AEGIS 2026 extended historical candle backtest — executed robustness report","",
      "**Not a validated trading edge; not an untouched holdout.**","",
      "## Net results (assumed modeled commissions, STT and spreads)","",
      "| Group | Trades | Net P&L ₹ | Win rate | Profit factor | Max closed-trade drawdown ₹ |",
      "|---|---:|---:|---:|---:|---:|"]
    for group,values in [("Full 2026",report["all_2026"]),("Jan-Apr21",report["by_period"]["2026_jan01_apr21"]),("Apr22-Jul21",report["by_period"]["2026_apr22_jul21"]),("Jul22-Nov03",report["by_period"]["2026_jul22_nov03"]),("Monday straddle baseline",report["fixed_monday_straddle_benchmark"])]:
        lines.append(f"| {group} | {values['n']} | {values['net_pnl_rs']:,.2f} | {100*values.get('win_rate',0):.1f}% | {values.get('profit_factor')} | {values.get('drawdown_closed_trade_rs',0):,.2f} |")
    lines+=["","## Uncertainty and tail risk",""]
    x=report["all_2026"]
    lines.append(f"- Mean-trade IID bootstrap 95% interval: ₹{x['bootstrap_iid_mean_trade_95ci_rs']}.")
    lines.append(f"- Net without best winning trade: ₹{x['net_without_best_trade_rs']:,.2f}; without two best: ₹{x['net_without_best_two_trades_rs']:,.2f}.")
    lines.append(f"- Worst trade: ₹{x['worst_trade_rs']:,.2f}; 5% worst-trade mean: ₹{x['cvar_worst_5pct_rs']:,.2f}.")
    lines+=["","## Fixed-trade adverse slippage sensitivity","",
      "| Adverse option premium slippage per side | 2026 net ₹ | Jul22-Nov03 net ₹ |",
      "|---|---:|---:|"]
    for pct,val in report["cost_sensitivity"].items():
        lines.append(f"| {float(pct)*100:.2f}% (floor 0.75 pt) | {val['all_2026']['net_pnl_rs']:,.2f} | {val['by_period']['2026_jul22_nov03']['net_pnl_rs']:,.2f} |")
    lines+=["","## Scope and caveats",""]
    lines +=["- "+x for x in report["limitations"]]
    lines+=["","**Decision:** Do not deploy live capital based on this preliminary research."]
    (out/"AEGIS_2026_ROBUSTNESS.md").write_text("\n".join(lines)+"\n")
    print("AEGIS_EXTENDED_ROBUSTNESS",json.dumps({
      "all":report["all_2026"],"by_period":report["by_period"],
      "cost_sensitivity_net":{k:v["all_2026"]["net_pnl_rs"] for k,v in report["cost_sensitivity"].items()}},default=str),flush=True)
if __name__=="__main__":main()
