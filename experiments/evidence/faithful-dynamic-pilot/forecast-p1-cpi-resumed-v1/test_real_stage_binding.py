import json,sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent/'forecast-p1-budget-successor-v1'))
import p1_retry as r
import gate,dispatch_frozen,dispatch_preflight,test_dispatch_preflight
class T(unittest.TestCase):
 def test_real_activated_stages_match_frozen_dispatch(self):
  with tempfile.TemporaryDirectory() as td:
   root=Path(td).resolve();old=r.CLAIM;r.CLAIM=root/'claim';base=r.RetryBase(str(root/'ledger'),r.config(),create=True)
   try:
    parent=r.inspect_parent();ap=root/'account';ar=b'{"test":true}';ap.write_bytes(ar);ah=r.digest(ar)
    base.db.execute("insert into run_events(event,reason,at_utc) values ('forecast_started',?,?)",(ah,r.now_utc()))
    r.CLAIM.write_bytes(r.canonical({'parent_sha256':r.NEWS_DB_SHA,'contract_sha256':ah,'ledger_root':str(base.root)}));account=r.RetryAccounting(base,parent,ap,ah)
    helper=test_dispatch_preflight.T();helper.setUp();prefreeze=dispatch_preflight.prepare(**helper.k)
    operations=prefreeze['remaining_status_operations']
    # Replace synthetic lightweight tickets with full valid ticket objects and
    # bind the exact replacement in both source and dispatch freeze.
    for op in operations:
     op['ticket'].update(max_micro=150000,evidence_sha256='a'*64,expires_utc='2026-10-29T23:59:59Z',settlement='orthogonal_price_cents')
    source={'schema':'cpi-p1-source-contract-v1','status':'frozen','account_contract_sha256':ah,'caps':r.p.CAPS,'case_id':'case-02','cpi_receipt_sha256':parent['cpi_receipt_sha256'],'no_retry':True,'no_canary':True,'bridge_sha256':r.digest(Path(r.p.__file__).read_bytes()),'operations':operations}
    sp=root/'source';sr=r.canonical(source);sp.write_bytes(sr);s=r.activate_source(account,stage_path=sp,stage_sha=r.digest(sr),verify_challenge=lambda b:b==sr,verify_ticket=lambda *a:True)
    model={'schema':'cpi-p1-retry-model-contract-v1','status':'frozen','account_contract_sha256':ah,'caps':r.p.CAPS,'case_id':'case-02','cpi_receipt_sha256':parent['cpi_receipt_sha256'],'no_canary':True,'retry_bridge_sha256':r.digest(Path(r.__file__).read_bytes()),'max_generations':112,'max_counts':112,'max_additional_attempts':20,'max_retry_per_operation':3,'arms':['c_no_news','b_no_news','c_news','b_news']}
    mp=root/'model';mr=r.canonical(model);mp.write_bytes(mr);m=r.activate_model(account,stage_path=mp,stage_sha=r.digest(mr),verify_challenge=lambda b:b==mr,verify_scope=lambda:True)
    self.assertEqual(m.kind,'model');self.assertIs(m.account,s.account)
    contract=gate.canonical(dispatch_frozen.expected(prefreeze));previous=dispatch_frozen.orchestrate_retry.run;dispatch_frozen.orchestrate_retry.run=lambda **kwargs:kwargs
    try:
     result=dispatch_frozen.run(prefreeze=prefreeze,contract_bytes=contract,contract_sha256=gate.sha(contract),verify_contract=lambda b:b==contract,model_stage=m,source_stage=s,
      model_transport=lambda *a:None,source_transport=lambda *a:None,decode_status=lambda *a:None,verify_operation=lambda *a:True,verify_news=lambda *a:True,verify_status=lambda *a:True,
      verify_admission=lambda *a:True,verify_ledger=lambda *a:True,record=lambda *a:None,clock=helper.clock,pacer=None,confirmed429=r.Confirmed429,rate_limit_exhausted=r.RateLimitExhausted,sleep=lambda *a:None,jitter=lambda:0)
     self.assertIs(result['model_stage'],m);self.assertIs(result['source_stage'],s);self.assertEqual(account.summary()['source_attempts'],19)
    finally:dispatch_frozen.orchestrate_retry.run=previous
   finally:base.close();r.CLAIM=old
if __name__=='__main__':unittest.main()
