import io
import unittest
import zipfile
from datetime import date, datetime, timezone
from titan.bse import targets, validate, matching_url, IST

DAY = date(2026, 10, 27)
CSV = b'TradDt,Src,Sgmt,FinInstrmId,ISIN,OpnPric,HghPric,LwPric,ClsPric,TtlTradgVol\n2026-10-27,BSE,CM,500001,INE123,10,12,9,11,100\n'

class ValidationTests(unittest.TestCase):
    def test_ist_boundary(self):
        self.assertEqual(targets(datetime(2026,10,28,11,tzinfo=timezone.utc)), [date(2026,10,28)])
        self.assertEqual(targets(datetime(2026,10,28,3,tzinfo=timezone.utc))[0], DAY)
    def test_weekend_not_assumed_closed(self):
        self.assertEqual(targets(datetime(2026,10,26,8,30,tzinfo=IST))[0], date(2026,10,25))
    def test_explicit_and_future(self):
        self.assertEqual(targets(datetime(2026,10,28,tzinfo=IST),'2026-10-27'), [DAY])
        with self.assertRaises(ValueError): targets(datetime(2026,10,28,tzinfo=IST),'2026-10-29')
    def test_naive_time(self):
        with self.assertRaises(ValueError): targets(datetime(2026,10,28))
    def test_csv_and_zip(self):
        self.assertEqual(validate(CSV, DAY)[1]['rows'], 1)
        f = io.BytesIO()
        with zipfile.ZipFile(f,'w') as z: z.writestr('x.csv', CSV)
        self.assertEqual(validate(f.getvalue(), DAY)[0], CSV)
    def test_wrong_date_source_segment_html_empty(self):
        for content in [CSV.replace(b'2026-10-27',b'2026-10-26'), CSV.replace(b'BSE',b'NSE'),
                        CSV.replace(b',CM,',b',FO,'), b'<html>Access Denied</html>', CSV.splitlines()[0]+b'\n']:
            with self.subTest(content=content):
                with self.assertRaises(ValueError): validate(content, DAY)
    def test_ambiguous_zip(self):
        f = io.BytesIO()
        with zipfile.ZipFile(f,'w') as z:
            z.writestr('a.csv',CSV)
            z.writestr('b.csv',CSV)
        with self.assertRaises(ValueError): validate(f.getvalue(),DAY)
    def test_exact_url(self):
        url='https://www.bseindia.com/download/BhavCopy_BSE_CM_0_0_0_20261027_F_0000.CSV.zip'
        self.assertTrue(matching_url(url,DAY))
        for wrong in [url.replace('20261027','20261026'),url.replace('_CM_','_FO_'),
                      url.replace('www.bseindia.com','evil.example'),url.replace('https:','http:')]:
            self.assertFalse(matching_url(wrong,DAY))

if __name__ == '__main__': unittest.main()
