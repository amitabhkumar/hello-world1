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


import unittest
from datetime import date
from nse_automation.download import session_constraints, interpret_reg1

class Sessions(unittest.TestCase):
    def evaluate(self, gsm='100', esm='100', status='A', day=date(2026,11,6)):
        return session_constraints(dict(GSM=gsm,ESM=esm,Status=status),day)
    def test_suspension_dominates(self):
        self.assertEqual(self.evaluate(esm='2',status='S')['trading_access'],'Blocked')
    def test_inactive(self):
        self.assertEqual(self.evaluate(status='I')['trading_access'],'Blocked')
    def test_gsm_one(self):
        self.assertEqual(self.evaluate(gsm='1')['rules'][0]['margin_percent'],100)
    def test_gsm_two(self):
        self.assertEqual(self.evaluate(gsm='2')['rules'][0]['buyer_asd_percent'],50)
    def test_weekly_denied(self):
        self.assertEqual(self.evaluate(gsm='3')['trading_access'],'Blocked')
    def test_monday_holiday_shift(self):
        r=self.evaluate(gsm='3',day=date(2026,1,27))
        self.assertTrue(r['rules'][0]['matches_weekly_date'])
    def test_stage_four(self):
        self.assertTrue(self.evaluate(gsm='4',day=date(2026,11,9))['rules'][0]['no_upward_movement'])
    def test_esm_one_margin_delay(self):
        self.assertIn('T+2',self.evaluate(esm='1')['rules'][0]['margin_activation'])
    def test_esm_two(self):
        self.assertEqual(self.evaluate(esm='2')['gsm_esm_session_result'],'PERIODIC_CALL_AUCTION_REQUIRED')
    def test_conjunction(self):
        r=self.evaluate(gsm='3',esm='2')
        self.assertEqual(r['trading_access'],'Blocked')
        self.assertEqual(len(r['rules']),2)
    def test_closed_day(self):
        self.assertIn('EXCHANGE_CLOSED',self.evaluate(day=date(2026,11,7))['blockers'])
    def test_special_session_not_weekly_exception(self):
        r=self.evaluate(gsm='3',day=date(2026,11,8))
        self.assertNotIn('EXCHANGE_CLOSED',r['blockers'])
        self.assertIn('OUTSIDE_GSM_WEEKLY_SESSION',r['blockers'])
    def test_unknown_and_legacy(self):
        for code in ('6','999',''):
            self.assertFalse(self.evaluate(gsm=code)['framework_rules_verified'])
    def test_missing_not_clear(self):
        self.assertEqual(session_constraints({},date(2026,11,6))['gsm_esm_session_result'],'UNKNOWN_INPUT_OR_RULE')
    def test_no_global_clearance(self):
        self.assertEqual(self.evaluate()['trading_access'],'Unknown')
    def test_top_level_block(self):
        r=interpret_reg1(b'Symbol,Series,Status,GSM,ESM\nTEST,BE,S,4,100\n',date(2026,11,5))
        self.assertEqual(r[0]['trading_access'],'Blocked')
    def test_year_coverage(self):
        with self.assertRaisesRegex(ValueError,'CALENDAR_COVERAGE_MISSING'):
            self.evaluate(day=date(2027,1,4))
if __name__=='__main__':unittest.main()
