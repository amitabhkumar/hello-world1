"""NSE All Reports: REG1 and price-band acquisition, one attempt per file."""
import argparse, csv, hashlib, io, json, os, re, sys
from datetime import datetime, date, time, timedelta
from pathlib import Path
from urllib.parse import urlparse
from zoneinfo import ZoneInfo
IST = ZoneInfo("Asia/Kolkata")
PAGE = "https://www.nseindia.com/all-reports"
PATTERN = re.compile(r"^(REG1_IND\d{6}|sec_list_\d{8}|eq_band_changes_\d{8}|sme_bands_complete_\d{8})\.csv$")

# Official equity calendar snapshot reviewed 2026-11-05. Fail closed outside coverage.
CALENDAR_SOURCES = [
 "https://nsearchives.nseindia.com/content/circulars/CMTR71775.pdf",
 "https://www.nseindia.com/resources/exchange-communication-holidays?apiversion=v2",
 "https://nsearchives.nseindia.com/content/circulars/CMTR72349.pdf",
 "https://nsearchives.nseindia.com/content/circulars/CMTR76941.pdf"]
HOLIDAYS = set("2026-01-15 2026-01-26 2026-03-03 2026-03-26 2026-03-31 2026-04-03 2026-04-14 2026-05-01 2026-05-28 2026-06-26 2026-09-14 2026-10-02 2026-10-20 2026-11-10 2026-11-24 2026-12-25".split())
SPECIAL = {"2026-02-01", "2026-11-08"}
def is_session(d):
    if d.year != 2026:
        raise ValueError("CALENDAR_COVERAGE_MISSING: " + str(d))
    return d.isoformat() in SPECIAL or (d.weekday() < 5 and d.isoformat() not in HOLIDAYS)
def select_date(now, explicit=None):
    now = now.astimezone(IST)
    today = now.date()
    is_session(today)  # Even an explicit old date must not conceal expired coverage.
    if explicit:
        d = date.fromisoformat(explicit)
        if d > today or not is_session(d):
            raise ValueError("Requested date is future or not an eligible equity session")
    elif is_session(today) and now.time() >= time(16, 0):
        d = today  # 16:30 records today's pending publication, never yesterday as final.
    else:
        d = today - timedelta(days=1) if is_session(today) else today
        while not is_session(d):
            d -= timedelta(days=1)
    return d, ("PENDING_PUBLICATION_WINDOW" if d == today and now.time() < time(20,35) else "ELIGIBLE_FOR_SINGLE_ATTEMPT")
REG1_DEFINITION_SOURCE = "https://nsearchives.nseindia.com/content/circulars/SURV76993.zip"
# Annexure pages 1-2. These are REG1 per-field codes, NOT REG_IND composite codes.
REG1_MAPS = {
 "Status": {"A":"Active", "S":"Suspended", "I":"Inactive"},
 "GSM": {"100":"Not applicable", "0":"GSM identified", **{str(n):"GSM stage " + str(n) for n in (1,2,3,4,6)}},
 "Long_Term_Additional_Surveillance_Measure (Long Term ASM)": {"100":"Not under LTASM", **{str(n):"LTASM stage " + str(n) for n in (1,2,3,4)}},
 "Short_Term_Additional_Surveillance_Measure (Short Term ASM)": {"100":"Not under STASM", "1":"STASM stage 1", "2":"STASM stage 2"},
 "ESM": {"100":"Not applicable", "1":"ESM stage 1", "2":"ESM stage 2"}}

