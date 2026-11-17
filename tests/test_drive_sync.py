import unittest,tempfile,json,os
from pathlib import Path
from unittest.mock import patch,MagicMock
from titan import drive_sync as m
class DriveTests(unittest.TestCase):
 def fixture(self,p):
  b=b'id,value\na,1\n';(p/'x.csv').write_bytes(b)
  return {'report_date':'2026-11-16','datasets':[{'dataset':'x','status':'VALIDATED_DATED_CSV','file':'x.csv','source':'https://nsearchives.nseindia.com/x.csv','rows':1,'bytes':len(b),'sha256':m.sha(b)}]}
 def test_inventory_hash_and_status(self):
  with tempfile.TemporaryDirectory() as td:
   p=Path(td);d=self.fixture(p);files,errors=m.inventory(p,d);self.assertEqual(len(files),1);self.assertFalse(errors)
   (p/'x.csv').write_bytes(b'bad');self.assertEqual(len(m.inventory(p,d)[1]),1)
   d['datasets'][0]['status']='FAILED';self.assertEqual(m.inventory(p,d),([],[]))
 def test_missing_secret_is_successful_skip(self):
  with tempfile.TemporaryDirectory() as td,patch.dict(os.environ,{},clear=True):
   p=Path(td);(p/'manifest.json').write_text(json.dumps(self.fixture(p)))
   r=m.run(p);self.assertEqual(r['status'],'NOT_TRANSFERRED');self.assertTrue((p/'sop_v3_manifest_summary.json').exists())
 def test_readback_mismatch_fails(self):
  d=object.__new__(m.Drive);a=MagicMock();a.json.return_value={'parents':['wrong']};b=MagicMock();b.content=b'abc';d.request=MagicMock(side_effect=[a,b])
  with self.assertRaisesRegex(ValueError,'hash/parent'):d.verify('id','right',m.sha(b'abc'))
 def test_duplicate_reuses_only_exact_date_and_hash(self):
  d=object.__new__(m.Drive);r=MagicMock();r.json.return_value={'files':[{'id':'existing','appProperties':{'source_date':'2026-11-16'}}]};d.request=MagicMock(return_value=r);d.verify=MagicMock(return_value={'id':'existing'})
  self.assertEqual(d.put(b'abc','name','parent','2026-11-16','x')['action'],'REUSED');self.assertEqual(d.request.call_count,1)
 def test_changed_bytes_get_new_file(self):
  d=object.__new__(m.Drive);a=MagicMock();a.json.return_value={'files':[]};b=MagicMock();b.json.return_value={'id':'new'};d.request=MagicMock(side_effect=[a,b]);d.verify=MagicMock(return_value={'id':'new'})
  self.assertEqual(d.put(b'new','revision','parent','2026-11-16','x')['action'],'UPLOADED');self.assertEqual(d.request.call_args_list[1].args[0],'POST')
if __name__=='__main__':unittest.main()
