"""Bounded parallel public BSE detail acquisition. No download retries."""
import json, re, base64, os, time, hashlib
from pathlib import Path
from html.parser import HTMLParser
from urllib.parse import urljoin

class Tables(HTMLParser):
 def __init__(self):
  super().__init__();self.tables=[];self.stack=[];self.text=[]
 def handle_starttag(self,tag,attrs):
  if tag=='table':self.stack.append({'rows':[],'row':None,'cell':None})
  if not self.stack:return
  t=self.stack[-1]
  if tag=='tr':t['row']=[]
  if tag in ('td','th'):t['cell']=[]
 def handle_data(self,data):
  self.text.append(data)
  if self.stack and self.stack[-1]['cell'] is not None:self.stack[-1]['cell'].append(data)
 def handle_endtag(self,tag):
  if not self.stack:return
  t=self.stack[-1]
  if tag in ('td','th') and t['cell'] is not None:
   if t['row'] is not None:t['row'].append(' '.join(' '.join(t['cell']).split()))
   t['cell']=None
  if tag=='tr' and t['row'] is not None:
   if any(t['row']):t['rows'].append(t['row'])
   t['row']=None
  if tag=='table':
   t=self.stack.pop()
   if t['rows']:self.tables.append(t['rows'])

def fetch_details(page,items,dest,kind,target):
 from titan.bse_data import official,write_blob,now,parse_source_date
 from decimal import Decimal
 rows=[];errors=[];blocked=False;cache={};cache_receipts={}
 resume=os.getenv('BSE_RESUME_DIRECTORY')
 if resume and kind=='ownership':
  root=Path(resume)/'shareholding'
  old=json.loads((root/'shareholding_one_year.json').read_text())['Table']
  receipt_file=root/'ownership_receipts.json'
  if receipt_file.exists():cache_receipts={r['url']:r for r in json.loads(receipt_file.read_text())}
  for entry in latest_filings(old):
   f=root/('ownership_'+entry['scrip_code']+'.html')
   if f.exists():
    receipt=cache_receipts.get(entry['url'])
    if receipt_file.exists() and (not receipt or hashlib.sha256(f.read_bytes()).hexdigest()!=receipt['sha256']):continue
    cache[entry['url']]=f
 # Eight in-flight requests maximum; no retries or evasion. Preserve each response.
 for offset in range(0,len(items),8):
  deadline=os.getenv('BSE_RUN_DEADLINE_MONOTONIC')
  if deadline and time.monotonic()+35>=float(deadline):
   errors.append({'error':'COLLECTION_BUDGET_EXHAUSTED','remaining':len(items)-offset,'next_action':'Resume saved artifact; no unsaved work credited'})
   (dest/(kind+'_receipts.json')).write_text(json.dumps(rows,ensure_ascii=False))
   (dest/(kind+'_progress.json')).write_text(json.dumps({'attempted':offset,'population':len(items),'validated':len(rows),'errors':errors,'remaining':items[offset:]},indent=2))
   break
  batch=items[offset:offset+8]
  if any(not official(x['url']) for x in batch):raise ValueError('Non-official detail source')
  network=[x for x in batch if x['url'] not in cache]
  network_replies=page.evaluate('''async items => await Promise.all(items.map(async x => {
   try {const r=await fetch(x.url,{signal:AbortSignal.timeout(30000)});
    const a=new Uint8Array(await r.arrayBuffer());let b='';for(let i=0;i<a.length;i+=8192)b+=String.fromCharCode(...a.subarray(i,i+8192));
    return {status:r.status,url:r.url,b64:btoa(b)};}
   catch(e){return {error:String(e)};}
  }))''',network) if network else []
  it=iter(network_replies)
  replies=[{'status':200,'url':x['url'],'b64':base64.b64encode(cache[x['url']].read_bytes()).decode(),'cached':True} if x['url'] in cache else next(it) for x in batch]
  for item,reply in zip(batch,replies):
   entry={**item,'retrieved_at':cache_receipts.get(item['url'],{}).get('retrieved_at') if reply.get('cached') else now(),'validated_at':now(),'requested_report_date':target,'reused_from_run':(os.getenv('BSE_RESUME_RUN_ID') or os.getenv('BSE_CACHE_SOURCE_RUN_ID')) if reply.get('cached') else None,'retrieval_note':'Original per-file retrieval time unavailable in interrupted run; source artifact preserved' if reply.get('cached') else 'Live response'}
   try:
    if reply.get('status') in (401,403,429):blocked=True
    if reply.get('status')!=200:raise ValueError('HTTP '+str(reply.get('status'))+' '+reply.get('error',''))
    if not official(reply['url']):raise ValueError('Unexpected redirect')
    raw=base64.b64decode(reply['b64']);body=raw.decode('utf-8-sig');suffix='json' if kind=='bands' else 'html'
    entry.update(write_blob(dest,kind+'_'+item['scrip_code']+'.'+suffix,raw))
    if kind=='bands':
     data=json.loads(body)
     if not isinstance(data,dict) or not {'UpperT','LowerT','PBdate'}<=data.keys():raise ValueError('Missing price-band fields')
     upper=Decimal(str(data['UpperT']).replace(',',''));lower=Decimal(str(data['LowerT']).replace(',',''))
     if not upper.is_finite() or not lower.is_finite() or not 0<lower<=upper:raise ValueError('Invalid limits')
     source_day=parse_source_date(data['PBdate']).isoformat()
     entry.update(data,source_date=source_day,date_relation='FUTURE_SOURCE_DATE' if source_day>target else 'MATCHED' if source_day==target else 'EARLIER_SOURCE_DATE',applicability='UNVERIFIED',price_unit='INR; per-security webpage labels All Prices in rupees')
    else:
     parser=Tables();parser.feed(body)
     text=' '.join(parser.text)
     if 'shareholding' not in text.lower() or not parser.tables:raise ValueError('Missing shareholding tables')
     # Binding comes from the original issuer index and its original attachment URL.
     # Do not equate submission date with reporting-period end.
     tablefile=write_blob(dest,'ownership_'+item['scrip_code']+'_tables.json',json.dumps(parser.tables,ensure_ascii=False).encode())
     entry.update(tables=len(parser.tables),table_file=tablefile,period_basis='Original index quarter; body tables retained without period substitution',interpretation='Original tables parsed; ownership changes require comparable prior-period filing')
    rows.append(entry)
   except Exception as e:errors.append({**entry,'error':str(e)})
  (dest/(kind+'_receipts.json')).write_text(json.dumps(rows,ensure_ascii=False))
  (dest/(kind+'_progress.json')).write_text(json.dumps({'attempted':min(offset+8,len(items)),'population':len(items),'validated':len(rows),'errors':errors,'remaining':items[offset+8:] if blocked else []},indent=2))
  print('DETAIL_PROGRESS',kind,min(offset+8,len(items)),len(items),len(rows),len(errors),flush=True)
  if blocked:break
 return rows,errors

def latest_filings(rows):
 latest={}
 for r in rows:
  code=str(r['FLD_ScripCode']);stamp=str(r.get('D') or '')
  if not re.fullmatch(r'\d{6}',code):raise ValueError('Invalid issuer identifier')
  if code not in latest or stamp>str(latest[code].get('D') or ''):latest[code]=r
 out=[]
 for code,r in sorted(latest.items()):
  url=urljoin('https://www.bseindia.com/',str(r.get('XBRLAttachment') or ''))
  if not re.search('/'+code+r'_[^/]+\.html$',url,re.I):raise ValueError('Unbound original filing URL for '+code)
  out.append({'scrip_code':code,'url':url,'publication_time':r.get('D'),'quarter':r.get('sQtrName'),'index_end_date':r.get('EndDate'),'issuer':r.get('Company_NAme')})
 return out
