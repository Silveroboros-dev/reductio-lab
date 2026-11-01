import datetime as dt,json,tempfile,unittest
from pathlib import Path
from unittest import mock
import recovery as r

class Tests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory(dir='/private/tmp');self.root=Path(self.tmp.name).resolve()
  self.claim=self.root/'claim.json';self.parent={'synthetic':'parent'}
  self.p=mock.patch.object(r,'inspect_stopped',return_value=self.parent);self.c=mock.patch.object(r,'CLAIM',self.claim)
  self.p.start();self.c.start();self.ledger=None
  cfg=(r.ROOT/'forecast-stopped-successor-v1/ledger_contract.json').read_bytes()
  contract={'schema':'faithful-forecast-post400-contract-v1','status':'frozen','caps':r.CAPS,'parent':self.parent,
   'ledger_contract_sha256':r.digest(cfg),'prohibited_request_sha256':r.FAILED_REQUEST_SHA,
   'scope':{'mode':'accounting_only','provider_effects':'forbidden'}}
  self.contract=self.root/'contract.json';self.contract.write_bytes(r.canonical(contract));self.contract_sha=r.digest(self.contract.read_bytes())
 def tearDown(self):
  if self.ledger is not None:self.ledger.close()
  self.p.stop();self.c.stop();self.tmp.cleanup()
 def create(self,challenge=lambda _:True,accounting=False):
  ledger=r.create_successor(successor_root=str(self.root/'ledger'),claim_path=str(self.claim),run_contract_path=str(self.contract),
   expected_contract_sha256=self.contract_sha,verify_challenge=challenge,verify_ticket=lambda *_:True)
  self.ledger=ledger if accounting else r.RecoveryLedger(ledger._base,self.claim.read_bytes(),self.parent,str(self.contract),self.contract_sha,lambda *_:True)
  return self.ledger
 def reopen(self):
  ledger=r.reopen_successor(successor_root=str(self.root/'ledger'),claim_path=str(self.claim),run_contract_path=str(self.contract),
   expected_contract_sha256=self.contract_sha,verify_challenge=lambda _:True,verify_ticket=lambda *_:True)
  self.ledger=r.RecoveryLedger(ledger._base,self.claim.read_bytes(),self.parent,str(self.contract),self.contract_sha,lambda *_:True)
  return self.ledger
 def ticket(self,op,raw,**extra):
  q={'id':op,'provider':'orthogonal','endpoint':'/v1/run','request_sha256':r.digest(raw),'max_micro':150000,'evidence_sha256':'a'*64,
   'expires_utc':(dt.datetime.now(dt.timezone.utc)+dt.timedelta(minutes=10)).isoformat(),'category':'search','settlement':'orthogonal_price_cents'}
  q.update(extra);return q
 def test_carry_and_caps(self):
  x=self.create().summary();self.assertEqual((x['exposure_micro'],x['generation_attempts'],x['count_attempts'],x['source_attempts']),(1510458,232,164,14))
  self.assertEqual(x['prior_http400_charge_unknown_retained_micro'],150000)
 def test_reject_failed_id_even_if_new_request(self):
  x=self.create();raw=b'{}';q=self.ticket(r.FAILED_OP,raw)
  with self.assertRaises(r.Stop):x.source(r.FAILED_OP,'orthogonal','/v1/run',raw,q,lambda *_:(200,b'{}'))
  self.assertEqual(x.summary()['source_attempts'],14)
 def test_reject_same_market_tickers_reencoded(self):
  x=self.create();p={'api':'kalshi','path':'/markets','query':{'limit':'4','tickers':','.join(reversed(sorted(r.FAILED_TICKERS)))},'body':{}}
  raw=r.canonical(p);q=self.ticket('different-id',raw,category='market')
  with self.assertRaises(r.Stop):x.source('different-id','orthogonal','/v1/run',raw,q,lambda *_:(200,b'{}'))
  self.assertEqual(x.summary()['source_attempts'],14)
 def test_new_source_settlement_and_reopen(self):
  x=self.create();raw=b'{"api":"serper","path":"/news"}';q=self.ticket('new-op',raw,category='news')
  x.source('new-op','orthogonal','/v1/run',raw,q,lambda *_:(200,b'{"priceCents":0.2}'))
  self.assertEqual((x.summary()['source_attempts'],x.summary()['exposure_micro']),(15,1512458))
  x.close();self.ledger=None;x=self.reopen()
  self.assertEqual(x.receipt('new-op')['actual_micro'],2000)
  self.assertEqual(x.summary()['prior_http400_charge_unknown_retained_micro'],150000)
 def test_uncertain_blocks_resume(self):
  x=self.create();raw=b'{}';q=self.ticket('new-op',raw)
  def fail(*_):raise TimeoutError()
  with self.assertRaises(r.Stop):x.source('new-op','orthogonal','/v1/run',raw,q,fail)
  self.assertEqual(x.receipt('new-op')['state'],'uncertain')
  x.close();self.ledger=None
  with self.assertRaises(r.Stop):self.reopen()
 def test_14_remaining_attempts(self):
  x=self.create()
  for i in range(14):
   op='new-'+str(i);raw=r.canonical({'api':'serper','path':'/news','i':i});q=self.ticket(op,raw)
   x.source(op,'orthogonal','/v1/run',raw,q,lambda *_:(200,b'{"priceCents":0.2}'))
  self.assertEqual(x.summary()['source_attempts'],28)
  raw=b'{}';q=self.ticket('new-14',raw)
  with self.assertRaises(r.Stop):x.source('new-14','orthogonal','/v1/run',raw,q,lambda *_:(200,b'{"priceCents":0.2}'))
 def test_generation_carries_and_settles(self):
  x=self.create();request={'contents':[],'generationConfig':{'maxOutputTokens':4096}}
  def transport(provider,endpoint,body):
   if endpoint=='countTokens':return 200,b'{"totalTokens":100}'
   return 200,b'{"modelVersion":"gemini-3.8-flash","usageMetadata":{"promptTokenCount":100,"totalTokenCount":140}}'
  x.count('count:new-1',request,transport);x.generate('generation:new-1',request,'count:new-1',transport)
  s=x.summary();self.assertEqual((s['exposure_micro'],s['generation_attempts'],s['count_attempts'],s['source_attempts']),(1510908,233,165,14))
  x.close();self.ledger=None;self.assertEqual(self.reopen().summary()['generation_attempts'],233)
 def test_accounting_only_forbids_all_provider_effects(self):
  x=self.create(accounting=True)
  for call in (lambda:x.count('n',{},None),lambda:x.generate('n',{},'n',None),lambda:x.source('n','x','y',b'',{},None)):
   with self.assertRaises(r.Stop):call()
  self.assertEqual(x.summary()['generation_attempts'],232)
  self.assertEqual(x.db.execute('select count(*) from effects').fetchone()[0],0)
 def test_p0_activation_requires_review_and_remains_model_only(self):
  x=self.create(accounting=True)
  p0={'schema':'faithful-forecast-p0-model-contract-v1','status':'frozen','caps':r.CAPS,
      'accounting_contract_sha256':self.contract_sha,'ledger_root':str(x.root),
      'starting_usage':x.summary(),'source_reads':0}
  path=self.root/'p0.json';path.write_bytes(r.canonical(p0));h=r.digest(path.read_bytes())
  with self.assertRaises(r.Stop):r.activate_model_stage(x,model_contract_path=str(path),expected_model_contract_sha256=h,verify_challenge=lambda _:False)
  active=r.activate_model_stage(x,model_contract_path=str(path),expected_model_contract_sha256=h,verify_challenge=lambda _:True)
  self.ledger=active
  with self.assertRaises(r.Stop):active.source('n','x','y',b'',{},None)
  self.assertEqual(active.db.execute("select count(*) from run_events where event='p0_model_started'").fetchone()[0],1)
  with self.assertRaises(r.Stop):r.activate_model_stage(x,model_contract_path=str(path),expected_model_contract_sha256=h,verify_challenge=lambda _:True)
 def test_p0_activation_rejects_stopped_without_marker(self):
  x=self.create(accounting=True)
  x.stop('test local stop')
  p0={'schema':'faithful-forecast-p0-model-contract-v1','status':'frozen','caps':r.CAPS,
      'accounting_contract_sha256':self.contract_sha,'ledger_root':str(x.root),
      'starting_usage':x.summary(),'source_reads':0}
  path=self.root/'p0.json';path.write_bytes(r.canonical(p0));h=r.digest(path.read_bytes())
  with self.assertRaises(r.Stop):r.activate_model_stage(x,model_contract_path=str(path),expected_model_contract_sha256=h,verify_challenge=lambda _:True)
  self.assertEqual(x.db.execute("select count(*) from run_events where event='p0_model_started'").fetchone()[0],0)
 def test_reject_challenge_and_duplicate_claim(self):
  with self.assertRaises(r.Stop):self.create(lambda _:False)
  self.assertFalse(self.claim.exists())
  self.create();self.ledger.close();self.ledger=None
  with self.assertRaises(FileExistsError):
   r.create_successor(successor_root=str(self.root/'ledger2'),claim_path=str(self.claim),run_contract_path=str(self.contract),
    expected_contract_sha256=self.contract_sha,verify_challenge=lambda _:True,verify_ticket=lambda *_:True)
 def test_prior_stopped_not_modified(self):
  self.p.stop()
  path=r.ROOT/'forecast-live-ledger-20261029-01/ledger.sqlite3';before=r.digest(path.read_bytes());p=r.inspect_stopped();after=r.digest(path.read_bytes())
  self.p.start();self.assertEqual(before,after);self.assertEqual(p['failed_operation']['effect_state'],'succeeded')
  self.assertEqual(p['failed_operation']['http_status'],400);self.assertIsNone(p['failed_operation']['charged_micro'])
  self.assertEqual(p['failed_operation']['retained_micro'],150000)

if __name__=='__main__':unittest.main()
