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
