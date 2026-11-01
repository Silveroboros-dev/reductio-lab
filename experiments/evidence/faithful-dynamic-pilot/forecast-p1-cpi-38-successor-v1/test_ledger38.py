import json,tempfile,unittest
from pathlib import Path
import ledger38 as l
class T(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.db=l.Base(str(Path(self.tmp.name).resolve()/'ledger'),l.config(),create=True);self.addCleanup(self.db.close)
  self.ops=json.loads((l.ROOT/'forecast-cpi-p1-status38-source-contract-20261029-v1.json').read_bytes())['operations'];self.stage=l.Stage(self.db,lambda:True,lambda:True,self.ops)
  self.req={'contents':[],'generationConfig':{'maxOutputTokens':4096}}
 def test_actual_parent_and_unstarted_arm_only(self):
  p=l.inspect_parent();self.assertEqual((p['prior_generations'],p['prior_counts'],p['prior_sources']),(315,244,25))
  for ident in ('count:p1:case-02:no_news:c:01','count:p1:case-02:no_news:b:01'):
   with self.assertRaises(l.Error):self.stage.count_attempt(ident,self.req,0,lambda *a:self.fail('old calls forbidden'))
 def test_news_retry_reuses_count_and_records_cost(self):
  c='count:p1:case-02:news:c:01';g='generation:p1:case-02:news:c:01'
  def err(*a):return 429,b'{"error":{"code":429,"status":"RESOURCE_EXHAUSTED"}}'
  with self.assertRaises(l.retry.Confirmed429):self.stage.count_attempt(c,self.req,0,err)
  self.stage.count_attempt(c,self.req,1,lambda *a:(200,b'{"totalTokens":100}'))
  self.stage.generate_attempt(g,self.req,c,0,lambda *a:(200,json.dumps({'modelVersion':'gemini-3.8-flash','usageMetadata':{'promptTokenCount':100,'totalTokenCount':200}}).encode()))
  self.assertEqual(self.stage.summary()['generation_attempts'],316);self.assertEqual(self.stage.summary()['count_attempts'],246)
  with self.assertRaises(Exception):self.stage.generate_attempt(g,self.req,c,0,lambda *a:self.fail('must not repeat'))
 def test_status_nonzero_charged_and_single_use(self):
  raw=json.dumps({'success':True,'priceCents':0.2,'billing':{'chargedPriceCents':0.2}}).encode();self.stage.status_source('p1-cpi-status-06',lambda *a:(200,raw),lambda *a:True)
  self.assertEqual((self.stage.summary()['source_attempts'],self.stage.summary()['exposure_micro']),(26,2071419))
  with self.assertRaises(Exception):self.stage.status_source('p1-cpi-status-06',lambda *a:self.fail('repeat'),lambda *a:True)
 def test_ambiguous_call_stops(self):
  def bad(*a):raise OSError('unknown')
  with self.assertRaises(Exception):self.stage.count_attempt('count:p1:case-02:news:c:01',self.req,0,bad)
  self.assertEqual(self.stage.summary()['stopped'],1)
if __name__=='__main__':unittest.main()
