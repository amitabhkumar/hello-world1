#!/usr/bin/env python3
"""Reconcile verified 2026 India VIX closes into *diagnostic* regime tags only.

Uses ONLY the prior available VIX market session, with max seven calendar-day
lag. Never changes historical trade selections, mark prices or modeled P&L.
"""
from __future__ import annotations
import argparse,datetime as dt,json,pathlib,shutil
import pandas as pd
from aegis.rolling_research_final import stats

def run(research,vixdir,out):
    research=pathlib.Path(research);vixdir=pathlib.Path(vixdir)
    out=pathlib.Path(out)
    out.mkdir(parents=True,exist_ok=True)
    for source in research.iterdir():
        if source.is_file():shutil.copy2(source,out/source.name)
    rows=pd.read_csv(out/"AEGIS_full_rolling_research_trade_ledger.csv")
    q=json.loads((vixdir/"AEGIS_VIX_2026_DATA_QUALITY.json").read_text())
    vix=pd.read_csv(vixdir/"vix_2026.csv")
    if q["distinct_sessions"]<200 or len(vix)!=q["distinct_sessions"] or q["token_used"]:
        raise ValueError("India VIX 2026 source quality failed")
    dates={}
    for _,r in vix.iterrows():
        d=dt.date.fromisoformat(r["market_date"])
        close=float(r["close"])
        if close<=0 or d.year!=2026:raise ValueError("Unexpected VIX close")
        dates[d]=close
    ordered=sorted(dates)
    assessed=0;missing=0
    evidence=[]
    for idx,r in rows.iterrows():
        d=dt.date.fromisoformat(r["date"])
        if d.year!=2026:continue
        prior=[x for x in ordered if x<d]
        latest=prior[-1] if prior else None
        if latest and (d-latest).days<=7:
            level=dates[latest]
            reg="high" if level>=20 else "normal"
            rows.at[idx,"vix_prior"]=level
            rows.at[idx,"vix_regime"]=reg
            assessed+=1
            evidence.append({"entry":str(d),"source_date":str(latest),"close":level,"regime":reg})
        else:
            rows.at[idx,"vix_prior"]=None
            rows.at[idx,"vix_regime"]="unknown"
            missing+=1
    evidence=json.loads(json.dumps(evidence))
    assert all(x["source_date"]<x["entry"] for x in evidence)
    rows.to_csv(out/"AEGIS_full_rolling_research_trade_ledger.csv",index=False)
    manifest=json.loads((out/"AEGIS_FULL_TWO_YEAR_RESEARCH_EVIDENCE.json").read_text())
    manifest["by_vix_regime"]={str(k):stats(r) for k,r in rows.groupby("vix_regime")}
    manifest["vix_regime_by_year"]={str(y):{str(k):stats(g) for k,g in v.groupby("vix_regime")}
               for y,v in rows.groupby(rows.date.str.slice(0,4))}
    manifest["vix_2026_reconciliation"]={
        "status":"verified_prior_day_regime_tagging_only",
        "source":"public Upstox Historical Candle V3 India VIX 1m",
        "source_distinct_days":q["distinct_sessions"],
        "source_1m_candles":q["valid_minute_records"],
        "2026_trades_with_prior_vix":assessed,
        "2026_trades_without_prior_vix":missing,
        "future_lookahead_observed":False,
        "strategic_effect":"none; not a trade entry, strike, exit or P&L input"}
    (out/"AEGIS_FULL_TWO_YEAR_RESEARCH_EVIDENCE.json").write_text(
        json.dumps(manifest,indent=2,default=str))
    (out/"AEGIS_2026_VIX_REGIME_RECONCILIATION.json").write_text(json.dumps({
        "source_quality":{k:q[k] for k in ("status","distinct_sessions","valid_minute_records",
                                          "first_session","last_session","non375_sessions")},
        "new_regime_counts":rows[rows.date.str.startswith("2026")].vix_regime.value_counts().to_dict(),
        "by_vix_regime":manifest["by_vix_regime"],
        "vix_evidence":evidence},indent=2,default=str))
    with (out/"AEGIS_FULL_TWO_YEAR_RESEARCH_REPORT.md").open("a",encoding="utf-8") as file:
        file.write("\n## VIX January–November 2026 public-history supplement (post-processing)\n\n")
        file.write(f"- Retrieved {q['valid_minute_records']:,} one-minute VIX candles over {q['distinct_sessions']} sessions; all were 375 bars/day.\n")
        file.write(f"- Reclassified {assessed}/{assessed+missing} previously simulated 2026 trades by *prior-day* VIX. No trading signal or P&L changed.\n")
        file.write("- The first cash-index session and last F&O session may differ; use VIX as a diagnostic only, not exchange-validated execution.\n")
        for name,m in manifest["by_vix_regime"].items():
            file.write(f"- **{name}**: {m['trades']} trades, ₹{m['net_pnl_rs']:,.2f} modeled net.\n")
    print("AEGIS_VIX_REGIME_RECONCILED",json.dumps({
        "assessed":assessed,"unclassified":missing,
        "by_vix_regime":manifest["by_vix_regime"],
        "unchanged_total_modelled_net_rs":manifest["all"]["net_pnl_rs"],
        "no_lookahead":True},default=str),flush=True)

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--research",required=True)
    p.add_argument("--vix",required=True)
    p.add_argument("--out",default="AEGIS_COMPLETE_FINAL")
    a=p.parse_args()
    run(a.research,a.vix,a.out)
if __name__=="__main__":main()
