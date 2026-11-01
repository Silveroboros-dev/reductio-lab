import tempfile
from pathlib import Path
import types
import unittest
from unittest import mock
import you_phase as s

class FakeLedger:
 def __init__(self,bad=False):self.calls=[];self.bad=bad;self.stopped=0;self.closed=False;self.row=None
 def summary(self):return {'stopped':self.stopped,'exposure_micro':1234590,'generation_attempts':200,'count_attempts':132,'source_attempts':12+len(self.calls)}
 def source(self,op,provider,endpoint,raw,ticket,transport):
  self.calls.append(op)
  if not self.verifier(ticket,raw):raise ValueError('ticket')
  response=s.canonical({'success':not self.bad,'data':{'results':[]},'priceCents':0.5})
  self.row={'http_status':200,'state':'succeeded','actual_micro':5000,'response_hash':s.sha(response),'started_at_utc':'start','completed_at_utc':'end'}
  return response
 def receipt(self,op):return self.row
 def stop(self,reason):self.stopped=1
 def close(self):self.closed=True

class Tests(unittest.TestCase):
 def test_frozen_request_and_prior(self):
  a=s.obj(s.read(s.ROOT/'forecast-source-you-addendum-20261029-v1.json'))
  self.assertEqual(a['operation']['payload'],s.PAYLOAD);self.assertEqual(a['operation']['ui_expected_micro'],5000)
  self.assertEqual(a['prior_state']['source_attempts_total'],12);self.assertEqual(a['caps']['total_source_attempts'],28)
  raw,expiry=s.quote();self.assertEqual(a['operation']['ticket']['evidence_sha256'],s.sha(raw))
  self.assertEqual(a['operation']['ticket']['expires_utc'],expiry)
 def fixture(self,bad=False):
  with tempfile.TemporaryDirectory(dir='/private/tmp') as td:
   path=Path(td).resolve(); ledger=FakeLedger(bad)
   a=s.obj(s.read(s.ROOT/'forecast-source-you-addendum-20261029-v1.json'))
   a['execution_context']={'output_root':str(path/'out'),'ledger_root':str(path/'ledger'),'claim_path':str(path/'claim')}
   def reopen(**kw):
    self.assertTrue(kw['verify_challenge'](s.read(s.ROOT/'forecast-source-run-contract-20261029-v1.json')))
    ledger.verifier=kw['verify_ticket'];return ledger
   fake_ledger=types.SimpleNamespace(CLAIM=path/'claim',reopen_successor=reopen)
   fake_hist=types.SimpleNamespace(verify=lambda **_:a['source_parent'])
   fake_transport=types.SimpleNamespace(OneShotTransport=lambda *_:lambda *_:None)
   with mock.patch.object(s,'verify',return_value=(a,b'addendum',b'challenge',b'receipt')):
    with mock.patch.dict('sys.modules',{'forecast_ledger':fake_ledger,'historical':fake_hist,'oneshot':fake_transport}):
     result=s.execute(path/'addendum',path/'challenge',path/'receipt','hash')
   self.assertTrue(ledger.closed);self.assertTrue((path/'out/summary.json').is_file())
   return result,ledger.calls
 def test_single_fake_call_success(self):
  result,calls=self.fixture();self.assertEqual(calls,[s.OP]);self.assertEqual(result['status'],'completed');self.assertEqual(result['record']['actual_micro'],5000)
 def test_semantic_failure_stops(self):
  result,calls=self.fixture(True);self.assertEqual(calls,[s.OP]);self.assertEqual(result['status'],'stopped');self.assertEqual(result['ledger']['stopped'],1)

if __name__=='__main__':unittest.main()
