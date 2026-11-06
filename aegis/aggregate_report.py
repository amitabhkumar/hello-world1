#!/usr/bin/env python3
import ast, json, pathlib, os, math, datetime as dt
import numpy as np
import pandas as pd
from aegis.backtest_v01 import fees
root=pathlib.Path(os.getenv("INPUT_DIR","INPUT"));out=pathlib.Path("AEGIS_REPORT");out.mkdir(exist_ok=True)
years=(2024,2025,2026)
parts=[];bases=[];sources={}
for yr in years:
    sources[str(yr)]=json.loads((root/f"summary_{yr}.json").read_text())
    f=root/f"trades_{yr}.csv"
    g=root/f"baseline_{yr}.csv"
    if f.exists() and f.stat().st_size:
        x=pd.read_csv(f);x["year"]=yr;parts.append(x)
    if g.exists() and g.stat().st_size:
        x=pd.read_csv(g);x["year"]=yr;bases.append(x)
tr=pd.concat(parts,ignore_index=True).sort_values(["date","exit_timestamp"]).reset_index(drop=True)
bs=pd.concat(bases,ignore_index=True).sort_values(["date","exit_timestamp"]).reset_index(drop=True)
tr.to_csv(out/"AEGIS_trades_all_years.csv",index=False)
bs.to_csv(out/"baseline_monday_straddle_all_years.csv",index=False)
def stats(df):
    if df.empty:return {"n":0}
    arr=df.net_pnl_rs.to_numpy(dtype=float);n=len(arr)
    winners=arr[arr>0].sum();losers=-arr[arr<0].sum()
    eq=arr.cumsum();dd=(np.maximum.accumulate(np.r_[0,eq])[1:]-eq).max()
    boot=np.random.default_rng(2026+n).choice(arr,(10000,n),replace=True).mean(axis=1)
    low,high=np.quantile(boot,[.025,.975])
    wins=np.mean(arr>0); z=1.96;den=1+z*z/n
    center=(wins+z*z/(2*n))/den
    half=z*np.sqrt(wins*(1-wins)/n+z*z/(4*n*n))/den
    ss=np.sort(arr)[::-1];lowest=np.sort(arr)[:max(1,math.ceil(.05*n))]
    return dict(n=int(n),wins=int((arr>0).sum()),win_rate=round(float(wins),4),
      net_pnl_rs=round(float(arr.sum()),2),expectancy_rs=round(float(arr.mean()),2),
      median_rs=round(float(np.median(arr)),2),
      profit_factor=round(float(winners/losers),3) if losers else None,
      drawdown_rs=round(float(dd),2),worst_rs=round(float(arr.min()),2),
      cvar_5pct_rs=round(float(lowest.mean()),2),
      bootstrap_IID_mean_95CI_rs=[round(float(low),2),round(float(high),2)],
      wilson_win_rate_95CI=[round(float(center-half),4),round(float(center+half),4)],
      after_removing_best_win_rs=round(float(arr.sum()-ss[0]),2),
      after_removing_top_two_wins_rs=round(float(arr.sum()-ss[:2].sum()),2))
train=tr[tr.year<2026];test=tr[tr.year==2026]
results={
  "development":stats(train),"oos_holdout":stats(test),"all_not_oos":stats(tr),
  "baseline_development":stats(bs[bs.year<2026]),"baseline_holdout":stats(bs[bs.year==2026]),
  "development_by_mode":{m:stats(train[train["mode"]==m]) for m in ("A","B_UP","B_DN","C")},
  "holdout_by_mode":{m:stats(test[test["mode"]==m]) for m in ("A","B_UP","B_DN","C")},
  "greeks_covered_legs": {"train":int(train.greeks_covered_all_legs.sum()),"holdout":int(test.greeks_covered_all_legs.sum())},
  "observed_spot_dates":{y:sources[y]["range"] for y in sources}
}
# Apples-to-apples cost sensitivity: same exact trades and exits; only fill-cost assumptions change.
def net_fixed(row,pct):
    legs=ast.literal_eval(row.legs)
    mids0=json.loads(row.entry_raw_open_prices);mids1=json.loads(row.exit_raw_open_prices)
    qty=int(row.lot_size)
    fill=lambda x,s:max(.05,float(x)+s*max(.75,float(x)*pct))
    fills0=[fill(mid,sgn) for mid,(_,__,sgn) in zip(mids0,legs)]
    fills1=[fill(mid,-sgn) for mid,(_,__,sgn) in zip(mids1,legs)]
    f=fees(dt.date.fromisoformat(row.date),qty,legs,fills0,fills1)
    return qty*sum(s*(x-y) for (_,__,s),y,x in zip(legs,fills0,fills1))-f["total"]
sens=[]
for _,row in tr.iterrows():
    for pct in (.0025,.0075,.015):
        sens.append({"date":row.date,"year":int(row.year),"mode":row["mode"],
                     "slippage_fraction":pct,"fixed_trade_net_rs":round(float(net_fixed(row,pct)),2)})
sd=pd.DataFrame(sens);sd.to_csv(out/"AEGIS_matched_trade_cost_stress.csv",index=False)
results["matched_cost_sensitivity"]={}
for label,group in (("development",sd[sd.year<2026]),("holdout",sd[sd.year==2026])):
    results["matched_cost_sensitivity"][label]={str(k):stats(x.rename(columns={"fixed_trade_net_rs":"net_pnl_rs"})) for k,x in group.groupby("slippage_fraction")}