REG1_EFFECTIVE_SOURCE = "https://nsearchives.nseindia.com/content/circulars/SURV67801.pdf#page=81"
REG1_MAPS.update({'Nse Exclusive': {'Y': 'NSE exclusive', 'N': 'Not NSE exclusive'}, 'Unsolicited_SMS': {'100': 'Not under SMS', '0': 'Information list', '1': 'Current watchlist'}, 'Insolvency_Resolution_Process(IRP)': {'100': 'Not under IRP', '0': 'Corporate disclosure received', '1': 'IBC stage I', '2': 'IBC stage II'}, 'Default': {'100': 'Not under default disclosure', '0': 'Default disclosure', '1': 'Default surveillance measure'}, 'ICA': {'100': 'Not under ICA', '0': 'ICA identified', '1': 'ICA surveillance measure'}, 'Social Media Platforms': {'100': 'Not identified', '2': 'Surveillance measure list'}, 'Pledge': {'100': 'Not identified', '1': 'Identified'}, 'Add-on_PB': {'100': 'Not identified', '1': 'Identified'}, 'Total Pledge': {'100': 'Not identified', '1': 'Identified'}, 'Loss making': {'100': 'Not under category', '0': 'Under category'}, 'The Overall encumbered share in the scrip is more than 50 Percent.': {'100': 'Not under category', '0': 'Under category'}, 'Under BZ/SZ Series': {'100': 'Not under category', '0': 'Under category'}, 'Company has failed to pay Annual listing fee': {'100': 'Not under category', '0': 'Under category'}, 'Derivative contracts in the scrip to be moved out of F and O': {'100': 'Not under category', '0': 'Under category'}, 'Scrip PE is greater than 50 (4 trailing quarters)': {'100': 'Not under category', '0': 'Under category'}, 'EPS in the scrip is zero (4 trailing quarters)': {'100': 'Not under category', '0': 'Under category'}, 'Less than 100 unique PAN traded in previous 30 days': {'100': 'Not under category', '0': 'Under category'}, 'Mandatory Market making period in SME scrip is over': {'100': 'Not under category', '0': 'Under category'}, 'SME scrip is not regularly traded': {'100': 'Not under category', '0': 'Under category'}, 'Close to Close price movement greater than 25perc in previous 5 trading days': {'100': 'Not flagged among selected criteria', '0': 'Under category'}, 'Close to Close price movement greater than 40perc in previous 15 trading days': {'100': 'Not flagged among selected criteria', '0': 'Under category'}, 'Close to Close price movement greater than 100perc in previous 60 trading Days': {'100': 'Not flagged among selected criteria', '0': 'Under category'}, 'Close to Close price movement greater than 25perc in previous 15 Days': {'100': 'Not flagged among selected criteria', '0': 'Under category'}, 'Close to Close price movement greater than 50perc in previous 1 month': {'100': 'Not flagged among selected criteria', '0': 'Under category'}, 'Close to Close price movement greater than 90perc in previous 3 months': {'100': 'Not flagged among selected criteria', '0': 'Under category'}, 'Close to Close price movement greater than 25perc in previous 1 month': {'100': 'Not flagged among selected criteria', '0': 'Under category'}, 'Close to Close price movement greater than 50perc in previous 3 months': {'100': 'Not flagged among selected criteria', '0': 'Under category'}, 'Close to Close price movement greater than 200perc in previous 365 Days': {'100': 'Not flagged among selected criteria', '0': 'Under category'}, 'Close to Close price movement greater than 75perc in previous 6 months': {'100': 'Not flagged among selected criteria', '0': 'Under category'}, 'Close to Close price movement greater than 100perc in previous 365 days': {'100': 'Not flagged among selected criteria', '0': 'Under category'}, 'High low price variation greater than 75perc in previous 1 month': {'100': 'Not flagged among selected criteria', '0': 'Under category'}, 'High low price variation greater than 150perc in previous 3 months': {'100': 'Not flagged among selected criteria', '0': 'Under category'}, 'High low price variation greater than 75perc in previous 3 months': {'100': 'Not flagged among selected criteria', '0': 'Under category'}, 'High low price variation greater than 300perc in previous 365 Days': {'100': 'Not flagged among selected criteria', '0': 'Under category'}, 'High low price variation greater than 100perc in previous 6 months': {'100': 'Not flagged among selected criteria', '0': 'Under category'}, 'High low price variation greater than 200perc in previous 365 Days': {'100': 'Not flagged among selected criteria', '0': 'Under category'}, 'High low price variation greater than 150perc in previous 12 months': {'100': 'Not flagged among selected criteria', '0': 'Under category'}})

def next_session(report_date):
    d = report_date + timedelta(days=1)
    while not is_session(d):
        d += timedelta(days=1)
    return d

