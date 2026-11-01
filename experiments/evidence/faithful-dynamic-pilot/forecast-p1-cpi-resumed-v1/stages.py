"""Compose separate reviewed CPI source/model stages without mixed privileges.

No credentials, transport, provider calls or default authorization. The source
stage saves every exact response and charge before returning; a separately
reviewed decoder and status verifier must bind venue content and timestamps.
"""
from __future__ import annotations
import copy
import gate

class Error(ValueError):pass

class ModelFacade:
 def __init__(self,model_stage,source_stage):
  if getattr(model_stage,'kind',None)!='model' or getattr(source_stage,'kind',None)!='source' or getattr(model_stage,'account',None) is None or model_stage.account is not source_stage.account:raise Error('stages must share a reviewed account')
  self.model=model_stage;self.source=source_stage;self.account=model_stage.account
 def summary(self):return self.account.summary()
 def stop(self,reason):return self.account.stop(reason)
 def count(self,*args):return self.model.count(*args)
 def generate(self,*args):return self.model.generate(*args)
 def count_attempt(self,*args):return self.model.count_attempt(*args)
 def generate_attempt(self,*args):return self.model.generate_attempt(*args)

def status_refresher(source_stage,operations,*,transport,decode,verify_operation,record):
 """One-shot pre-registered status reads; never silently retry a failed op.

 Source stage independently validates each ticket, expiry and exact request.
 Every source response must already be in its common ledger before decoder use.
 A status observation is time-stamped at local receipt, not publication time.
 The decoder does not independently attest that an upstream venue is genuine.
 """
 if getattr(source_stage,'kind',None)!='source' or not isinstance(operations,list) or not 1<=len(operations)<=12 or not all(callable(x) for x in (transport,decode,verify_operation,record)):raise Error('source stage, operations and callbacks required')
 ids=[]
 for op in operations:
  if not isinstance(op,dict) or op.get('kind')!='status_refresh' or not isinstance(op.get('ticket'),dict) or op['ticket'].get('category')!='market' or op['ticket'].get('provider')!='orthogonal' or op['ticket'].get('endpoint')!='/v1/run' or not isinstance(op.get('payload'),dict):raise Error('status operation shape')
  ident=op['ticket'].get('id')
  if not isinstance(ident,str) or not ident or any(ch not in 'abcdefghijklmnopqrstuvwxyz0123456789-' for ch in ident) or ident in ids or op['ticket'].get('request_sha256')!=gate.sha(gate.canonical(op['payload'])) or verify_operation(copy.deepcopy(op)) is not True:raise Error('unreviewed or duplicate status operation')
  ids.append(ident)
 cursor=0
 def refresh():
  nonlocal cursor
  if cursor>=len(operations):raise Error('status operation allowlist exhausted')
  op=copy.deepcopy(operations[cursor]);cursor+=1
  ticket=op['ticket'];rawreq=gate.canonical(op['payload']);ident=ticket['id']
  raw=source_stage.source(ident,'orthogonal','/v1/run',rawreq,ticket,transport)
  receipt=source_stage.receipt(ident)
  if (not isinstance(raw,bytes) or receipt.get('id')!=ident or receipt.get('kind')!='source' or receipt.get('state')!='succeeded' or receipt.get('http_status')!=200 or
   receipt.get('request_hash')!=gate.sha(rawreq) or receipt.get('response_hash')!=gate.sha(raw) or bytes(receipt.get('response',b''))!=raw or type(receipt.get('actual_micro')) is not int or receipt['actual_micro']<0):raise Error('status response receipt mismatch')
  status=decode(raw,copy.deepcopy(receipt),copy.deepcopy(op))
  if not isinstance(status,dict) or status.get('contract_id')!=gate.TICKER:raise Error('status decoder contract mismatch')
  finished=receipt.get('completed_at_utc')
  try:gate.o.instant(finished)
  except gate.o.EligibilityError:raise Error('source completion timestamp missing') from None
  status=copy.deepcopy(status);status['observed_at_utc']=finished;status['captured_at_utc']=finished
  status['source_op_id']=ident;status['response_sha256']=receipt['response_hash']
  record('source-'+ident,{'id':ident,'request_sha256':receipt['request_hash'],'response_sha256':receipt['response_hash'],
   'started_at_utc':receipt['started_at_utc'],'completed_at_utc':finished,'actual_micro':receipt['actual_micro']})
  return status
 return refresh
