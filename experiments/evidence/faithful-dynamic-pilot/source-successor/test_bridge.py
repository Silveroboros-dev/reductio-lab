import json
import shutil
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import bridge

ROOT=bridge.ROOT
DB=ROOT/'live-source-ledger-20261029-01/ledger.sqlite3'
CONTRACT=ROOT/'live-source-capture-contract-frozen-v3.json'
STARTED=ROOT/'live-source-capture-20261029-01/started.json'
STOPPED=ROOT/'live-source-capture-20261029-01/case-01-stopped.json'
CONFIG=ROOT/'live-ledger-successor-contract-20261029.json'

def inputs(db=DB): return tuple(map(str,(db,CONTRACT,STARTED,STOPPED)))
def capture_requests():
 rows=json.loads(CONTRACT.read_bytes())['source_requests']
 return {f"source:{r['case_id']}:serper":bridge.canonical({'api':'serper','path':'/news','body':r['body'],'query':{}}) for r in rows}
def quote(request): return {'provider':'orthogonal','endpoint':'/v1/run','request_sha256':bridge.digest(request),'max_micro':250000,'evidence_sha256':bridge.NEW_QUOTE_SHA,'expires_utc':'2099-01-01T00:00:00Z'}
def ok(*args): return 200,b'{"success":true,"priceCents":0.2,"data":{"news":[]}}'

class BridgeTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name).resolve();self.claim=self.root/'singleton.json';self.patch=patch.object(bridge,'CLAIM_PATH',self.claim);self.patch.start();self.ledgers=[]
 def tearDown(self):
  for l in self.ledgers:l.close()
  self.patch.stop();self.tmp.cleanup()
 def create(self,**kwargs):
  l=bridge.create_successor(*inputs(),successor_root=str(kwargs.get('root',self.root/'successor')),claim_path=str(kwargs.get('claim',self.claim)),ledger_contract_path=str(CONFIG));self.ledgers.append(l);return l
 def test_exact_predecessor_carry_and_full_raw_receipt(self):
  before=bridge.digest(DB.read_bytes());l=self.create();s=l.verify_predecessor();r=l.receipt(bridge.OLD_SOURCE_ID)
  self.assertEqual((s['previous_exposure_micro'],s['previous_source_actual_micro'],s['previous_source_news_count']),(723593,2000,10))
  self.assertEqual(bridge.digest(r['response']),bridge.OLD_RESPONSE_SHA)
  self.assertEqual(len(json.loads(r['response'])['data']['news']),10)
  self.assertEqual(l.summary()['source_attempts'],1);self.assertEqual(l.summary()['exposure_micro'],723593)
  self.assertEqual(l._contract['source_cap_micro'],4998000);self.assertEqual(l._contract['max_sources'],17)
  self.assertEqual(bridge.digest(DB.read_bytes()),before)
 def test_only_correct_seven_in_predeclared_order_no_repetition(self):
  l=self.create();reqs=capture_requests();calls=[]
  def transport(*a):calls.append(a);return ok()
  def submit(op,body=None,q=None):return l.source(op,'orthogonal','/v1/run',reqs[op] if body is None else body,quote(reqs[op]) if q is None else q,transport)
  with self.assertRaises(bridge.BridgeError):submit(bridge.OLD_SOURCE_ID)
  with self.assertRaises(bridge.BridgeError):submit('source:case-03:serper')
  with self.assertRaises(bridge.BridgeError):submit('source:case-02:serper',body=reqs['source:case-03:serper'])
  self.assertFalse(calls)
  ids=l.verify_predecessor()['remaining_source_ids']
  for op in ids:submit(op)
  self.assertEqual(len(calls),7);self.assertEqual(l.summary()['source_attempts'],8)
  self.assertEqual(l.summary()['exposure_micro'],723593+7*2000)
  with self.assertRaises(bridge.BridgeError):submit(ids[0])
  with self.assertRaises(bridge.BridgeError):l.generate('x',{},'c',transport)
 def test_wrong_provider_quote_or_evidence_denied(self):
  l=self.create();p=capture_requests()['source:case-02:serper'];seen=[];q=quote(p)
  for changes in ({'evidence_sha256':'c'*64},{'max_micro':2000}):
   bad=dict(q,**changes)
   with self.assertRaises(bridge.BridgeError):l.source('source:case-02:serper','orthogonal','/v1/run',p,bad,lambda *a:seen.append(1))
  with self.assertRaises(bridge.BridgeError):l.source('source:case-02:serper','bad','/v1/run',p,q,lambda *a:seen.append(1))
  self.assertFalse(seen)
 def test_fixed_singleton_and_claim_tamper(self):
  l=self.create()
  with self.assertRaises((FileExistsError,bridge.BridgeError)):
   bridge.create_successor(*inputs(),successor_root=str(self.root/'second'),claim_path=str(self.claim),ledger_contract_path=str(CONFIG))
  with self.assertRaises(bridge.BridgeError):
   bridge.create_successor(*inputs(),successor_root=str(self.root/'third'),claim_path=str(self.root/'other'),ledger_contract_path=str(CONFIG))
  self.claim.write_text('changed')
  with self.assertRaises(bridge.BridgeError):l.verify_predecessor()
 def test_previous_db_tampering_blocked_even_with_recomputed_outer_hash(self):
  target=self.root/'copy';target.mkdir();p=target/'ledger.sqlite3';shutil.copyfile(DB,p);shutil.copyfile(DB.parent/'owner.lock',target/'owner.lock')
  d=sqlite3.connect(p);d.execute("UPDATE run SET exposure_micro=723594");d.commit();d.close()
  with patch.object(bridge,'OLD_DB_SHA',bridge.digest(p.read_bytes())):
   with self.assertRaises(bridge.BridgeError):bridge.inspect_predecessor(*inputs(p),bridge.OLD_DB_SHA)
 def test_changed_stop_and_effect_blocked_even_with_recomputed_outer_hash(self):
  target=self.root/'copy';target.mkdir();p=target/'ledger.sqlite3';shutil.copyfile(DB,p);shutil.copyfile(DB.parent/'owner.lock',target/'owner.lock')
  d=sqlite3.connect(p);d.execute("DELETE FROM run_events WHERE event='stopped'");d.commit();d.close()
  with patch.object(bridge,'OLD_DB_SHA',bridge.digest(p.read_bytes())):
   with self.assertRaises(bridge.BridgeError):bridge.inspect_predecessor(*inputs(p),bridge.OLD_DB_SHA)
  shutil.copyfile(DB,p);d=sqlite3.connect(p);d.execute("UPDATE effects SET id='source:case-02:serper'");d.commit();d.close()
  with patch.object(bridge,'OLD_DB_SHA',bridge.digest(p.read_bytes())):
   with self.assertRaises(bridge.BridgeError):bridge.inspect_predecessor(*inputs(p),bridge.OLD_DB_SHA)
 def test_successor_contract_drift_rejected_before_claim(self):
  p=self.root/'config.json';p.write_text('{}')
  with self.assertRaises(bridge.BridgeError):bridge.create_successor(*inputs(),successor_root=str(self.root/'new'),claim_path=str(self.claim),ledger_contract_path=str(p))
  self.assertFalse(self.claim.exists())
 def test_uncertain_source_stops_no_retry(self):
  l=self.create();p=capture_requests()['source:case-02:serper'];calls=[]
  def timeout(*a):calls.append(1);raise TimeoutError()
  with self.assertRaises(bridge.Stop):l.source('source:case-02:serper','orthogonal','/v1/run',p,quote(p),timeout)
  self.assertEqual(l.receipt('source:case-02:serper')['state'],'uncertain')
  self.assertEqual(l.summary()['exposure_micro'],723593+250000)
  with self.assertRaises(bridge.Stop):l.source('source:case-02:serper','orthogonal','/v1/run',p,quote(p),timeout)
  self.assertEqual(calls,[1])
 def test_count_tokens_and_metadata_denied_without_effect(self):
  l=self.create()
  for fn in (l.count,l.generate,l.metadata):
   with self.assertRaises(bridge.BridgeError):fn()
  self.assertEqual(l.summary()['generation_attempts'],79);self.assertEqual(l.summary()['count_attempts'],11)
if __name__=='__main__':unittest.main()
