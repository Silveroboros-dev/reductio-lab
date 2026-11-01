import datetime as dt,json,tempfile,unittest
from pathlib import Path
import p1_budget as p

class BudgetTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name).resolve();self.oldclaim=p.CLAIM;p.CLAIM=self.root/'claim.json';self.addCleanup(lambda:setattr(p,'CLAIM',self.oldclaim))
  self.base=p.Base(str(self.root/'ledger'),p.config(),create=True);self.addCleanup(self.base.close)
  self.acpath=self.root/'account.json';self.acraw=b'{"account":"test"}';self.acpath.write_bytes(self.acraw);self.acsha=p.digest(self.acraw)
  self.base.db.execute("insert into run_events(event,reason,at_utc) values ('forecast_started',?,?)",(self.acsha,p.now_utc()))
  p.CLAIM.write_bytes(p.canonical({'parent_sha256':p.PARENT_SHA,'contract_sha256':self.acsha,'ledger_root':str(self.base.root)}))
  self.parent=p.inspect_parent();self.account=p.Accounting(self.base,self.parent,self.acpath,self.acsha)
 def stage(self,kind,ops=None):
  c={'schema':'cpi-p1-'+kind+'-contract-v1','status':'frozen','account_contract_sha256':self.acsha,'caps':p.CAPS,'case_id':'case-02','cpi_receipt_sha256':self.parent['cpi_receipt_sha256'],'no_retry':True,'no_canary':True,'bridge_sha256':p.digest(Path(p.__file__).read_bytes())}
  if kind=='source':c['operations']=ops
  else:c.update(max_generations=92,max_counts=92,arms=['c_no_news','b_no_news','c_news','b_news'])
  raw=p.canonical(c);path=self.root/(kind+'.json');path.write_bytes(raw)
  return p.activate(self.account,stage_path=path,stage_sha=p.digest(raw),kind=kind,verify_challenge=lambda b:b==raw,verify_ticket=(lambda *x:True) if kind=='source' else None)
 def source_op(self,ident):
  payload={'api':'kalshi','path':'/markets','body':{},'query':{'tickers':'KXCPI-26OCT-T0.2'}};raw=p.canonical(payload)
  ticket={'id':ident,'provider':'orthogonal','endpoint':'/v1/run','request_sha256':p.digest(raw),'max_micro':150000,'evidence_sha256':'a'*64,'expires_utc':'2026-10-29T23:59:59Z','category':'market','settlement':'orthogonal_price_cents'}
  return {'ticket':ticket,'payload':payload,'kind':'status_refresh'}
 def test_real_parent_exact(self):
  x=p.inspect_parent();self.assertEqual((x['prior_micro'],x['prior_generations'],x['prior_counts'],x['prior_sources']),(1988563,299,228,16))
 def test_accounting_only_forbids_effects(self):
  for method in (self.account.source,self.account.count,self.account.generate):
   with self.assertRaises(p.Error):method('x',{},lambda *a:self.fail('unexpected effect'))
 def test_stages_share_budget_and_distinct_status_reads(self):
  a,b=self.source_op('cpi-status-1'),self.source_op('cpi-status-2');s=self.stage('source',[a,b]);m=self.stage('model')
  def src(provider,endpoint,raw):return 200,json.dumps({'success':True,'priceCents':0.2}).encode()
  for op in (a,b):s.source(op['ticket']['id'],'orthogonal','/v1/run',p.canonical(op['payload']),op['ticket'],src)
  req={'contents':[],'generationConfig':{'maxOutputTokens':4096}}
  def cnt(*a):return 200,json.dumps({'totalTokens':100}).encode()
  def gen(*a):return 200,json.dumps({'modelVersion':'gemini-3.8-flash','usageMetadata':{'promptTokenCount':100,'totalTokenCount':200}}).encode()
  n='p1:case-02:no_news:c:01';m.count('count:'+n,req,cnt);m.generate('generation:'+n,req,'count:'+n,gen)
  summary=self.account.summary();self.assertEqual((summary['source_attempts'],summary['generation_attempts'],summary['count_attempts']),(18,300,229));self.assertEqual(summary['exposure_micro'],1993463)
  with self.assertRaises(Exception):s.source(a['ticket']['id'],'orthogonal','/v1/run',p.canonical(a['payload']),a['ticket'],src)
 def test_non_status_duplicate_rejected(self):
  a,b=self.source_op('1'),self.source_op('2');a['kind']='event'
  with self.assertRaises(p.Error):self.stage('source',[a,b])
 def test_stage_rejects_more_than_twelve_sources(self):
  with self.assertRaises(p.Error):self.stage('source',[self.source_op(str(x)) for x in range(13)])
 def test_old_failed_generation_digest_rejected_before_count(self):
  m=self.stage('model');ident='generation:p0:case-01:b:02';rel,sha,_=p.old.FAILED[ident];db=p.old._connect(rel,sha)
  try:req=json.loads(db.execute('select request from effects where id=?',(ident,)).fetchone()[0])
  finally:db.close()
  with self.assertRaises(p.Error):m.count('count:p1:case-02:news:c:01',req,lambda *a:self.fail('unexpected effect'))
 def test_model_scope_and_stage_single_claim(self):
  m=self.stage('model')
  with self.assertRaises(p.Error):m.count('count:p1:case-04:news:c:01',{},lambda *a:self.fail('unexpected effect'))
  with self.assertRaises(p.Error):self.stage('model')
 def test_accounting_create_and_reopen(self):
  path=self.root/'contract.json';root=self.root/'other-ledger';parent=p.inspect_parent();c={'schema':'cpi-p1-accounting-contract-v1','status':'frozen','parent':parent,'config':p.config(),'ledger_root':str(root),'caps':p.CAPS,'scope':{'mode':'accounting_only','provider_effects':'forbidden'},'bridge_sha256':p.digest(Path(p.__file__).read_bytes())};raw=p.canonical(c);path.write_bytes(raw);p.CLAIM.unlink();h=p.digest(raw)
  a=p.create(root,contract_path=path,contract_sha=h,verify_challenge=lambda b:b==raw);self.assertEqual(a.summary()['source_attempts'],16);a.close()
  a=p.reopen(root,contract_path=path,contract_sha=h,verify_challenge=lambda b:b==raw);a.close()
 def test_reopen_after_source_with_old_id_consumed_and_refresh_remaining(self):
  path=self.root/'real-account.json';root=self.root/'other-ledger';parent=p.inspect_parent();c={'schema':'cpi-p1-accounting-contract-v1','status':'frozen','parent':parent,'config':p.config(),'ledger_root':str(root),'caps':p.CAPS,'scope':{'mode':'accounting_only','provider_effects':'forbidden'},'bridge_sha256':p.digest(Path(p.__file__).read_bytes())};raw=p.canonical(c);path.write_bytes(raw);p.CLAIM.unlink();h=p.digest(raw)
  a=p.create(root,contract_path=path,contract_sha=h,verify_challenge=lambda b:b==raw);self.account=a;self.acsha=h
  op1,op2=self.source_op('cpi-status-1'),self.source_op('cpi-status-2');s=self.stage('source',[op1,op2]);spath=self.root/'source.json';sraw=spath.read_bytes();sh=p.digest(sraw)
  def src(*args):return 200,json.dumps({'success':True,'priceCents':0.2}).encode()
  s.source(op1['ticket']['id'],'orthogonal','/v1/run',p.canonical(op1['payload']),op1['ticket'],src);a.close()
  a,s=p.reopen_after_source(root,contract_path=path,contract_sha=h,verify_challenge=lambda b:b==raw,source_path=spath,source_sha=sh,verify_source_challenge=lambda b:b==sraw,verify_historical_ticket=lambda *x:True,verify_ticket=lambda *x:True)
  self.assertEqual(a.summary()['source_attempts'],17)
  s.source(op2['ticket']['id'],'orthogonal','/v1/run',p.canonical(op2['payload']),op2['ticket'],src)
  self.assertEqual(a.summary()['source_attempts'],18);a.close()
if __name__=='__main__':unittest.main()
