"""Bounded parallel public BSE detail acquisition. No download retries."""
import json, re, base64
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
 rows=[];errors=[];blocked=False
 # Eight in-flight requests maximum; no retries or evasion. Preserve each response.
 for offset in range(0,len(items),8):
  batch=items[offset:offset+8]
  if any(not official(x['url']) for x in batch):raise ValueError('Non-official detail source')
  replies=page.evaluate('''async items => await Promise.all(items.map(async x => {
   try {const r=await fetch(x.url,{signal:AbortSignal.timeout(30000)});
    const a=new Uint8Array(await r.arrayBuffer());let b='';for(let i=0;i<a.length;i+=8192)b+=String.fromCharCode(...a.subarray(i,i+8192));
    return {status:r.status,url:r.url,b64:btoa(b)};}
   catch(e){return {error:String(e)};}
  }))''',batch)
  for item,reply in zip(batch,replies):
   entry={**item,'retrieved_at':now(),'requested_report_date':target}
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
