import csv
import gzip
import io
import unittest
from nse_automation.access import official_url, decode_master, master_record, reconcile

class AccessEvidence(unittest.TestCase):
    def setUp(self):
        self.row=dict(FinInstrmId='123',TckrSymb='TEST',SctySrs='EQ',ISIN='INE000A01010',
            PricRg='90.00-110.00',SctyStsNrmlMkt='6',ElgbltyNrmlMkt='1',
            CallAuctnInd='1',DelFlg='N',ElgbltyClsgAuctnSsn='0')
        self.reg=dict(symbol='TEST',series='EQ',effective_trading_date='2026-11-16',session_constraints={'blockers':[]})
    def payload(self,rows):
        s=io.StringIO();w=csv.DictWriter(s,fieldnames=list(self.row));w.writeheader();w.writerows(rows)
        return gzip.compress(s.getvalue().encode())
    def test_master_structure(self):
        self.assertEqual(len(decode_master(self.payload([self.row]))[0]),1)
    def test_duplicate_rejected(self):
        with self.assertRaisesRegex(ValueError,'DUPLICATE'):
            decode_master(self.payload([self.row,self.row]))
    def test_corrupt_gzip(self):
        with self.assertRaises(Exception): decode_master(b'not gzip')
    def test_empty_master(self):
        with self.assertRaisesRegex(ValueError,'EMPTY'): decode_master(self.payload([]))
    def test_missing_schema(self):
        with self.assertRaisesRegex(ValueError,'COLUMNS'): decode_master(gzip.compress(b'a,b\n1,2\n'))
    def test_known_official_hosts(self):
        for url in ['https://nsearchives.nseindia.com/a','https://www.nseindia.in/a']:
            self.assertTrue(official_url(url))
    def test_host_spoofs_rejected(self):
        for url in ['http://www.nseindia.com/a','https://nseindia.com.evil.test/a',
                    'https://www.nseindia.com@evil.test/a','blob:https://www.nseindia.in/id']:
            self.assertFalse(official_url(url))
    def test_preopen_not_live_open(self):
        x=master_record(self.row);self.assertEqual(x['master_status'],'PRICE_DISCOVERY')
        self.assertTrue(x['normal_market_eligible']);self.assertNotIn('trading_access',x)
    def test_suspension_and_deletion(self):
        for k,v,reason in [('SctyStsNrmlMkt','3','SUSPENDED'),('DelFlg','Y','DELETED'),('ElgbltyNrmlMkt','0','NOT_ELIGIBLE')]:
            x=master_record(dict(self.row,**{k:v}));self.assertTrue(any(reason in b for b in x['blockers']))
    def test_unknown_code_preserved(self):
        self.assertIn('CallAuctnInd=99',master_record(dict(self.row,CallAuctnInd='99'))['unknown'])
    def test_bad_ranges(self):
        for value in ['NaN-1','0-1','200-100','-10-100','']:
            self.assertIsNone(master_record(dict(self.row,PricRg=value))['price_range'])
    def test_cas_distinct(self):
        self.assertTrue(master_record(dict(self.row,ElgbltyClsgAuctnSsn='1'))['closing_auction_eligible'])
    def test_band_proof_scoped(self):
        bands=[dict(Symbol='TEST',Series='EQ',Band='10')]
        ev=dict(status='ROW_MATCH_VERIFIED',effective_date='2026-11-16',records=[dict(csv_record=dict(Symbol='TEST',Series='EQ',To='10'))])
        r=reconcile([self.reg],[self.row],bands,[ev],'2026-11-16')[0]
        self.assertEqual(r['band_effective_status'],'ROW_MATCH_VERIFIED')
        self.assertEqual(r['trading_access'],'Unknown')
        ev['effective_date']='2026-11-17'
        self.assertEqual(reconcile([self.reg],[self.row],bands,[ev],'2026-11-16')[0]['band_effective_status'],'UNKNOWN')
    def test_series_not_symbol_only(self):
        r=reconcile([dict(self.reg,series='BE')],[self.row],[],[],'2026-11-16')[0]
        self.assertIsNone(r['master_snapshot'])
    def test_dated_deny_dominates(self):
        r=dict(self.reg,session_constraints={'blockers':['SUSPENDED']})
        self.assertEqual(reconcile([r],[],[],[],'2026-11-16')[0]['trading_access'],'Blocked')
        self.assertEqual(reconcile([r],[],[],[],'2026-11-17')[0]['trading_access'],'Unknown')

if __name__=='__main__': unittest.main()
