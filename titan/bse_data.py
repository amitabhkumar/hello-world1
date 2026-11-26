"""BSE public-data acquisition using an ordinary browser, with per-source evidence.
No fingerprint masking, proxy rotation, credential access or challenge bypass.
A captured page is not a validated dataset. Failures remain separately visible.
"""
import argparse, csv, hashlib, io, json, os, re, sys, zipfile
from contextlib import contextmanager
from time import perf_counter_ns
from datetime import datetime, date, timedelta
from pathlib import Path
from urllib.parse import urlparse, unquote
from zoneinfo import ZoneInfo
IST=ZoneInfo('Asia/Kolkata')
ROOT='https://www.bseindia.com'
MAX_BYTES=50_000_000
BSE_PACING_MS = int(os.environ.get("BSE_PACING_MS", "1800"))


@contextmanager
def timed(result, stage, **fields):
 entry = dict(stage=stage, **fields)
 start = perf_counter_ns()
 try:
  yield
 except Exception as error:
  entry["error"] = str(error)
  raise
 finally:
  entry["elapsed_ms"] = (perf_counter_ns() - start) / 1_000_000
  result.setdefault("timings", []).append(entry)


SOURCES={
 'announcements':('/corporates/ann.html','Corporate announcements/results/orders'),
 'delivery':('/markets/equity/EQReports/GrossShortPos?expandable=3&flag=0','Gross delivery download; actual page and file scope validated at runtime'),
 'bulk_block':('/markets/equity/EQReports/BulknBlockDeals.aspx','Bulk and block deals'),
 'corporate_actions':('/corporates/corporate_act.aspx','Corporate actions'),
 'asm':('/markets/equity/EQReports/additional_surveillance_measure.aspx','Additional surveillance measures'),
 'gsm':('/markets/equity/EQReports/graded_surveil_measure.aspx','Graded surveillance measures'),
 'shareholding':('/corporates/Sharehold_Searchnew.aspx','Shareholding patterns'),
 'pledges':('/corporates/pledge_new','Pledged shares'),
 'calendar':('/static/markets/marketinfo/listholi.aspx','Trading holidays'),
 'high_low':('/markets/equity/EQReports/HighLow?Flag=H','52-week high/low'),
 'breadth':('/markets/Equity/EQReports/Tradinghighlights_histroical.aspx','Breadth/circuit statistics'),
 'var_margin':('/markets/equity/EQReports/varmargin.aspx?flag=1','VaR margin groups'),
 'regulatory_files':('/members/index.aspx','SCRIP and REG_IND official reference files; ESM/TFT/bands require file validation'),
 'price_bands':('/stock-share-price/tech-mahindra-ltd/techm/532755/','Per-security price-band source probe (one observed primary-source page; not exchange-wide)'),
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

# Dataset adapters. Raw responses remain immutable beside normalized exports.
def snapshot_page(page):
 return page.evaluate("""() => ({title:document.title,url:location.href,text:document.body.innerText,inputs:[...document.querySelectorAll('input,select,button')].map(e=>({tag:e.tagName,id:e.id,name:e.name,type:e.type,value:e.value,text:e.innerText,options:e.options?[...e.options].map(x=>({text:x.text,value:x.value})):null})),links:[...document.querySelectorAll('a[href]')].map(a=>({text:a.innerText,url:a.href})),tables:[...document.querySelectorAll('table')].map(t=>[...t.rows].map(r=>[...r.cells].map(c=>c.innerText)))})""")
def settled(page):
 page.wait_for_timeout(1200)
 try:page.wait_for_load_state('networkidle',timeout=8000)
 except Exception:pass
def matched(responses,dest,term):
 found=[r for r in responses if term.lower() in r['url'].lower() and r.get('http_status')==200 and r.get('file','').endswith('.json')]
 if not found:raise ValueError('Required data response not observed: '+term)
 r=found[-1];return r,safe_json_bytes((dest/r['file']).read_bytes())
def require_rows(rows,keys):
 if not isinstance(rows,list) or not rows:raise ValueError('No records; empty response is not proof of no data')
 if not all(isinstance(r,dict) and set(keys)<=r.keys() for r in rows):raise ValueError('Required record fields missing: '+str(keys))
 return rows
def export_rows(dest,name,rows,keys,source,scope):
 require_rows(rows,keys);files=[]
 # Partition large normalized JSON without dropping records or changing raw inputs.
 for offset in range(0,len(rows),5000):
  part=rows[offset:offset+5000];suffix='' if len(rows)<=5000 else '_part%03d'%(offset//5000+1)
  j=write_blob(dest,name+suffix+'.json',json.dumps(part,ensure_ascii=False,separators=(',',':')).encode())
  assert safe_json_bytes((dest/j['file']).read_bytes())==part
  files.append(dict(j,first_row=offset+1,last_row=offset+len(part)))
 fields=list(dict.fromkeys(k for r in rows for k in r))
 buf=io.StringIO(newline='');writer=csv.DictWriter(buf,fieldnames=fields);writer.writeheader();writer.writerows(rows)
 cf=write_blob(dest,name+'.csv',buf.getvalue().encode('utf-8-sig'));files.append(cf)
 assert len(list(csv.DictReader(io.StringIO((dest/cf['file']).read_text(encoding='utf-8-sig')))))==len(rows)
 dates={k:sorted({str(r.get(k)) for r in rows}) for k in fields if any(w in k.lower() for w in ['date','dttm','dt_tm','time'])}
 return dict(rows=len(rows),source_url=source,scope=scope,files=files,required_fields=keys,
             source_date_fields={k:values[:20] for k,values in dates.items()},
             source_date_values_truncated={k:len(values)>20 for k,values in dates.items()})
def query_url(url,**changes):
 from urllib.parse import parse_qsl,urlencode,urlunparse
 p=urlparse(url);q=dict(parse_qsl(p.query,keep_blank_values=True));q.update({k:str(v) for k,v in changes.items()})
 return urlunparse(p._replace(query=urlencode(q)))
def browser_json(page,url,dest,name):
 if not official(url):raise ValueError('Non-official API')
 x=page.evaluate("""async u => {const r=await fetch(u,{signal:AbortSignal.timeout(90000)}); return {status:r.status,url:r.url,text:await r.text()};}""",url)
 if x['status'] in [401,403,429]:raise PermissionError('Official API denied access: '+str(x['status']))
 if x['status']!=200 or not official(x['url']):raise ValueError('Unexpected API response '+str(x['status']))
 b=x['text'].encode();meta=write_blob(dest,name+'.json',b)
 return safe_json_bytes(b),dict(url=url,retrieved_at=now(),http_status=x['status'],**meta)
def announcement_json(page,url,dest,name):
 # Let Chromium supply same-session Origin/Referer for the rendered official page.
 obj,meta=browser_json(page,url,dest,name)
 if not isinstance(obj,dict) or 'Table' not in obj:raise ValueError('Announcement response missing Table; empty object is not zero records')
 return obj,meta

def pledge_csv(page,target,dest,result):
 # Official visible export; no manually generated pledge JSON request.
 control=page.locator("main a:has-text('CSV'),main button:has-text('CSV'),main [title*='Download'],main [aria-label*='Download'],main a:has(img[alt*='Download'])").filter(visible=True)
 with timed(result,'export_control_detection'):
  control.first.wait_for(state='visible',timeout=30000)
 if control.count()!=1:raise ValueError('Pledge CSV export control missing or ambiguous')
 with timed(result,'download_event'):
  with page.expect_download(timeout=45000) as pending:
   with timed(result,'export_click'):
    control.click()
 with timed(result,'download_completion'):
  download=pending.value
  failure=download.failure()
  if failure:raise ValueError('Pledge download failed: '+str(failure))
  name='pledges_official.csv';download.save_as(dest/name);body=(dest/name).read_bytes()
 if not body or body.lstrip().startswith(b'<'):raise ValueError('Pledge export empty or HTML')
 text,encoding=decode_reference(body);reader=csv.DictReader(io.StringIO(text));rows=list(reader)
 fields=reader.fieldnames or [];norm={re.sub(r'[^a-z0-9]','',f.lower()):f for f in fields}
 code=next((norm[x] for x in ['scripcode','securitycode','companycode'] if x in norm),None)
 company='Name of the Company (1)'
 if code is None and company in fields:
  code='BSE_Code_Derived'
  for row in rows:
   match=re.search(r'\((\d{6})\)\s*$',str(row[company]))
   if not match:raise ValueError('Missing BSE code in official company label')
   row[code]=match.group(1)
 pledged=[f for f in fields if 'pledg' in f.lower()]
 if not code or not pledged:raise ValueError('Pledge CSV schema missing security code or pledged holding columns: '+str(fields))
 require_rows(rows,[code]+pledged)
 if any(not re.fullmatch(r'\d{6}',str(r[code]).strip()) for r in rows):raise ValueError('Invalid pledge security identifier')
 result['downloads']=[dict(file=name,**fingerprint(body),suggested_filename=download.suggested_filename,source_url=page.url,download_url=download.url,encoding=encoding)]
 result['exports']=[export_rows(dest,'pledges_csv_records',rows,[code]+pledged,page.url,'Official consolidated CSV snapshot; reporting periods and current as-on date are not historical reconstruction')]
 result.update(status='VALIDATED_SNAPSHOT',coverage='Official CSV export; current snapshot, not proof of complete historical coverage for requested date',source_asof_text=page.locator('main').inner_text()[:4000],historical_asof_verified=False)

def pledge_json_fallback(page,dest,responses,result):
 try:
  r,obj=matched(responses,dest,'GetCorpPledgeShareholding_ng')
  src_url=r['url']
 except ValueError:
  src_url='https://api.bseindia.com/BseIndiaAPI/api/GetCorpPledgeShareholding_ng/w?COMPANY=&Group=&Status=&Industryname=&PledgeRange=&DeriTrade='
  obj,meta=browser_json(page,src_url,dest,'pledges_api_raw')
  result.setdefault('requests',[]).append(meta)
 rows=require_rows(obj.get('Table') if isinstance(obj,dict) else obj,['ScripCode','CompanyName','Noofsharespledged'])
 result['exports']=[export_rows(dest,'pledges_api_records',rows,['ScripCode','CompanyName','Noofsharespledged'],src_url,'Official consolidated pledge API snapshot (fallback after CSV export timeout); current as-on snapshot, not historical reconstruction')]
 result.update(status='VALIDATED_SNAPSHOT',coverage='Official GetCorpPledgeShareholding_ng JSON fallback; current snapshot, not proof of complete historical coverage for requested date',historical_asof_verified=False)

def transient_error(error):
 if isinstance(error,PermissionError):return False
 text=str(error).lower()
 return any(word in text for word in ('failed to fetch','timeout','timed out','connection reset','connection closed','net::err_','response 500','response 502','response 503','response 504'))

def bounded_attempt(operation,attempts,page,history,label):
 for attempt in range(1,attempts+1):
  try:
   value=operation(attempt)
   history.append({'operation':label,'attempt':attempt,'status':'SUCCESS','at':now()})
   return value
  except Exception as error:
   retry=attempt<attempts and transient_error(error)
   history.append({'operation':label,'attempt':attempt,'status':'ERROR','error':type(error).__name__+': '+str(error),'retry_planned':retry,'at':now()})
   if not retry:raise
   delay=2**(attempt-1);history[-1]['backoff_seconds']=delay
   page.wait_for_timeout(delay*1000)

def pledge_with_reloads(page,target,dest,result):
 history=result.setdefault('attempt_history',[])
 result['retry_policy']='3 total page/download attempts; 1s/2s backoff; no retry of access denial or invalid CSV'
 def attempt(n):
  response=page.goto(ROOT+SOURCES['pledges'][0],wait_until='domcontentloaded',timeout=40000) if n==1 else page.reload(wait_until='domcontentloaded',timeout=40000)
  if response and response.status in [401,403,429]:raise PermissionError('Pledge page denied access: '+str(response.status))
  if response and response.status>=500:raise RuntimeError('Pledge response '+str(response.status))
  try:
   if page_blocked(page.locator('body').inner_text(timeout=10000)):raise PermissionError('Pledge page access challenge')
   with timed(result,'consolidated_pledge_csv_path'):
    pledge_csv(page,target,dest,result)
  finally:
   try:(dest/('page_attempt_%02d.json'%n)).write_text(json.dumps(snapshot_page(page),indent=2))
   except Exception as e:result.setdefault('diagnostic_errors',[]).append(str(e))
 if os.getenv('BSE_DIAGNOSTIC_SINGLE_PASS')=='1':
  result['retry_policy']='NONE; diagnostic run'
  return attempt(1)
 return bounded_attempt(attempt,3,page,history,'pledge_page_and_export')

def announcement_ui_response(page,target,start,dest,result,n,label,backward=False):
 """One genuine UI action, one response; never manufacture a pagination URL."""
 from urllib.parse import parse_qs
 controls=page.get_by_text('Prev',exact=True).filter(visible=True) if backward else page.locator('#idnext').filter(visible=True) if n!=1 else page.get_by_role('button',name='Submit',exact=True)
 if not controls.count():raise ValueError('Required announcement UI control unavailable')
 write_blob(dest,label+'_before_dom.json',json.dumps(snapshot_page(page),ensure_ascii=False).encode())
 def matches(response):
  if not official(response.url) or 'AnnSubCategoryGetData' not in response.url:return False
  q=parse_qs(urlparse(response.url).query)
  return q.get('pageno')==[str(n)] and q.get('strPrevDate')==[start.replace('-','')] and q.get('strToDate')==[target.replace('-','')]
 try:
  with page.expect_response(matches,timeout=90000) as event:
   with timed(result,'pagination_click' if backward or n>1 else 'submit_click',page=n,label=label):
    controls.first.click()
  response=event.value;body=response.body()
  meta=dict(url=response.url,http_status=response.status,retrieved_at=now(),**write_blob(dest,label+'.json',body))
  result['requests'].append(meta)
  if response.status!=200:raise ValueError('Announcement UI response HTTP '+str(response.status))
  obj=safe_json_bytes(body)
  if not isinstance(obj,dict) or 'Table' not in obj:raise ValueError('Announcement response missing Table')
  page.get_by_text(re.compile(r'Current Page Number\s*'+str(n)+r'\s+out of')).first.wait_for(state='visible',timeout=30000)
  return obj
 finally:
  write_blob(dest,label+'_after_dom.json',json.dumps(snapshot_page(page),ensure_ascii=False).encode())

def announcement_pages(page,target,dest,responses,result):
 start=result.get('requested_from_date',target)
 result['requests']=[]
 result['retry_policy']='NONE; genuine UI Submit/Next clicks only; no synthetic pagination requests'
 result['pagination_control']='Observed current BSE UI #idnext Next; advances each page including 6/11/16/21'
 def fetch(n,label):
  backward=label.startswith('ann_recheck')
  if n!=1 or backward:page.wait_for_timeout(BSE_PACING_MS)
  stage='page_1_stability_recheck' if n==1 and 'recheck' in label else 'pagination_response' if backward or n>1 else 'first_announcements_response'
  with timed(result,stage,page=n,label=label):
   return announcement_ui_response(page,target,start,dest,result,n,label,backward=backward)
 obj=fetch(1,'ann_page_001');rows=require_rows(obj.get('Table'),['NEWSID','SCRIP_CD','NEWS_DT'])
 expected=int(obj['Table1'][0]['ROWCNT']);size=len(rows)
 if expected<1 or expected>50000:raise ValueError('Announcement count outside explicit safety bound')
 result['expected_rows']=expected;unique={};duplicate_count=0
 def add(records):
  nonlocal duplicate_count
  for row in records:
   ident=str(row['NEWSID'])
   if not ident.strip():raise ValueError('Empty NEWSID')
   if ident in unique:
    if unique[ident]!=row:raise ValueError('Conflicting records for NEWSID '+ident)
    duplicate_count+=1
   else:unique[ident]=row
  result.update(captured_unique_rows=len(unique),duplicate_records=duplicate_count)
  write_blob(dest,'announcements_partial_checkpoint.json',json.dumps(list(unique.values()),ensure_ascii=False).encode())
 add(rows)
 for n in range(2,(expected+size-1)//size+1):
  obj=fetch(n,'ann_page_%03d'%n)
  if int(obj['Table1'][0]['ROWCNT'])!=expected:raise ValueError('Announcement ROWCNT changed during pagination')
  add(require_rows(obj.get('Table'),['NEWSID','SCRIP_CD','NEWS_DT']))
 check=obj
 for n in range((expected+size-1)//size-1,0,-1):
  check=fetch(n,'ann_recheck_%03d'%n)
 if (expected+size-1)//size==1:
  check=fetch(1,'ann_page_001_recheck')
 stable=int(check['Table1'][0]['ROWCNT'])==expected and [x['NEWSID'] for x in check['Table']]==[x['NEWSID'] for x in rows]
 allrows=list(unique.values());dates_ok=all(start<=str(x['NEWS_DT'])[:10]<=target for x in allrows)
 result.update(pagination_stable=stable,unique_ids=True,record_dates_match=dates_ok)
 if len(allrows)!=expected:raise ValueError('Unique announcement count mismatch: %s != %s'%(len(allrows),expected))
 if not stable or not dates_ok:raise ValueError('Announcement stability/date verification failed')
 result['exports']=[export_rows(dest,'announcements',allrows,['NEWSID','SCRIP_CD','NEWS_DT'],result['requests'][0]['url'],'All category announcements for inclusive date window; attachments not assessed')]
 result.update(status='VALIDATED_DATED_RECORDS',coverage='All unique rows reconciled to stable official ROWCNT; publication times retained; material attachments remain research work')

def announcement_api_fallback(page,target,dest,result):
 start=result.get('requested_from_date',target)
 result['requests']=[]
 result['retry_policy']='Same-session official AnnSubCategoryGetData API fallback with BSE_PACING_MS delay'
 base_url='https://api.bseindia.com/BseIndiaAPI/api/AnnSubCategoryGetData/w?pageno=1&strCat=-1&strPrevDate='+start.replace('-','')+'&strScrip=&strSearch=P&strToDate='+target.replace('-','')+'&strType=C&subcategory=-1'
 history=result.setdefault('attempt_history',[])
 def fetch(n,label):
  if n>1:page.wait_for_timeout(BSE_PACING_MS)
  url=query_url(base_url,pageno=n)
  def call_api(_attempt):
   obj,meta=announcement_json(page,url,dest,label)
   result['requests'].append(meta)
   return obj
  with timed(result,'api_fallback_page',page=n,label=label):
   return bounded_attempt(call_api,2,page,history,label)
 obj=fetch(1,'ann_api_001');rows=require_rows(obj.get('Table'),['NEWSID','SCRIP_CD','NEWS_DT'])
 expected=int(obj['Table1'][0]['ROWCNT']);size=len(rows)
 if expected<1 or expected>50000:raise ValueError('Announcement count outside explicit safety bound')
 result['expected_rows']=expected;unique={};duplicate_count=0
 def add(records):
  nonlocal duplicate_count
  for row in records:
   ident=str(row['NEWSID'])
   if not ident.strip():raise ValueError('Empty NEWSID')
   if ident in unique:duplicate_count+=1
   else:unique[ident]=row
  result.update(captured_unique_rows=len(unique),duplicate_records=duplicate_count)
 add(rows)
 for n in range(2,(expected+size-1)//size+1):
  obj=fetch(n,'ann_api_%03d'%n)
  page_rows=obj.get('Table') or []
  if not page_rows:break
  add(require_rows(page_rows,['NEWSID','SCRIP_CD','NEWS_DT']))
 allrows=list(unique.values());dates_ok=all(start<=str(x['NEWS_DT'])[:10]<=target for x in allrows)
 result.update(unique_ids=True,record_dates_match=dates_ok)
 if len(allrows)<expected:raise ValueError('Unique announcement count below expected: %s < %s'%(len(allrows),expected))
 if not dates_ok:raise ValueError('Announcement date verification failed')
 result['exports']=[export_rows(dest,'announcements',allrows,['NEWSID','SCRIP_CD','NEWS_DT'],result['requests'][0]['url'],'All category announcements for inclusive date window (API fallback); attachments not assessed')]
 result.update(status='VALIDATED_DATED_RECORDS',coverage='All unique rows reconciled to official AnnSubCategoryGetData ROWCNT via same-session API fallback; publication times retained')

def fill_dates(page,target):
 value=date.fromisoformat(target).strftime('%d/%m/%Y')
 loc=page.locator('input');filled=[]
 for i in range(loc.count()):
  e=loc.nth(i);ident=e.get_attribute('id') or ''
  if ('date' in ident.lower() or ident in ['SelectFromDt','SelectToDt']) and e.is_visible() and e.get_attribute('type') not in ['checkbox','radio','button','submit']:
   try:e.fill(value);e.press('Tab');filled.append(ident)
   except Exception:pass
 return filled
def submit(page):
 # Header controls also declare type=submit; target the report's actual Submit.
 loc=page.locator("input[value='Submit'],button:has-text('Submit'),#btnSubmit,#ContentPlaceHolder1_btnSubmit")
 for i in range(loc.count()):
  if loc.nth(i).is_visible():loc.nth(i).click();settled(page);return
 raise ValueError('No visible report Submit control')
def file_candidates(snapshot,objects,key):
 from urllib.parse import urljoin
 urls=[]
 for x in snapshot['links']:
  u=x['url'];text=(x['text'] or '').lower();base=urlparse(u).path.lower()
  if key=='delivery':
   keep=bool(re.search(r'/SCBSEALL.*\.(zip|txt)$',base,re.I))
  elif key=='regulatory_files':
   keep=bool(re.search(r'/(scrip\.zip|reg_ind[^/]*\.(zip|txt|csv))$',base))
  else:keep=bool(re.search(r'\.(csv|zip|xlsx?|pdf)$',base)) and any(w in (base+' '+text) for w in {'asm':['asm','surveil','short term','long term'],'gsm':['gsm','graded'],'var_margin':['varmargin','var margin']}[key])
  if keep and official(u):urls.append(u)
 for obj in objects:
  for _,rows in row_arrays(obj):
   for r in rows:
    for k,v in r.items():
     if k.lower() in ['url','filepath','file_path','file_path_csv'] and isinstance(v,str):
      u=urljoin(ROOT+'/',v.replace('\\','/'))
      if official(u) and re.search(r'\.(zip|csv|xlsx?|pdf)$',urlparse(u).path,re.I):urls.append(u)
 return list({u.lower():u for u in reversed(urls)}.values())
def inspect_download(body,name):
 if body.lstrip().lower().startswith((b'<!doctype html',b'<html')):raise ValueError('HTML returned instead of file')
 if name.lower().endswith('.zip'):
  with zipfile.ZipFile(io.BytesIO(body)) as z:
   if sum(i.file_size for i in z.infolist())>MAX_BYTES*4:raise ValueError('Expanded archive too large')
   bad=z.testzip()
   if bad:raise ValueError('Bad ZIP CRC: '+bad)
   return {'format':'zip','members':[{'name':i.filename,'bytes':i.file_size} for i in z.infolist()]}
 if name.lower().endswith('.csv'):
  rows=list(csv.reader(io.StringIO(body.decode('utf-8-sig'))))
  if len(rows)<2:raise ValueError('CSV has no data records')
  return {'format':'csv','rows_including_header':len(rows),'first_rows':rows[:3]}
 if name.lower().endswith('.pdf') and body.startswith(b'%PDF'):return {'format':'pdf','semantic_validation':'PENDING'}
 if name.lower().endswith(('.xls','.xlsx')):return {'format':'spreadsheet','semantic_validation':'PENDING'}
 raise ValueError('Unsupported or invalid file format')
def download_files(context,dest,urls):
 files=[];errors=[]
 for i,url in enumerate(urls):
  try:
   r=context.request.get(url,timeout=30000,max_redirects=0)
   if r.status in [401,403,429]:raise PermissionError('Access denied '+str(r.status))
   if r.status!=200:raise ValueError('HTTP '+str(r.status))
   b=r.body();name='%02d_'%i+re.sub(r'[^A-Za-z0-9_.-]','_',unquote(urlparse(url).path.rsplit('/',1)[-1]))
   check=inspect_download(b,name);meta=write_blob(dest,name,b)
   assert fingerprint((dest/name).read_bytes())['sha256']==meta['sha256']
   files.append(dict(source_url=url,retrieved_at=now(),http_status=r.status,validation=check,**meta))
  except PermissionError as e:errors.append({'url':url,'error':str(e)});break
  except Exception as e:errors.append({'url':url,'error':str(e)})
 return files,errors


def parse_source_date(value):
 s=str(value).strip()
 try:return datetime.fromisoformat(s.replace('Z','+00:00')).date()
 except ValueError:pass
 for fmt in ['%d/%m/%Y','%d-%b-%Y','%d %b %Y','%d/%m/%y','%d-%b-%y','%Y%m%d','%d%m%Y']:
  try:return datetime.strptime(s,fmt).date()
  except ValueError:pass
 raise ValueError('Unrecognized source date: '+s)
def validate_delivery(rows,target):
 from decimal import Decimal
 require_rows(rows,['DATE','SCRIP CODE','DELIVERY QTY',"DAY'S VOLUME",'DELV. PER.'])
 seen=set()
 for r in rows:
  if parse_source_date(r['DATE'])!=date.fromisoformat(target):raise ValueError('Delivery record date mismatch')
  code=r['SCRIP CODE'].strip()
  if code in seen or not re.fullmatch(r'\d{6}',code):raise ValueError('Invalid/duplicate delivery code')
  seen.add(code);qty=int(r['DELIVERY QTY']);volume=int(r["DAY'S VOLUME"]);pct=Decimal(r['DELV. PER.'])
  if qty<0 or volume<0 or qty>volume or not pct.is_finite() or not 0<=pct<=100:raise ValueError('Invalid delivery quantities/percentage')
  if volume and abs(Decimal(qty)*100/Decimal(volume)-pct)>Decimal('0.011'):raise ValueError('Delivery percentage arithmetic mismatch')
  if volume==0 and (qty!=0 or pct!=0):raise ValueError('Nonzero delivery with zero volume')

def decode_reference(body):
 try:return body.decode('utf-8-sig'),'utf-8-sig'
 except UnicodeDecodeError:return body.decode('cp1252'),'cp1252 (explicit fallback; original bytes preserved)'
def extract_reference_files(dest,files):
 import xml.etree.ElementTree as ET
 result=[]
 for f in files:
  if f['validation']['format']!='zip':continue
  with zipfile.ZipFile(dest/f['file']) as z:
   for item in z.infolist():
    base=Path(item.filename).name
    if item.is_dir() or not base.lower().endswith(('.csv','.txt','.docx')):continue
    body=z.read(item);name=re.sub(r'[^A-Za-z0-9_.-]','_',Path(f['file']).stem+'_'+base)
    rec=dict(archive=f['file'],member=item.filename,**write_blob(dest,name,body))
    if base.lower().endswith('.docx'):
     with zipfile.ZipFile(io.BytesIO(body)) as doc:
      root=ET.fromstring(doc.read('word/document.xml'));ns={'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
      paras=[''.join(p.itertext()) for p in root.findall('.//w:p',ns)]
      # Use text nodes only; preserve documentation alongside the raw archive.
      textparts=[''.join(t.text or '' for t in p.findall('.//w:t',ns)) for p in root.findall('.//w:p',ns)]
      txt='\n'.join(textparts);write_blob(dest,name+'.txt',txt.encode())
      snippets=[]
      for m in re.finditer('REG_IND|REG1_IND|ESM|Trade.to.Trade|price band|circuit',txt,re.I):
       snippets.append(txt[max(0,m.start()-200):m.start()+1100])
      rec['documentation_excerpt']=snippets[:14];rec['documentation_text']=txt[:35000]
    else:
     txt,encoding=decode_reference(body);rec['encoding']=encoding;delim='|' if txt.splitlines() and '|' in txt.splitlines()[0] else ','
     records=list(csv.reader(io.StringIO(txt),delimiter=delim));rec.update(line_count=len(records),delimiter=delim,first_rows=records[:3])
    result.append(rec)
 print('ARCHIVE_DIAGNOSTIC '+json.dumps(result,ensure_ascii=False),flush=True)
 return result

def adapt(context,page,key,target,dest,responses,result):
 result['exports']=[]
 if key=='announcements':
  if os.getenv('BSE_DIAGNOSTIC_SINGLE_PASS')=='1':
   result['date_controls_filled']=fill_dates(page,target)
   from_input=page.locator('#corporates-ann-from-date')
   from_input.fill(result.get('requested_from_date',target)[8:10]+'/'+result.get('requested_from_date',target)[5:7]+'/'+result.get('requested_from_date',target)[:4])
   from_input.press('Tab')
   announcement_pages(page,target,dest,responses,result);return
  announcement_api_fallback(page,target,dest,result);return
 if key=='pledges':pledge_csv(page,target,dest,result);return
 if key=='security_master':
  page.locator('#ddlsegment').select_option('Equity');page.locator('#ddlstatus').select_option(label='Active');submit(page)
 if key in ['delivery','high_low']:
  if page.locator('#Period').count():page.locator('#Period').select_option('D');settled(page)
  result['date_controls_filled']=fill_dates(page,target)
  try:submit(page)
  except ValueError:result['form_note']='No visible report Submit; preserve page controls and downloads'
 if key=='bulk_block':
  if page.locator('#checkId').count():page.locator('#checkId').check()
  result['date_controls_filled']=fill_dates(page,target)
  for value in ['1','2']:
   page.locator('#SelectDeal').select_option(value);submit(page)
 # Diagnose unknown adapters from the actually rendered controls and responses.
 snap=snapshot_page(page);(dest/'page_snapshot_after.json').write_text(json.dumps(snap,indent=2))
 relevant=[r for r in responses if not any(t in r['url'] for t in ['appConfig','Mkt_GetTicker','GetSensexDatanew','GetINDUSTRYWATCHLIST'])]
 result['observed_data_responses']=[{'url':r['url'],'arrays':r.get('arrays',[])} for r in relevant]
 print('ADAPTER_DIAGNOSTIC '+json.dumps({'dataset':key,'inputs':[{**x,'options':(x.get('options') or [])[:12]} for x in snap['inputs'] if x.get('id')][-18:],'responses':result['observed_data_responses'],'tables_preview':[t[:3] for t in snap['tables']][:4]},ensure_ascii=False),flush=True)
 contracts={
  'security_master':('ListofScripData_new/w',['SCRIP_CD','ISIN_NUMBER','Status','Segment'],'Active Equity T+1 securities returned by official all-group endpoint; other statuses and segments excluded'),
  'shareholding':('Corp_Shareholding_ng',['FLD_ScripCode','EndDate'],'All industries; last one year of filing metadata requested; underlying ownership tables are linked, not parsed'),
  'corporate_actions':('DefaultData/w',['scrip_code','Ex_date','Purpose'],'All equity actions for requested 370-day history plus 30-day forward Ex Date window; raw actions, not adjustment factors'),
  'breadth':('tradinghighlight/w',['DTTM','Gainer','Loser'],'Source date-window market breadth'),
  'market_quotes':('GetMktData/w',['scrip_cd','FileDTTM','trd_vol'],'AllMkt endpoint snapshot; not order-book depth or same-time intraday history'),
 }
 if key in contracts:
  term,keys,scope=contracts[key]
  try:r,obj=matched(responses,dest,term)
  except ValueError:
   known={
    'security_master':'https://api.bseindia.com/BseIndiaAPI/api/ListofScripData_new/w?Group=&Scripcode=&segment=Equity&status=Active&scripName='
   }
   if key not in known or result.get('access_errors'):raise
   obj,m=browser_json(page,known[key],dest,'explicit_'+key);result['requests']=[m];r={'url':m['url']}
  rows=obj.get('Table') if isinstance(obj,dict) else obj
  if key=='shareholding':
   obj,m=browser_json(page,query_url(r['url'],flag='6'),dest,'shareholding_one_year');result['requests']=[m];rows=obj.get('Table');r={'url':m['url']}
  if key=='corporate_actions':
   start=date.fromisoformat(target)-timedelta(days=370);end=date.fromisoformat(target)+timedelta(days=30)
   obj,m=browser_json(page,query_url(r['url'],Fdate=start.strftime('%Y%m%d'),TDate=end.strftime('%Y%m%d'),strSearch='S'),dest,'corporate_actions_window')
   result['requests']=[m];rows=obj.get('Table') if isinstance(obj,dict) else obj;r={'url':m['url']}
   result['requested_action_window']={'from':start.isoformat(),'to':end.isoformat(),'field':'Ex Date'}
  if key=='breadth':
   d=target.replace('-','');obj,m=browser_json(page,query_url(r['url'],fromdate=d,todate=d),dest,'dated_breadth')
   result['requests']=[m];rows=obj.get('Table');scope='Requested single-date breadth; source DTTM retained'
  result['exports']=[export_rows(dest,key,rows,keys,m['url'] if key=='breadth' else r['url'],scope)]
  if key=='breadth' and not all(str(x['DTTM']).startswith(target) for x in rows):raise ValueError('Breadth date mismatch')
  result.update(status='VALIDATED_SNAPSHOT',coverage=scope,point_in_time_reconstruction=False)
  if key=='shareholding':
   from titan.bse_details import latest_filings,fetch_details
   items=latest_filings(rows)
   result['_detail_capture_active']=True
   try:details,errors=fetch_details(page,items,dest,'ownership',target)
   finally:result.pop('_detail_capture_active',None)
   result['detail_population']=len(items);result['detail_validated']=len(details);result['detail_errors']=errors
   if details:result['exports'].append(export_rows(dest,'latest_original_ownership',details,['scrip_code','url','quarter','tables'],r['url'],'Latest original filing per issuer in the one-year index; original ownership tables parsed and retained, no ownership-change inference'))
   result.update(status='VALIDATED_SNAPSHOT' if len(details)==len(items) and not errors else 'PARTIAL',coverage='One-year filing index plus latest original ownership tables per issuer. Earlier-quarter comparisons remain research work, not completed by acquisition.')
  if key=='corporate_actions':
   dates=[datetime.strptime(str(x['exdate']),'%Y%m%d').date() for x in rows]
   ok=all(start<=d<=end for d in dates)
   result.update(status='VALIDATED_DATED_RECORDS' if ok else 'PARTIAL',window_dates_match=ok,observed_ex_date_min=min(dates).isoformat(),observed_ex_date_max=max(dates).isoformat())
  if key=='breadth':result['status']='VALIDATED_DATED_RECORDS'
 elif key=='bulk_block':
  from urllib.parse import parse_qs
  result['deal_types']=[]
  for value,label in [('1','bulk'),('2','block')]:
   try:
    candidates=[r for r in responses if 'BulkDealData_ng/w' in r['url'] and parse_qs(urlparse(r['url']).query).get('DealType')==[value] and r.get('http_status')==200]
    if not candidates:raise ValueError('Missing dated '+label+' response')
    r=candidates[-1];obj=safe_json_bytes((dest/r['file']).read_bytes());rows=obj.get('Table')
    print('DEAL_PAYLOAD '+json.dumps({'type':label,'payload':obj if not rows else {'rows':len(rows),'first':rows[0]}},ensure_ascii=False),flush=True)
    params=parse_qs(urlparse(r['url']).query);d=date.fromisoformat(target).strftime('%d/%m/%Y')
    if params.get('FDate')!=[d] or params.get('TDate')!=[d]:raise ValueError('Deal date filter mismatch')
    if rows in [None,[]] and 'Table' in obj:
     result['deal_types'].append({'type':label,'status':'EMPTY_RESPONSE','rows':0,'source_url':r['url'],'evidence':r['file'],'meaning':'Official dated endpoint returned no rows; not proof of no institutional activity'})
     continue
    require_rows(rows,['DEAL_DATE','SCRIP_CODE','QUANTITY','PRICE'])
    parsed=[parse_source_date(x['DEAL_DATE']) for x in rows]
    if any(x!=date.fromisoformat(target) for x in parsed):raise ValueError('Deal record date mismatch')
    result['exports'].append(export_rows(dest,label+'_deals',rows,['DEAL_DATE','SCRIP_CODE','QUANTITY','PRICE'],r['url'],'Official dated '+label+' deal records; clients and buy/sell side retained without investor-intent inference'))
    result['deal_types'].append({'type':label,'status':'VALIDATED_DATED_RECORDS','rows':len(rows),'source_url':r['url']})
   except Exception as e:
    result['deal_types'].append({'type':label,'status':'FAILED','error':str(e)})
  result.update(status='VALIDATED_DATED_RECORDS' if all(x['status'] in ['VALIDATED_DATED_RECORDS','EMPTY_RESPONSE'] for x in result['deal_types']) else 'PARTIAL',coverage='Both deal types requested separately for exact date; failures and schema-confirmed empty responses explicitly recorded')
 elif key=='high_low':
  r,obj=matched(responses,dest,'MktHighLowDataNew/w')
  for table,label,field in [('Table','high','Cur52wkHigh'),('Table1','low','Cur52wkLow')]:
   rows=require_rows(obj.get(table),['SCRIP_CD',field,'dt_tm'])
   result['exports'].append(export_rows(dest,'52_week_'+label,rows,['SCRIP_CD',field,'dt_tm'],r['url'],'All returned current 52-week '+label+' events; timestamps retained, not a historical adjusted-price reconstruction'))
  result.update(status='VALIDATED_SNAPSHOT',coverage='Both high and low arrays, all returned groups; may include non-ordinary instruments')
 elif key in ['asm','gsm','var_margin','regulatory_files','delivery']:
  objects=[]
  for r in relevant:
   if r.get('file','').endswith('.json'):
    objects.append(safe_json_bytes((dest/r['file']).read_bytes()))
  urls=file_candidates(snap,objects,key)
  if key=='delivery':urls=[u for u in urls if urlparse(u).hostname=='www.bseindia.com']
  if key in ['asm','gsm']:urls=[u for u in urls if '/downloads1/' in u.lower() and 'list_of_' in u.lower() and u.lower().endswith('.csv')]
  result['download_candidates']=urls
  files,errors=download_files(context,dest,urls);result.update(downloads=files,download_errors=errors)
  result.update(status='DOWNLOADED_UNVALIDATED' if files else 'NO_DOWNLOAD_FOUND',coverage='File integrity checked; effective dates and security restriction semantics require validation')
  if key in ['asm','gsm']:
   token=date.fromisoformat(target).strftime('%d%m%Y')
   valid=len(files)==(2 if key=='asm' else 1) and not errors
   for f in files:
    rows=list(csv.DictReader(io.StringIO((dest/f['file']).read_text(encoding='utf-8-sig'))))
    valid=valid and token in f['file'] and bool(rows) and all(re.fullmatch(r'\d{6}',r.get('Scrip Code','').strip()) and r.get('ISIN','').strip() for r in rows)
    result['exports'].append(export_rows(dest,Path(f['file']).stem+'_records',rows,['Scrip Code','ISIN'],f['source_url'],'Official dated surveillance list; stage definitions retained; no retrospective reconstruction'))
   result.update(status='VALIDATED_DATED_RECORDS' if valid else 'PARTIAL',record_dates_match=valid,coverage='Filename date, security identifier and nonempty records checked for all expected lists')
  if key in ['regulatory_files','var_margin','delivery']:
   result['archive_members']=extract_reference_files(dest,files)
   if key=='delivery':
    for member in result['archive_members']:
     if not re.fullmatch(r'SCBSEALL\d{4}\.TXT',Path(member['member']).name,re.I):continue
     text,enc=decode_reference((dest/member['file']).read_bytes())
     rows=list(csv.DictReader(io.StringIO(text),delimiter='|'))
     validate_delivery(rows,target)
     result['exports'].append(export_rows(dest,'delivery',rows,['DATE','SCRIP CODE','DELIVERY QTY',"DAY'S VOLUME",'DELV. PER.'],files[0]['source_url'],'Exact-date delivery report. Quantity fields: shares; published percentage: percent. Value/turnover fields retained as published; units not silently converted.'))
    result.update(status='VALIDATED_DATED_RECORDS' if result['exports'] else 'PARTIAL',coverage='All records in downloaded daily delivery file; unique codes, dates, nonnegative quantities, delivery<=volume and reported percentage checked')
   if key=='var_margin':
    for member in result['archive_members']:
     if not re.fullmatch(r'gr[12]_\d{8}\.csv',Path(member['member']).name,re.I):continue
     text,enc=decode_reference((dest/member['file']).read_bytes());rows=list(csv.DictReader(io.StringIO(text)))
     keyfield='Scrip Code' if 'Scrip Code' in rows[0] else 'SCRIP_CODE'
     result['exports'].append(export_rows(dest,Path(member['file']).stem+'_records',rows,[keyfield,'ISIN'],files[0]['source_url'],'Published VaR grouping file, not numerical VaR rates. File period/member date retained; do not apply to earlier sessions.'))
    result.update(status='VALIDATED_SNAPSHOT' if result['exports'] else 'PARTIAL',coverage='Published next-period groups. Member filename date may be future-effective; raw as-of snapshot only.')
   if key=='regulatory_files':
    for member in result['archive_members']:
     if re.search(r'(REG1?_IND|BSE_EQ_SCRIP|BannedSecurities)',member['member']):
      text,enc=decode_reference((dest/member['file']).read_bytes())
      reader=csv.DictReader(io.StringIO(text));rows=list(reader);keys=['FinInstrmId','ISIN'] if 'BSE_EQ_SCRIP' in member['member'] else ['ScripCode','ESM'] if 'REG' in member['member'] else ['Date','ISIN']
      if not rows:
       if not set(keys)<=set(reader.fieldnames or []):raise ValueError('Empty reference has invalid header')
       result.setdefault('empty_members',[]).append({'member':member['member'],'status':'EMPTY_SCHEMA_VALID','rows':0,'meaning':'Empty member retained; does not prove absence of restrictions'})
       continue
      result['exports'].append(export_rows(dest,Path(member['file']).stem+'_records',rows,keys,files[0]['source_url'],'Raw dated reference records. Numeric flag codes are not decoded into risk classifications. Mixed security types/statuses retained.'))
    result['status']='VALIDATED_SNAPSHOT' if result['exports'] else 'PARTIAL'
    result['coverage']='Downloaded and extracted SCRIP reference archive; per-member dates retained. Raw REG_IND/REG1_IND/UDiFF flags are not an approved restriction interpretation.'


 elif key=='calendar':
  tables=page.locator('table').evaluate_all("""ts=>ts.map(t=>({caption:t.caption?.innerText||'',rows:[...t.rows].map(r=>[...r.cells].map(c=>c.innerText))}))""")
  write_blob(dest,'holiday_tables.json',json.dumps({'text':snap['text'],'tables':tables},ensure_ascii=False,indent=2).encode())
  chosen=[t for t in tables if 'Equity Segment' in t['caption'] and 'Currency' not in t['caption']]
  if len(chosen)!=1:raise ValueError('Cannot uniquely identify equity holiday table by caption')
  t=chosen[0];rows=[]
  for row in t['rows'][1:]:
   if len(row)!=4:raise ValueError('Holiday row shape changed')
   d=datetime.strptime(row[2],'%d-%b-%y').date()
   if d.year!=date.fromisoformat(target).year or d.strftime('%A')!=row[3]:raise ValueError('Holiday year/weekday mismatch')
   rows.append({'date':d.isoformat(),'holiday':row[1],'weekday':row[3],'segment':'Equity and Equity Derivatives'})
  result['exports']=[export_rows(dest,'equity_holidays',rows,['date','holiday','weekday'],page.url,t['caption'])]
  result['special_session_notices']=[line for line in snap['text'].splitlines() if 'Muhurat' in line or 'separate circular' in line]
  result.update(status='VALIDATED_DATED_RECORDS',coverage='Annual equity holiday table; special-session notice retained separately and exact hours must be confirmed from later circulars')
 elif key=='price_bands':
  from titan.bse_details import fetch_details
  master_url='https://api.bseindia.com/BseIndiaAPI/api/ListofScripData_new/w?Group=&Scripcode=&segment=Equity&status=Active&scripName='
  master,meta=browser_json(page,master_url,dest,'price_band_universe');result['requests']=[meta]
  population=master.get('Table') if isinstance(master,dict) else master
  require_rows(population,['SCRIP_CD','ISIN_NUMBER','Status','Segment'])
  codes=sorted({str(x['SCRIP_CD']) for x in population})
  if any(not re.fullmatch(r'\d{6}',x) for x in codes):raise ValueError('Invalid active-universe code')
  items=[{'scrip_code':x,'url':'https://api.bseindia.com/BseIndiaAPI/api/PriceBand/w?scripcode='+x} for x in codes]
  result['_detail_capture_active']=True
  try:details,errors=fetch_details(page,items,dest,'bands',target)
  finally:result.pop('_detail_capture_active',None)
  result.update(universe_rows=len(population),unique_codes=len(codes),validated_codes=len(details),detail_errors=errors,
    status='VALIDATED_SNAPSHOT' if len(details)==len(codes) and not errors else 'PARTIAL',
    coverage='All active Equity T+1 codes returned by official master; returned price-band dates retained separately. Snapshot coverage does not prove target-session effective applicability.',effective_applicability='UNVERIFIED; do not substitute snapshot dates for official effective-session instructions')
  if details:result['exports']=[export_rows(dest,'price_band_universe_snapshot',details,['scrip_code','UpperT','LowerT','PBdate','date_relation'],master_url,result['coverage'])]
 elif key=='preopen':
  minutes=datetime.now(IST).hour*60+datetime.now(IST).minute
  result.update(status='NOT_APPLICABLE' if not 540<=minutes<=555 else 'SOURCE_ONLY',
    coverage='Information page only; no live auction feed configured. Requires actual pre-open session validation; indicative orders are not trades',
    future_trigger='Trading day 09:00-09:15 Asia/Kolkata')
 else:
  # Keep useful raw responses but never interpret dropdown lists as market records.
  result.update(status='CAPTURED_UNVALIDATED' if relevant else 'SOURCE_ONLY',
                coverage='Adapter still requires endpoint-specific schema, date and coverage validation')
 result['diagnostic_links']=[x for x in snap['links'] if re.search(r'\.(zip|csv|xlsx?|pdf)(?:\?|$)',x['url'],re.I)]

def collect_one(context,key,target,out,from_date=None):
 path,label=SOURCES[key];dest=out/key;dest.mkdir();responses=[];blocks=[];errors=[]
 result={'dataset':key,'description':label,'requested_report_date':target,'started_at':now(),'source_url':ROOT+path,'status':'STARTED','coverage':'UNVERIFIED','drive_status':'NOT_TRANSFERRED'}
 if from_date:result['requested_from_date']=from_date
 page=context.new_page();page.set_default_timeout(20_000)
 def receive(r):
  if not official(r.url) or result.get('_detail_capture_active'):return
  if r.status in [401,403,429]:blocks.append({'url':r.url,'status':r.status})
  ct=r.headers.get('content-type','').lower()
  if (r.status>=400 and r.request.resource_type in ('fetch','xhr')) or ('json' in ct or 'xml' in ct or 'csv' in ct):
   rec={'url':r.url,'method':r.request.method,'http_status':r.status,'content_type':ct,'retrieved_at':now()}
   try:
    body=r.body()
    if r.request.method=='POST' and not body and r.status in (200,202):return
    ext='json' if 'json' in ct else 'xml' if 'xml' in ct else 'csv'
    rec['body_prefix']=body.decode('utf-8',errors='replace')[:200]
    rec.update(write_blob(dest,f'response_{len(responses):03}.{ext}',body))
    if ext=='json':
     obj=safe_json_bytes(body);rec['arrays']=[{'path':p,'rows':len(rows),'keys':sorted(set().union(*(r.keys() for r in rows)))[:100]} for p,rows in row_arrays(obj)]
   except Exception as e:rec['capture_error']=str(e)
   responses.append(rec)
 page.on('response',receive)
 page.on('requestfailed',lambda req:result.setdefault('network_failures',[]).append({'url':req.url,'failure':req.failure,'at':now()}) if official(req.url) else None)
 try:
  if key=='pledges':
   try:
    pledge_with_reloads(page,target,dest,result)
   except PermissionError:
    raise
   except Exception as csv_err:
    result['csv_fallback_reason']=f'{type(csv_err).__name__}: {csv_err}'
    with timed(result,'pledge_json_fallback'):
     pledge_json_fallback(page,dest,responses,result)
   return result
  with timed(result,'initial_page_load',dataset=key):
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
  if key in ['high_low','calendar','delivery']:print('SOURCE_DIAGNOSTIC '+json.dumps({'dataset':key,'inputs':snapshot['inputs'],'text':snapshot['text'][:7000],'links':[x for x in snapshot['links'] if any(w in (x['text']+' '+x['url']).lower() for w in ['gross','deliver','csv','zip','highlow','bulk','block'])]},ensure_ascii=False),flush=True)
  result['access_errors']=blocks
  if blocks:raise PermissionError('An official endpoint denied access: '+str(blocks))
  adapt(context,page,key,target,dest,responses,result)
 except Exception as e:result.update(status='FAILED',error=f'{type(e).__name__}: {e}')
 finally:
  result.update(finished_at=now(),responses=responses,access_errors=blocks)
  (dest/'manifest.json').write_text(json.dumps(result,indent=2));page.close()
 return result

# Trading files and calendar-day disclosure feeds have different clocks.
EOD_DATASETS={'delivery','bulk_block','breadth','asm','gsm','regulatory_files','price_bands'}
def dataset_dates(clock, explicit=None, calendar_dir=None):
 from titan.bse import targets, Unavailable
 if clock.tzinfo is None:raise ValueError('Aware clock required')
 clock=clock.astimezone(IST)
 calendar_dir=calendar_dir or Path(__file__).parent/'calendars'
 holidays=set();special=set();years=set();evidence=[]
 for f in sorted(calendar_dir.glob('*.json')):
  c=json.loads(f.read_text())
  if not official(c['source']):raise ValueError('Non-official calendar provenance')
  year=int(c['year']);days={date.fromisoformat(x) for x in c['holidays']}
  if not days or any(d.year!=year for d in days):raise ValueError('Invalid calendar coverage')
  years.add(year);holidays.update(days);special.update(date.fromisoformat(x) for x in c.get('special_sessions',[]))
  evidence.append(dict(file=f.name,source=c['source'],sha256=fingerprint(f.read_bytes())['sha256']))
 if clock.year not in years:raise Unavailable('Calendar unavailable for '+str(clock.year))
 event_day=date.fromisoformat(explicit) if explicit else clock.date()
 if event_day>clock.date():raise ValueError('Future report date')
 if explicit:
  if event_day.year not in years:raise Unavailable('Calendar unavailable for '+str(event_day.year))
  if event_day not in special and (event_day.weekday()>=5 or event_day in holidays):
   raise ValueError('Explicit report date is not an eligible BSE session')
  eod=event_day
 else:eod=targets(clock,holidays=holidays,calendar_years=years,special_sessions=special)[0]
 overlap=event_day if explicit else targets(clock.replace(hour=0,minute=0,second=0,microsecond=0),holidays=holidays,calendar_years=years,special_sessions=special)[0]
 return {'event_date':event_day.isoformat(),'announcement_from_date':overlap.isoformat(),'eod_date':eod.isoformat(),'calendar_evidence':evidence,
         'policy':'Before 19:00 previous eligible session; after 19:00 latest eligible session; disclosures overlap previous eligible session through execution date; older missed watermarks require reconciliation'}

def main():
 p=argparse.ArgumentParser();p.add_argument('--date');p.add_argument('--datasets',default='all');p.add_argument('--output',type=Path,default=Path('bse_data_output'));args=p.parse_args()
 explicit=args.date
 if not explicit and os.getenv('GITHUB_EVENT_NAME')=='push' and os.getenv('GITHUB_EVENT_PATH'):
  event=json.loads(Path(os.environ['GITHUB_EVENT_PATH']).read_text())
  match=re.search(r'\[bse-data-date=(\d{4}-\d{2}-\d{2})\]',(event.get('head_commit') or {}).get('message',''))
  if match:explicit=match.group(1)
 clock=datetime.now(IST);date_plan=dataset_dates(clock,explicit);target=date_plan['event_date']
 if date.fromisoformat(target)>datetime.now(IST).date():p.error('Future report date')
 args.output.mkdir(parents=True,exist_ok=True)
 if any(args.output.iterdir()):p.error('Output must be empty; never reuse stale outputs')
 dataset_selection=args.datasets
 if dataset_selection=='all' and os.getenv('GITHUB_EVENT_NAME')=='push' and os.getenv('GITHUB_EVENT_PATH'):
  event=json.loads(Path(os.environ['GITHUB_EVENT_PATH']).read_text())
  m=re.search(r'\[bse-data-sets=([a-z_,]+)\]',(event.get('head_commit') or {}).get('message',''))
  if m:dataset_selection=m.group(1)
 names=list(SOURCES) if dataset_selection=='all' else dataset_selection.split(',')
 if not set(names)<=set(SOURCES):p.error('Unknown dataset')
 names=[n for n in names if n not in ['price_bands','shareholding']]+[n for n in ['price_bands','shareholding'] if n in names]
 import time
 os.environ['BSE_RUN_DEADLINE_MONOTONIC']=str(time.monotonic()+2700)
 started=now();results=[];bootstrap={}
 from playwright.sync_api import sync_playwright
 with sync_playwright() as pw:
  browser=pw.chromium.launch(headless=False)
  try:
   context=browser.new_context(accept_downloads=True)
   # Ordinary browser bootstrap only; no evasion or repeated challenge attempts.
   with timed(bootstrap,'context_warm_up'):
    home=context.new_page();r=home.goto('https://bseindia.com',wait_until='domcontentloaded',timeout=40_000);body=home.locator('body').inner_text()
   if (r and r.status in [401,403,429]) or page_blocked(body):
    results=[{'dataset':n,'status':'ACCESS_BLOCKED','error':'BSE home denied access; no source retries','requested_report_date':target} for n in names]
   else:
    home.close()
    for n in names:
     dataset_target=date_plan['eod_date'] if n in EOD_DATASETS else target
     x=collect_one(context,n,dataset_target,args.output,from_date=date_plan['announcement_from_date'] if n=='announcements' else None);x['execution_calendar_date']=clock.date().isoformat();x['date_policy']=date_plan['policy'];results.append(x);print('DATASET_RESULT '+json.dumps({k:v for k,v in x.items() if k not in ['responses','observed_data_responses','calendar_tables','diagnostic_links']},ensure_ascii=False),flush=True)
  except Exception as e:
   seen={x['dataset'] for x in results};results += [{'dataset':n,'status':'FAILED','error':str(e)} for n in names if n not in seen]
  finally:browser.close()
 diagnostics=dict(timings=bootstrap.get('timings',[]),http=[],network_failures=[])
 for result in results:
  dataset=result['dataset']
  diagnostics['timings'].extend(dict(t,dataset=dataset) for t in result.get('timings',[]))
  for response in result.get('responses',[]):
   diagnostics['http'].append({**{k:response.get(k) for k in ('http_status','content_type','body_prefix','capture_error')},'dataset':dataset,'path':urlparse(response['url']).path})
  for failure in result.get('network_failures',[]):
   diagnostics['network_failures'].append(dict(dataset=dataset,path=urlparse(failure['url']).path,http_status=None,content_type=None,body_prefix=None,error=failure['failure']))
 (args.output/'timing_diagnostics.json').write_text(json.dumps(diagnostics,indent=2))
 status='COMPLETE' if results and all(x['status'] in ['VALIDATED_DATED_RECORDS','VALIDATED_SNAPSHOT','VALIDATED_DOWNLOAD','NOT_APPLICABLE'] for x in results) else 'PARTIAL'
 manifest={'schema_version':2,'date_plan':date_plan,'started_at':started,'finished_at':now(),'requested_report_date':target,'mode':'Public BSE source acquisition; page captures are explicitly unvalidated','status':status,'github_run_id':os.getenv('GITHUB_RUN_ID'),'github_run_attempt':os.getenv('GITHUB_RUN_ATTEMPT'),'commit':os.getenv('GITHUB_SHA'),'datasets':results,'drive_status':'NOT_TRANSFERRED'}
 (args.output/'manifest.json').write_text(json.dumps(manifest,indent=2))
 return 0 if status=='COMPLETE' else 2
if __name__=='__main__':sys.exit(main())
