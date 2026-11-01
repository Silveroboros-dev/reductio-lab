import unittest,copy
import conditional_news as n,gate
class T(unittest.TestCase):
 def setUp(self):
  self.raw=b'{"synthetic":"BEA fetch"}';self.receipt={'id':'p1-cpi-bea-fetch','kind':'source','state':'succeeded','http_status':200,'response_hash':gate.sha(self.raw),'response':self.raw,'actual_micro':5000,'completed_at_utc':'2026-10-29T12:31:00Z'}
  self.k={'raw':self.raw,'receipt':self.receipt,'verify_amendment':lambda *a:True,'verify_fetch':lambda *a:True}
 def test_evidence_caveat_is_visible(self):
  x=n.make(**self.k)[0];self.assertIn('first actual public visibility was not independently measured',x['text']);self.assertIn('embargo',x['text']);self.assertEqual(x['published_at_utc'],'2026-10-29T12:30:00Z')
 def test_unreviewed_or_bad_receipt_fails(self):
  self.k['verify_fetch']=lambda *a:False
  with self.assertRaises(n.Error):n.make(**self.k)
  self.k['verify_fetch']=lambda *a:True;self.k['receipt']=copy.deepcopy(self.receipt);self.k['receipt']['response_hash']='a'*64
  with self.assertRaises(n.Error):n.make(**self.k)
 def test_capture_before_observation_fails(self):
  self.receipt['completed_at_utc']='2026-10-29T12:30:01Z'
  with self.assertRaises(n.Error):n.make(**self.k)
if __name__=='__main__':unittest.main()
