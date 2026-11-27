"""Exact-date NSE final equity/delivery and index files; one attempt, no fallback."""
import csv, io, json, hashlib, os, urllib.request
from pathlib import Path
from datetime import datetime, timezone
from urllib.parse import urlparse
from .download import select_date, IST, CALENDAR_SOURCES

def plan(now, explicit=None):
    day, gate = select_date(now, explicit)
    return day, gate, [
        ('equity_delivery', 'sec_bhavdata_full_'+day.strftime('%d%m%Y')+'.csv',
         'https://nsearchives.nseindia.com/products/content/sec_bhavdata_full_'+day.strftime('%d%m%Y')+'.csv'),
        ('indices', 'ind_close_all_'+day.strftime('%d%m%Y')+'.csv',
         'https://nsearchives.nseindia.com/content/indices/ind_close_all_'+day.strftime('%d%m%Y')+'.csv')]

def validate(body, kind, day):
    rows=[{k.strip():str(v or '').strip() for k,v in r.items()} for r in csv.DictReader(io.StringIO(body.decode('utf-8-sig')))]
    if not rows: raise ValueError('Empty CSV; no coverage inferred')
    fields=({'SYMBOL','SERIES','DATE1','PREV_CLOSE','OPEN_PRICE','HIGH_PRICE','LOW_PRICE','CLOSE_PRICE','TTL_TRD_QNTY','DELIV_QTY'}
            if kind=='equity_delivery' else {'Index Name','Index Date','Closing Index Value'})
    if not fields<=rows[0].keys(): raise ValueError('Required columns missing; not a valid report')
    col,fmt=('DATE1','%d-%b-%Y') if kind=='equity_delivery' else ('Index Date','%d-%m-%Y')
    if any(datetime.strptime(r[col],fmt).date()!=day for r in rows):raise ValueError('Wrong or mixed source dates')
    return dict(rows=len(rows),bytes=len(body),sha256=hashlib.sha256(body).hexdigest(),source_date=str(day),scope='Date/schema validated; corporate-action, metric and instrument-quality checks still required')

def _fetch_all_playwright(items):
    from playwright.sync_api import sync_playwright
    results = {}
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, args=['--no-sandbox'])
        context = browser.new_context()
        page = context.new_page()
        try:
            page.goto('https://www.nseindia.com/all-reports', wait_until='domcontentloaded', timeout=60000)
            for kind, name, url in items:
                try:
                    response = context.request.get(url, timeout=60000)
                    if response.status != 200:
                        raise ValueError('HTTP ' + str(response.status))
                    parsed = urlparse(response.url)
                    if parsed.scheme != 'https' or parsed.hostname != 'nsearchives.nseindia.com':
                        raise ValueError('Unexpected source redirect')
                    body = response.body()
                    if len(body) > 50000000:
                        raise ValueError('Oversized report')
                    results[kind] = (body, None)
                except Exception as e:
                    results[kind] = (None, e)
        finally:
            browser.close()
    return results

def collect(now, out, explicit=None, opener=None):
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    if any(out.iterdir()):raise ValueError('Use empty output directory')
    m=dict(started_at=now.isoformat(),run_id=os.getenv('GITHUB_RUN_ID'),attempt=os.getenv('GITHUB_RUN_ATTEMPT'),commit=os.getenv('GITHUB_SHA'),calendar_sources=CALENDAR_SOURCES,retry_policy='NONE',publication_timestamp=None,drive_status='NOT_TRANSFERRED',datasets=[])
    try:
        day,gate,items=plan(now,explicit);m.update(report_date=str(day),publication_status=gate)
        if gate=='PENDING_PUBLICATION_WINDOW':m['status']=gate;return m
        pw_results = _fetch_all_playwright(items) if opener is None else None
        for kind,name,url in items:
            r=dict(dataset=kind,file=name,source=url,required_date=str(day),retrieval_utc=datetime.now(IST).astimezone(timezone.utc).isoformat())
            try:
                if opener is not None:
                    with opener(urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0'}),timeout=60)as response:
                        if urlparse(response.geturl()).scheme!='https' or urlparse(response.geturl()).hostname!='nsearchives.nseindia.com':raise ValueError('Unexpected source redirect')
                        body=response.read(50000001)
                    if len(body)>50000000:raise ValueError('Oversized report')
                else:
                    body, err = pw_results[kind]
                    if err is not None:
                        raise err
                r.update(validate(body,kind,day));(out/name).write_bytes(body);r['status']='VALIDATED_DATED_CSV'
            except Exception as e:r.update(status='UNAVAILABLE_REQUIRED_DATE',error=type(e).__name__+': '+str(e))
            m['datasets'].append(r)
        m['status']='VALIDATED_DOWNLOADS' if all(r['status']=='VALIDATED_DATED_CSV' for r in m['datasets']) else 'PARTIAL_OR_BLOCKED'
    except Exception as e:m.update(status='BLOCKED',error=type(e).__name__+': '+str(e))
    finally:
        m['finished_at']=datetime.now(IST).isoformat();(out/'manifest.json').write_text(json.dumps(m,indent=2))
    return m

if __name__=='__main__':
    m=collect(datetime.now(IST),'nse-market-output',os.getenv('REPORT_DATE')or None)
    print(json.dumps(m));raise SystemExit(0 if m['status']in['VALIDATED_DOWNLOADS','PENDING_PUBLICATION_WINDOW'] else 1)
