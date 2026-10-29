"""BSE public-data acquisition using an ordinary browser, with per-source evidence.
No fingerprint masking, proxy rotation, credential access or challenge bypass.
A captured page is not a validated dataset. Failures remain separately visible.
"""
import argparse, csv, hashlib, io, json, os, re, sys, zipfile
from datetime import datetime, date
from pathlib import Path
from urllib.parse import urlparse, unquote
from zoneinfo import ZoneInfo
IST=ZoneInfo('Asia/Kolkata')
ROOT='https://www.bseindia.com'
MAX_BYTES=50_000_000
SOURCES={
 'announcements':('/corporates/ann.html','Corporate announcements/results/orders'),
 'delivery':('/markets/equity/EQReports/StockPrcHistori.aspx?flag=0','Security price-volume-deliverable history'),
 'bulk_block':('/markets/equity/EQReports/BulknBlockDeals.aspx','Bulk and block deals'),
 'corporate_actions':('/corporates/corporate_act.aspx','Corporate actions'),
 'asm':('/markets/equity/EQReports/additional_surveillance_measure.aspx','Additional surveillance measures'),
 'gsm':('/markets/equity/EQReports/graded_surveil_measure.aspx','Graded surveillance measures'),
 'shareholding':('/corporates/Sharehold_Searchnew.aspx','Shareholding patterns'),
 'pledges':('/corporates/Pledge_new.aspx','Pledged shares'),
 'calendar':('/static/markets/marketinfo/listholi.aspx','Trading holidays'),
 'high_low':('/markets/equity/EQReports/ScripwiseHighLow.aspx','52-week high/low'),
 'breadth':('/markets/Equity/EQReports/Tradinghighlights_histroical.aspx','Breadth/circuit statistics'),
 'var_margin':('/markets/equity/EQReports/varmargin.aspx?flag=1','VaR margin groups'),
 'regulatory_files':('/members/index.aspx','SCRIP and REG_IND official reference files; ESM/TFT/bands require file validation'),
 'price_bands':('/static/markets/equity/EQReports/sur_Surveillance.html#!#her3','Price-band notices and surveillance'),
 'security_master':('/corporates/List_Scrips.aspx','Listed security master'),
 'preopen':('/static/markets/equity/preopen_session.html','Pre-open source discovery; information page is not live data'),
 'market_quotes':('/markets/Equity/EQReports/MarketWatch.aspx','Market quote source discovery; depth/timestamps require validation'),
}
def now(): return datetime.now(IST).isoformat()
def official(url):
 u=urlparse(url);h=u.hostname or ''
 return u.scheme=='https' and (h=='bseindia.com' or h.endswith('.bseindia.com'))
def safe_json_bytes(body):
 if len(body)>MAX_BYTES: raise ValueError('Response exceeds size limit')
 return json.loads(body.decode('utf-8-sig'))
def row_arrays(value,path='$'):
 """Expose candidate arrays without flattening counts/metadata into records."""
 out=[]
 if isinstance(value,list):
  if value and all(isinstance(x,dict) for x in value):out.append((path,value))
 elif isinstance(value,dict):
  for k,v in value.items():out.extend(row_arrays(v,path+'.'+k))
 return out
def fingerprint(body):return {'bytes':len(body),'sha256':hashlib.sha256(body).hexdigest()}
def write_blob(out,name,body):
 if len(body)>MAX_BYTES: raise ValueError('Oversized response')
 (out/name).write_bytes(body);return dict(file=name,**fingerprint(body))
def page_blocked(text):
 # Plain challenge pages, not incidental mentions of access rules in documents.
 return bool(re.search(r'^\s*(access denied|request blocked|forbidden)',text,re.I) or re.search(r'verify (?:that )?you are human|complete the captcha|captcha challenge',text,re.I))
