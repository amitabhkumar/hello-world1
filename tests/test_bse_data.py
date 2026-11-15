import unittest
from titan.bse_data import official,row_arrays,page_blocked,safe_json_bytes
class AcquisitionTests(unittest.TestCase):
 def test_official_https_host(self):
  self.assertTrue(official('https://api.bseindia.com/BseIndiaAPI/api/test'))
  for u in ['http://www.bseindia.com/x','https://bseindia.com.evil.test/x','https://evil.test/?bseindia.com']:
   self.assertFalse(official(u))
 def test_metadata_not_records(self):
  self.assertEqual(row_arrays({'Table':[{'code':'500001'}],'total':100})[0][1],[{'code':'500001'}])
  self.assertEqual(row_arrays({'count':100}),[])
 def test_empty_not_success(self):self.assertEqual(row_arrays({'Table':[]}),[])
 def test_html_not_json(self):
  with self.assertRaises(ValueError):safe_json_bytes(b'<html>Access denied</html>')
 def test_challenge(self):
  self.assertTrue(page_blocked('Access denied'))
  self.assertTrue(page_blocked('Please verify you are human'))
  self.assertFalse(page_blocked('Surveillance measures include access rules for some securities'))
if __name__=='__main__':unittest.main()


class ExportContractTests(unittest.TestCase):
 def test_missing_schema_rejected(self):
  from titan.bse_data import require_rows
  with self.assertRaises(ValueError): require_rows([{'count':40}],['ScripCode'])
 def test_html_download_rejected(self):
  from titan.bse_data import inspect_download
  with self.assertRaises(ValueError):inspect_download(b'<html>Error</html>','data.csv')
 def test_corrupt_archive_rejected(self):
  from titan.bse_data import inspect_download
  with self.assertRaises(Exception):inspect_download(b'not a zip','data.zip')
 def test_query_preserves_empty_filters(self):
  from titan.bse_data import query_url
  self.assertEqual(query_url('https://api.bseindia.com/a?scrip=&pageno=1',pageno=2),'https://api.bseindia.com/a?scrip=&pageno=2')
 def test_export_roundtrip(self):
  import tempfile
  from pathlib import Path
  from titan.bse_data import export_rows
  with tempfile.TemporaryDirectory() as p:
   r=export_rows(Path(p),'sample',[{'id':1,'text':'a,b\nc'}],['id'],'https://www.bseindia.com','test')
   self.assertEqual(r['rows'],1)

class DataQualityTests(unittest.TestCase):
 def test_delivery_wrong_date_and_bad_percentage(self):
  from titan.bse_data import validate_delivery
  row={'DATE':'29102026','SCRIP CODE':'500002','DELIVERY QTY':'50',"DAY'S VOLUME":'100','DELV. PER.':'50.00'}
  validate_delivery([row],'2026-10-29')
  with self.assertRaises(ValueError):validate_delivery([row],'2026-10-28')
  with self.assertRaises(ValueError):validate_delivery([{**row,'DELV. PER.':'60'}],'2026-10-29')
  with self.assertRaises(ValueError):validate_delivery([row,row],'2026-10-29')
 def test_chunked_export_preserves_all_rows(self):
  import tempfile,json
  from pathlib import Path
  from titan.bse_data import export_rows
  rows=[{'id':i} for i in range(5001)]
  with tempfile.TemporaryDirectory() as p:
   r=export_rows(Path(p),'sample',rows,['id'],'https://www.bseindia.com','test')
   parts=[f for f in r['files'] if f['file'].endswith('.json')]
   self.assertEqual(len(parts),2)
   actual=[x for f in parts for x in json.loads((Path(p)/f['file']).read_text())]
   self.assertEqual(rows,actual)
 def test_cp1252_is_explicit(self):
  from titan.bse_data import decode_reference
  text,enc=decode_reference(b'Company\xa0Name')
  self.assertIn('cp1252',enc);self.assertIn('Name',text)


