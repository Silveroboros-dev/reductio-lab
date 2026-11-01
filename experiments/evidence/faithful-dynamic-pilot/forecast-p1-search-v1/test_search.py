import copy,sys,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parent))
import search
class SearchTest(unittest.TestCase):
 def test_real_p0_and_two_distinct_exact_requests(self):
  p=search.p0_binding();self.assertEqual(p['case_id'],'case-03');self.assertEqual(p['durable_before_utc'],search.DURABLE)
  ops=search.operations();self.assertEqual(len(ops),2)
  self.assertEqual([(o['payload']['api'],o['payload']['path']) for o in ops],[('you/search','/v1/search'),('serper','/news')])
  self.assertIn('Astra 6.1',ops[0]['payload']['body']['query']);self.assertNotIn('Astra',ops[1]['payload']['body']['q'])
  self.assertTrue(all(x['ticket']['max_micro']==150000 for x in ops))
  self.assertEqual(len({x['ticket']['request_sha256'] for x in ops}),2)
 def test_expired_quote_cannot_authorize(self):
  with patch.object(search,'now',return_value='2026-10-29T11:43:52Z'):
   with self.assertRaises(search.Error):search.operations()
 def test_real_ledger_historical_exposure(self):
  s=search.account()['ledger'];self.assertEqual((s['exposure_micro'],s['generation_attempts'],s['count_attempts'],s['source_attempts']),(1882731,274,206,14))
  self.assertEqual([s['prior_http400_charge_unknown_retained_micro'],s['prior_http429_charge_unknown_retained_micro'],s['prior_http429b_charge_unknown_retained_micro'],s['prior_http429c_charge_unknown_retained_micro']],[150000,86016,86016,86016])
if __name__=='__main__':unittest.main()
