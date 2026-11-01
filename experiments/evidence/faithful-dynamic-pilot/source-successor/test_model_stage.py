import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import bridge
import model_stage as stage
from test_bridge import inputs, CONFIG, capture_requests, quote, ok

class Tests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name).resolve();self.claim=self.root/'claim';self.patch=patch.object(bridge,'CLAIM_PATH',self.claim);self.patch.start()
  self.phase=bridge.create_successor(*inputs(),successor_root=str(self.root/'successor'),claim_path=str(self.claim),ledger_contract_path=str(CONFIG))
  self.source_contract='f'*64;self.summary=self.root/'summary.json';self.dataset=self.root/'manifest.json';self.runner=self.root/'runner.py';self.sources=self.root/'sources.json';self.contract=self.root/'model-contract.json'
  self.dataset.write_bytes(b'{"cases":[]}');self.runner.write_bytes(b'# synthetic runner')
 def tearDown(self):self.phase.close();self.patch.stop();self.tmp.cleanup()
 def complete_sources(self):
  self.phase.db.execute("INSERT INTO run_events(event,reason,at_utc) VALUES ('source_continuation_started',?,'fixture')",(self.source_contract,))
  reqs=capture_requests()
  for op in self.phase.verify_predecessor()['remaining_source_ids']:
   self.phase.source(op,'orthogonal','/v1/run',reqs[op],quote(reqs[op]),ok)
  self.summary.write_bytes(bridge.canonical({'status':'completed','source_count':7,'ledger':self.phase.summary()}))
  self.phase.db.execute("INSERT INTO run_events(event,reason,at_utc) VALUES ('source_continuation_complete',?,'fixture')",(bridge.digest(self.summary.read_bytes()),))
 def write_contract(self):
  source_bytes=stage.prepare_binding(self.phase,str(self.summary),self.source_contract);self.sources.write_bytes(source_bytes)
  binding={'predecessor_db_sha256':bridge.OLD_DB_SHA,'source_continuation_contract_sha256':self.source_contract,
    'source_continuation_summary_sha256':bridge.digest(self.summary.read_bytes()),'source_receipt_manifest_sha256':bridge.digest(source_bytes),
    'successor_ledger_contract_sha256':bridge.SUCCESSOR_LEDGER_CONTRACT_FILE_SHA,'dataset_manifest_sha256':bridge.digest(self.dataset.read_bytes()),
    'runner_sha256':bridge.digest(self.runner.read_bytes())}
  caps={'total_usd_micro':40000000,'total_generation_attempts':835,'total_count_attempts':767,'total_source_attempts':18}
  self.contract.write_bytes(bridge.canonical({'schema':'faithful-model-stage-contract-v1','status':'frozen','bindings':binding,'caps':caps}))
 def activate(self,verifier=lambda *a:True):
  return stage.activate_model_stage(self.phase,summary_path=str(self.summary),source_contract_sha256=self.source_contract,
    source_manifest_path=str(self.sources),dataset_manifest_path=str(self.dataset),runner_path=str(self.runner),
    model_contract_path=str(self.contract),expected_model_contract_sha256=bridge.digest(self.contract.read_bytes()),verify_challenge=verifier)
 def test_needs_all_seven_and_summary_event_before_activation(self):
  with self.assertRaises(stage.ModelStageError):stage.prepare_binding(self.phase,str(self.summary),self.source_contract)
  self.assertEqual(self.phase.summary()['source_attempts'],1)
 def test_activation_and_model_use_same_ledger_without_new_sources(self):
  self.complete_sources();self.write_contract();l=self.activate()
  req={'contents':[{'parts':[{'text':'hello'}]}],'generationConfig':{'maxOutputTokens':4096}}
  def t(provider,endpoint,body):
   if endpoint=='countTokens':return 200,b'{"totalTokens":100}'
   return 200,b'{"modelVersion":"gemini-3.8-flash","usageMetadata":{"promptTokenCount":100,"totalTokenCount":150,"thoughtsTokenCount":40}}'
  l.count('c',req,t);l.generate('g',req,'c',t)
  self.assertEqual(l.summary()['exposure_micro'],723593+7*2000+525)
  self.assertEqual(l.summary()['source_attempts'],8)
  self.assertEqual(l.verify_source_binding()['source_attempts_total'],8)
  self.assertEqual(l.receipt(bridge.OLD_SOURCE_ID)['response_hash'],bridge.OLD_RESPONSE_SHA)
  with self.assertRaises(stage.ModelStageError):l.source()
  with self.assertRaises(stage.ModelStageError):l.metadata()
  with self.assertRaises(stage.ModelStageError):self.activate()
 def test_challenge_rejection_does_not_activate(self):
  self.complete_sources();self.write_contract()
  with self.assertRaises(stage.ModelStageError):self.activate(lambda *a:False)
  self.assertFalse(self.phase.db.execute("SELECT 1 FROM run_events WHERE event='model_stage_started'").fetchone())
 def test_dataset_drift_stops_before_transport(self):
  self.complete_sources();self.write_contract();l=self.activate();self.dataset.write_bytes(b'changed');called=[]
  with self.assertRaises(stage.ModelStageError):l.count('c',{},lambda *a:called.append(1))
  self.assertFalse(called);self.assertEqual(l.summary()['stopped'],1)
 def test_source_receipt_corruption_rejected_before_activation(self):
  self.complete_sources();self.phase.db.execute("UPDATE effects SET response=? WHERE id='source:case-03:serper'",(b'{}',))
  with self.assertRaises(stage.ModelStageError):stage.prepare_binding(self.phase,str(self.summary),self.source_contract)
 def test_unfinished_or_changed_summary_rejected(self):
  self.complete_sources();self.summary.write_bytes(b'{}')
  with self.assertRaises(stage.ModelStageError):stage.prepare_binding(self.phase,str(self.summary),self.source_contract)
 def test_aggregate_counter_drift_blocked_even_if_summary_forged(self):
  self.complete_sources();self.phase.db.execute('UPDATE run SET exposure_micro=exposure_micro-1000')
  self.summary.write_bytes(bridge.canonical({'status':'completed','source_count':7,'ledger':self.phase.summary()}))
  self.phase.db.execute("UPDATE run_events SET reason=? WHERE event='source_continuation_complete'",(bridge.digest(self.summary.read_bytes()),))
  with self.assertRaises(stage.ModelStageError):stage.prepare_binding(self.phase,str(self.summary),self.source_contract)
 def test_missing_source_event_blocks_even_if_effect_succeeded(self):
  self.complete_sources();self.phase.db.execute("DELETE FROM events WHERE effect_id='source:case-03:serper' AND state='accounted'")
  with self.assertRaises(stage.ModelStageError):stage.prepare_binding(self.phase,str(self.summary),self.source_contract)
 def test_in_memory_ledger_contract_drift_blocks_binding(self):
  self.complete_sources();self.phase._contract['cap_micro']=100000000
  with self.assertRaises(stage.ModelStageError):stage.prepare_binding(self.phase,str(self.summary),self.source_contract)
if __name__=='__main__':unittest.main()
