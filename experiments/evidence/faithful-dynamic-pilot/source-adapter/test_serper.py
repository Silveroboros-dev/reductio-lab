import copy
import datetime as dt
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'budget-v2'))
from ledger import Ledger, Stop, UnknownEffect
from test_ledger import contract
from serper import AdmissionError, EvidenceError, bind_quote, build_request, canonical, details_request, execute, sha

NOW=dt.datetime.now(dt.timezone.utc)

def sample_capture(price=0.002, dynamic=False, array=True):
 endpoint={'path':'/news','method':'POST','isPayable':True,'price':price}
 if dynamic is not None: endpoint['hasDynamicPricing']=dynamic
 obj={'success':True,'api':{'slug':'serper'},'endpoint':endpoint}
 if array: obj['endpoints']=[endpoint.copy()]
 raw=json.dumps(obj,separators=(',',':')).encode()
 return {'provider':'orthogonal','endpoint':'/v1/details','request':details_request(),'response':raw,
         'response_sha256':sha(raw),'http_status':200,
         'started_at_utc':(NOW-dt.timedelta(seconds=4)).isoformat(),
         'completed_at_utc':(NOW-dt.timedelta(seconds=2)).isoformat()}

def alter(c, change):
 d=json.loads(c['response']); change(d); c['response']=json.dumps(d,separators=(',',':')).encode();c['response_sha256']=sha(c['response']);return c

class AdmissionTests(unittest.TestCase):
 def setUp(self): self.request=build_request('Federal Reserve latest decision',3);self.c=sample_capture()
 def q(self,c=None,request=None): return bind_quote(request or self.request,c or self.c,now=NOW)
 def test_numeric_actual_style_fixed(self):
  q=self.q(); self.assertEqual(q['max_micro'],2000);self.assertEqual(q['request_sha256'],sha(self.request)); self.assertEqual(q['evidence_sha256'],sha(self.c['response']))
 def test_documented_dollar_string_no_dynamic_flag(self):
  self.assertEqual(self.q(sample_capture('$0.0025',None,False))['max_micro'],2500)
 def test_dynamic_unknown_price_or_wrong_units_block(self):
  for p,d in [('dynamic',None),('$0.002',True),(0.002,None),('$0.0000001',None),(True,False),('$0.3',None)]:
   with self.subTest(p=p,d=d), self.assertRaises(AdmissionError): self.q(sample_capture(p,d))
  c=alter(sample_capture(),lambda d:d['endpoint'].update(pricingUnit='per_result'))
  with self.assertRaises(AdmissionError):self.q(c)
 def test_wrong_api_path_method_and_inconsistent_list_block(self):
  for mutate in [lambda d:d['api'].update(slug='linkup'),lambda d:d['endpoint'].update(path='/search'),lambda d:d['endpoint'].update(method='GET'),lambda d:d.update(endpoints=[])]:
   c=alter(sample_capture(),mutate)
   with self.assertRaises(AdmissionError): self.q(c)
 def test_stale_future_and_wrong_capture_binding_block(self):
  for changes in [{'provider':'wrong'},{'endpoint':'/v1/run'},{'request':b'{}'},{'http_status':429},{'response_sha256':'0'*64},{'completed_at_utc':(NOW-dt.timedelta(seconds=901)).isoformat()},{'completed_at_utc':(NOW+dt.timedelta(seconds=1)).isoformat()}]:
   c=sample_capture(); c.update(changes)
   with self.assertRaises(AdmissionError):self.q(c)
 def test_duplicate_json_rejected(self):
  c=sample_capture();c['response']=b'{"success":true,"success":true}';c['response_sha256']=sha(c['response'])
  with self.assertRaises(AdmissionError):self.q(c)
 def test_query_bounds_and_exact_envelope(self):
  for query,num in [('',1),('x',0),('x',4),('x',True),('a\nb',1)]:
   with self.assertRaises(AdmissionError):build_request(query,num)
  bad=canonical({'api':'serper','path':'/news','body':{'q':'hello','num':3,'page':2},'query':{}})
  with self.assertRaises(AdmissionError):self.q(request=bad)
 def test_old_real_linkup_metadata_rejected_despite_compatible_shape(self):
  path=Path('/Users/rk/.codex/visualizations/2026/10/19/01a152a3-fbde-7cc1-acdd-cb13ff14c2d9/exploration-loop-run-20261023/response-d714920a0afb46a4972dbe7f0440a4d5.bin')
  if not path.exists(): self.skipTest('historic raw capture unavailable')
  c=sample_capture();c['response']=path.read_bytes();c['response_sha256']=sha(c['response'])
  with self.assertRaises(AdmissionError):self.q(c)

class IntegrationTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory(); self.ledger=Ledger(str(Path(self.tmp.name).resolve()/'run'),contract(),create=True)
  self.request=build_request('Federal Reserve latest decision',3);self.capture=sample_capture()
 def tearDown(self):self.ledger.close();self.tmp.cleanup()
 def test_single_capture_preserves_bytes_and_accounting(self):
  response=b'{"success":true,"priceCents":0.2,"requestId":"run-1","data":{"news":[{"title":"Example","date":"2026-10-29"}]}}'
  calls=[]
  def transport(p,e,b): calls.append((p,e,b));return 200,response
  result=execute(self.ledger,'s1',self.request,self.capture,transport,now=NOW)
  self.assertEqual(len(calls),1); self.assertEqual(calls[0],('orthogonal','/v1/run',self.request));self.assertEqual(result['price_micro_usd'],2000)
  self.assertEqual(result['request_id'],'run-1');self.assertEqual(result['response_sha256'],sha(response)); self.assertEqual(self.ledger.receipt('s1')['response'],response)
  self.assertEqual(self.ledger.summary()['exposure_micro'],721593+2000)
 def test_malformed_source_result_stops_but_keeps_effect_truth(self):
  raw=b'{"success":false,"priceCents":0.2,"requestId":"run-1","data":{}}'
  with self.assertRaises(EvidenceError):execute(self.ledger,'s1',self.request,self.capture,lambda *a:(200,raw),now=NOW)
  self.assertEqual(self.ledger.summary()['stopped'],1); self.assertEqual(self.ledger.receipt('s1')['state'],'succeeded'); self.assertEqual(self.ledger.receipt('s1')['actual_micro'],2000)
 def test_timeout_stops_and_never_retries(self):
  calls=[]
  def timeout(*a): calls.append(1);raise TimeoutError()
  with self.assertRaises(UnknownEffect):execute(self.ledger,'s1',self.request,self.capture,timeout,now=NOW)
  self.assertEqual(len(calls),1);self.assertEqual(self.ledger.summary()['stopped'],1);self.assertEqual(self.ledger.receipt('s1')['state'],'uncertain')
 def test_wrong_quote_or_metadata_never_calls_transport(self):
  calls=[]; c=sample_capture();c['http_status']=429
  with self.assertRaises(AdmissionError):execute(self.ledger,'s1',self.request,c,lambda *a:calls.append(1),now=NOW)
  self.assertEqual(calls,[]);self.assertEqual(self.ledger.summary()['source_attempts'],0)
 def test_actual_over_quote_stops_and_records_actual(self):
  raw=b'{"success":true,"priceCents":0.3,"requestId":"run-1","data":{}}'
  with self.assertRaises(Stop):execute(self.ledger,'s1',self.request,self.capture,lambda *a:(200,raw),now=NOW)
  self.assertEqual(self.ledger.summary()['stopped'],1);self.assertEqual(self.ledger.receipt('s1')['actual_micro'],3000)

if __name__=='__main__':unittest.main()
