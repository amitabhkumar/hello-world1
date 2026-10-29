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