(out/"AEGIS_METRICS.json").write_text(json.dumps(results,indent=2))
dev=results["development"];oos=results["oos_holdout"]
lines=[
"# NIFTY AEGIS v0.1: executed historical option-candle research",
"",
"**Status: preliminary execution research, NOT bid/ask-verified and NOT a complete two-year backtest.**",
"",
"## Data and implementation",
"",
"- Real NIFTY 1-minute option OHLCV and separate NIFTY 5-minute spot reference data.",
"- Sampled option executions based on 1-minute candle OPEN at 10:06 and subsequent observed opening prices at monitoring times; no true historical order book.",
"- Development: Oct–Dec 2024 (transitional Nov20–Dec31 excluded) and 2025. Holdout: Jan 2026 to Apr 21, 2026 (last observed cash-index reference).",
"- A: selective long ATM straddle after preceding shock; B: breakout-confirmed call/put debit spread; C: reverse iron condor under compression; otherwise cash.",
"- Benchmark: Monday long ATM straddle held for two trading sessions, same execution-cost assumptions.",
"- 1% risk limit against hypothetical ₹50 lakh account; historical NIFTY lot sizes 25/75/65 by stable contract-era; ₹20 per executed leg/order.",
"- Adverse execution 0.75% of price or 0.75 points per leg per side (whichever higher), estimated STT/GST/stamp/exchange charges. Assumptions are not verified fills.",
"- Approximate BSM Greek diagnostics use constant r=6.5%, dividend yield=1.2%; no historical forward curve or traded IV surface.",
"- Some dates and quotes are excluded for absence of matching option legs, missing source dates or lot-size transitional ambiguity.",
"",
"## Net outcomes",
"",
"| Metric | Development | Out-of-sample 2026 Jan–Apr21 |",
"|---|---:|---:|",
f"| Trades | {dev['n']} | {oos['n']} |",
f"| P&L | ₹{dev['net_pnl_rs']:,.2f} | ₹{oos['net_pnl_rs']:,.2f} |",
f"| Expectancy/trade | ₹{dev['expectancy_rs']:,.2f} | ₹{oos['expectancy_rs']:,.2f} |",
f"| Win rate | {100*dev['win_rate']:.1f}% | {100*oos['win_rate']:.1f}% |",
f"| Profit factor | {dev['profit_factor']} | {oos['profit_factor']} |",
f"| Closed-trade max drawdown | ₹{dev['drawdown_rs']:,.2f} | ₹{oos['drawdown_rs']:,.2f} |",
f"| IID bootstrap mean 95% CI | ₹{dev['bootstrap_IID_mean_95CI_rs']} | ₹{oos['bootstrap_IID_mean_95CI_rs']} |",
f"| P&L without best trade | ₹{dev['after_removing_best_win_rs']:,.2f} | ₹{oos['after_removing_best_win_rs']:,.2f} |",
"",
"### Matched-trade execution sensitivity (same strikes and exit timestamps)",
"",
"| Slippage each leg each side | Development P&L | Holdout P&L |",
"|---|---:|---:|",
]
for p in (.0025,.0075,.015):
    a=results["matched_cost_sensitivity"]["development"][str(p)]["net_pnl_rs"]
    b=results["matched_cost_sensitivity"]["holdout"][str(p)]["net_pnl_rs"]
    lines.append(f"| {100*p:.2f}% premium, 0.75pt floor | ₹{a:,.2f} | ₹{b:,.2f} |")
lines+=["",
"## Conclusions and remaining blockers",
"",
"Development expectancy is NEGATIVE. A positive 16-trade 2026 holdout is not sufficient evidence of positive future expectancy.",
"Bootstrap treats trades as IID; overlapping regimes and few stress episodes can make intervals overly optimistic.",
"2026 is missing after April 21 from spot-reference data and after July 21 from available intraday options data.",
"Absent bid/ask quotes, intraday futures forward curve, complete 2026 India VIX and fully matched historical interest rates.",
"No trade signals or performance parameters were tuned after inspecting the holdout; an actual institutional-quality validation remains incomplete.",
"**Do not fund or deploy AEGIS based on these results.**",
"",
"## Source and execution references",
"",
"- GitHub code: https://github.com/amitabhkumar/hello-world1/tree/aegis-nifty-backtest/aegis",
"- Options: https://huggingface.co/datasets/rissin/nse-options-intraday",
"- NIFTY 5m/futures daily: https://github.com/voletiramu/nse-fno-1min-data/releases/tag/indices-v1.0.0",
"- India VIX 2024/2025: https://github.com/Hareeshkesavan/Stock-Market-Dataset",
"- NSE STT: https://www.nseindia.in/static/products-services/equity-derivatives-securities-transaction-tax",
"",
"Files: AEGIS_trades_all_years.csv, AEGIS_matched_trade_cost_stress.csv, AEGIS_METRICS.json, and the baseline ledger.",
]
(out/"AEGIS_EXECUTED_REPORT.md").write_text("\n".join(lines)+"\n")
print("AGGREGATED_RESULTS",json.dumps({k:results[k] for k in ("development","oos_holdout","matched_cost_sensitivity","greeks_covered_legs")}))
