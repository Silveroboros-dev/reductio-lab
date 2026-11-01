import datetime as dt,json,tempfile,unittest
from pathlib import Path
import resume_ledger as r
class ResumeTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
  self.base=r.Base(str(Path(self.tmp.name).resolve()/'ledger'),r.config(),create=True);self.addCleanup(self.base.close)
  self.obj=r.Resume(self.base,{},clock=lambda:dt.datetime(2026,10,29,11,45,tzinfo=dt.timezone.utc))
 def request(self,ident):
  rel,sha,_=r.FAILED[ident];db=r._connect(rel,sha)
  try:return json.loads(db.execute('select request from effects where id=?',(ident,)).fetchone()[0])
  finally:db.close()
 def fake(self,provider,endpoint,body):
  self.assertEqual((provider,endpoint),('vertex','gemini-3.8-flash@global'))
  return 200,json.dumps({'modelVersion':'gemini-3.8-flash','usageMetadata':{'promptTokenCount':100,'totalTokenCount':200,'thoughtsTokenCount':20}}).encode()
 def test_actual_parent_and_exact_count(self):
  p=r.inspect();self.assertEqual((p['exposure_micro'],p['generation_attempts'],p['count_attempts'],p['source_attempts']),(1889731,274,206,16))
  self.assertEqual([x['count_tokens'] for x in p['failed_429']],[1614,1640,564])
 def test_accounting_only_never_calls_provider(self):
  account=r.Accounting(self.base,{},'unused')
  for method in (account.retry_failed,account.count_new,account.generate_new):
   with self.assertRaises(r.Error):method('anything',{},lambda *args:self.fail('unexpected network'))
  self.assertEqual(self.base.db.execute('select count(*) from effects').fetchone()[0],0)
 def test_accounting_create_reopen_and_claim_bound(self):
  root=Path(self.tmp.name).resolve()/'real';path=Path(self.tmp.name).resolve()/'contract.json'
  c={'schema':'p0-429-resume-accounting-contract-v1','status':'frozen','scope':{'mode':'accounting_only','provider_effects':'forbidden'},'parent':r.inspect(),'config':r.config(),'ledger_root':str(root),'caps':r.CAPS,'bridge_sha256':r.digest(Path(r.__file__).read_bytes()),'strict_p0_deadline_utc':r.DEADLINE,'no_source':True,'no_canary':True}
  raw=r.canonical(c);path.write_bytes(raw);h=r.digest(raw);verify=lambda x:x==raw
  a=r.create(root,contract_path=path,contract_sha256=h,verify_challenge=verify);a.close()
  a=r.reopen(root,contract_path=path,contract_sha256=h,verify_challenge=verify)
  self.assertEqual(a.summary()['source_attempts'],16)
  with self.assertRaises(r.Error):a.retry_failed('x',{},lambda *a:self.fail('unexpected network'))
  a.close()
  with self.assertRaises(r.Error):r.create(root,contract_path=path,contract_sha256=h,verify_challenge=verify)
 def test_retry_original_success_count_without_repeat(self):
  ident='generation:p0:case-01:b:02';self.obj.retry_failed(ident,self.request(ident),self.fake)
  rows=self.base.db.execute('select id,kind,related_id from effects').fetchall()
  self.assertEqual(len(rows),1);self.assertEqual(rows[0][1],'generation');self.assertIn('historical-count:',rows[0][2]);self.assertIn('count:p0:case-01:b:02',rows[0][2])
  self.assertEqual((self.obj.summary()['generation_attempts'],self.obj.summary()['count_attempts']),(275,206))
  with self.assertRaises(r.Error):self.obj.retry_failed(ident,self.request(ident),self.fake)
 def test_reject_wrong_or_successful_original(self):
  ident='generation:p0:case-01:b:02';req=self.request(ident);req['extra']='mutated'
  with self.assertRaises(r.Error):self.obj.retry_failed(ident,req,self.fake)
  with self.assertRaises(r.Error):self.obj.retry_failed('generation:p0:case-01:b:01',self.request(ident),self.fake)
  self.assertEqual(self.base.db.execute('select count(*) from effects').fetchone()[0],0)
 def test_new_scope_and_predecessor(self):
  req=self.request('generation:p0:case-01:b:02')
  for ident in ['p0:case-01:b:01','p0:case-03:b:01','p0:case-04:c:03','p0:case-01:b:03','p0:case-01:b:003']:
   with self.assertRaises(r.Error):self.obj.count_new(ident,req,lambda *x:self.fail('unexpected network'))
 def test_retry_then_new_ordinal_and_accounting(self):
  ident='generation:p0:case-01:b:02';req=self.request(ident)
  self.obj.retry_failed(ident,req,self.fake)
  with self.assertRaises(r.Error):self.obj.count_new('p0:case-01:b:04',req,lambda *x:self.fail('unexpected call'))
  def count_fake(provider,endpoint,body):
   self.assertEqual((provider,endpoint),('vertex','countTokens'))
   return 200,json.dumps({'totalTokens':100}).encode()
  self.obj.count_new('p0:case-01:b:03',req,count_fake)
  self.obj.generate_new('p0:case-01:b:03',req,self.fake)
  self.assertEqual((self.obj.summary()['generation_attempts'],self.obj.summary()['count_attempts']),(276,207))
 def test_model_version_mismatch_keeps_known_usage(self):
  ident='generation:p0:case-01:b:02'
  def fake(*args):return 200,json.dumps({'modelVersion':'other','usageMetadata':{'promptTokenCount':100,'totalTokenCount':200}}).encode()
  with self.assertRaises(ValueError):self.obj.retry_failed(ident,self.request(ident),fake)
  self.assertEqual(self.base.db.execute('select http_status,actual_micro from effects').fetchone(),(200,900));self.assertEqual(self.base.summary()['stopped'],1)
 def test_usage_above_envelope_keeps_known_cost(self):
  ident='generation:p0:case-01:b:02'
  def fake(*args):return 200,json.dumps({'modelVersion':'gemini-3.8-flash','usageMetadata':{'promptTokenCount':100,'totalTokenCount':8300}}).encode()
  with self.assertRaises(ValueError):self.obj.retry_failed(ident,self.request(ident),fake)
  self.assertEqual(self.base.db.execute('select http_status,actual_micro from effects').fetchone(),(200,61650));self.assertEqual(self.base.summary()['stopped'],1)
 def test_deadline_fails_before_effect(self):
  self.obj.clock=lambda:dt.datetime(2026,10,29,12,30,tzinfo=dt.timezone.utc);ident='generation:p0:case-01:b:02'
  with self.assertRaises(r.Error):self.obj.retry_failed(ident,self.request(ident),lambda *x:self.fail('unexpected network'))
  self.assertEqual(self.base.summary()['stopped'],1);self.assertEqual(self.base.db.execute('select count(*) from effects').fetchone()[0],0)
 def test_completion_after_deadline_accounted_then_stopped(self):
  times=iter([dt.datetime(2026,10,29,12,29,59,tzinfo=dt.timezone.utc),dt.datetime(2026,10,29,12,30,tzinfo=dt.timezone.utc)])
  self.obj.clock=lambda:next(times);ident='generation:p0:case-01:b:02'
  with self.assertRaises(r.Error):self.obj.retry_failed(ident,self.request(ident),self.fake)
  self.assertEqual(self.base.db.execute('select state,http_status,actual_micro from effects').fetchone(),('succeeded',200,900));self.assertEqual(self.base.summary()['stopped'],1)
if __name__=='__main__':unittest.main()
