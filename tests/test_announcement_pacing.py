import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from titan.bse_data import announcement_pages

class AnnouncementPacingTests(unittest.TestCase):
 def exercise(self,count,fail_page=None):
  trace=[]
  class Page:
   def wait_for_timeout(self,ms):trace.append(('pause',ms))
  def response(page,target,start,dest,result,n,label,backward=False):
   trace.append(('click','Prev' if backward else 'Submit' if n==1 else 'Next',n))
   if n==fail_page and not backward:raise ValueError('Announcement UI response HTTP 400')
   result['requests'].append({'url':'https://api.bseindia.com/observed-ui-response'})
   return {'Table':[{'NEWSID':str(i),'SCRIP_CD':500001,'NEWS_DT':'2026-11-16T10:00:00'} for i in range((n-1)*50,min(n*50,count))],'Table1':[{'ROWCNT':count}]}
  result={}
  with tempfile.TemporaryDirectory() as directory,patch('titan.bse_data.announcement_ui_response',side_effect=response):
   if fail_page:
    with self.assertRaisesRegex(ValueError,'HTTP 400'):announcement_pages(Page(),'2026-11-16',Path(directory),[],result)
   else:announcement_pages(Page(),'2026-11-16',Path(directory),[],result)
  return trace,result
 def test_forward_and_backward_each_paced_once(self):
  trace,result=self.exercise(1073)
  self.assertEqual(trace[0],('click','Submit',1))
  self.assertEqual(len(trace),85) # 1 Submit + 42 (pause, Next/Prev) pairs
  for i in range(1,len(trace),2):
   self.assertEqual(trace[i],('pause',1800));self.assertIn(trace[i+1][1],('Next','Prev'))
  self.assertEqual(trace[-1],('click','Prev',1))
  self.assertEqual(result['captured_unique_rows'],1073)
  self.assertTrue(result['pagination_stable'])
 def test_single_page_submit_recheck_has_no_navigation_pause(self):
  trace,result=self.exercise(1)
  self.assertEqual(trace,[('click','Submit',1),('click','Submit',1)])
 def test_page6_error_propagates_without_retry(self):
  trace,result=self.exercise(1073,6)
  self.assertEqual(trace[-1],('click','Next',6))
  self.assertEqual(sum(x[0]=='pause' for x in trace),5)
  self.assertEqual(result['captured_unique_rows'],250)
