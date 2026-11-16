import json
import tempfile
import unittest
from pathlib import Path
from datetime import date, datetime
from titan.bse import wait_for_date_form, date_controls

class ReadinessTests(unittest.TestCase):
    def controls(self):
        return [dict(options=[dict(text=str(y),value=str(y)) for y in range(2020,2028)]),
                dict(options=[dict(text=str(d),value=str(d)) for d in range(1,32)]),
                dict(options=[dict(text=datetime(2000,m,1).strftime('%B'),value=str(m)) for m in range(1,13)])]
    def test_old_market_watch_controls_rejected(self):
        with self.assertRaises(ValueError):
            date_controls([dict(id='dllUAssetgrp',options=[dict(text='Equity(T+1)',value='Equity')])],date(2026,11,13))
    def test_wait_precedes_capture_and_retains_evidence(self):
        calls=[];controls=self.controls()
        class Page:
            def wait_for_function(self,script,**kwargs):
                calls.append('wait')
                assert 'location.pathname' in script and 'hasYear && hasDay && hasMonth' in script
                assert kwargs==dict(arg=2026,timeout=60000)
            def evaluate(self,script):
                calls.append('capture');return dict(url='https://www.bseindia.com/markets/MarketInfo/BhavCopy.aspx',title='Bhav Copy',controls=controls)
        with tempfile.TemporaryDirectory()as d:
            result=wait_for_date_form(Page(),date(2026,11,13),Path(d))
            self.assertEqual(result,dict(year=(0,'2026'),day=(1,'13'),month=(2,'11')))
            self.assertEqual(calls,['wait','capture'])
            self.assertEqual(json.loads((Path(d)/'date_controls.json').read_text()),controls)
    def test_timeout_preserves_wrong_page(self):
        class Page:
            def wait_for_function(self,*a,**kw):raise TimeoutError('not ready')
            def evaluate(self,*a):return dict(url='https://www.bseindia.com/MarketWatch',controls=[])
        with tempfile.TemporaryDirectory()as d:
            with self.assertRaises(TimeoutError):wait_for_date_form(Page(),date(2026,11,13),Path(d))
            self.assertIn('MarketWatch',(Path(d)/'navigation_state.json').read_text())

class PledgeRequestTests(unittest.TestCase):
    def test_real_submit_before_parsing_no_empty_filter_fallback(self):
        import inspect
        from titan.bse_data import adapt
        code=inspect.getsource(adapt)
        self.assertIn('page.expect_response',code)
        self.assertLess(code.index("if key=='pledges'"),code.index('relevant='))
        self.assertNotIn('PledgeRange=&DeriTrade=',code)
