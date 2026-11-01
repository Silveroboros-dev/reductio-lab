import json
import tempfile
from pathlib import Path
import types
import unittest
from unittest import mock
import seed_phase as s

class MockLedger:
 def __init__(self,events,fail_at=None):self.events=events;self.fail_at=fail_at;self.rows={};self.stopped=0;self.closed=False
 def source(self,op,provider,endpoint,raw,ticket,transport):
  self.events.append(op)
  if not self.verify_ticket(ticket,raw):raise ValueError('ticket')
  result={'success':op!=self.fail_at,'priceCents': 0.2 if ticket['category'] in ('search','news') and b'serper' in raw else 1.0,'data':{'ok':True}}
  data=s.canonical(result);self.rows[op]={'http_status':200,'state':'succeeded','actual_micro':int(result['priceCents']*10000),'response_hash':s.sha(data),'started_at_utc':'start','completed_at_utc':'end'}
  return data
 def receipt(self,op):return self.rows[op]
 def summary(self):return {'stopped':self.stopped,'source_attempts':8+len(self.events)}
 def stop(self,reason):self.stopped=1
 def close(self):self.closed=True

class TestSeed(unittest.TestCase):
 def test_contract_exact_and_quote_binding(self):
  c=s.obj(s.read(s.ROOT/'forecast-source-run-contract-20261029-v1.json'))
  self.assertEqual(len(c['source_phase']['requests']),4)
  self.assertEqual([r['id'] for r in c['source_phase']['requests']],[op[0] for op in s.OPS])
  ui,expiry=s._ui();self.assertEqual(s.sha(ui),c['source_phase']['ui_sha256'])
  self.assertTrue(all(r['ticket']['expires_utc']==expiry for r in c['source_phase']['requests']))
  self.assertEqual(c['caps']['total_usd_micro'],60000000)

 def run_fixture(self,fail_at=None):
  with tempfile.TemporaryDirectory(dir='/private/tmp') as td:
   path=Path(td).resolve();events=[]; ledger=MockLedger(events,fail_at)
   c=s.obj(s.read(s.ROOT/'forecast-source-run-contract-20261029-v1.json'))
   c['execution_context']={'output_root':str(path/'out'),'ledger_root':str(path/'ledger'),'claim_path':str(path/'claim')}
   def create(**kwargs):
    self.assertTrue(kwargs['verify_challenge'](b'contract'))
    ledger.verify_ticket=kwargs['verify_ticket'];return ledger
   fake_ledger=types.SimpleNamespace(CLAIM=path/'claim',create_successor=create)
   fake_transport=types.SimpleNamespace(OneShotTransport=lambda *_:lambda *_:None)
   with mock.patch.object(s,'verify',return_value=(c,b'contract',b'challenge',b'receipt')):
    with mock.patch.dict('sys.modules',{'forecast_ledger':fake_ledger,'oneshot':fake_transport}):
     outcome=s.execute(path/'contract',path/'challenge',path/'receipt','hash')
   self.assertTrue(ledger.closed)
   self.assertTrue((path/'out/summary.json').is_file())
   return outcome,events

 def test_fake_transport_four_operations(self):
  outcome,events=self.run_fixture()
  self.assertEqual(outcome['status'],'completed')
  self.assertEqual(events,[x[0] for x in s.OPS]);self.assertEqual(len(outcome['settled_records']),4)
  self.assertEqual(sum(x['actual_micro'] for x in outcome['settled_records']),24000)

 def test_fake_semantic_failure_stops_without_retry(self):
  outcome,events=self.run_fixture('seed-openai-search')
  self.assertEqual(outcome['status'],'stopped');self.assertEqual(len(events),3)
  self.assertEqual(outcome['not_attempted'],1)
  self.assertEqual(outcome['ledger']['stopped'],1)

if __name__=='__main__':unittest.main()
