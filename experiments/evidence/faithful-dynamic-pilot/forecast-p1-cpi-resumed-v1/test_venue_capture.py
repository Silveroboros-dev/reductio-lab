import json,unittest
import gate,venue_capture as v
class T(unittest.TestCase):
 def setUp(self):
  self.case=gate.verify_p0()['prepared']['case'];self.market={'ticker':gate.TICKER,'status':'active','result':'','rules_primary':self.case['rules_primary'],'rules_secondary':self.case['rules_secondary'],'yes_bid_dollars':'0.99'}
 def raw(self,markets):return json.dumps({'success':True,'data':{'markets':markets}}).encode()
 def test_extracts_status_but_not_new_price(self):
  x=v.extract(self.raw([self.market]));self.assertEqual(x['state'],'active');self.assertNotIn('0.99',str(x));self.assertNotIn('yes_bid_dollars',x)
 def test_missing_and_ambiguous_rejected(self):
  with self.assertRaises(v.Error):v.extract(self.raw([]))
  with self.assertRaises(v.Error):v.extract(self.raw([self.market,self.market]))
  bad=dict(self.market);del bad['rules_secondary']
  with self.assertRaises(v.Error):v.extract(self.raw([bad]))
 def test_unbound_status_rejected(self):
  self.assertFalse(v.verify_status({'source_op_id':'invented','response_sha256':'a'*64},self.case,'2026-10-29T12:40:00Z'))
if __name__=='__main__':unittest.main()
