"""Offline-injected P1 runner with individually ledgered status refreshes.

No credentials, network client, scheduling, default verifiers or live authority.
The caller must provide a reviewed ledger stage supporting both exact bounded
source refresh and model operations. Status is never injected into model inputs.
"""
from __future__ import annotations
import copy,json
import gate
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT/'forecast-orchestrator-v1'))
sys.path.insert(0,str(ROOT/'forecast-controller-v1'))
import orchestrator as o,forecast

class Error(ValueError):pass

def run(admission,initial_status,*,ledger,transport,refresh_status,verify_status,verify_admission,verify_ledger,record,clock,pacer):
 """Run original P1 with no automatic retry, using an externally reviewed stage.

 refresh_status is an injected, separately authorized source operation. It
 MUST record exact request/response/charge, increment the shared source counter,
 enforce ticket/time/identity, and return a normalized snapshot. This function
 cannot establish that external behavior; verify_status must check each real
 receipt/provenance. It may only be called between fully settled effects.
 A non-refreshable stale/resolved status stops the run, preserving partial data.
 """
 if not isinstance(admission,dict) or admission.get('status')!='ready':raise Error('admitted P1 required')
 if not all(callable(x) for x in (transport,refresh_status,verify_status,verify_admission,verify_ledger,record,clock)) or not callable(getattr(pacer,'wait',None)) or not callable(getattr(pacer,'ended',None)):
  raise Error('reviewed callbacks and pacer required')
 bundle=copy.deepcopy(admission.get('bundle'));bundle_sha=admission.get('bundle_sha256')
 if gate.sha(gate.canonical(bundle))!=bundle_sha or verify_admission(copy.deepcopy(admission)) is not True:raise Error('admission binding mismatch')
 if admission.get('p0_receipt_sha256')!=gate.HASHES['forecast-p0-429-resume-results-20261029-01/case-02-p0-receipt.json'] or admission.get('p0_ledger_sha256')!=gate.HASHES['forecast-p0-429-resume-ledger-20261029-01/ledger.sqlite3']:raise Error('p0 binding mismatch')
 if admission.get('source_correction_sha256')!=gate.HASHES['kalshi-user-message-transcription-correction-20261029-v1.json']:raise Error('user relay correction not bound')
 checked=gate.verify_p0();case=checked['prepared']['case'];news=bundle['tasks']['c_news']['evidence']
 news=[x for x in news if x.get('kind')=='news']
 if not news:raise Error('news absent')
 if set(bundle.get('tasks',{}))!={'c_news','c_no_news','b_news','b_no_news'}:raise Error('P1 task set mismatch')
 for arm in ('c','b'):
  baseline=copy.deepcopy(checked['prepared']['task'])
  baseline.update(phase='p1',condition='no_news',as_of_utc=bundle['t1'],prior_forecast=copy.deepcopy(checked['p0_frozen'][arm]['result']))
  treated=copy.deepcopy(baseline);treated['condition']='news';treated['evidence']+=copy.deepcopy(news)
  if bundle['tasks'][arm+'_no_news']!=baseline or bundle['tasks'][arm+'_news']!=treated:raise Error('P1 prior, treatment, or information set mismatch')
 if bundle.get('intervention_sha256')!=gate.sha(gate.canonical(news)):raise Error('news digest mismatch')
 last_news=max(o.instant(x['captured_at_utc']) for x in news)
 status=copy.deepcopy(initial_status);status_count=0
 if gate.sha(gate.canonical(status))!=admission['status_evidence_sha256']:raise Error('initial status drift')
 def scope():
  try:
   return verify_admission(copy.deepcopy(admission)) is True and verify_ledger(ledger) is True and o.instant(clock())>=o.instant(bundle['t1']) and o.instant(clock())<o.instant(case['close_time_utc'])
  except Exception:return False
 def valid_status(candidate,at):
  if not isinstance(candidate,dict) or candidate.get('contract_id')!=gate.TICKER or candidate.get('state')!='active' or candidate.get('result')!='' or candidate.get('rules_primary')!=case['rules_primary'] or candidate.get('rules_secondary')!=case['rules_secondary']:return False
  try:observed=o.instant(candidate.get('observed_at_utc'));captured=o.instant(candidate.get('captured_at_utc'));ts=o.instant(at)
  except o.EligibilityError:return False
  if not (last_news<=observed<=captured<=ts) or not 0<=(ts-captured).total_seconds()<=300:return False
  return verify_status(copy.deepcopy(candidate),copy.deepcopy(case),at) is True
 def refresh(force=False):
  nonlocal status,status_count
  if not scope():raise Error('p1 scope or deadline invalid')
  at=clock()
  # Refresh early enough to leave room for the required 20s inter-call wait.
  try:age=(o.instant(at)-o.instant(status['captured_at_utc'])).total_seconds()
  except (KeyError,o.EligibilityError):age=301
  if force or age>260 or not valid_status(status,at):
   before_source=ledger.summary().get('source_attempts',28)
   if type(before_source) is not int or before_source>=28:raise Error('source attempt limit prevents status refresh')
   pacer.wait(scope)
   try:updated=refresh_status()
   finally:pacer.ended()
   if ledger.summary().get('source_attempts')!=before_source+1:raise Error('status refresh did not record one source operation')
   at=clock()
   if not valid_status(updated,at):raise Error('refreshed market status not valid')
   status=copy.deepcopy(updated);status_count+=1
   record(f'status-{status_count:04d}',{'status_sha256':gate.sha(gate.canonical(status)),'observed_at_utc':status['observed_at_utc'],'captured_at_utc':status['captured_at_utc']})
  if not valid_status(status,clock()):raise Error('market status is invalid, stale or unresolved not confirmed')
 def before(kind):
  refresh()
  pacer.wait(scope)
  # A wait or status refresh can consume the remaining 300-second window.
  refresh()
  pacer.wait(scope)
  if not valid_status(status,clock()):raise Error('market status stale at dispatch')
  s=ledger.summary()
  if s.get('stopped')!=0 or type(s.get('exposure_micro')) is not int or s['exposure_micro']>=60000000 or type(s.get('generation_attempts')) is not int or s['generation_attempts']>=835 or type(s.get('count_attempts')) is not int or s['count_attempts']>=767 or type(s.get('source_attempts')) is not int or s['source_attempts']>28:raise Error('global budget exhausted')
 def effect(kind,operation):
  before(kind)
  try:value=operation()
  finally:pacer.ended()
  # Check after settlement, never throw from the transport after actual success.
  refresh()
  return value
 started=set()
 def factory(phase,condition,arm):
  if phase!='p1' or condition not in ('news','no_news') or arm not in ('c','b') or (condition,arm) in started:raise Error('arm identity or retry violation')
  started.add((condition,arm));n=0
  def generate(stage,payload):
   nonlocal n
   if n>=23:raise Error('arm cap exceeded')
   n+=1;ident=f'p1:case-02:{condition}:{arm}:{n:02d}';request=forecast.build_request(stage,payload)
   def guard(provider,endpoint,raw):
    # This check is after ledger start; do not run network when wrong provider.
    if provider!='vertex' or endpoint not in ('countTokens','gemini-3.8-flash@global') or not scope():raise Error('provider or scope mismatch')
    return transport(provider,endpoint,raw)
   effect('count',lambda:ledger.count('count:'+ident,request,guard))
   raw=effect('generation',lambda:ledger.generate('generation:'+ident,request,'count:'+ident,guard))
   return forecast.parse_response(json.loads(raw))
  return generate
 def durable(name,value):
  # Final independent status observation must follow every model result.
  if name=='p1-frozen':refresh(force=True)
  try:record(name,value)
  except BaseException:
   ledger.stop('p1 persistence failed');raise
 try:
  if not scope():raise Error('unverified stage')
  result=o.run_p1(bundle,expected_bundle_sha256=bundle_sha,verify_bundle=lambda _:scope(),generator_factory=factory,record=durable)
  # Each arm result has its own output; errors/unknowns remain visible.
  summary={'schema':'resumed-cpi-p1-summary-v1','p0_receipt_sha256':admission['p0_receipt_sha256'],
   'p1_input_sha256':bundle_sha,'completed_at_utc':clock(),'status_observations_during_run':status_count,
   'status_after_last_result_sha256':gate.sha(gate.canonical(status)),
   'model_results':result,'limitation':'Status observations do not prove continuous unresolved state; independent outcome review is required.'}
  record('p1-summary',summary);return summary
 except BaseException:
  if not ledger.summary().get('stopped'):ledger.stop('p1 interrupted or market state unverified; no automatic retry')
  raise
