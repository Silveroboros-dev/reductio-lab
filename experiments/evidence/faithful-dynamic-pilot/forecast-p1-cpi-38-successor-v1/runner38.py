"""Offline-injected P1 runner with individually ledgered status refreshes.

No credentials, network client, scheduling, default verifiers or live authority.
Only confirmed model 429 may receive bounded ledgered retries; unknown outcomes stop.
The caller must provide a reviewed ledger stage supporting both exact bounded
source refresh and model operations. Status is never injected into model inputs.
"""
from __future__ import annotations
import copy,json
import gate,replay,reconstruct
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT/'forecast-orchestrator-v1'))
sys.path.insert(0,str(ROOT/'forecast-controller-v1'))
import orchestrator as o,forecast

class Error(ValueError):pass
class ArmRateLimitExhausted(Exception):pass
class ArmUnparseable(Exception):pass

def run(admission,initial_status,*,ledger,transport,refresh_status,verify_status,verify_admission,verify_ledger,record,clock,pacer,confirmed429,rate_limit_exhausted,sleep,jitter):
 """Run original P1 with no automatic retry, using an externally reviewed stage.

 refresh_status is an injected, separately authorized source operation. It
 MUST record exact request/response/charge, increment the shared source counter,
 enforce ticket/time/identity, and return a normalized snapshot. This function
 cannot establish that external behavior; verify_status must check each real
 receipt/provenance. It may only be called between fully settled effects.
 A non-refreshable stale/resolved status stops the run, preserving partial data.
 """
 if not isinstance(admission,dict) or admission.get('status')!='ready':raise Error('admitted P1 required')
 if not all(callable(x) for x in (transport,refresh_status,verify_status,verify_admission,verify_ledger,record,clock,sleep,jitter)) or not callable(getattr(pacer,'wait',None)) or not callable(getattr(pacer,'ended',None)) or not isinstance(confirmed429,type) or not issubclass(confirmed429,Exception) or not isinstance(rate_limit_exhausted,type) or not issubclass(rate_limit_exhausted,Exception) or confirmed429 is rate_limit_exhausted:
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
 if status.get('source_op_id')!='p1-cpi-status-05' or status.get('response_sha256')!='0f8cff07c0f2288c7df936fc5101c15e324572ab816a9c738195c09aad8c8633':raise Error('recovery initial status drift')
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
   before_source=ledger.summary().get('source_attempts',38)
   if type(before_source) is not int or before_source>=38:raise Error('source attempt limit prevents status refresh')
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
  if s.get('stopped')!=0 or type(s.get('exposure_micro')) is not int or s['exposure_micro']>=60000000 or type(s.get('generation_attempts')) is not int or s['generation_attempts']>=835 or type(s.get('count_attempts')) is not int or s['count_attempts']>=767 or type(s.get('source_attempts')) is not int or s['source_attempts']>38:raise Error('global budget exhausted')
 def retry_effect(kind,operation):
  # Scope the retry catch to one model/count effect only. A source refresh,
  # persistence or scope exception is NEVER converted into a model retry.
  for attempt in range(4):
   before(kind)
   got429=False
   try:
    try:value=operation(attempt)
    except confirmed429:got429=True
    except rate_limit_exhausted:raise ArmRateLimitExhausted('model 429 cap reached') from None
   finally:pacer.ended()
   if got429:
    if attempt>=3:raise Error('ledger returned retryable after max attempts')
    # Received and journaled 429, not an unknown transport effect. The
    # currently reviewed transport does not retain HTTP Retry-After.
    refresh()
    j=jitter()
    if type(j) not in (float,int) or not 0<=j<=1:raise Error('jitter outside [0,1]')
    sleep((2**attempt)*(1+j))
    if not scope():raise Error('scope changed during backoff')
    refresh()
    continue
   # Check market status only after the successful effect was settled, so a
   # stale status cannot convert a captured provider success into uncertainty.
   refresh()
   return value
  raise Error('unreachable attempt loop')
 started=set()
 def factory(phase,condition,arm):
  if phase!='p1' or condition not in ('news','no_news') or arm not in ('c','b') or (condition,arm) in started:raise Error('arm identity or retry violation')
  started.add((condition,arm));n=0
  def generate(stage,payload):
   nonlocal n
   if n>=23:raise Error('arm cap exceeded')
   n+=1;ident=f'p1:case-02:{condition}:{arm}:{n:02d}';request=forecast.build_request(stage,payload)
   def guard(provider,endpoint,raw):
    if provider!='vertex' or endpoint not in ('countTokens','gemini-3.8-flash@global') or not scope():raise Error('provider or scope mismatch')
    return transport(provider,endpoint,raw)
   retry_effect('count',lambda a:ledger.count_attempt('count:'+ident,request,a,guard))
   raw=retry_effect('generation',lambda a:ledger.generate_attempt('generation:'+ident,request,'count:'+ident,a,guard))
   try:return forecast.parse_response(json.loads(raw))
   except (ValueError,TypeError,KeyError,IndexError):raise ArmUnparseable('successful HTTP response failed strict parsing') from None
  return generate

 def durable(name,value):
  # Final independent status observation must follow every model result.
  if name=='p1-frozen':refresh(force=True)
  try:record(name,value)
  except BaseException:
   ledger.stop('p1 persistence failed');raise
 try:
  if not scope():raise Error('unverified stage')
  durable('p1-input',copy.deepcopy(bundle));results={}
  for condition in ('no_news','news'):
   ct=copy.deepcopy(bundle['tasks']['c_'+condition]);bt=copy.deepcopy(bundle['tasks']['b_'+condition])
   if any(ct[k]!=bt[k] for k in ct if k!='prior_forecast'):raise Error('unmatched information')
   if condition=='no_news':
    reconstructed=reconstruct.bundle();c=copy.deepcopy(reconstructed['c_no_news_posthoc']['outcome']);b=copy.deepcopy(reconstructed['b_no_news'])
    if c.get('calls')!=8 or b.get('calls')!=8:raise Error('no-news reconstruction not eight logical calls')
    durable('p1-c-no-news-posthoc-repair',copy.deepcopy(reconstructed['c_no_news_posthoc']))
    durable('p1-b-no-news',copy.deepcopy(b))
    results[condition]={'c':c,'b':b}
    continue
   ce=forecast.FaithfulEngine(factory('p1',condition,'c'),max_calls=23)
   try:c=ce.run(ct)
   except ArmRateLimitExhausted:
    c=ce.outcome('technical_failure','confirmed_429_retry_budget_exhausted')
   except ArmUnparseable:
    c=ce.outcome('technical_failure','unparseable_successful_http_response')
   durable('p1-c-'+condition,copy.deepcopy(c))
   n=c.get('calls')
   if c.get('status')=='technical_failure' or type(n) is not int or not 1<=n<=23:
    results[condition]={'c':c,'b':{'status':'unavailable','reason':'matched_c_did_not_complete'}}
    continue
   be=forecast.BaselineEngine(factory('p1',condition,'b'),matched_calls=n)
   try:b=be.run(bt)
   except ArmRateLimitExhausted:
    b=be.outcome('technical_failure','confirmed_429_retry_budget_exhausted',first=be.first)
   except ArmUnparseable:
    b=be.outcome('technical_failure','unparseable_successful_http_response',first=be.first)
   durable('p1-b-'+condition,copy.deepcopy(b))
   results[condition]={'c':c,'b':b}
  result={'schema':'forecast-p1-result-v1','input_sha256':bundle_sha,'results':results,
   'limitation':'C/no-news required a post-hoc one-character JSON format repair; its strict first output failed. B matched to eight logical C calls. B-first p1 is conditional on B-matched p0; exhausted 429 arms remain partial.'}
  durable('p1-frozen',copy.deepcopy(result))
  summary={'schema':'resumed-cpi-p1-summary-v1','p0_receipt_sha256':admission['p0_receipt_sha256'],
   'p1_input_sha256':bundle_sha,'completed_at_utc':clock(),'status_observations_during_run':status_count,
   'status_after_last_result_sha256':gate.sha(gate.canonical(status)),
   'model_results':result,'limitation':'C/no-news is post-hoc format-repaired, not strict compliant. Status observations do not prove continuous unresolved state; upstream cache age is unknown. BEA timing assumes embargo respected. Independent outcome review required.'}
  record('p1-summary',summary);return summary
 except BaseException:
  if not ledger.summary().get('stopped'):ledger.stop('p1 interrupted or market state unverified; no automatic retry')
  raise
