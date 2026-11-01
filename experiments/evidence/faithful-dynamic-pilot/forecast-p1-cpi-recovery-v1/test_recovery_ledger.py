import json,sys,tempfile,unittest
from pathlib import Path
import recovery_ledger as q
class RecoveryTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
  self.db=q.RecoveryBase(str(Path(self.tmp.name).resolve()/'ledger'),q.config(),create=True);self.addCleanup(self.db.close)
  self.stage=q.RecoveryStage(self.db,lambda:True,lambda:True)
  self.req={'contents':[],'generationConfig':{'maxOutputTokens':4096}}
  self.c='count:p1:case-02:no_news:b:01';self.g='generation:p1:case-02:no_news:b:01'
 def count(self,*args):return 200,json.dumps({'totalTokens':100}).encode()
 def gen(self,*args):return 200,json.dumps({'modelVersion':'gemini-3.8-flash','usageMetadata':{'promptTokenCount':100,'totalTokenCount':200}}).encode()
 def err429(self,*args):return 429,json.dumps({'error':{'code':429,'status':'RESOURCE_EXHAUSTED'}}).encode()
 def test_actual_parent(self):
  p=q.inspect_parent();self.assertEqual((p['prior_sources'],p['prior_generations'],p['prior_counts']), (23,307,236))
 def test_prior_http200_and_all_c_no_news_blocked(self):
  for kind in ('count','generation'):
   for n in (1,8,9):
    ident=f'{kind}:p1:case-02:no_news:c:{n:02d}'
    with self.assertRaises(q.p.Error):
     if kind=='count':self.stage.count_attempt(ident,self.req,0,lambda *a:self.fail('unexpected provider'))
     else:self.stage.generate_attempt(ident,self.req,ident.replace('generation:','count:'),0,lambda *a:self.fail('unexpected provider'))
  self.assertEqual(self.db.summary()['generation_attempts'],307)
 def test_allowed_one_shot_count_and_generation_and_429(self):
  with self.assertRaises(q.r.Confirmed429):self.stage.count_attempt(self.c,self.req,0,self.err429)
  self.stage.count_attempt(self.c,self.req,1,self.count)
  with self.assertRaises(q.r.Confirmed429):self.stage.generate_attempt(self.g,self.req,self.c,0,self.err429)
  self.stage.generate_attempt(self.g,self.req,self.c,1,self.gen)
  with self.assertRaises(q.p.Error):self.stage.generate_attempt(self.g,self.req,self.c,2,self.gen)
  self.assertEqual((self.stage.summary()['generation_attempts'],self.stage.summary()['count_attempts']), (309,238))
 def test_unknown_stops_and_no_retry(self):
  def bad(*a):raise OSError('uncertain')
  with self.assertRaises(Exception):self.stage.count_attempt(self.c,self.req,0,bad)
  self.assertEqual(self.db.summary()['stopped'],1)
  with self.assertRaises(Exception):self.stage.count_attempt(self.c,self.req,1,self.count)
 def test_status_billing_and_single_use(self):
  body=json.dumps({'success':True,'priceCents':0,'billing':{'chargedPriceCents':0}}).encode()
  self.stage.status_source('p1-cpi-status-04',lambda *a:(200,body),lambda *a:True)
  self.assertEqual(self.stage.summary()['source_attempts'],24)
  with self.assertRaises(Exception):self.stage.status_source('p1-cpi-status-04',lambda *a:self.fail('duplicate provider'),lambda *a:True)
 def test_status_missing_billing_reserve_and_stop(self):
  body=json.dumps({'success':True,'priceCents':0}).encode()
  with self.assertRaises(q.p.Error):self.stage.status_source('p1-cpi-status-04',lambda *a:(200,body),lambda *a:True)
  self.assertEqual((self.stage.summary()['stopped'],self.stage.summary()['exposure_micro']),(1,2033331+150000))
 def test_status_nonzero_billing_is_accounted(self):
  body=json.dumps({'success':True,'priceCents':0.2,'billing':{'chargedPriceCents':0.2}}).encode()
  self.stage.status_source('p1-cpi-status-04',lambda *a:(200,body),lambda *a:True)
  self.assertEqual((self.stage.summary()['stopped'],self.stage.summary()['exposure_micro']),(0,2033331+2000))
if __name__=='__main__':unittest.main()
