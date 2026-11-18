import unittest,tempfile,json
from pathlib import Path
from unittest.mock import MagicMock,patch
from titan import bse_data as m

class RetryTests(unittest.TestCase):
 def test_transient_recovers_and_preserves_failures(self):
  p=MagicMock();history=[];op=MagicMock(side_effect=[RuntimeError('Failed to fetch')]*3+['ok'])
  self.assertEqual(m.bounded_attempt(op,4,p,history,'page2'),'ok')
  self.assertEqual([c.args[0] for c in p.wait_for_timeout.call_args_list],[1000,2000,4000])
  self.assertEqual([h['status'] for h in history],['ERROR']*3+['SUCCESS'])
 def test_exhaustion_is_bounded(self):
  p=MagicMock();op=MagicMock(side_effect=TimeoutError('timeout'));h=[]
  with self.assertRaises(TimeoutError):m.bounded_attempt(op,4,p,h,'page2')
  self.assertEqual(op.call_count,4);self.assertEqual(len(h),4)
 def test_access_and_schema_not_retried(self):
  for error in [PermissionError('403'),ValueError('Missing Table'),ValueError('Invalid CSV')]:
   op=MagicMock(side_effect=error);p=MagicMock()
   with self.assertRaises(type(error)):m.bounded_attempt(op,4,p,[],'test')
   self.assertEqual(op.call_count,1);p.wait_for_timeout.assert_not_called()
 def test_pledge_reload_after_timeout(self):
  page=MagicMock();page.goto.return_value=None;page.reload.return_value=None;page.locator.return_value.inner_text.return_value='Consolidated pledge data'
  with tempfile.TemporaryDirectory() as td,patch.object(m,'pledge_csv',side_effect=[TimeoutError('timeout'),TimeoutError('timeout'),None]) as export,patch.object(m,'snapshot_page',return_value={}):
   r={};m.pledge_with_reloads(page,'2026-11-16',Path(td),r)
   self.assertEqual(export.call_count,3);self.assertEqual(page.goto.call_count,1);self.assertEqual(page.reload.call_count,2)
   self.assertEqual(len(r['attempt_history']),3)
 def run_pages(self,objects):
  p=MagicMock();r={'requests':[{'url':'https://www.bseindia.com'}]};row={'url':'https://api.bseindia.com/BseIndiaAPI/api/AnnSubCategoryGetData/w'}
  with tempfile.TemporaryDirectory() as td,patch.object(m,'matched',return_value=(row,{})),patch.object(m,'announcement_ui_response',side_effect=lambda *args,**kwargs: (args[4]['requests'].append({'url':'https://api.bseindia.com'}) or objects.pop(0))),patch.object(m,'export_rows',return_value={'rows':3}):
   m.announcement_pages(p,'2026-11-16',Path(td),[],r)
  return p,r
 def obj(self,ids,total=3):
  return {'Table':[{'NEWSID':x,'SCRIP_CD':'500001','NEWS_DT':'2026-11-16'} for x in ids],'Table1':[{'ROWCNT':total}]}
 def test_full_count_paced(self):
  p,r=self.run_pages([self.obj(['a','b']),self.obj(['c']),self.obj(['a','b'])])
  self.assertEqual(r['captured_unique_rows'],3);self.assertEqual(r['status'],'VALIDATED_DATED_RECORDS')
  self.assertTrue(all(x.args[0]==850 for x in p.wait_for_timeout.call_args_list))
 def test_duplicates_deduplicated(self):
  _,r=self.run_pages([self.obj(['a','b']),self.obj(['b','c']),self.obj(['a','b'])])
  self.assertEqual(r['captured_unique_rows'],3);self.assertEqual(r['duplicate_records'],1)
 def test_missing_rows_not_complete(self):
  with self.assertRaisesRegex(ValueError,'count mismatch'):self.run_pages([self.obj(['a','b']),self.obj(['b']),self.obj(['a','b'])])
 def test_count_change_not_complete(self):
  with self.assertRaisesRegex(ValueError,'ROWCNT changed'):self.run_pages([self.obj(['a','b']),self.obj(['c'],4)])
if __name__=='__main__':unittest.main()

