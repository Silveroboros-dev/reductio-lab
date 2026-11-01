import copy,unittest
import gate,dispatch_preflight,dispatch_frozen,test_dispatch_preflight,test_orchestrate_retry,test_runner_retry
class T(unittest.TestCase):
 def setUp(self):
  t=test_dispatch_preflight.T();t.setUp();self.t=t;self.p=dispatch_preflight.prepare(**t.k);self.model=test_orchestrate_retry.Model(t.a)
  self.original=dispatch_frozen.orchestrate_retry.run;dispatch_frozen.orchestrate_retry.run=lambda **kw:kw
  self.contract=gate.canonical(dispatch_frozen.expected(self.p));self.k={'prefreeze':self.p,'contract_bytes':self.contract,'contract_sha256':gate.sha(self.contract),'verify_contract':lambda b:True,
   'model_stage':self.model,'source_stage':t.source,'model_transport':lambda *a:None,'source_transport':lambda *a:None,'decode_status':lambda *a:None,
   'verify_operation':lambda *a:True,'verify_news':lambda *a:True,'verify_status':lambda *a:True,'verify_admission':lambda *a:True,'verify_ledger':lambda *a:True,
   'record':lambda *a:None,'clock':t.clock,'pacer':None,'confirmed429':test_runner_retry.Confirmed429,'rate_limit_exhausted':test_runner_retry.RateLimitExhausted,'sleep':lambda *a:None,'jitter':lambda:0}
 def tearDown(self):dispatch_frozen.orchestrate_retry.run=self.original
 def test_exact_contract_and_account(self):
  out=dispatch_frozen.run(**self.k);self.assertEqual(out['status_operations'],self.p['remaining_status_operations']);self.assertTrue(out['verify_admission'](self.p['admission']))
 def test_drift_blocks_before_effects(self):
  self.k['prefreeze']=copy.deepcopy(self.p);self.k['prefreeze']['news'][0]['text']='altered'
  with self.assertRaises(dispatch_frozen.Error):dispatch_frozen.run(**self.k)
 def test_unreviewed_or_budget_invalid_blocks(self):
  self.k['verify_contract']=lambda b:False
  with self.assertRaises(dispatch_frozen.Error):dispatch_frozen.run(**self.k)
  self.k['verify_contract']=lambda b:True;self.t.a.s['source_attempts']=27
  with self.assertRaises(dispatch_frozen.Error):dispatch_frozen.run(**self.k)
if __name__=='__main__':unittest.main()
