import tempfile
import unittest
from pathlib import Path
from ledger import Ledger, Stop, UnknownEffect, canonical, digest

def contract():
 return {'run_id':'test','cap_micro':40_000_000,'prior_micro':721_593,'prior_generations':79,'prior_counts':11,'max_generations':835,'max_counts':767,'max_sources':18,'source_cap_micro':5_000_000,'model':'gemini-3.8-flash','location':'global','input_limit':16384,'output_reserve':8192,'max_output_tokens':4096,'input_rate_half_micro':3,'output_rate_half_micro':15,'model_price_evidence_sha256':'a'*64,'count_price_evidence_sha256':'b'*64}
def request(): return {'contents':[{'role':'user','parts':[{'text':'hello'}]}], 'generationConfig':{'maxOutputTokens':4096}}
def model(provider,endpoint,body):
 if endpoint=='countTokens': return 200,b'{"totalTokens":100}'
 return 200,b'{"modelVersion":"gemini-3.8-flash","usageMetadata":{"promptTokenCount":100,"totalTokenCount":150,"thoughtsTokenCount":40}}'
def source_request(): return canonical({'api':'serper','path':'/news','body':{'q':'fixture','num':3},'query':{}})
def pin(payload): return {'provider':'orthogonal','endpoint':'/v1/run','request_sha256':digest(payload),'max_micro':2500,'evidence_sha256':'c'*64,'expires_utc':'2099-01-01T00:00:00Z'}
class LedgerTest(unittest.TestCase):
 def setUp(self): self.tmp=tempfile.TemporaryDirectory(); self.path=str(Path(self.tmp.name).resolve()/'run'); self.c=contract(); self.l=Ledger(self.path,self.c,create=True)
 def tearDown(self): self.l.close(); self.tmp.cleanup()
 def test_all_types_share_budget_and_thought_cost(self):
  self.assertEqual(self.l.count('c1',request(),model),100)
  self.l.generate('g1',request(),'c1',model)
  payload=source_request(); self.l.source('s1','orthogonal','/v1/run',payload,pin(payload),lambda *a:(200,b'{"priceCents":0.25}'))
  self.assertEqual(self.l.summary(),{'stopped':0,'exposure_micro':721593+525+2500,'generation_attempts':80,'count_attempts':12,'source_attempts':1,'metadata_attempts':0,'metadata_retained_micro':0})
  self.assertEqual([x[0] for x in self.l.db.execute("SELECT state FROM events WHERE effect_id='g1' ORDER BY seq")],['prepared','started','succeeded','accounted'])
 def test_source_quote_must_match_exact_bytes_and_ceiling(self):
  p=source_request(); q=pin(p)
  with self.assertRaises(ValueError): self.l.source('x','orthogonal','/v1/run',b'{"a":1}',q,model)
  q['max_micro']=250001
  with self.assertRaises(ValueError): self.l.source('x','orthogonal','/v1/run',p,q,model)
  self.assertEqual(self.l.summary()['source_attempts'],0)
 def test_uncertain_stops_and_retains_reserved_exposure_after_reopen(self):
  p=source_request(); q=pin(p)
  def timeout(*a): raise TimeoutError()
  with self.assertRaises(UnknownEffect): self.l.source('s','orthogonal','/v1/run',p,q,timeout)
  self.assertEqual(self.l.summary()['exposure_micro'],724093)
  self.l.close(); self.l=Ledger(self.path,self.c,create=False)
  self.assertEqual(self.l.summary()['stopped'],1)
  with self.assertRaises(Stop): self.l.source('s','orthogonal','/v1/run',p,q,model)
 def test_provider_overquote_records_actual_and_stops(self):
  p=source_request()
  with self.assertRaises(Stop): self.l.source('s','orthogonal','/v1/run',p,pin(p),lambda *a:(200,b'{"priceCents":1.0}'))
  self.assertEqual(self.l.summary()['exposure_micro'],731593)
  self.assertEqual(self.l.summary()['stopped'],1)
 def test_unknown_price_keeps_reservation_and_effect_success(self):
  p=source_request()
  with self.assertRaises(Stop): self.l.source('s','orthogonal','/v1/run',p,pin(p),lambda *a:(200,b'{}'))
  self.assertEqual(self.l.db.execute("SELECT state,actual_micro FROM effects WHERE id='s'").fetchone(),('succeeded',None))
  self.assertEqual(self.l.summary()['exposure_micro'],724093)
  self.assertEqual(self.l.summary()['stopped'],1)
 def test_model_requires_bound_once_only_count(self):
  self.l.count('c',request(),model)
  q=request(); q['contents'][0]['parts'][0]['text']='other'
  with self.assertRaises(Stop): self.l.generate('g',q,'c',model)
  self.l.generate('g',request(),'c',model)
  with self.assertRaises(Stop): self.l.generate('g2',request(),'c',model)
 def test_live_lock_prevents_two_ledgers_and_drift_blocks_reopen(self):
  with self.assertRaises(Stop): Ledger(self.path,self.c,create=False)
  self.l.close(); drift=dict(self.c,run_id='different')
  with self.assertRaises(Stop): Ledger(self.path,drift,create=False)
  self.l=Ledger(self.path,self.c,create=False)
 def test_crash_started_recovery_forbids_resume(self):
  self.l._start('crash','source','orthogonal','/v1/run',b'{}',2500,'c'*64)
  self.l.close(); self.l=Ledger(self.path,self.c,create=False)
  self.assertEqual(self.l.summary()['stopped'],1)
  self.assertEqual(self.l.db.execute("SELECT state FROM effects WHERE id='crash'").fetchone()[0],'uncertain')
 def test_crash_after_success_before_settle_stays_success_and_stops(self):
  self.l._execute('x','source','orthogonal','/v1/run',b'{}',2500,'c'*64,lambda *a:(200,b'{}'))
  self.l.close(); self.l=Ledger(self.path,self.c,create=False)
  self.assertEqual(self.l.summary()['stopped'],1)
  self.assertEqual(self.l.db.execute("SELECT state FROM effects WHERE id='x'").fetchone()[0],'succeeded')
 def test_budget_refuses_before_external_effect(self):
  self.l.db.execute('UPDATE run SET exposure_micro=39999000')
  p=source_request(); invoked=[]
  with self.assertRaises(Stop): self.l.source('s','orthogonal','/v1/run',p,pin(p),lambda *a:invoked.append(1))
  self.assertFalse(invoked)
 def test_count_unchanged_model_and_token_excess_prevent_generation(self):
  self.l.count('c',request(),lambda *a:(200,b'{"totalTokens":16385}'))
  with self.assertRaises(Stop): self.l.generate('g',request(),'c',model)
  self.assertEqual(self.l.summary()['generation_attempts'],79)
 def test_rate_or_model_drift_invalid_at_creation(self):
  for changes in ({'model':'other'},{'location':'us'},{'input_rate_half_micro':1}):
   c=dict(self.c,**changes)
   with tempfile.TemporaryDirectory() as t:
    with self.assertRaises(ValueError): Ledger(str(Path(t).resolve()/'run'),c,create=True)
 def test_non200_reserve_remains_and_stops(self):
  p=source_request()
  with self.assertRaises(Stop): self.l.source('s','orthogonal','/v1/run',p,pin(p),lambda *a:(429,b'{}'))
  self.assertEqual(self.l.summary()['exposure_micro'],724093)
  self.assertEqual(self.l.db.execute("SELECT state FROM effects WHERE id='s'").fetchone()[0],'succeeded')
 def test_contract_copied_and_internal_mutation_fails_closed(self):
  self.c['cap_micro']=100_000_000
  self.assertEqual(self.l._contract['cap_micro'],40_000_000)
  self.l._contract['cap_micro']=100_000_000
  with self.assertRaises(Stop): self.l.count('c',request(),model)
  self.assertTrue(self.l.poisoned)
  self.c['cap_micro']=40_000_000
 def test_out_of_envelope_usage_accounts_real_amount_then_stops(self):
  self.l.count('c',request(),model)
  reply=b'{"modelVersion":"gemini-3.8-flash","usageMetadata":{"promptTokenCount":100,"totalTokenCount":20100,"thoughtsTokenCount":19000}}'
  with self.assertRaises(Stop): self.l.generate('g',request(),'c',lambda *a:(200,reply))
  self.assertEqual(self.l.receipt('g')['actual_micro'],150150)
  self.assertEqual(self.l.summary()['exposure_micro'],721593+150150)
  self.assertEqual(self.l.summary()['stopped'],1)
 def test_count_and_generate_wire_bytes_identical(self):
  seen=[]
  def transport(provider,endpoint,body):
   seen.append((provider,endpoint,body))
   return model(provider,endpoint,body)
  self.l.count('c',request(),transport)
  self.l.generate('g',request(),'c',transport)
  self.assertEqual(seen[0][2],seen[1][2])
  self.assertEqual(seen[0][1],'countTokens')
  self.assertEqual(seen[1][1],'gemini-3.8-flash@global')
 def test_source_receipt_contains_full_quote_and_timestamps(self):
  p=source_request(); q=pin(p)
  self.l.source('s','orthogonal','/v1/run',p,q,lambda *a:(200,b'{"priceCents":0.25}'))
  receipt=self.l.receipt('s')
  self.assertEqual(receipt['quote_metadata'],__import__('json').dumps(q,sort_keys=True,separators=(',',':')).encode())
  self.assertEqual(receipt['actual_micro'],2500)
  self.assertTrue(receipt['started_at_utc'])
  self.assertTrue(receipt['completed_at_utc'])
 def test_adapter_stop_persists_and_blocks_all_further_calls(self):
  self.l.stop('source schema incomplete')
  self.assertEqual(self.l.summary()['stopped'],1)
  self.assertEqual(self.l.db.execute('SELECT reason FROM run_events').fetchone()[0],'source schema incomplete')
  with self.assertRaises(Stop): self.l.count('c',request(),model)
 def test_wrong_or_missing_model_version_is_accounted_then_stops(self):
  self.l.count('c',request(),model)
  reply=b'{"modelVersion":"gemini-3.7-flash","usageMetadata":{"promptTokenCount":100,"totalTokenCount":150}}'
  with self.assertRaises(Stop): self.l.generate('g',request(),'c',lambda *a:(200,reply))
  self.assertEqual(self.l.receipt('g')['actual_micro'],525)
  self.assertEqual(self.l.summary()['stopped'],1)
 def test_metadata_unknown_actual_is_succeeded_reserved_and_stops(self):
  body=b'{"api":"serper","path":"/news"}'; calls=[]
  def transport(provider,endpoint,request):
   calls.append((provider,endpoint,request))
   return 200,b'{"success":true,"endpoint":{"price":"$0.0025"}}'
  raw=self.l.metadata('metadata1',body,250000,'d'*64,transport,verify_bound=lambda *a:True)
  self.assertEqual(len(calls),1);self.assertEqual(calls[0],('orthogonal','/v1/details',body))
  receipt=self.l.receipt('metadata1')
  self.assertEqual((receipt['state'],receipt['actual_micro'],receipt['quote_micro'],receipt['response']),('succeeded',None,250000,raw))
  self.assertEqual(self.l.summary()['metadata_attempts'],1)
  self.assertEqual(self.l.summary()['metadata_retained_micro'],250000)
  self.assertEqual(self.l.summary()['source_attempts'],0)
  self.assertEqual(self.l.summary()['exposure_micro'],971593)
  self.assertEqual(self.l.summary()['stopped'],1)
  with self.assertRaises(Stop): self.l.count('c',request(),model)
  self.l.close();self.l=Ledger(self.path,self.c,create=False)
  self.assertEqual(self.l.receipt('metadata1')['actual_micro'],None)
  self.assertEqual(self.l.summary()['stopped'],1)
 def test_unverified_metadata_bound_denied_before_effect(self):
  seen=[];body=b'{"api":"serper","path":"/news"}'
  with self.assertRaises(Stop): self.l.metadata('m',body,250000,'d'*64,lambda *a:seen.append(1),verify_bound=lambda *a:False)
  self.assertEqual(seen,[]);self.assertEqual(self.l.summary()['metadata_attempts'],0)
  with self.assertRaises(ValueError): self.l.metadata('m',b'{}',250000,'d'*64,lambda *a:seen.append(1),verify_bound=lambda *a:True)
  with self.assertRaises(ValueError): self.l.metadata('m',body,250001,'d'*64,lambda *a:seen.append(1),verify_bound=lambda *a:True)
 def test_metadata_timeout_uncertain_and_no_second_effect(self):
  body=b'{"api":"serper","path":"/news"}';calls=[]
  def timeout(*a): calls.append(1);raise TimeoutError()
  with self.assertRaises(UnknownEffect): self.l.metadata('m',body,250000,'d'*64,timeout,verify_bound=lambda *a:True)
  self.assertEqual(self.l.receipt('m')['state'],'uncertain')
  self.assertIsNone(self.l.receipt('m')['actual_micro'])
  self.assertEqual(self.l.summary()['metadata_retained_micro'],250000)
  with self.assertRaises(Stop): self.l.metadata('m2',body,250000,'d'*64,timeout,verify_bound=lambda *a:True)
  self.assertEqual(calls,[1])
 def test_metadata_uses_same_source_budget(self):
  with tempfile.TemporaryDirectory() as d:
   c=dict(contract(),source_cap_micro=249999)
   l=Ledger(str(Path(d).resolve()/'run'),c,create=True)
   calls=[]
   try:
    with self.assertRaises(Stop): l.metadata('m',b'{"api":"serper","path":"/news"}',250000,'d'*64,lambda *a:calls.append(1),verify_bound=lambda *a:True)
    self.assertEqual(calls,[]);self.assertEqual(l.summary()['metadata_attempts'],0)
   finally: l.close()
 def test_source_and_metadata_share_one_database_and_exposure(self):
  source_body=source_request();q=pin(source_body)
  self.l.source('source','orthogonal','/v1/run',source_body,q,lambda *a:(200,b'{"priceCents":0.25}'))
  metadata_body=b'{"api":"serper","path":"/news"}'
  self.l.metadata('meta',metadata_body,250000,'d'*64,lambda *a:(200,b'{}'),verify_bound=lambda *a:True)
  self.assertEqual(self.l.summary()['exposure_micro'],721593+2500+250000)
  self.assertEqual((self.l.summary()['source_attempts'],self.l.summary()['metadata_attempts']),(1,1))
  self.assertEqual(self.l.receipt('source')['actual_micro'],2500)
  self.assertIsNone(self.l.receipt('meta')['actual_micro'])
 def test_source_rejects_forged_endpoints_and_out_of_scope_body(self):
  seen=[]; good=source_request()
  for provider,endpoint in [('evil','/v1/run'),('orthogonal','/v1/search'),('orthogonal','/v1/details')]:
   q=pin(good);q['provider']=provider;q['endpoint']=endpoint
   with self.assertRaises(ValueError):self.l.source('s',provider,endpoint,good,q,lambda *a:seen.append(1))
  cases=[
   canonical({'api':'serper','path':'/search','body':{'q':'fixture','num':3},'query':{}}),
   canonical({'api':'other','path':'/news','body':{'q':'fixture','num':3},'query':{}}),
   canonical({'api':'serper','path':'/news','body':{'q':'fixture','num':4},'query':{}}),
   canonical({'api':'serper','path':'/news','body':{'q':'fixture','num':True},'query':{}}),
   canonical({'api':'serper','path':'/news','body':{'q':'fixture','num':3,'page':2},'query':{}}),
   canonical({'api':'serper','path':'/news','body':{'q':'fixture','num':3},'query':{'page':2}}),
   canonical({'api':'serper','path':'/news','body':{'q':'','num':3},'query':{}}),
   canonical({'api':'serper','path':'/news','body':{'q':'a\ncommand','num':3},'query':{}}),
   b'{}', b'not-json']
  for body in cases:
   with self.assertRaises(ValueError):self.l.source('s','orthogonal','/v1/run',body,pin(body),lambda *a:seen.append(1))
  self.assertEqual(seen,[]);self.assertEqual(self.l.summary()['source_attempts'],0)
if __name__=='__main__': unittest.main()
