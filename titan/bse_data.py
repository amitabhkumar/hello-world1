def announcement_api_fallback(page,target,dest,result):
 start=result.get('requested_from_date',target)
 result['requests']=[]
 result['retry_policy']='Same-session official AnnSubCategoryGetData API (single-day queries) with BSE_PACING_MS delay and 3-attempt backoff on HTTP 400'
 history=result.setdefault('attempt_history',[])
 days=[start] if start==target else [start,target]
 unique={};duplicate_count=0;total_expected=0
 def fetch_day_page(day_str,n,label):
  if n>1 or day_str!=days[0]:page.wait_for_timeout(BSE_PACING_MS)
  d=day_str.replace('-','')
  url=f'https://api.bseindia.com/BseIndiaAPI/api/AnnSubCategoryGetData/w?pageno={n}&strCat=-1&strPrevDate={d}&strScrip=&strSearch=P&strToDate={d}&strType=C&subcategory=-1'
  def call_api(_attempt):
   x=None
   for retry_400 in range(3):
    x=page.evaluate("""async u => {const r=await fetch(u,{headers:{'Accept':'application/json, text/plain, */*'},signal:AbortSignal.timeout(90000)}); return {status:r.status,url:r.url,text:await r.text()};}""",url)
    if x['status']==400 and retry_400<2:
     page.wait_for_timeout(BSE_PACING_MS*(retry_400+1))
     continue
    break
   if x['status'] in [401,403,429]:raise PermissionError('Official API denied access: '+str(x['status']))
   if x['status']!=200 or not official(x['url']):raise ValueError('Unexpected API response '+str(x['status']))
   b=x['text'].encode();meta=dict(url=url,retrieved_at=now(),http_status=x['status'],**write_blob(dest,label+'.json',b))
   result['requests'].append(meta)
   obj=safe_json_bytes(b)
   if not isinstance(obj,dict) or 'Table' not in obj:raise ValueError('Announcement response missing Table; empty object is not zero records')
   return obj
  with timed(result,'api_fallback_page',day=day_str,page=n,label=label):
   return bounded_attempt(call_api,2,page,history,label)
 def add(records):
  nonlocal duplicate_count
  for row in records:
   ident=str(row['NEWSID'])
   if not ident.strip():raise ValueError('Empty NEWSID')
   if ident in unique:duplicate_count+=1
   else:unique[ident]=row
  result.update(captured_unique_rows=len(unique),duplicate_records=duplicate_count)
 for day_str in days:
  obj=fetch_day_page(day_str,1,f'ann_api_{day_str}_001')
  expected=int((obj.get('Table1') or [{}])[0].get('ROWCNT',0))
  total_expected+=expected
  if expected==0:continue
  if expected>50000:raise ValueError('Announcement count outside explicit safety bound')
  rows=require_rows(obj.get('Table'),['NEWSID','SCRIP_CD','NEWS_DT'])
  size=len(rows);add(rows)
  for n in range(2,(expected+size-1)//size+1):
   obj=fetch_day_page(day_str,n,f'ann_api_{day_str}_{n:03d}')
   page_rows=obj.get('Table') or []
   if not page_rows:break
   add(require_rows(page_rows,['NEWSID','SCRIP_CD','NEWS_DT']))
 result['expected_rows']=total_expected
 allrows=list(unique.values());dates_ok=all(start<=str(x['NEWS_DT'])[:10]<=target for x in allrows)
 result.update(unique_ids=True,record_dates_match=dates_ok)
 if not allrows and total_expected>0:raise ValueError('No announcements captured despite nonzero ROWCNT')
 if not dates_ok:raise ValueError('Announcement date verification failed')
 result['exports']=[export_rows(dest,'announcements',allrows,['NEWSID','SCRIP_CD','NEWS_DT'],result['requests'][0]['url'],'All category announcements for inclusive date window (single-day API queries); attachments not assessed')]
 result.update(status='VALIDATED_DATED_RECORDS',coverage='All unique rows reconciled to official AnnSubCategoryGetData ROWCNT via same-session single-day API queries; publication times retained')
