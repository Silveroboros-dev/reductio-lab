import datetime as dt,json,os,tempfile,types,unittest
from pathlib import Path
from unittest import mock
import market_lookup as m

class Ledger:
 def __init__(self,fee):self.calls=[];self.fee=fee;self.closed=False;self.stopped=0;self.row=None
 def summary(self):return {'stopped':self.stopped,'exposure_micro':1250000,'generation_attempts':205,'count_attempts':137,'source_attempts':13}
 def source(self,op,provider,endpoint,raw,ticket,transport):
  self.calls.append(op)
  if not self.check(ticket,raw):raise ValueError('ticket')
  response=m.canonical({'success':True,'priceCents':self.fee/10000,'data':{'markets':[]}})
  self.row={'http_status':200,'state':'succeeded','actual_micro':self.fee,'response_hash':m.sha(response),'started_at_utc':'start','completed_at_utc':'end'}
  return response
 def receipt(self,op):return self.row
 def stop(self,reason):self.stopped=1
 def close(self):self.closed=True

class Tests(unittest.TestCase):
 def test_payload_and_fresh_quote(self):
  self.assertEqual(m.PAYLOAD['api'],'kalshi')
  self.assertEqual(m.PAYLOAD['query']['limit'],4)
  self.assertEqual(m.PAYLOAD['query']['tickers'].split(','),['KXIPO-26-ANTHROPIC','KXWTI-26NOV03-T97.99','KXGPT-ASTRA61-26NOV13','KXCPI-26OCT-T0.2'])
  with tempfile.TemporaryDirectory(dir='/private/tmp') as t:
   p=Path(t).resolve()/'quote.json'
   q={'schema':'forecast-source-ui-observation-v1','api':'kalshi','path':'/markets','method':'POST','provider_method':'GET','rate_usd':'Free',
    'endpoint_url':'https://www.orthogonal.com/discover/kalshi/26336e71-0806-4771-b1e0-2913fcd8cf03',
    'observed_at_utc':dt.datetime.now(dt.timezone.utc).isoformat()}
   p.write_text(json.dumps(q));self.assertTrue(m.quote(p)[0])
   q['observed_at_utc']='2000-01-01T00:00:00+00:00';p.write_text(json.dumps(q))
   with self.assertRaises(m.Error):m.quote(p)
 def run_fixture(self,fee):
  with tempfile.TemporaryDirectory(dir='/private/tmp') as t:
   root=Path(t).resolve();ledger=Ledger(fee);parent={'fake':'predecessor'}
   ticket={'test':'ticket'};a={'execution_context':{'output_root':str(root/'out'),'ledger_root':str(root/'ledger'),'claim_path':str(root/'claim')},
    'starting_usage':ledger.summary(),'seed_parent':parent,'operation':{'ticket':ticket}}
   fake_history=types.SimpleNamespace(verify=lambda:parent)
   def reopen(**kwargs):
    self.assertTrue(kwargs['verify_challenge'](m.read(m.ROOT/'forecast-source-run-contract-20261029-v1.json')))
    ledger.check=kwargs['verify_ticket'];return ledger
   fake_ledger=types.SimpleNamespace(CLAIM=root/'claim',reopen_successor=reopen)
   fake_transport=types.SimpleNamespace(OneShotTransport=lambda *_:lambda *_:None)
   with mock.patch.object(m,'verify',return_value=(a,b'addendum',b'challenge',b'receipt')):
    with mock.patch.dict('sys.modules',{'historical_seed':fake_history,'forecast_ledger':fake_ledger,'oneshot':fake_transport}):
     result=m.execute(root/'addendum',root/'challenge',root/'receipt','hash')
   self.assertTrue(ledger.closed);self.assertTrue((root/'out/summary.json').is_file())
   return result,ledger.calls
 def test_one_free_call(self):
  result,calls=self.run_fixture(0);self.assertEqual(calls,[m.OP]);self.assertEqual(result['status'],'completed')
 def test_unexpected_charge_stops_without_retry(self):
  result,calls=self.run_fixture(5000);self.assertEqual(calls,[m.OP]);self.assertEqual(result['status'],'stopped')
 def test_incomplete_seed_cannot_freeze(self):
  with tempfile.TemporaryDirectory(dir='/private/tmp') as t:
   target=Path(t).resolve()/'addendum.json'; previous=os.getcwd()
   def not_ready():raise m.Error('seed not complete')
   try:
    os.chdir(m.ROOT)
    with mock.patch.dict('sys.modules',{'historical_seed':types.SimpleNamespace(verify=not_ready)}):
     with self.assertRaises(m.Error):m.prepare_addendum(target,target.parent/'quote.json')
   finally:os.chdir(previous)
   self.assertFalse(target.exists())

if __name__=='__main__':unittest.main()
