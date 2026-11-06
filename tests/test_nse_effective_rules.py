"""Regression tests for official price-band evidence and partial session constraints."""
import unittest
from datetime import date
from nse_automation.download import verify_band_changes, session_constraints

class EffectiveRules(unittest.TestCase):
    def setUp(self):
        self.csv=b"Symbol,Series,From,To\nUCAL,EQ,5,2\n"
        self.history=[dict(symbol="UCAL",fromPriceBand="5",toPriceBand="2",effectiveDate="06-NOV-2026")]
    def test_exact_match(self):
        self.assertEqual(verify_band_changes(self.csv,self.history,date(2026,11,6))["effective_date"],"2026-11-06")
    def test_reject_missing_duplicate_wrong_date(self):
        for history,day in [( [],6),(self.history*2,6),(self.history,5)]:
            with self.assertRaises(ValueError):
                verify_band_changes(self.csv,history,date(2026,11,day))
    def test_gsm_weekly(self):
        self.assertFalse(session_constraints({"GSM":"3"},date(2026,11,6))["rules"][0]["matches_weekly_date"])
        self.assertTrue(session_constraints({"GSM":"4"},date(2026,11,9))["rules"][0]["no_upward_movement"])
    def test_esm(self):
        result=session_constraints({"ESM":"2"},date(2026,11,6))
        self.assertEqual(result["rules"][0]["session"],"Periodic call auction")
        self.assertEqual(result["trading_access"],"Unknown")
    def test_no_rules_does_not_mean_permission(self):
        self.assertEqual(session_constraints({},date(2026,11,6))["trading_access"],"Unknown")
if __name__=="__main__": unittest.main()
