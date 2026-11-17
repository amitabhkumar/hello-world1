"""Optional append-only Drive delivery. No credentials or folder IDs are stored here.
Requires GDRIVE_SERVICE_ACCOUNT_JSON, GDRIVE_INCOMING_FOLDER_ID and
GDRIVE_LOGS_FOLDER_ID secrets. Acquisition remains independent of delivery.
"""
import argparse, csv, hashlib, io, json, os, re
from pathlib import Path
from datetime import datetime, timezone
from urllib.parse import urlparse
VALID={'VALIDATED_DOWNLOAD','VALIDATED_DATED_CSV','VALIDATED_DATE_CSV','CONFIRMED_EMPTY_DATE_EXPORT','VALIDATED_DATED_RECORDS','VALIDATED_SNAPSHOT','VALIDATED_CSV'}
def sha(b):return hashlib.sha256(b).hexdigest()
def stamp():return datetime.now(timezone.utc).isoformat()
def official(url):
 u=urlparse(url or '');h=u.hostname or ''
 return u.scheme=='https' and any(h==d or h.endswith('.'+d) for d in ('bseindia.com','nseindia.com','nseindia.in'))
def inventory(root,manifest):
 """Only explicitly validated exports; failed/partial source captures stay excluded."""
 root=Path(root).resolve();out=[];errors=[]
 datasets=manifest.get('datasets',[dict(manifest,dataset='bse_bhavcopy')])
 for d in datasets:
  if d.get('status') not in VALID:continue
  name=d.get('dataset',d.get('filename','dataset'))
  exports=d.get('exports',[d])
  for e in exports:
   source=e.get('source_url') or d.get('source_url') or d.get('source') or d.get('url')
   dt=d.get('source_date') or d.get('file_date') or d.get('requested_report_date') or d.get('requested_date') or manifest.get('report_date') or manifest.get('requested_report_date')
   for f in e.get('files',[e]):
    filename=f.get('file') or f.get('filename')
    if not filename or Path(filename).suffix.lower() not in ('.csv','.json'):continue
    try:
     if not dt or not official(source):raise ValueError('Missing source date or official HTTPS source')
     candidates=[root/filename,root/str(name)/filename]
     candidates=[p for p in candidates if p.is_file() and p.resolve().is_relative_to(root)]
     if not candidates:raise ValueError('Export file unavailable')
     p=candidates[0];b=p.read_bytes()
     if len(b)!=f.get('bytes') or sha(b)!=f.get('sha256'):raise ValueError('Export bytes/SHA256 mismatch')
     rows=list(csv.DictReader(io.StringIO(b.decode('utf-8-sig')))) if p.suffix.lower()=='.csv' else json.loads(b)
     count=len(rows) if isinstance(rows,list) else None
     expected=(f['last_row']-f['first_row']+1) if 'last_row' in f else e.get('rows',d.get('rows'))
     if count is None or count!=expected:raise ValueError('Export row count mismatch')
     if p.suffix.lower()=='.csv' and e.get('required_fields') and rows and not set(e['required_fields'])<=set(rows[0]):raise ValueError('Required fields missing')
     out.append(dict(path=str(p),dataset=name,source_date=dt,effective_date=d.get('effective_date'),status=d['status'],source_url=source,rows=count,bytes=len(b),sha256=sha(b)))
    except Exception as ex:errors.append(dict(dataset=name,file=filename,error=str(ex)))
 return out,errors
