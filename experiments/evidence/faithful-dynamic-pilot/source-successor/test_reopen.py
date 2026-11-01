import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import bridge
import reopen
from test_bridge import inputs,CONFIG,capture_requests,quote,ok

class Tests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name).resolve();self.claim=self.root/'claim';self.patch=patch.object(bridge,'CLAIM_PATH',self.claim);self.patch.start()
  self.out=self.root/'ledger';self.contract='f'*64;self.summary=self.root/'summary.json'
  p=bridge.create_successor(*inputs(),successor_root=str(self.out),claim_path=str(self.claim),ledger_contract_path=str(CONFIG))
  p.db.execute("INSERT INTO run_events(event,reason,at_utc) VALUES ('source_continuation_started',?,'fixture')",(self.contract,))
  reqs=capture_requests()
  for op in p.verify_predecessor()['remaining_source_ids']:p.source(op,'orthogonal','/v1/run',reqs[op],quote(reqs[op]),ok)
  self.summary.write_bytes(bridge.canonical({'status':'completed','source_count':7,'ledger':p.summary()}))
  p.db.execute("INSERT INTO run_events(event,reason,at_utc) VALUES ('source_continuation_complete',?,'fixture')",(bridge.digest(self.summary.read_bytes()),))
  p.close()
 def tearDown(self):self.patch.stop();self.tmp.cleanup()
 def open_ro(self):return reopen.open_completed_readonly(str(self.out),summary_path=str(self.summary),source_contract_sha256=self.contract)
 def test_readonly_open_preserves_db_and_blocks_mutation(self):
  db=self.out/'ledger.sqlite3';before=bridge.digest(db.read_bytes());p,manifest,h=self.open_ro()
  try:
   self.assertEqual(h,before);self.assertEqual(p.summary()['source_attempts'],8)
   with self.assertRaises(sqlite3.OperationalError):p.db.execute('UPDATE run SET stopped=1')
  finally:p.close()
  self.assertEqual(bridge.digest(db.read_bytes()),before)
 def test_writable_reopen_requires_existing_claim_and_preserves_receipts(self):
  p=reopen.reopen_completed_successor(str(self.out),summary_path=str(self.summary),source_contract_sha256=self.contract)
  try:
   self.assertEqual(p.summary()['source_attempts'],8)
   self.assertEqual(p.receipt(bridge.OLD_SOURCE_ID)['response_hash'],bridge.OLD_RESPONSE_SHA)
   with self.assertRaises(bridge.BridgeError):p.generate()
  finally:p.close()
 def test_already_started_model_cannot_reopen(self):
  d=sqlite3.connect(self.out/'ledger.sqlite3');d.execute("INSERT INTO run_events(event,reason,at_utc) VALUES ('model_stage_started','x','fixture')");d.commit();d.close()
  with self.assertRaises(reopen.ReopenError):self.open_ro()
 def test_claim_and_summary_tamper_fail(self):
  self.claim.write_text('{}')
  with self.assertRaises(reopen.ReopenError):self.open_ro()
 def test_active_ledger_blocks_second_open(self):
  p=reopen.reopen_completed_successor(str(self.out),summary_path=str(self.summary),source_contract_sha256=self.contract)
  try:
   with self.assertRaises(reopen.ReopenError):self.open_ro()
  finally:p.close()
if __name__=='__main__':unittest.main()
