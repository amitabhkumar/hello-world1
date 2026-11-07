#!/usr/bin/env python3
"""Audit forward/spot NIFTY near-month futures premium with previous session only.

Available source: publicly pinned voletiramu five-year NIFTY_FUT daily and
NIFTY cash index five-minute series, roughly 2022-Apr2026. This is a *daily*
front-month proxy, NOT a per-option intraday forward curve, and does not cover
the 2026 May–Nov period (except separate user Upstox 2026 futures that are not
yet part of a continuous five-minute spot/futures join).

Do not optimize AEGIS signal selection using this exploratory attribution.
"""
from __future__ import annotations
import argparse,datetime as dt,json,pathlib,shutil
import numpy as np,pandas as pd
from aegis.rolling_research_final import stats

def run(final_root,reference_root,out):
    final_root=pathlib.Path(final_root)
    reference_root=pathlib.Path(reference_root)
    out=pathlib.Path(out);out.mkdir(parents=True,exist_ok=True)
    for file in final_root.iterdir():
        if file.is_file():shutil.copy2(file,out/file.name)
    fut=reference_root/"NIFTY_FUT_daily_5yr_2022_2026.csv"
    spot=reference_root/"NIFTY_5min_5yr_2021_2026.csv"
    if not fut.is_file() or not spot.is_file():
        raise FileNotFoundError("Pinned public NIFTY future and spot context not present")
    f=pd.read_csv(fut)
    s=pd.read_csv(spot)
    if not {"timestamp","close"}.issubset(f) or not {"timestamp","close"}.issubset(s):
        raise ValueError("Unexpected public futures/index schema")
    f["date"]=pd.to_datetime(f.timestamp,utc=True).dt.tz_convert("Asia/Kolkata").dt.date
    s["date"]=pd.to_datetime(s.timestamp).dt.date
    s=s.groupby("date").tail(1)[["date","close"]]
    joined=f[["date","close"]].merge(s,on="date",suffixes=("_futures","_spot"))
    joined=joined[(joined.date>=dt.date(2024,11,6)) &
                  (joined.date<=dt.date(2026,11,5))].copy()
    joined=joined[(joined.close_futures>0)&(joined.close_spot>0)]
    joined["basis_pct"]=100*(joined.close_futures/joined.close_spot-1)
    joined=joined.sort_values("date").drop_duplicates("date",keep="last")
    if joined.empty:raise ValueError("No overlapping historical daily NIFTY futures and spot dates")
    # Daily futures source is continuous near-month (roll method not verified).
    # This is a prior-session basis *label*, NOT signal with future info.
    ledger=pd.read_csv(out/"AEGIS_full_rolling_research_trade_ledger.csv")
    ledger["date"]=ledger.date.astype(str)
    included=0;missing=0;observations=[]
    for i,row in ledger.iterrows():
        d=dt.date.fromisoformat(row["date"])
        prev=joined[joined.date<d]
        if prev.empty:
            missing+=1;continue
        r=prev.iloc[-1];gap=(d-r.date).days
        if gap>7:
            missing+=1;continue
        basis=float(r["basis_pct"])
        ledger.at[i,"prior_session_futures_basis_pct"]=basis
        ledger.at[i,"prior_session_futures_basis_date"]=str(r.date)
        ledger.at[i,"prior_session_futures_basis_regime"]="premium" if basis>=0 else "discount"
        observations.append({"entry":str(d),"basis_source_date":str(r.date),"basis_pct":basis})
        included+=1
    assert all(x["basis_source_date"]<x["entry"] for x in observations)
    ledger["prior_session_futures_basis_regime"]=ledger["prior_session_futures_basis_regime"].fillna("unavailable")
    ledger.to_csv(out/"AEGIS_full_rolling_research_trade_ledger.csv",index=False)
    byreg={str(k):stats(v) for k,v in ledger.groupby("prior_session_futures_basis_regime")}
    original=json.loads((out/"AEGIS_FULL_TWO_YEAR_RESEARCH_EVIDENCE.json").read_text())
    original["futures_basis_research"]={
      "source":"pinned public NIFTY 5min cash-index and NIFTY near-month futures daily context; approx through Apr2026",
      "first":str(joined.date.min()),"last":str(joined.date.max()),
      "daily_spot_futures_overlap":len(joined),
      "trades_with_prior_daily_basis":included,"trades_without_prior_daily_basis":missing,
      "future_lookahead":False,
      "models":"diagnostic only; never used to choose a trade in v0.1",
      "per_regime":byreg,
      "limitations":["No continuous 2026 May–Nov futures basis in public reference",
                     "2024/25 minute-by-minute futures historical data not available in current archive",
                     "No broker bid/ask, depth or price impact",
                     "Near-month futures roll handling derived from public daily source, not exchange contract master"]}
    (out/"AEGIS_FULL_TWO_YEAR_RESEARCH_EVIDENCE.json").write_text(json.dumps(original,indent=2,default=str))
    joined.to_csv(out/"AEGIS_public_daily_futures_spot_basis.csv",index=False)
    (out/"AEGIS_FUTURES_BASIS_DIAGNOSTIC.json").write_text(json.dumps(
       original["futures_basis_research"],indent=2,default=str))
    with (out/"AEGIS_FULL_TWO_YEAR_RESEARCH_REPORT.md").open("a") as h:
        h.write("\n## NSE NIFTY near-month futures daily basis (exploratory only)\n\n")
        h.write(f"- Daily futures/spot overlap: {len(joined)} days ({joined.date.min()} to {joined.date.max()}).\n")
        h.write(f"- Prior-session futures basis assigned to {included}/{len(ledger)} trades without future leakage; missing for {missing} trades.\n")
        h.write("- Basis coverage after April 2026 is incomplete; results are **not** a full intraday futures-basis signal ablation.\n")
        for tag,val in byreg.items():
            h.write(f"- {tag}: {val['trades']} trades, net ₹{val['net_pnl_rs']:,.2f}; observational only.\n")
    print("AEGIS_PRIOR_DAY_FUTURES_BASIS_RECONCILED",json.dumps({
       "from":str(joined.date.min()),"to":str(joined.date.max()),
       "daily_source_rows":len(joined),"trades_with_basis":included,
       "trades_missing_basis":missing,
       "by_regime":byreg,"unchanged_full_net_rs":original["all"]["net_pnl_rs"]},default=str),flush=True)

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--research",required=True)
    p.add_argument("--support",required=True)
    p.add_argument("--out",required=True)
    a=p.parse_args()
    run(a.research,a.support,a.out)
if __name__=="__main__":main()