class Drive:
 def __init__(self,info):
  from google.oauth2 import service_account
  from google.auth.transport.requests import AuthorizedSession
  self.session=AuthorizedSession(service_account.Credentials.from_service_account_info(info,scopes=['https://www.googleapis.com/auth/drive']))
 def request(self,method,url,**kw):
  r=self.session.request(method,url,timeout=90,**kw)
  if not r.ok:raise RuntimeError('Drive HTTP %s: %s'%(r.status_code,r.text[:500]))
  return r
 def verify(self,ident,parent,digest):
  base='https://www.googleapis.com/drive/v3/files/'+ident
  meta=self.request('GET',base,params={'fields':'id,parents','supportsAllDrives':'true'}).json()
  body=self.request('GET',base,params={'alt':'media','supportsAllDrives':'true'}).content
  if parent not in meta.get('parents',[]) or sha(body)!=digest:raise ValueError('Drive readback hash/parent mismatch')
  return dict(id=ident,sha256=sha(body),parent_verified=True,readback_at=stamp())
 def put(self,body,name,parent,dt,dataset,dedup=True):
  digest=sha(body);escaped=parent.replace("'","\\'")
  if dedup:
   params={'q':"'%s' in parents and trashed=false and appProperties has { key='sha256' and value='%s' }"%(escaped,digest),'fields':'files(id,appProperties),nextPageToken','supportsAllDrives':'true','includeItemsFromAllDrives':'true','pageSize':100}
   while True:
    result=self.request('GET','https://www.googleapis.com/drive/v3/files',params=params).json()
    for f in result.get('files',[]):
     if f.get('appProperties',{}).get('source_date')==dt:
      return dict(self.verify(f['id'],parent,digest),action='REUSED')
    if not result.get('nextPageToken'):break
    params['pageToken']=result['nextPageToken']
  meta={'name':name,'parents':[parent],'appProperties':{'sha256':digest,'source_date':str(dt),'dataset':str(dataset)[:120]}}
  boundary='titan_'+digest
  data=('--'+boundary+'\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n'+json.dumps(meta)+'\r\n--'+boundary+'\r\nContent-Type: application/octet-stream\r\n\r\n').encode()+body+('\r\n--'+boundary+'--\r\n').encode()
  f=self.request('POST','https://www.googleapis.com/upload/drive/v3/files',params={'uploadType':'multipart','supportsAllDrives':'true','fields':'id'},headers={'Content-Type':'multipart/related; boundary='+boundary},data=data).json()
  return dict(self.verify(f['id'],parent,digest),action='UPLOADED')
def run(root):
 root=Path(root);root.mkdir(parents=True,exist_ok=True)
 receipt={'started_at':stamp(),'run_id':os.getenv('GITHUB_RUN_ID'),'attempt':os.getenv('GITHUB_RUN_ATTEMPT'),'commit':os.getenv('GITHUB_SHA'),'event':os.getenv('GITHUB_EVENT_NAME'),'status':'NOT_TRANSFERRED','files':[],'errors':[]}
 manifest=json.loads((root/'manifest.json').read_text()) if (root/'manifest.json').exists() else {}
 files,errors=inventory(root,manifest);receipt['errors']=errors
 summary={k:receipt[k] for k in ('run_id','attempt','commit','event')}
 summary.update(dataset_statuses=[{k:d.get(k) for k in ('dataset','filename','status','rows','source_date','file_date','effective_date','requested_report_date','error','coverage')} for d in manifest.get('datasets',[manifest])],validated_files=[{k:v for k,v in f.items() if k!='path'} for f in files],validation_errors=errors,acquisition_status=manifest.get('status'),generated_at=stamp())
 summary_path=root/'sop_v3_manifest_summary.json';summary_path.write_text(json.dumps(summary,indent=2))
 config=[os.getenv(k) for k in ('GDRIVE_SERVICE_ACCOUNT_JSON','GDRIVE_INCOMING_FOLDER_ID','GDRIVE_LOGS_FOLDER_ID')]
 if not all(config):receipt['errors'].append({'error':'Missing Drive service-account secret or destination folder secrets; delivery NOT_TRANSFERRED'})
 else:
  try:
   drive=Drive(json.loads(config[0]));token='%s_%s_%s'%(receipt['run_id'],receipt['attempt'],datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
   for f in files:
    try:
     p=Path(f['path']);name='%s_%s_%s_%s'%(f['source_date'],f['sha256'][:16],token,p.name)
     receipt['files'].append(dict({k:v for k,v in f.items() if k!='path'},**drive.put(p.read_bytes(),name,config[1],f['source_date'],f['dataset'])))
    except Exception as ex:receipt['errors'].append({'dataset':f['dataset'],'error':str(ex)})
   receipt['summary']=drive.put(summary_path.read_bytes(),token+'_sop_v3_manifest_summary.json',config[1],datetime.now(timezone.utc).date().isoformat(),'manifest_summary',False)
   receipt['status']='VERIFIED' if files and not receipt['errors'] else 'PARTIAL' if receipt['files'] else 'NOT_TRANSFERRED'
   receipt['finished_at']=stamp()
   evidence=json.dumps(receipt,indent=2).encode()
   receipt['logs_receipt']=drive.put(evidence,token+'_drive_receipt.json',config[2],datetime.now(timezone.utc).date().isoformat(),'delivery_receipt',False)
  except Exception as ex:receipt['errors'].append({'error':str(ex)});receipt['status']='PARTIAL' if receipt['files'] else 'NOT_TRANSFERRED'
 receipt['finished_at']=stamp();(root/'drive_sync_receipt.json').write_text(json.dumps(receipt,indent=2));print(json.dumps({'drive_status':receipt['status'],'verified_files':len(receipt['files']),'errors':len(receipt['errors'])}))
 return receipt
if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('--root',required=True);run(parser.parse_args().root)