class SessionDateTests(unittest.TestCase):
 def plan(self,stamp,explicit=None):
  from datetime import datetime
  from titan.bse_data import dataset_dates
  return dataset_dates(datetime.fromisoformat(stamp),explicit)
 def test_sunday_keeps_news_separate(self):
  p=self.plan('2026-11-15T10:00:00+05:30');self.assertEqual(p['eod_date'],'2026-11-13');self.assertEqual(p['event_date'],'2026-11-15')
 def test_publication_boundary(self):
  self.assertEqual(self.plan('2026-11-13T18:59:00+05:30')['eod_date'],'2026-11-12')
  self.assertEqual(self.plan('2026-11-13T19:00:00+05:30')['eod_date'],'2026-11-13')
 def test_holiday_and_special(self):
  self.assertEqual(self.plan('2026-11-10T22:00:00+05:30')['eod_date'],'2026-11-09')
  self.assertEqual(self.plan('2026-11-09T08:30:00+05:30')['eod_date'],'2026-11-08')
 def test_month_rollover(self):
  self.assertEqual(self.plan('2026-11-02T08:30:00+05:30')['eod_date'],'2026-10-30')
 def test_uncovered_year_fails(self):
  with self.assertRaises(RuntimeError):self.plan('2027-01-01T08:30:00+05:30')
 def test_explicit_closed_date_rejected(self):
  with self.assertRaises(ValueError):self.plan('2026-11-15T22:00:00+05:30','2026-11-15')

class DetailTests(unittest.TestCase):
 def test_latest_original_keeps_quarter_and_publication(self):
  from titan.bse_details import latest_filings
  base={'FLD_ScripCode':500001,'XBRLAttachment':'/XBRLFILES/500001_a.html','sQtrName':'September 2026','EndDate':'2026-10-01','D':'2026-11-01'}
  out=latest_filings([base,{**base,'D':'2026-11-14','XBRLAttachment':'/XBRLFILES/500001_b.html'}])
  self.assertEqual(len(out),1);self.assertEqual(out[0]['quarter'],'September 2026');self.assertTrue(out[0]['url'].endswith('_b.html'))
 def test_original_issuer_mismatch_fails(self):
  from titan.bse_details import latest_filings
  with self.assertRaises(ValueError):latest_filings([{'FLD_ScripCode':500001,'XBRLAttachment':'/500002_a.html'}])
 def test_tables_preserve_labels_and_zero(self):
  from titan.bse_details import Tables
  p=Tables();p.feed('<table><tr><th>Shareholding</th><th>Percent</th></tr><tr><td>Promoter</td><td>0</td></tr></table>')
  self.assertEqual(p.tables[0][1],['Promoter','0'])

class ContinuationTests(unittest.TestCase):
 def test_budget_checkpoint_without_request(self):
  import os,time,tempfile,json
  from pathlib import Path
  from unittest.mock import patch
  from titan.bse_details import fetch_details
  class NoNetwork:
   def evaluate(self,*args):raise AssertionError('Unexpected request')
  with tempfile.TemporaryDirectory() as d, patch.dict(os.environ,{'BSE_RUN_DEADLINE_MONOTONIC':str(time.monotonic()-1)}):
   rows,errors=fetch_details(NoNetwork(),[{'scrip_code':'500001','url':'https://api.bseindia.com/test'}],Path(d),'bands','2026-11-13')
   self.assertEqual(rows,[]);self.assertEqual(errors[0]['error'],'COLLECTION_BUDGET_EXHAUSTED')
   self.assertEqual(len(json.loads((Path(d)/'bands_progress.json').read_text())['remaining']),1)
 def test_original_cache_no_refetch(self):
  import os,tempfile,json
  from pathlib import Path
  from unittest.mock import patch
  from titan.bse_details import fetch_details,latest_filings
  class NoNetwork:
   def evaluate(self,*args):raise AssertionError('Unexpected request')
  with tempfile.TemporaryDirectory() as d:
   p=Path(d);old=p/'shareholding';old.mkdir();out=p/'out';out.mkdir()
   index=[{'FLD_ScripCode':500001,'XBRLAttachment':'/XBRLFILES/500001_a.html','sQtrName':'September 2026','D':'2026-11-01'}]
   (old/'shareholding_one_year.json').write_text(json.dumps({'Table':index}))
   original=b'<table><tr><td>Shareholding</td><td>0</td></tr></table>'
   (old/'ownership_500001.html').write_bytes(original)
   with patch.dict(os.environ,{'BSE_RESUME_DIRECTORY':str(p),'BSE_RESUME_RUN_ID':'123','BSE_RUN_DEADLINE_MONOTONIC':''}):
    rows,errors=fetch_details(NoNetwork(),latest_filings(index),out,'ownership','2026-11-15')
   self.assertFalse(errors);self.assertEqual((out/'ownership_500001.html').read_bytes(),original)
   self.assertIsNone(rows[0]['retrieved_at']);self.assertEqual(rows[0]['reused_from_run'],'123')
