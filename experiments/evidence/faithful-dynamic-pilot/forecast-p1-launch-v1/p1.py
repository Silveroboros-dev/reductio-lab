"""Offline prospective p1 gate and injected model executor.

No credentials, network, ledger open, authority, clocks, or news on import.
Callers must separately challenge exact inputs, witnesses and effect boundary.
"""
import copy,datetime as dt,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT/'forecast-orchestrator-v1'))
sys.path.insert(0,str(ROOT/'forecast-controller-v1'))
import orchestrator as o,forecast

class Error(ValueError):pass

def _pending(reason):return {'status':'pending','reason':reason}

def prepare(prepared,p0,news,status,*,t1,verify_p0,verify_news,verify_status,max_status_age_seconds=300):
 """Prepare without effects; missing news/status/prior remains pending.

 News reviewer verifies exact source bytes, event publication time and semantic
 novelty, not just timestamps. Status reviewer verifies venue observation,
 identity and receipt, with provenance and uncertainty. P0 reviewer binds each
 prior to its own arm, case, source contract, completed ledger and durable files.
 """
 if not news:return _pending('no_eligible_new_event')
 if status is None:return _pending('unresolved_market_not_verified')
 if not isinstance(p0,dict):return _pending('p0_not_available')
 for arm in ('c','b'):
  x=p0.get(arm)
  if not isinstance(x,dict) or x.get('status') not in ('proposal','unknown') or not isinstance(x.get('result'),dict):return _pending('own_prior_unavailable_'+arm)
 c,b=p0['c'],p0['b']
 if type(c.get('calls')) is not int or not 1<=c['calls']<=23 or b.get('calls')!=c['calls']:
  return _pending('matched_p0_calls_unavailable')
 if type(max_status_age_seconds) is not int or not 0<max_status_age_seconds<=300:raise Error('bad status freshness threshold')
 if not callable(verify_p0) or not callable(verify_news) or not callable(verify_status):raise Error('review verifiers required')
 case=prepared.get('case',{});ticker=case.get('contract_id')
 if not isinstance(status,dict):return _pending('market_status_invalid')
 if (status.get('contract_id')!=ticker or status.get('state')!='active' or status.get('result')!='' or
  status.get('rules_primary')!=case.get('rules_primary') or status.get('rules_secondary')!=case.get('rules_secondary')):
  return _pending('market_not_verified_open_with_same_rules')
 try:
  t=o.instant(t1);observed=o.instant(status.get('observed_at_utc'));captured=o.instant(status.get('captured_at_utc'))
  frozen=o.instant(p0['durable_before_utc'])
 except (o.EligibilityError,KeyError):return _pending('market_or_p0_timestamp_missing')
 if not (frozen<=observed<=captured<=t) or (t-captured).total_seconds()>max_status_age_seconds:
  return _pending('market_status_not_fresh_or_time_invalid')
 # An observation predating the news cannot establish that the same event did
 # not resolve the market. Verify the market after the evidence was captured.
 try:
  if not isinstance(news,list) or observed < max(o.instant(e['captured_at_utc']) for e in news):
   return _pending('market_status_predates_news_capture')
 except (KeyError,TypeError,ValueError,o.EligibilityError):
  return _pending('news_timestamp_missing')
 if verify_status(copy.deepcopy(status),copy.deepcopy(case),t1) is not True:return _pending('market_unresolved_unconfirmed')
 try:
  bdl=o.prepare_p1(prepared,p0,news,t1=t1,verify_p0=verify_p0,verify_intervention=verify_news,
   verify_unresolved=lambda exact_case,at:exact_case==case and at==t1)
 except o.EligibilityError as exc:
  return _pending('p1_temporal_or_evidence_ineligible: '+str(exc))
 return {'status':'ready','bundle':bdl,'bundle_sha256':o.sha(o.canonical(bdl)),
  'status_evidence_sha256':o.sha(o.canonical(status)),'status_observed_at_utc':status['observed_at_utc'],
  'status_captured_at_utc':status['captured_at_utc'],'max_status_age_seconds':max_status_age_seconds,
  'limitation':'Observed active status is not a guarantee against subsequent early resolution.'}

