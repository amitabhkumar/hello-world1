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
    def test_official_download_and_invalid_exports(self):
        from unittest.mock import MagicMock
        from titan.bse_data import pledge_csv
        page=MagicMock();page.url='https://www.bseindia.com/corporates/pledge_new'
        page.locator.return_value.filter.return_value.count.return_value=1
        dl=page.expect_download.return_value.__enter__.return_value.value
        dl.failure.return_value=None;dl.url='blob:https://www.bseindia.com/test';dl.suggested_filename='pledge.csv'
        for body,valid in [(b'Security Code,Pledged Shares\n500001,10\n',True),(b'',False),(b'<html>error',False),(b'Security Code,Pledged Shares\n',False),(b'Name,Value\nA,1',False)]:
            with self.subTest(body=body),tempfile.TemporaryDirectory() as d:
                dl.save_as.side_effect=lambda dest,b=body:Path(dest).write_bytes(b)
                if valid:
                    result={};pledge_csv(page,'2026-11-16',Path(d),result)
                    self.assertEqual(result['exports'][0]['rows'],1)
                    self.assertFalse(result['historical_asof_verified'])
                else:
                    with self.assertRaises(ValueError):pledge_csv(page,'2026-11-16',Path(d),{})
        page.expect_download.assert_called()