def collect_one(context,key,target,out):
 path,label=SOURCES[key];dest=out/key;dest.mkdir();responses=[];blocks=[];errors=[]
 result={'dataset':key,'description':label,'requested_report_date':target,'started_at':now(),'source_url':ROOT+path,'status':'STARTED','coverage':'UNVERIFIED','drive_status':'NOT_TRANSFERRED'}
 page=context.new_page();page.set_default_timeout(20_000)
 def receive(r):
  if not official(r.url):return
  if r.status in [401,403,429]:blocks.append({'url':r.url,'status':r.status})
  ct=r.headers.get('content-type','').lower()
  if r.request.method=='GET' and ('json' in ct or 'xml' in ct or 'csv' in ct):
   rec={'url':r.url,'http_status':r.status,'content_type':ct,'retrieved_at':now()}
   try:
    body=r.body();ext='json' if 'json' in ct else 'xml' if 'xml' in ct else 'csv'
    rec.update(write_blob(dest,f'response_{len(responses):03}.{ext}',body))
    if ext=='json':
     obj=safe_json_bytes(body);rec['arrays']=[{'path':p,'rows':len(rows),'keys':sorted(set().union(*(r.keys() for r in rows)))[:100]} for p,rows in row_arrays(obj)]
   except Exception as e:rec['capture_error']=str(e)
   responses.append(rec)
 page.on('response',receive)
 try:
  main=page.goto(ROOT+path,wait_until='domcontentloaded',timeout=40_000)
  page.wait_for_timeout(1500)
  text=page.locator('body').inner_text(timeout=10_000)
  if (main and main.status in [401,403,429]) or page_blocked(text):
   result.update(status='ACCESS_BLOCKED',error='Official page denied access; no retry/bypass');return result
  try:page.wait_for_load_state('networkidle',timeout=12_000)
  except Exception:pass
  # Preserve rendered controls to adapt each dated export from observed UI.
  snapshot=page.evaluate('''() => ({title:document.title,url:location.href,text:document.body.innerText,inputs:[...document.querySelectorAll('input,select,button')].map(e=>({tag:e.tagName,id:e.id,name:e.name,type:e.type,value:e.value,text:e.innerText,options:e.options?[...e.options].map(x=>({text:x.text,value:x.value})):undefined})),links:[...document.querySelectorAll('a[href]')].map(a=>({text:a.innerText,url:a.href})),tables:[...document.querySelectorAll('table')].map(t=>[...t.rows].map(r=>[...r.cells].map(c=>c.innerText)))})''')
  (dest/'page_snapshot.json').write_text(json.dumps(snapshot,indent=2))
  result['page_title']=snapshot['title'];result['page_http_status']=main.status if main else None
  result['observed_controls']=len(snapshot['inputs']);result['observed_tables']=len(snapshot['tables'])
  # An API capture may be useful but is not silently promoted to validated coverage.
  captured=any(r.get('arrays') for r in responses)
  result.update(status='CAPTURED_UNVALIDATED' if captured else 'PAGE_ONLY',coverage='Page defaults/first response only; date, scope, pagination and export semantics need dataset adapter')
 except Exception as e:result.update(status='FAILED',error=f'{type(e).__name__}: {e}')
 finally:
  result.update(finished_at=now(),responses=responses,access_errors=blocks)
  (dest/'manifest.json').write_text(json.dumps(result,indent=2));page.close()
 return result

def main():
 p=argparse.ArgumentParser();p.add_argument('--date');p.add_argument('--datasets',default='all');p.add_argument('--output',type=Path,default=Path('bse_data_output'));args=p.parse_args()
 target=args.date or datetime.now(IST).date().isoformat();date.fromisoformat(target)
 if date.fromisoformat(target)>datetime.now(IST).date():p.error('Future report date')
 args.output.mkdir(parents=True,exist_ok=True)
 if any(args.output.iterdir()):p.error('Output must be empty; never reuse stale outputs')
 names=list(SOURCES) if args.datasets=='all' else args.datasets.split(',')
 if not set(names)<=set(SOURCES):p.error('Unknown dataset')
 started=now();results=[]
 from playwright.sync_api import sync_playwright
 with sync_playwright() as pw:
  browser=pw.chromium.launch(headless=False)
  try:
   context=browser.new_context(accept_downloads=True)
   # Ordinary browser bootstrap only; no evasion or repeated challenge attempts.
   home=context.new_page();r=home.goto(ROOT,wait_until='domcontentloaded',timeout=40_000);body=home.locator('body').inner_text()
   if (r and r.status in [401,403,429]) or page_blocked(body):
    results=[{'dataset':n,'status':'ACCESS_BLOCKED','error':'BSE home denied access; no source retries','requested_report_date':target} for n in names]
   else:
    home.close()
    for n in names:
     x=collect_one(context,n,target,args.output);results.append(x);print(n,x['status'],flush=True)
  except Exception as e:
   seen={x['dataset'] for x in results};results += [{'dataset':n,'status':'FAILED','error':str(e)} for n in names if n not in seen]
  finally:browser.close()
 status='COMPLETE' if results and all(x['status']=='VALIDATED_DOWNLOAD' for x in results) else 'PARTIAL'
 manifest={'schema_version':1,'started_at':started,'finished_at':now(),'requested_report_date':target,'mode':'Public BSE source acquisition; page captures are explicitly unvalidated','status':status,'github_run_id':os.getenv('GITHUB_RUN_ID'),'github_run_attempt':os.getenv('GITHUB_RUN_ATTEMPT'),'commit':os.getenv('GITHUB_SHA'),'datasets':results,'drive_status':'NOT_TRANSFERRED'}
 (args.output/'manifest.json').write_text(json.dumps(manifest,indent=2))
 return 0 if status=='COMPLETE' else 2
if __name__=='__main__':sys.exit(main())
