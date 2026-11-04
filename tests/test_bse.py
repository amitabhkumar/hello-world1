import io
import unittest
import zipfile
from datetime import date, datetime, timezone
from titan.bse import targets, validate, matching_url, IST, date_controls, Unavailable

DAY = date(2026, 10, 27)
CSV = b'TradDt,Src,Sgmt,FinInstrmId,ISIN,OpnPric,HghPric,LwPric,ClsPric,TtlTradgVol\n2026-10-27,BSE,CM,500001,INE123,10,12,9,11,100\n'

class ValidationTests(unittest.TestCase):
    def test_ist_boundary(self):
        self.assertEqual(targets(datetime(2026,10,28,13,30,tzinfo=timezone.utc),holidays=set(),calendar_years={2026}), [date(2026,10,28)])
        self.assertEqual(targets(datetime(2026,10,28,18,59,tzinfo=IST),holidays=set(),calendar_years={2026}), [DAY])
        self.assertEqual(targets(datetime(2026,10,28,8,29,tzinfo=IST),holidays=set(),calendar_years={2026}), [DAY])
    def test_weekend_holiday_month_year(self):
        for stamp,expected in [('2026-11-02T08:00:00','2026-10-30'),('2026-11-11T08:00:00','2026-11-09'),('2026-11-01T19:01:00','2026-10-30'),('2026-01-01T08:00:00','2025-12-31')]:
            self.assertEqual(targets(datetime.fromisoformat(stamp).replace(tzinfo=IST),holidays={date(2026,11,10)},calendar_years={2025,2026}),[date.fromisoformat(expected)])
        with self.assertRaises(Unavailable): targets(datetime(2026,1,1,8,tzinfo=IST),holidays=set(),calendar_years={2026})
        self.assertEqual(targets(datetime(2026,11,9,8,tzinfo=IST),holidays=set(),calendar_years={2026},special_sessions={date(2026,11,8)}),[date(2026,11,8)])
    def test_options_zero_padding_reordering(self):
        c=[{'options':[{'text':'Unrelated','value':'x'}]}, {'options':[{'text':str(y),'value':str(y)} for y in range(2020,2028)]}, {'options':[{'text':f'{d:02}','value':str(d)} for d in range(1,32)]}, {'options':[{'text':datetime(2000,m,1).strftime('%B'),'value':str(m)} for m in range(1,13)]}]
        self.assertEqual(date_controls(c,date(2026,11,4)),{'year':(1,'2026'),'day':(2,'4'),'month':(3,'11')})
        with self.assertRaises(ValueError):date_controls(c+c[2:3],date(2026,11,4))
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

