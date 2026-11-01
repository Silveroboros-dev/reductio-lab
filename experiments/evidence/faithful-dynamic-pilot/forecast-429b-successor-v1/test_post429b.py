import tempfile,unittest,json
from pathlib import Path
from unittest import mock
import post429b as p
class Test(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory(dir='/private/tmp');self.root=Path(self.tmp.name).resolve();self.parent={'synthetic':'immutable'}
  self.i=mock.patch.object(p,'inspect',return_value=self.parent);self.i.start();self.cc=mock.patch.object(p,'CLAIM',self.root/'claim');self.cc.start();self.ledger=None
  self.contract=self.root/'contract';c={'schema':'faithful-forecast-post429b-accounting-v1','status':'frozen','caps':p.CAPS,'parent':self.parent,'ledger_config':p.config(),'bridge_sha256':p.digest(p.r.read(Path(p.__file__))),'ledger_root':str(self.root/'ledger'),'scope':{'mode':'accounting_only','provider_effects':'forbidden','future_cases':['case-03','case-04'],'no_retry':True}}
  self.contract.write_bytes(p.canonical(c));self.sha=p.digest(self.contract.read_bytes())
 def tearDown(self):
  if self.ledger:self.ledger.close()
  self.i.stop();self.cc.stop();self.tmp.cleanup()
 def create(self):
  self.ledger=p.create(successor_root=str(self.root/'ledger'),contract_path=str(self.contract),expected_sha=self.sha,verify_challenge=lambda _:True);return self.ledger
 def activate(self):
  a=self.create(); c={'schema':'faithful-forecast-post429b-model-v1','status':'frozen','caps':p.CAPS,'accounting_contract_sha256':self.sha,'ledger_root':str(a.root),'starting_usage':a.summary(),'case_ids':['case-03','case-04'],'source_reads':0,'no_retry':True,'pacing_min_seconds':20,'pacing_scope':'all_provider_calls'};f=self.root/'model';f.write_bytes(p.canonical(c));h=p.digest(f.read_bytes());self.ledger=p.activate(a,model_contract_path=str(f),expected_sha=h,verify_challenge=lambda _:True);return self.ledger
 def test_accounting_carry_and_forbidden(self):
  a=self.create();s=a.summary();self.assertEqual((s['exposure_micro'],s['generation_attempts'],s['count_attempts'],s['source_attempts']),(1737725,255,187,14));self.assertEqual((s['prior_http400_charge_unknown_retained_micro'],s['prior_http429_charge_unknown_retained_micro']),(150000,86016));self.assertEqual(s['prior_http429b_charge_unknown_retained_micro'],86016)
  for fn in (a.count,a.generate,a.source):
   with self.assertRaises(p.Error):fn()
  a.close();self.ledger=None;self.ledger=p.reopen(successor_root=str(self.root/'ledger'),contract_path=str(self.contract),expected_sha=self.sha,verify_challenge=lambda _:True)
 def test_activation_model_cost_and_scope(self):
  a=self.activate();req={'contents':[],'generationConfig':{'maxOutputTokens':4096}}
  def tr(provider,endpoint,body):
   if endpoint=='countTokens':return 200,b'{"totalTokens":100}'
   return 200,b'{"modelVersion":"gemini-3.8-flash","usageMetadata":{"promptTokenCount":100,"totalTokenCount":140}}'
  with self.assertRaises(p.Error):a.count('count:p0:case-01:c:01',req,tr)
  with self.assertRaises(p.Error):a.count('count:p0:case-02:c:01',req,tr)
  a.count('count:p0:case-03:c:01',req,tr);a.generate('generation:p0:case-03:c:01',req,'count:p0:case-03:c:01',tr)
  s=a.summary();self.assertEqual((s['exposure_micro'],s['generation_attempts'],s['count_attempts']),(1738175,256,188))
  with self.assertRaises(p.r.Error):a.source('n','x','x',b'',{},tr)
 def test_no_retry_failed_request(self):
  a=self.activate()
  with mock.patch.object(p,'FAILED_REQ',p.digest(p.canonical({'x':1}))):
   with self.assertRaises(p.Error):a.count('count:p0:case-03:c:01',{'x':1},lambda *_:None)
 def test_failed_challenge_creates_nothing(self):
  with self.assertRaises(p.Error):p.create(successor_root=str(self.root/'ledger'),contract_path=str(self.contract),expected_sha=self.sha,verify_challenge=lambda _:False)
  self.assertFalse((self.root/'ledger').exists());self.assertFalse(p.CLAIM.exists())
if __name__=='__main__':unittest.main()
