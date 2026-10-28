"""One-off public BSE history collection for the 28 October review."""
import json,sys
from pathlib import Path
from datetime import date,datetime,timedelta
from zoneinfo import ZoneInfo
from titan.bse import collect,Blocked
from playwright.sync_api import sync_playwright
P=Path('backfill_output');P.mkdir(exist_ok=True)
holidays={date(2026,10,2),date(2026,10,20)}
d=date(2026,10,27);dates=[]
while len(dates)<20:
 if d.weekday()<5 and d not in holidays:dates.append(d)
 d-=timedelta(days=1)
manifest=[]
for d in sorted(dates):
 out=P/d.isoformat();out.mkdir(exist_ok=True)
 try:
  result=collect([d],out);manifest.append(dict(result,status='VALIDATED'))
 except Exception as e:
  manifest.append({'date':str(d),'status':'FAILED','error':str(e)})
  if isinstance(e,Blocked):break
 (P/'manifest.json').write_text(json.dumps(manifest,indent=2))
print(json.dumps(manifest,indent=2))
# Observe the official delivery page and its advertised links, without guessing a download.
with sync_playwright() as p:
 b=p.chromium.launch(headless=False)
 page=b.new_page()
 try:
  response=page.goto('https://www.bseindia.com/markets/equity/EQReports/GrossShortPos.aspx?expandable=3&flag=0',wait_until='domcontentloaded',timeout=45000)
  page.wait_for_timeout(2000)
  info={'status':response.status,'text':page.locator('body').inner_text(),'links':page.locator('a[href]').evaluate_all('(els)=>els.map(a=>({text:a.innerText,href:a.href}))')}
  (P/'delivery_page.json').write_text(json.dumps(info,indent=2))
  if response.status==200 and 'Access Denied' not in info['text']:
   links=[a for a in info['links'] if 'SCBSEALL2810' in a['href'] and '/2026/' in a['href']]
   if links:
    loc=page.locator('a').filter(has_text=links[0]['text']).first
    with page.expect_download(timeout=45000) as ev:loc.click()
    ev.value.save_as(P/'BSE_delivery_20261028.zip')
 except Exception as e:(P/'delivery_error.txt').write_text(str(e))
 finally:b.close()
