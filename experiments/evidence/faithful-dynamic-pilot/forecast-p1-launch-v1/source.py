"""Bounded, injected post-p0 source effects; no activity on import.

The source-only ledger, one-shot transport and reviewer are provided by a later
separately challenged stage. The contract cannot be frozen until p0 settles.
"""
import copy,datetime as dt,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT/'forecast-orchestrator-v1'))
import orchestrator as o
class Error(ValueError):pass

def execute(contract,*,ledger,transport,record_raw,verify_contract,verify_completed_p0,clock):
 """Run exact pre-reviewed source operations once through budget ledger.

 record_raw must create-only durably persist both raw response and receipt.
 Unknown effect outcomes stop the stage, preserve reservation and never retry.
 Do not supply the prior accounting-only ledger: this requires an independently
 activated source-only successor wrapper, not yet implemented by p0.
 """
 if not isinstance(contract,dict) or contract.get('schema')!='forecast-p1-source-plan-v1' or contract.get('status')!='frozen':raise Error('frozen source plan required')
 if not all(map(callable,(transport,record_raw,verify_contract,verify_completed_p0,clock))):raise Error('review and effect callbacks required')
 if verify_contract(copy.deepcopy(contract)) is not True or verify_completed_p0(copy.deepcopy(contract)) is not True:raise Error('source or p0 review unavailable')
 operations=contract.get('operations');usage=ledger.summary()
 if usage!=contract.get('starting_usage') or usage.get('stopped')!=0:raise Error('ledger starting state mismatch')
 if not isinstance(operations,list) or not operations or len(operations)>28-usage['source_attempts']:raise Error('source attempt budget exceeded')
 if usage['exposure_micro']>60000000 or usage['generation_attempts']>835 or usage['count_attempts']>767:raise Error('global limits exceeded')
 ids=[];reserved=0
 for x in operations:
  if not isinstance(x,dict) or set(x)!={'id','provider','endpoint','payload','ticket'}:raise Error('source operation schema invalid')
  ident=x['id'];ticket=x['ticket'];raw=o.canonical(x['payload'])
  if (not isinstance(ident,str) or not ident.startswith('p1:') or ident in ids or not isinstance(ticket,dict) or
   ticket.get('id')!=ident or ticket.get('provider')!=x['provider'] or ticket.get('endpoint')!=x['endpoint'] or
   ticket.get('request_sha256')!=o.sha(raw) or type(ticket.get('max_micro')) is not int or not 0<=ticket['max_micro']<=150000):raise Error('source ticket binding invalid')
  if o.instant(ticket.get('expires_utc'))<=o.instant(clock()):raise Error('source quote expired')
  ids.append(ident);reserved+=ticket['max_micro']
 if usage['exposure_micro']+reserved>60000000:raise Error('reserved sources exceed global budget')
 if o.instant(clock())<o.instant(contract.get('not_before_utc')):raise Error('source stage too early')
 records=[]
 for x in operations:
  raw=o.canonical(x['payload'])
  def guarded(provider,endpoint,body):
   if (provider,endpoint,body)!=(x['provider'],x['endpoint'],raw) or verify_contract(copy.deepcopy(contract)) is not True:
    ledger.stop('p1 source contract drift');raise Error('source transport scope drift')
   return transport(provider,endpoint,body)
  try:
   response=ledger.source(x['id'],x['provider'],x['endpoint'],raw,x['ticket'],guarded)
   receipt=ledger.receipt(x['id'])
   if (not isinstance(response,bytes) or receipt.get('state')!='succeeded' or receipt.get('http_status')!=200 or
    receipt.get('response_hash')!=o.sha(response) or receipt.get('actual_micro') is None):raise Error('source settlement or bytes unavailable')
   record_raw(x['id'],response,copy.deepcopy(receipt))
   records.append({'id':x['id'],'response_sha256':o.sha(response),'started_at_utc':receipt['started_at_utc'],
    'completed_at_utc':receipt['completed_at_utc'],'actual_micro':receipt['actual_micro']})
  except BaseException:
   try:ledger.stop('p1 source interruption or failed persistence; do not retry')
   finally:ledger.poisoned=True
   raise
 return {'status':'completed','records':records,'ledger':ledger.summary(),
  'qualification':'Raw capture alone does not establish event publication time or unresolved market.'}
