import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import model_accounting as m

CONFIG=m.ROOT/'model-successor-ledger-contract-20261029.json'
class Tests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name).resolve();self.claim=self.root/'claim';self.p=patch.object(m,'CLAIM',self.claim);self.p.start();self.handles=[]
 def tearDown(self):
  for h in self.handles:h.close()
  self.p.stop();self.tmp.cleanup()
 def create(self):
  h=m.create_successor(successor_root=str(self.root/'ledger'),claim_path=str(self.claim),ledger_contract_path=str(CONFIG));self.handles.append(h);return h
 def contract(self):
  protocol=self.root/'protocol.py';runner=self.root/'runner.py';contract=self.root/'model.json';protocol.write_bytes(b'# protocol');runner.write_bytes(b'# runner')
  binding={'parent_db_sha256':m.PARENT_DB_SHA,'parent_summary_sha256':m.SUMMARY_SHA,'source_manifest_sha256':m.SOURCE_MANIFEST_SHA,'ledger_contract_sha256':m.CONFIG_SHA,'cohort_manifest_sha256':m.COHORT_SHA,'protocol_sha256':m.digest(protocol.read_bytes()),'runner_sha256':m.digest(runner.read_bytes())}
  caps={'total_usd_micro':40000000,'total_generation_attempts':835,'total_count_attempts':767,'total_source_attempts':18,'slots':32}
  contract.write_bytes(m.canonical({'schema':'faithful-model-successor-contract-v1','status':'frozen','bindings':binding,'caps':caps}))
  return protocol,runner,contract
 def activate(self,h):
  p,r,c=self.contract();h.activate(contract_path=str(c),contract_sha256=m.digest(c.read_bytes()),protocol_path=str(p),runner_path=str(r),verify_challenge=lambda raw:True);return p,r,c
 def test_parent_readonly_and_precise_accounting(self):
  path=m.ROOT/'live-source-ledger-20261029-02/ledger.sqlite3';before=m.digest(path.read_bytes());x=m.inspect_parent()
  self.assertEqual((x['prior_micro'],x['prior_generations'],x['prior_counts'],x['prior_sources'],x['uncertain_current_effects']),(797567,95,27,8,0))
  self.assertEqual(m.digest(path.read_bytes()),before)
 def test_source_receipts_preserved_no_new_source(self):
  h=self.create();self.assertEqual(h.summary()['exposure_micro'],797567);self.assertEqual(h.summary()['source_attempts'],8)
  self.assertEqual(h.receipt('source:case-01:serper')['response_hash'],m.source_bridge.OLD_RESPONSE_SHA)
  self.assertEqual(len(h.verify_source_binding()['records']),8)
  for fn in (h.source,h.metadata):
   with self.assertRaises(m.AdmissionError):fn()
 def test_activation_gates_and_includes_prior_usage(self):
  h=self.create();called=[]
  with self.assertRaises(m.AdmissionError):h.count('c',{},lambda *a:called.append(1))
  self.activate(h)
  req={'contents':[{'parts':[{'text':'hello'}]}],'generationConfig':{'maxOutputTokens':4096}}
  def fake(provider,endpoint,body):
   called.append(1)
   if endpoint=='countTokens':return 200,b'{"totalTokens":100}'
   return 200,b'{"modelVersion":"gemini-3.8-flash","usageMetadata":{"promptTokenCount":100,"totalTokenCount":150}}'
  h.count('c',req,fake);h.generate('g',req,'c',fake)
  self.assertEqual(h.summary()['exposure_micro'],797567+525);self.assertEqual(h.summary()['generation_attempts'],96);self.assertEqual(h.summary()['count_attempts'],28)
 def test_claim_is_unique_and_bound(self):
  h=self.create()
  with self.assertRaises((FileExistsError,m.AdmissionError)):m.create_successor(successor_root=str(self.root/'other'),claim_path=str(self.claim),ledger_contract_path=str(CONFIG))
  self.claim.write_bytes(b'changed')
  with self.assertRaises(m.AdmissionError):h.verify_parent()
 def test_reject_unverified_challenge_before_marker(self):
  h=self.create();p,r,c=self.contract()
  with self.assertRaises(m.AdmissionError):h.activate(contract_path=str(c),contract_sha256=m.digest(c.read_bytes()),protocol_path=str(p),runner_path=str(r),verify_challenge=lambda raw:False)
  self.assertFalse(h.db.execute("select 1 from run_events where event='model_successor_started'").fetchone())
 def test_code_drift_stops_before_dispatch(self):
  h=self.create();p,r,c=self.activate(h);p.write_bytes(b'changed');calls=[]
  with self.assertRaises(m.AdmissionError):h.count('c',{},lambda *a:calls.append(1))
  self.assertFalse(calls);self.assertEqual(h.summary()['stopped'],1)
 def test_wrong_parent_or_summary_rejected_before_claim(self):
  with patch.object(m,'SUMMARY_SHA','a'*64):
   with self.assertRaises(m.AdmissionError):self.create()
  self.assertFalse(self.claim.exists())
 def test_no_uncertain_model_effect_retried(self):
  h=self.create();self.activate(h);calls=[]
  def timeout(*a):calls.append(1);raise TimeoutError()
  with self.assertRaises(StopAlias):h.count('c',{},timeout)
  self.assertEqual(h.summary()['stopped'],1)
  with self.assertRaises(StopAlias):h.count('c',{},timeout)
  self.assertEqual(calls,[1])
 def test_activation_is_one_shot(self):
  h=self.create();p,r,c=self.activate(h)
  with self.assertRaises(m.AdmissionError):h.activate(contract_path=str(c),contract_sha256=m.digest(c.read_bytes()),protocol_path=str(p),runner_path=str(r),verify_challenge=lambda raw:True)
 def test_global_cap_denies_generation_before_effect(self):
  h=self.create();self.activate(h)
  h.db.execute('UPDATE run SET exposure_micro=39999999')
  calls=[]
  req={'contents':[{'parts':[{'text':'hello'}]}],'generationConfig':{'maxOutputTokens':4096}}
  def fake(provider,endpoint,body):calls.append(endpoint);return 200,b'{"totalTokens":100}'
  h.count('c',req,fake)
  with self.assertRaises(StopAlias):h.generate('g',req,'c',fake)
  self.assertEqual(calls,['countTokens'])
StopAlias=m.Stop
if __name__=='__main__':unittest.main()
