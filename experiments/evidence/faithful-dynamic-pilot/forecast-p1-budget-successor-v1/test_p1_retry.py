import json,tempfile,unittest
from pathlib import Path
import p1_retry as r

class RetryTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.db=r.RetryBase(str(Path(self.tmp.name).resolve()/'ledger'),r.config(),create=True);self.addCleanup(self.db.close)
  self.req={'contents':[],'generationConfig':{'maxOutputTokens':4096}};self.c='count:p1:case-02:no_news:c:01';self.g='generation:p1:case-02:no_news:c:01';self.calls=[]
 def r429(self,provider,endpoint,raw):
  self.calls.append((provider,endpoint,raw));return 429,json.dumps({'error':{'code':429,'status':'RESOURCE_EXHAUSTED'}}).encode()
 def cnt(self,*args):self.calls.append(args);return 200,json.dumps({'totalTokens':100}).encode()
 def gen(self,*args):self.calls.append(args);return 200,json.dumps({'modelVersion':'gemini-3.8-flash','usageMetadata':{'promptTokenCount':100,'totalTokenCount':200}}).encode()
 def test_count_429_followed_by_success_without_extra_count(self):
  with self.assertRaises(r.Confirmed429):self.db.count_attempt(self.c,self.req,0,self.r429)
  self.assertEqual(self.db.count_attempt(self.c,self.req,1,self.cnt),100)
  with self.assertRaises(pick_error()):self.db.count_attempt(self.c,self.req,2,self.cnt)
  self.assertEqual((self.db.summary()['count_attempts'],self.db.summary()['stopped']),(230,0))
 def test_gen_429_reuses_successful_count(self):
  self.db.count_attempt(self.c,self.req,0,self.cnt)
  with self.assertRaises(r.Confirmed429):self.db.generate_attempt(self.g,self.req,self.c,0,self.r429)
  self.db.generate_attempt(self.g,self.req,self.c,1,self.gen)
  rows=self.db.db.execute('select id,kind,related_id,actual_micro from effects order by rowid').fetchall()
  self.assertEqual(len(rows),3);self.assertEqual(rows[1][2],rows[2][2]);self.assertIsNone(rows[1][3]);self.assertEqual(rows[2][3],900)
  with self.assertRaises(pick_error()):self.db.generate_attempt(self.g,self.req,self.c,2,self.gen)
 def test_non_429_or_timeout_stops(self):
  def other(*a):return 500,b'error'
  with self.assertRaises(r.Stop):self.db.count_attempt(self.c,self.req,0,other)
  self.assertEqual(self.db.summary()['stopped'],1)
 def test_changed_request_and_skipped_retry_rejected(self):
  with self.assertRaises(r.Confirmed429):self.db.count_attempt(self.c,self.req,0,self.r429)
  changed=dict(self.req);changed['contents']=['changed']
  with self.assertRaises(pick_error()):self.db.count_attempt(self.c,changed,1,self.cnt)
  with self.assertRaises(pick_error()):self.db.count_attempt(self.c,self.req,2,self.cnt)
 def test_exhausted_isolated_operation(self):
  for n in range(3):
   with self.assertRaises(r.Confirmed429):self.db.count_attempt(self.c,self.req,n,self.r429)
  with self.assertRaises(r.RateLimitExhausted):self.db.count_attempt(self.c,self.req,3,self.r429)
  self.assertEqual(self.db.summary()['stopped'],0)
  other='count:p1:case-02:news:c:01';self.assertEqual(self.db.count_attempt(other,self.req,0,self.cnt),100)
 def test_unknown_effect_not_retried(self):
  def bad(*a):raise OSError('unknown')
  with self.assertRaises(Exception):self.db.count_attempt(self.c,self.req,0,bad)
  self.assertEqual(self.db.summary()['stopped'],1)
  with self.assertRaises(Exception):self.db.count_attempt(self.c,self.req,1,self.cnt)
 def test_stage_facade_rejects_stale_scope_before_effect(self):
  stage=r.RetryModelStage(self.db,lambda:False,16)
  with self.assertRaises(r.p.Error):stage.count_attempt(self.c,self.req,0,lambda *a:self.fail('unexpected call'))
  self.assertEqual(self.db.summary()['stopped'],1);self.assertEqual(self.db.db.execute('select count(*) from effects').fetchone()[0],0)
 def test_integrated_source_and_model_with_confirmed_retry(self):
  root=Path(self.tmp.name).resolve();oldclaim=r.CLAIM;r.CLAIM=root/'claim';self.addCleanup(lambda:setattr(r,'CLAIM',oldclaim))
  parent=r.inspect_parent();path=root/'account.json';araw=b'{"test":true}';path.write_bytes(araw);ah=r.digest(araw)
  self.db.db.execute("insert into run_events(event,reason,at_utc) values ('forecast_started',?,?)",(ah,r.now_utc()))
  r.CLAIM.write_bytes(r.canonical({'parent_sha256':r.NEWS_DB_SHA,'contract_sha256':ah,'ledger_root':str(self.db.root)}))
  account=r.RetryAccounting(self.db,parent,path,ah)
  payload={'api':'kalshi','path':'/markets','body':{},'query':{'tickers':'KXCPI-26OCT-T0.2'}};body=r.canonical(payload)
  ticket={'id':'cpi-status-1','provider':'orthogonal','endpoint':'/v1/run','request_sha256':r.digest(body),'max_micro':150000,'evidence_sha256':'a'*64,'expires_utc':'2026-10-29T23:59:59Z','category':'market','settlement':'orthogonal_price_cents'}
  source={'schema':'cpi-p1-source-contract-v1','status':'frozen','account_contract_sha256':ah,'caps':r.p.CAPS,'case_id':'case-02','cpi_receipt_sha256':parent['cpi_receipt_sha256'],'no_retry':True,'no_canary':True,'bridge_sha256':r.digest(Path(r.p.__file__).read_bytes()),'operations':[{'ticket':ticket,'payload':payload,'kind':'status_refresh'}]}
  spath=root/'source';sr=r.canonical(source);spath.write_bytes(sr);s=r.activate_source(account,stage_path=spath,stage_sha=r.digest(sr),verify_challenge=lambda b:b==sr,verify_ticket=lambda *a:True)
  s.source(ticket['id'],'orthogonal','/v1/run',body,ticket,lambda *a:(200,json.dumps({'success':True,'priceCents':0.2,'billing':{'chargedPriceCents':0.2}}).encode()))
  model={'schema':'cpi-p1-retry-model-contract-v1','status':'frozen','account_contract_sha256':ah,'caps':r.p.CAPS,'case_id':'case-02','cpi_receipt_sha256':parent['cpi_receipt_sha256'],'no_canary':True,'retry_bridge_sha256':r.digest(Path(r.__file__).read_bytes()),'max_generations':112,'max_counts':112,'max_additional_attempts':20,'max_retry_per_operation':3,'arms':['c_no_news','b_no_news','c_news','b_news']}
  mpath=root/'model';mr=r.canonical(model);mpath.write_bytes(mr);m=r.activate_model(account,stage_path=mpath,stage_sha=r.digest(mr),verify_challenge=lambda b:b==mr,verify_scope=lambda:True)
  with self.assertRaises(r.Confirmed429):m.count_attempt(self.c,self.req,0,self.r429)
  m.count_attempt(self.c,self.req,1,self.cnt)
  with self.assertRaises(r.Confirmed429):m.generate_attempt(self.g,self.req,self.c,0,self.r429)
  m.generate_attempt(self.g,self.req,self.c,1,self.gen)
  self.assertEqual((m.summary()['source_attempts'],m.summary()['generation_attempts'],m.summary()['count_attempts']),(20,301,230))

 def test_source_missing_and_mismatched_billing_stop_with_safe_accounting(self):
  # Each example uses its own journal: these are synthetic HTTP receipts.
  for response,expected in [({'success':True,'priceCents':0.2},150000),({'success':True,'priceCents':0.2,'billing':{'chargedPriceCents':0.3}},3000)]:
   with self.subTest(response=response),tempfile.TemporaryDirectory() as td:
    root=Path(td).resolve();claim=r.CLAIM;r.CLAIM=root/'claim'
    try:
     db=r.RetryBase(str(root/'ledger'),r.config(),create=True)
     try:
      parent=r.inspect_parent();ap=root/'account';araw=b'{}';ap.write_bytes(araw);ah=r.digest(araw)
      db.db.execute("insert into run_events(event,reason,at_utc) values ('forecast_started',?,?)",(ah,r.now_utc()))
      r.CLAIM.write_bytes(r.canonical({'parent_sha256':r.NEWS_DB_SHA,'contract_sha256':ah,'ledger_root':str(db.root)}));account=r.RetryAccounting(db,parent,ap,ah)
      payload={'api':'kalshi','path':'/markets','query':{'tickers':'KXCPI-26OCT-T0.2'}};body=r.canonical(payload)
      ticket={'id':'cpi-status-1','provider':'orthogonal','endpoint':'/v1/run','request_sha256':r.digest(body),'max_micro':150000,'evidence_sha256':'a'*64,'expires_utc':'2026-10-29T23:59:59Z','category':'market','settlement':'orthogonal_price_cents'}
      c={'schema':'cpi-p1-source-contract-v1','status':'frozen','account_contract_sha256':ah,'caps':r.p.CAPS,'case_id':'case-02','cpi_receipt_sha256':parent['cpi_receipt_sha256'],'no_retry':True,'no_canary':True,'bridge_sha256':r.digest(Path(r.p.__file__).read_bytes()),'operations':[{'ticket':ticket,'payload':payload,'kind':'status_refresh'}]}
      sp=root/'source';sr=r.canonical(c);sp.write_bytes(sr);stage=r.activate_source(account,stage_path=sp,stage_sha=r.digest(sr),verify_challenge=lambda b:True,verify_ticket=lambda *a:True)
      with self.assertRaises(r.p.Error):stage.source(ticket['id'],'orthogonal','/v1/run',body,ticket,lambda *a:(200,json.dumps(response).encode()))
      self.assertEqual(db.summary()['stopped'],1);self.assertEqual(db.summary()['exposure_micro'],2005563+expected)
     finally:db.close()
    finally:r.CLAIM=claim

 def test_reopen_after_source_preserves_observation_and_allows_new_status(self):
  with tempfile.TemporaryDirectory() as td:
   root=Path(td).resolve();claim=r.CLAIM;r.CLAIM=root/'claim';ledger=root/'reopen-ledger'
   try:
    parent=r.inspect_parent();c={'schema':'cpi-p1-retry-accounting-contract-v1','status':'frozen','parent':parent,'config':r.config(),'ledger_root':str(ledger),'caps':r.p.CAPS,'scope':{'mode':'accounting_only','provider_effects':'forbidden'},'retry_bridge_sha256':r.digest(Path(r.__file__).read_bytes()),'budget_bridge_sha256':r.digest(Path(r.p.__file__).read_bytes())}
    ap=root/'account';ar=r.canonical(c);ap.write_bytes(ar);ah=r.digest(ar)
    account=r.create(ledger,contract_path=ap,contract_sha=ah,verify_challenge=lambda raw:raw==ar)
    payload={'api':'kalshi','path':'/markets','query':{'tickers':'KXCPI-26OCT-T0.2'}};body=r.canonical(payload)
    def ticket(i):return {'id':f'cpi-status-{i}','provider':'orthogonal','endpoint':'/v1/run','request_sha256':r.digest(body),'max_micro':150000,'evidence_sha256':'a'*64,'expires_utc':'2026-10-29T23:59:59Z','category':'market','settlement':'orthogonal_price_cents'}
    source={'schema':'cpi-p1-source-contract-v1','status':'frozen','account_contract_sha256':ah,'caps':r.p.CAPS,'case_id':'case-02','cpi_receipt_sha256':parent['cpi_receipt_sha256'],'no_retry':True,'no_canary':True,'bridge_sha256':r.digest(Path(r.p.__file__).read_bytes()),'operations':[{'ticket':ticket(i),'payload':payload,'kind':'status_refresh'} for i in (1,2)]}
    sp=root/'source';sr=r.canonical(source);sp.write_bytes(sr);sh=r.digest(sr)
    stage=r.activate_source(account,stage_path=sp,stage_sha=sh,verify_challenge=lambda raw:raw==sr,verify_ticket=lambda *a:True)
    transport=lambda *a:(200,json.dumps({'success':True,'priceCents':0.2,'billing':{'chargedPriceCents':0.2}}).encode())
    stage.source(ticket(1)['id'],'orthogonal','/v1/run',body,ticket(1),transport);account.close()
    account,stage=r.reopen_after_source(ledger,contract_path=ap,contract_sha=ah,verify_challenge=lambda raw:raw==ar,source_path=sp,source_sha=sh,verify_source_challenge=lambda raw:raw==sr,verify_historical_ticket=lambda *a:True,verify_ticket=lambda *a:True)
    try:
     with self.assertRaises(Exception):stage.source(ticket(1)['id'],'orthogonal','/v1/run',body,ticket(1),transport)
     stage.source(ticket(2)['id'],'orthogonal','/v1/run',body,ticket(2),transport)
     self.assertEqual((account.summary()['source_attempts'],account.summary()['exposure_micro']),(21,2009563))
    finally:account.close()
   finally:r.CLAIM=claim

def pick_error():return r.p.Error
if __name__=='__main__':unittest.main()