def interpret_reg1(payload, report_date=None):
    rows = list(csv.DictReader(io.StringIO(payload.decode("utf-8-sig"))))
    effective = next_session(report_date).isoformat() if report_date else None
    output = []
    identifiers = {"ScripCode", "Symbol", "Series"}
    for r in rows:
        indicators = {}
        for k, raw in r.items():
            if k in identifiers:
                continue
            value = (raw or "").strip()
            meaning = REG1_MAPS.get(k, {}).get(value, "Unknown")
            if k.startswith("Filler"):
                meaning = "Reserved field; not interpreted" if value in ("", "100") else "Unknown"
            indicators[k] = dict(raw=raw, meaning=meaning)
        output.append(dict(symbol=r.get("Symbol"), series=r.get("Series"),
            indicators=indicators, report_date=report_date.isoformat() if report_date else None,
            effective_trading_date=effective, effective_date_source=REG1_EFFECTIVE_SOURCE,
            trading_access="Unknown", snapshot_status=REG1_MAPS["Status"].get(r.get("Status"),"Unknown"),
            reason="Effective REG1 labels verified; permission additionally requires current session, band and dated restriction notices."))
    return output

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
    if not name.startswith("REG1_") and not (any("band" in x or "price" in x for x in norm) or (name.startswith("eq_band_changes_") and {"from","to"}.issubset(norm))):
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
    target=now.date()
    out=args.output
    out.mkdir(parents=True,exist_ok=True)
    if any(out.iterdir()): raise ValueError("Output must be empty")
    m=dict(started_at=now.isoformat(),requested_date=target.isoformat(),source_page=PAGE,
           commit=os.getenv("GITHUB_SHA"),run_id=os.getenv("GITHUB_RUN_ID"),run_attempt=os.getenv("GITHUB_RUN_ATTEMPT"),
           retry_policy="NONE",drive_status="NOT_TRANSFERRED",datasets=[],
           date_policy="Official equity calendar; morning previous session; post-market today pending until 20:35; closed day latest session; no older substitute.",
           calendar_status="2026_OFFICIAL_SNAPSHOT_REVIEWED_2026_11_05", calendar_sources=CALENDAR_SOURCES,
           interpretation_status="Acquisition only; effective dates and regulatory code meanings require official definitions")
    exitcode=1
    try:
        target, publication_status = select_date(now, args.date)
        m.update(requested_date=target.isoformat(), publication_status=publication_status, publication_timestamp=None)
        if publication_status == "PENDING_PUBLICATION_WINDOW":
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
                        if name.startswith("REG1_"):
                            interpreted=interpret_reg1(data, filedate(name))
                            item.update(effective_date=next_session(filedate(name)).isoformat(), effective_date_source=REG1_EFFECTIVE_SOURCE)
                            (out/"reg1_interpreted.json").write_text(json.dumps(dict(source=REG1_DEFINITION_SOURCE,records=interpreted),indent=2))
                    except Exception as e:
                        item.update(status="FAILED",error=type(e).__name__+": "+str(e))
                        (out/(name+".part")).unlink(missing_ok=True)
                page.screenshot(path=str(out/"all_reports.png"),full_page=True)
                good={x["filename"] for x in m["datasets"] if x["status"]=="VALIDATED_DOWNLOAD"}
                m["status"]="ALL_SELECTED_DOWNLOADS_VALIDATED" if set(required)<=good and all(x["status"]=="VALIDATED_DOWNLOAD" for x in m["datasets"]) else "PARTIAL_OR_BLOCKED"
                exitcode=0 if m["status"]=="ALL_SELECTED_DOWNLOADS_VALIDATED" else 1
            finally: browser.close()
    except Exception as e:
        m.update(status="FAILED",error=type(e).__name__+": "+str(e))
    finally:
        m["finished_at"]=datetime.now(IST).isoformat()
        (out/"manifest.json").write_text(json.dumps(m,indent=2)+"\n")
        print(json.dumps(m,indent=2))
    return exitcode
if __name__=="__main__": sys.exit(main())


