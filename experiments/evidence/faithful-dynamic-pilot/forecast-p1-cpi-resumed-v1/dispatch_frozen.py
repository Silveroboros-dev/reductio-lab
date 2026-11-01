"""Model dispatcher for independently frozen CPI P1 input; no default effects.

The actual event, source receipts and market authenticity must be checked by
reviewers before a caller creates a frozen contract and activates stages. This
module supplies no credentials, transport or default verification callbacks.
"""
import copy,json
import gate,orchestrate_retry,conditional_news
from pathlib import Path
GATEWAY_AMENDMENT_SHA="09bdd18e60aedc4013625fa7718a400ce6197370137b11ac9423b6b747f51980"
GATEWAY_AMENDMENT=Path(__file__).resolve().parent.parent/"forecast-cpi-p1-gateway-observation-amendment-20261029-v1.json"
class Error(ValueError):pass

def expected(prefreeze):
 if not isinstance(prefreeze,dict) or prefreeze.get('schema')!='cpi-p1-prefreeze-v1' or prefreeze.get('admission',{}).get('status')!='ready':raise Error('ready prefreeze required')
 admission=prefreeze['admission'];ops=prefreeze.get('remaining_status_operations')
 if not isinstance(ops,list) or not ops or len(ops)>8:raise Error('bounded future status operations required')
 if gate.sha(gate.canonical(admission.get('bundle')))!=admission.get('bundle_sha256'):raise Error('invalid admission bundle')
 return {'schema':'cpi-p1-frozen-dispatch-v1','status':'frozen','case_id':'case-02',
  'admission_sha256':gate.sha(gate.canonical(admission)),'news_sha256':gate.sha(gate.canonical(prefreeze['news'])),
  'initial_status_sha256':gate.sha(gate.canonical(prefreeze['initial_status'])),
  'status_operations_sha256':gate.sha(gate.canonical(ops)),'t1':prefreeze['t1'],
  'p0_receipt_sha256':admission['p0_receipt_sha256'],
  'conditional_release_amendment_sha256':conditional_news.AMENDMENT_SHA,
  'gateway_observation_amendment_sha256':GATEWAY_AMENDMENT_SHA,
  'arms':['c_no_news','b_no_news','c_news','b_news'],'max_additional_model_attempts':20,
  'max_retries_per_operation':3,'source_retry':False,'canary':False}

def run(*,prefreeze,contract_bytes,contract_sha256,verify_contract,model_stage,source_stage,
        model_transport,source_transport,decode_status,verify_operation,verify_news,verify_status,
        verify_admission,verify_ledger,record,clock,pacer,confirmed429,rate_limit_exhausted,sleep,jitter):
 if not isinstance(contract_bytes,bytes) or gate.sha(contract_bytes)!=contract_sha256 or not callable(verify_contract) or verify_contract(contract_bytes) is not True:raise Error('frozen dispatch challenge missing')
 try:contract=json.loads(contract_bytes)
 except Exception as exc:raise Error('invalid frozen dispatch') from exc
 if contract!=expected(prefreeze) or contract_bytes!=gate.canonical(contract) or gate.sha(GATEWAY_AMENDMENT.read_bytes())!=GATEWAY_AMENDMENT_SHA:raise Error('frozen dispatch mismatch')
 if getattr(model_stage,'kind',None)!='model' or getattr(source_stage,'kind',None)!='source' or getattr(model_stage,'account',None) is not getattr(source_stage,'account',None) or getattr(source_stage,'account',None) is None:raise Error('stages do not share account')
 summary=source_stage.account.summary();ops=prefreeze['remaining_status_operations']
 if summary.get('stopped')!=0 or type(summary.get('source_attempts')) is not int or len(ops)>28-summary['source_attempts']:raise Error('shared source budget unavailable')
 admission=copy.deepcopy(prefreeze['admission'])
 def reviewed(candidate):return candidate==admission and callable(verify_admission) and verify_admission(candidate) is True
 return orchestrate_retry.run(news=copy.deepcopy(prefreeze['news']),initial_status=copy.deepcopy(prefreeze['initial_status']),t1=prefreeze['t1'],
  model_stage=model_stage,source_stage=source_stage,status_operations=copy.deepcopy(ops),model_transport=model_transport,
  source_transport=source_transport,decode_status=decode_status,verify_operation=verify_operation,verify_news=verify_news,
  verify_status=verify_status,verify_admission=reviewed,verify_ledger=verify_ledger,record=record,clock=clock,pacer=pacer,
  confirmed429=confirmed429,rate_limit_exhausted=rate_limit_exhausted,sleep=sleep,jitter=jitter)
