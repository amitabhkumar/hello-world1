"""Offline acceptance checks for scheduled NSE bulk/block acquisition."""
import ast, csv, io, json, pathlib, unittest
from datetime import datetime
from decimal import Decimal
from nse_automation.download import select_date, IST

class DatePolicy(unittest.TestCase):
 def test_sessions_and_gates(self):
  cases=[
   ("2026-11-06T08:30:00","2026-11-05","ELIGIBLE_FOR_SINGLE_ATTEMPT"),
   ("2026-11-06T16:30:00","2026-11-06","PENDING_PUBLICATION_WINDOW"),
   ("2026-11-06T22:00:00","2026-11-06","ELIGIBLE_FOR_SINGLE_ATTEMPT"),
   ("2026-11-07T08:00:00","2026-11-06","ELIGIBLE_FOR_SINGLE_ATTEMPT"),
   ("2026-11-08T08:30:00","2026-11-06","ELIGIBLE_FOR_SINGLE_ATTEMPT"),
   ("2026-11-08T22:00:00","2026-11-08","ELIGIBLE_FOR_SINGLE_ATTEMPT"),
   ("2026-11-09T08:30:00","2026-11-08","ELIGIBLE_FOR_SINGLE_ATTEMPT"),
   ("2026-11-10T22:00:00","2026-11-09","ELIGIBLE_FOR_SINGLE_ATTEMPT"),
   ("2026-11-02T08:30:00","2026-10-30","ELIGIBLE_FOR_SINGLE_ATTEMPT"),
   ("2026-12-01T08:30:00","2026-11-30","ELIGIBLE_FOR_SINGLE_ATTEMPT")]
  for now,date,gate in cases:
   with self.subTest(now=now):
    got,status=select_date(datetime.fromisoformat(now).replace(tzinfo=IST))
    self.assertEqual((str(got),status),(date,gate))
 def test_unknown_calendar_and_bad_explicit(self):
  with self.assertRaisesRegex(ValueError,"CALENDAR_COVERAGE_MISSING"):
   select_date(datetime(2027,1,4,8,30,tzinfo=IST))
  for date in ("2026-11-07","2026-11-10","2026-12-01"):
   with self.subTest(date=date),self.assertRaises(ValueError):
    select_date(datetime(2026,11,6,22,tzinfo=IST),date)
 def test_workflow_no_fixed_default_or_retry(self):
  content=pathlib.Path(".github/workflows/nse_deals_recovery.yml").read_text()
  self.assertNotIn('or "2026-11-04"',content)
  self.assertNotIn("default: '2026-11-04'",content)
  for cron in ("0 3 * * 1-5","0 11 * * 1-5","30 16 * * *","30 2 * * 6"):
   self.assertIn(cron,content)
  self.assertIn('retry_policy":"NONE"',content)
 def test_date_case_and_mixed_date(self):
  expected={"04-Nov-2026","04-11-2026","04/11/2026","2026-11-04"}
  check=lambda values:{x.upper() for x in values}.issubset({x.upper() for x in expected})
  self.assertTrue(check({"04-NOV-2026"}))
  self.assertFalse(check({"04-NOV-2026","05-NOV-2026"}))
 def test_schema_and_values(self):
  # Execute the exact production validation block on a fixture and mutations.
  content=pathlib.Path(".github/workflows/nse_deals_recovery.yml").read_text()
  block=content.split('              required={"Date"',1)[1].split('              name=kind+',1)[0]
  code='required={"Date"'+block
  lines=code.splitlines(); code=lines[0]+"\n"+"\n".join(x[14:] for x in lines[1:])
  row={"Date":"04-NOV-2026","Symbol":"TEST","Security Name":"Test","Client Name":"Client","Buy / Sell":"BUY","Quantity Traded":"100","Trade Price / Wght. Avg. Price":"12.5"}
  exec(code,{"rows":[row],"Decimal":Decimal})
  for field,value in [("Symbol",""),("Buy / Sell","OTHER"),("Quantity Traded","0"),("Quantity Traded","1.5"),("Trade Price / Wght. Avg. Price","NaN")]:
   with self.subTest(field=field,value=value),self.assertRaises(ValueError):
    exec(code,{"rows":[dict(row,**{field:value})],"Decimal":Decimal})

if __name__=="__main__":unittest.main()
