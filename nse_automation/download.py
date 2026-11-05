"""NSE All Reports: REG1 and price-band acquisition, one attempt per file."""
import argparse, csv, hashlib, io, json, os, re, sys
from datetime import datetime, date, time
from pathlib import Path
from urllib.parse import urlparse
from zoneinfo import ZoneInfo
IST = ZoneInfo("Asia/Kolkata")
PAGE = "https://www.nseindia.com/all-reports"
PATTERN = re.compile(r"^(REG1_IND\d{6}|sec_list_\d{8}|eq_band_changes_\d{8}|sme_bands_complete_\d{8})\.csv$")
def validate(payload, name):
    if not PATTERN.fullmatch(name): raise ValueError("Unexpected filename")
    if not payload or len(payload)>20_000_000: raise ValueError("Empty/oversized file")
    rows=list(csv.reader(io.StringIO(payload.decode("utf-8-sig"))))
    if len(rows)<2 or len(rows[0])<2: raise ValueError("Missing CSV header/data")
    if "<html" in payload[:1000].decode("utf-8",errors="ignore").lower(): raise ValueError("HTML instead of CSV")
    header=[x.strip() for x in rows[0]]
    norm=[re.sub(r"[^a-z0-9]","",x.lower()) for x in header]
    if not any("symbol" in x for x in norm): raise ValueError("Missing symbol column")
    if name.startswith("REG1_") and not any("gsm" in x or "surveillance" in x or "esm" in x for x in norm):
        raise ValueError("Missing surveillance fields")
    if not name.startswith("REG1_") and not any("band" in x or "price" in x for x in norm):
        raise ValueError("Missing band/price columns")
    records=[r for r in rows[1:] if any(x.strip() for x in r)]
    if not records or any(len(r)!=len(header) for r in records): raise ValueError("Empty/ragged CSV")
    return dict(rows=len(records),bytes=len(payload),sha256=hashlib.sha256(payload).hexdigest(),columns=header)
def filedate(name):
    token=re.search(r"(\d{6,8})\.csv$",name).group(1)
    return datetime.strptime(token,"%d%m%y" if len(token)==6 else "%d%m%Y").date()
def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--date")
    ap.add_argument("--output",type=Path,default=Path("nse-output"))
    args=ap.parse_args()
    now=datetime.now(IST)
    target=date.fromisoformat(args.date) if args.date else now.date()
    out=args.output
    out.mkdir(parents=True,exist_ok=True)
    if any(out.iterdir()): raise ValueError("Output must be empty")
    m=dict(started_at=now.isoformat(),requested_date=target.isoformat(),source_page=PAGE,
           commit=os.getenv("GITHUB_SHA"),run_id=os.getenv("GITHUB_RUN_ID"),run_attempt=os.getenv("GITHUB_RUN_ATTEMPT"),
           retry_policy="NONE",drive_status="NOT_TRANSFERRED",datasets=[],
           date_policy="Exact requested/current IST date. Never substitute older files. Future-dated band changes stored separately.",
           calendar_status="NOT_VERIFIED; absent date is not classified as holiday",
           interpretation_status="Acquisition only; effective dates and regulatory code meanings require official definitions")
    exitcode=1
    try:
        if target>now.date(): raise ValueError("Future requested date")
        if target==now.date() and now.time()<time(20,35):
            m["status"]="PENDING_PUBLICATION_WINDOW"
            return 2
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser=p.chromium.launch(headless=False)
            try:
                context=browser.new_context(accept_downloads=True)
                page=context.new_page()
                page.set_default_timeout(45000)
                page.goto(PAGE,wait_until="domcontentloaded",timeout=60000)
                page.locator(".reportCardSegmentDaily").filter(has_text=re.compile(r"\.csv$")).first.wait_for()
                body=page.locator("body").inner_text()
                if re.search(r"access denied|verify you are human|captcha|request blocked",body,re.I):
                    raise RuntimeError("Site access restriction; no retry")
                inventory=page.locator(".card-body").evaluate_all("""els=>els.map(e=>({
                    name:e.querySelector('.reportCardSegmentDaily')?.textContent?.trim(),
                    text:e.innerText,visible:!!(e.offsetWidth||e.offsetHeight||e.getClientRects().length)
                })).filter(e=>e.name)""")
                (out/"inventory.json").write_text(json.dumps(inventory,indent=2))
                names=sorted({x["name"] for x in inventory if x["visible"] and PATTERN.fullmatch(x["name"])})
                required=["REG1_IND"+target.strftime("%d%m%y")+".csv","sec_list_"+target.strftime("%d%m%Y")+".csv"]
                selected=[n for n in names if filedate(n)==target or (n.startswith(("eq_band_changes_","sme_bands_complete_")) and filedate(n)>target)]
                for name in required:
                    if name not in selected: m["datasets"].append(dict(filename=name,status="UNAVAILABLE",error="Exact dated file absent from loaded All Reports inventory; calendar/publication not inferred"))
                for name in selected:
                    item=dict(filename=name,file_date=filedate(name).isoformat(),status="STARTED",
                              scope="future-dated separate reference" if filedate(name)>target else "requested-date snapshot",
                              effective_date="UNVERIFIED",source_page=PAGE)
                    m["datasets"].append(item)
                    try:
                        card=page.locator(".card-body").filter(has=page.get_by_text(name,exact=True)).filter(visible=True)
                        if card.count()!=1: raise ValueError("Ambiguous visible report card")
                        with page.expect_download(timeout=60000) as event:
                            card.get_by_label("Download File",exact=True).click()
                        download=event.value
                        source=download.url
                        host=urlparse(source).hostname or ""
                        if urlparse(source).scheme!="https" or not (host=="nseindia.com" or host.endswith(".nseindia.com")):
                            raise ValueError("Download source not official NSE HTTPS")
                        if download.suggested_filename!=name: raise ValueError("Downloaded filename differs from selected report")
                        if download.failure(): raise RuntimeError(download.failure())
                        tmp=out/(name+".part")
                        download.save_as(tmp)
                        data=tmp.read_bytes()
                        item.update(validate(data,name),source_url=source,retrieved_at=datetime.now(IST).isoformat(),status="VALIDATED_DOWNLOAD")
                        tmp.rename(out/name)
                    except Exception as e:
                        item.update(status="FAILED",error=type(e).__name__+": "+str(e))
                        (out/(name+".part")).unlink(missing_ok=True)
                page.screenshot(path=str(out/"all_reports.png"),full_page=True)
                good={x["filename"] for x in m["datasets"] if x["status"]=="VALIDATED_DOWNLOAD"}
                m["status"]="REQUIRED_DOWNLOADS_VALIDATED" if set(required)<=good else "PARTIAL_OR_BLOCKED"
                exitcode=0 if set(required)<=good else 1
            finally: browser.close()
    except Exception as e:
        m.update(status="FAILED",error=type(e).__name__+": "+str(e))
    finally:
        m["finished_at"]=datetime.now(IST).isoformat()
        (out/"manifest.json").write_text(json.dumps(m,indent=2)+"\n")
        print(json.dumps(m,indent=2))
    return exitcode
if __name__=="__main__": sys.exit(main())