def generator_factory(ledger,*,case_id,transport,verify_scope,verify_ledger):
 """Pair every model call with exact count via authorized model-only ledger."""
 if not isinstance(case_id,str) or not case_id or ':' in case_id or not callable(transport) or not callable(verify_scope) or not callable(verify_ledger):raise Error('scope required')
 started=set()
 def guard(provider,endpoint,request):
  if provider!='vertex' or endpoint not in ('countTokens','gemini-3.8-flash@global') or verify_scope() is not True:
   ledger.stop('p1 model scope drift');raise Error('p1 model endpoint or binding invalid')
  return transport(provider,endpoint,request)
 def factory(phase,condition,arm):
  key=(condition,arm)
  if phase!='p1' or condition not in ('news','no_news') or arm not in ('c','b') or key in started:raise Error('phase, arm, or retry invalid')
  started.add(key);n=0
  def generate(stage,payload):
   nonlocal n
   if n>=23:raise Error('per-arm call cap')
   if verify_ledger(ledger) is not True:raise Error('reviewed p1-only ledger stage required')
   s=ledger.summary()
   if (s.get('stopped')!=0 or type(s.get('exposure_micro')) is not int or s['exposure_micro']>=60000000 or
    type(s.get('generation_attempts')) is not int or s['generation_attempts']>=835 or
    type(s.get('count_attempts')) is not int or s['count_attempts']>=767 or
    type(s.get('source_attempts')) is not int or s['source_attempts']>28):raise Error('global budget unavailable')
   n+=1;ident=f'p1:{case_id}:{condition}:{arm}:{n:02d}'
   req=forecast.build_request(stage,payload)
   ledger.count('count:'+ident,req,guard)
   raw=ledger.generate('generation:'+ident,req,'count:'+ident,guard)
   return forecast.parse_response(__import__('json').loads(raw))
  return generate
 return factory

def run(admission,*,verify_bundle,verify_ledger,ledger,transport,record,clock):
 """Execute reviewed ready bundle only; exceptions stop and never retry."""
 if not isinstance(admission,dict) or admission.get('status')!='ready':return _pending('p1_not_ready')
 if not all(map(callable,(verify_bundle,verify_ledger,transport,record,clock))):raise Error('callbacks required')
 b=admission['bundle'];digest=admission['bundle_sha256']
 if o.sha(o.canonical(b))!=digest or verify_bundle(copy.deepcopy(admission)) is not True:raise Error('p1 review or bundle mismatch')
 captured=o.instant(admission['status_captured_at_utc']);now=o.instant(clock())
 if now<o.instant(b['t1']) or (now-captured).total_seconds()>admission['max_status_age_seconds']:
  return _pending('market_status_stale_at_dispatch')
 def scope():
  if verify_bundle(copy.deepcopy(admission)) is not True:return False
  now2=o.instant(clock())
  return now2>=o.instant(b['t1']) and (now2-captured).total_seconds()<=admission['max_status_age_seconds']
 if verify_ledger(ledger) is not True:raise Error('reviewed p1-only ledger stage required')
 factory=generator_factory(ledger,case_id=b['tasks']['c_news']['case_id'],transport=transport,verify_scope=scope,verify_ledger=verify_ledger)
 def durable(name,value):
  try:return record(name,value)
  except BaseException:
   try:ledger.stop('p1 persistence failed')
   finally:ledger.poisoned=True
   raise
 try:
  return o.run_p1(b,expected_bundle_sha256=digest,verify_bundle=lambda _:scope(),generator_factory=factory,record=durable)
 except BaseException:
  try:ledger.stop('p1 interrupted; no automatic retry')
  finally:ledger.poisoned=True
  raise
