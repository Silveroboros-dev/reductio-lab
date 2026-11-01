"""Only adapter composition; importing it does not open ledgers or networks.

Callers must separately freeze+challenge exact p0 inputs/logic and recover the
successor under the recovery module's independently challenged contract. An
injected transport is external and must itself be reviewed for no retries.
"""
import json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT/'forecast-controller-v1'))
sys.path.insert(0,str(ROOT/'forecast-stopped-successor-v1'))
import forecast,recovery

class Error(ValueError):pass

def reopen(*,successor_root,run_contract_path,expected_contract_sha256,verify_recovery_challenge):
 """Open already-created successor; denies every source ticket."""
 return recovery.reopen_successor(successor_root=successor_root,claim_path=recovery.CLAIM,
  run_contract_path=run_contract_path,expected_contract_sha256=expected_contract_sha256,
  verify_challenge=verify_recovery_challenge,verify_ticket=lambda *args:False)

def activate(accounting,*,model_contract_path,expected_model_contract_sha256,verify_p0_challenge):
 """Activate only the separately challenged exact p0 model contract."""
 return recovery.activate_model_stage(accounting,model_contract_path=model_contract_path,
  expected_model_contract_sha256=expected_model_contract_sha256,verify_challenge=verify_p0_challenge)

def generator_factory(ledger,*,case_ids,transport,verify_p0_binding):
 """Vertex-only, once per arm, count then generation with durable ledger IDs."""
 if not isinstance(ledger,recovery.ModelOnlyLedger):raise Error('activated model-only ledger required')
 if not isinstance(case_ids,(list,tuple)) or len(set(case_ids))!=len(case_ids) or not 1<=len(case_ids)<=4:
  raise Error('case identities required')
 if not callable(transport) or not callable(verify_p0_binding):raise Error('missing independently reviewed guard or transport')
 started=set()
 def guard(provider,endpoint,body):
  if provider!='vertex' or endpoint not in ('countTokens','gemini-3.8-flash@global'):
   ledger.stop('p0 attempted out-of-scope endpoint');raise Error('endpoint prohibited')
  if verify_p0_binding() is not True:
   ledger.stop('p0 binding drift');raise Error('p0 contract binding mismatch')
  return transport(provider,endpoint,body)
 def factory(case_id,phase,condition,arm):
  key=(case_id,arm)
  if case_id not in case_ids or (phase,condition)!=('p0','no_news') or arm not in ('c','b') or key in started:
   raise Error('p0 factory scope or retry prohibited')
  started.add(key);count=0
  def generate(stage,payload):
   nonlocal count
   if count>=23:raise Error('p0 arm cap')
   count+=1;ident=f'p0:{case_id}:{arm}:{count:02d}';request=forecast.build_request(stage,payload)
   ledger.count('count:'+ident,request,guard)
   raw=ledger.generate('generation:'+ident,request,'count:'+ident,guard)
   return forecast.parse_response(json.loads(raw))
  return generate
 return factory

def stop_on_record_error(ledger,record):
 def wrapper(name,data):
  try:return record(name,data)
  except BaseException:
   try:ledger.stop('p0 record persistence failed')
   finally:ledger.poisoned=True
   raise
 return wrapper
