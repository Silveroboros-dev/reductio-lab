import json,tempfile,unittest
from pathlib import Path
import news_v2 as news
class Tests(unittest.TestCase):
 def test_exact_new_scope_and_parent(self):
  ops,bindings=news.evidence();self.assertEqual([x['case_id'] for x in ops],['case-01','case-03','case-04']);self.assertEqual([x['payload']['api'] for x in ops],['serper','you/search','linkup']);self.assertEqual(len(bindings),3)
  self.assertEqual(news.parent.inspect_parent()['prior_micro'],1988563)
 def test_fake_three_sources_and_no_model(self):
  with tempfile.TemporaryDirectory() as tmp:
   base=news.Base(str(Path(tmp).resolve()/'ledger'),news.config(),create=True)
   try:
    ops,_=news.evidence();allowed=lambda ticket,raw:any(op['ticket']==ticket and news.canonical(op['payload'])==raw for op in ops)
    ledger=news.Source(base,b'claim',{},'a'*64,allowed);ledger._guard=lambda:None
    for op in ops:
     rate={'case-01':0.2,'case-03':0.5,'case-04':1.0}[op['case_id']]
     raw=ledger.source(op['ticket']['id'],'orthogonal','/v1/run',news.canonical(op['payload']),op['ticket'],lambda *a:(200,json.dumps({'success':True,'priceCents':rate,'billing':{'chargedPriceCents':rate}}).encode()))
     self.assertTrue(json.loads(raw)['success'])
    s=ledger.summary();self.assertEqual((s['generation_attempts'],s['count_attempts'],s['source_attempts'],s['exposure_micro']),(299,228,19,2005563))
    with self.assertRaises(news.Error):ledger.count('x',{},lambda *a:self.fail('unexpected effect'))
    with self.assertRaises(news.Error):ledger.generate('x',{},'y',lambda *a:self.fail('unexpected effect'))
    with self.assertRaises(Exception):
     op=ops[0];ledger.source(op['ticket']['id'],'orthogonal','/v1/run',news.canonical(op['payload']),op['ticket'],lambda *a:self.fail('unexpected effect'))
   finally:base.close()
 def test_billing_mismatch_settles_actual_and_stops(self):
  with tempfile.TemporaryDirectory() as tmp:
   base=news.Base(str(Path(tmp).resolve()/'ledger'),news.config(),create=True)
   try:
    op=news.evidence()[0][0];ledger=news.Source(base,b'claim',{},'a'*64,lambda *x:True);ledger._guard=lambda:None
    with self.assertRaises(news.Error):ledger.source(op['ticket']['id'],'orthogonal','/v1/run',news.canonical(op['payload']),op['ticket'],lambda *a:(200,json.dumps({'success':True,'priceCents':0.2,'billing':{'chargedPriceCents':0.3}}).encode()))
    self.assertEqual(base.receipt(op['ticket']['id'])['actual_micro'],3000);self.assertEqual(base.summary()['stopped'],1)
   finally:base.close()
 def test_missing_billing_retains_reserve_and_stops(self):
  with tempfile.TemporaryDirectory() as tmp:
   base=news.Base(str(Path(tmp).resolve()/'ledger'),news.config(),create=True)
   try:
    op=news.evidence()[0][0];ledger=news.Source(base,b'claim',{},'a'*64,lambda *x:True);ledger._guard=lambda:None
    with self.assertRaises(news.Error):ledger.source(op['ticket']['id'],'orthogonal','/v1/run',news.canonical(op['payload']),op['ticket'],lambda *a:(200,json.dumps({'success':True,'priceCents':0.2}).encode()))
    self.assertIsNone(base.receipt(op['ticket']['id'])['actual_micro']);self.assertEqual(base.summary()['stopped'],1);self.assertEqual(base.summary()['exposure_micro'],2138563)
   finally:base.close()
if __name__=='__main__':unittest.main()
