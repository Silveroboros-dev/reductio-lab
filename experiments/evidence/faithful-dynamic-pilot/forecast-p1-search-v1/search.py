"""Exactly two reviewed p1 candidate searches. No calls on import or freeze.

No automatic fetch, market check, model, retry, or automatic news admission.
"""
import datetime as dt,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
for d in ('forecast-p1-search-v1','forecast-source-only-v1','forecast-p0-final-two-v1','forecast-p0-launch-v1','forecast-seed-launch-v1','forecast-stopped-successor-v1'):
 sys.path.insert(0,str(ROOT/d))
import source_only,source_only_launch,pace,dispatch as prior,launcher as seed,accounting_launch

ACCOUNT_SHA='cf2daf46cdbe2eed6309446bac2a524febd7016d2faef7fe56338c698eb5bc8f'
PRICE_SHA='5d71ca0d76901f010312c67a032fb73a84e79d680ed6a4657ceb6d61ceae2fb5'
PRICE=ROOT/'forecast-p1-search-price-observation-20261029-v1.json'
CONTRACT=ROOT/'forecast-p1-search-contract-20261029-v1.json'
PACKET=ROOT/'forecast-p1-search-challenge-packet-v1.json'
RECEIPT=ROOT/'forecast-p1-search-challenge-receipt-v1.json'
OUTPUT=ROOT/'forecast-p1-search-results-20261029-01'
P0=ROOT/'forecast-p0-final-two-results-20261029-01/00-p0-receipt.json'
FROZEN=ROOT/'forecast-p0-final-two-results-20261029-01/00-p0-frozen.json'
ACCOUNT=source_only_launch.CONTRACT;APACKET=source_only_launch.PACKET;ARECEIPT=source_only_launch.RECEIPT
ACCOUNT_LOCAL=source_only_launch.LOCAL_RECEIPT;LEDGER=source_only_launch.LEDGER
CAPS=prior.CAPS;DURABLE='2026-10-29T11:24:43.776392+00:00'
OPS=[('p1-openai-official-you',{'api':'you/search','path':'/v1/search','body':{'query':'"Astra 6.1" OpenAI announcement planned public release','count':5,'include_domains':['openai.com']},'query':{}},5000),
 ('p1-openai-related-serper-news',{'api':'serper','path':'/news','body':{'q':'OpenAI model release plans deployment infrastructure compute availability November 2026'},'query':{}},2000)]
FILES=('forecast-p1-search-v1/search.py','forecast-p0-final-two-v1/pace.py',
 'forecast-p1-search-price-observation-20261029-v1.json',
 'forecast-source-only-accounting-contract-20261029-v1.json','forecast-source-only-accounting-challenge-packet-v1.json',
 'forecast-source-only-accounting-challenge-receipt-v1.json','forecast-source-only-accounting-receipt-20261029.json',
 'forecast-p0-final-two-results-20261029-01/00-p0-receipt.json','forecast-p0-final-two-results-20261029-01/00-p0-frozen.json',
 'forecast-p0-final-two-results-20261029-01/00-p0-input.json')
class Error(ValueError):pass
read=prior.read;obj=prior.obj;sha=prior.sha;canonical=prior.canonical;now=prior.now

def components():
 return {rel:sha(read(ROOT/rel)) for rel in sorted(set(FILES)|set(source_only_launch.FILES))}

def quote():
 raw=read(PRICE);q=obj(raw)
 if (sha(raw)!=PRICE_SHA or q.get('schema')!='p1-search-ui-price-observation-v1' or
  {(e.get('api'),e.get('path'),e.get('rate_usd')) for e in q.get('observations',[])}!=
   {('serper','/news','0.002 per call'),('you/search','/v1/search','0.005 per call')}):raise Error('price observation mismatch')
 observed=prior.p.o.instant(q['observed_at_utc']);expires=observed+dt.timedelta(minutes=15)
 if not observed<=prior.p.o.instant(now())<expires:raise Error('source quote expired or not yet observed')
 return raw,expires.isoformat()

def p0_binding():
 raw=read(P0);r=obj(raw);frozen=read(FROZEN);f=obj(frozen)
 if (r.get('schema')!='forecast-p0-v1' or r.get('durable_before_utc')!=DURABLE or
  r.get('frozen_content_sha256')!=sha(frozen) or {k:v for k,v in r.items() if k not in ('frozen_content_sha256','durable_before_utc')}!=f or
  any(r.get(a,{}).get('status')!='proposal' or not isinstance(r[a].get('result'),dict) or r[a].get('calls')!=8 for a in ('c','b'))):raise Error('case03 p0 lineage incomplete')
 if source_only.inspect()['completed_pair']!='case-03':raise Error('case03 accounting not settled')
 return {'receipt_sha256':sha(raw),'frozen_sha256':sha(frozen),'durable_before_utc':DURABLE,'case_id':'case-03'}

def account():
 _,ar,ap,at=source_only_launch.verify(ACCOUNT,APACKET,ARECEIPT,ACCOUNT_SHA)
 r=obj(read(ACCOUNT_LOCAL));s=r.get('ledger',{})
 if (r.get('schema')!='forecast-source-only-accounting-receipt-v1' or r.get('contract_sha256')!=ACCOUNT_SHA or
  r.get('challenge_sha256')!=sha(ap) or r.get('challenge_receipt_sha256')!=sha(at) or r.get('ledger_root')!=str(LEDGER) or
  (s.get('stopped'),s.get('exposure_micro'),s.get('generation_attempts'),s.get('count_attempts'),s.get('source_attempts'))!=(0,1882731,274,206,14) or
  (s.get('prior_http400_charge_unknown_retained_micro'),s.get('prior_http429_charge_unknown_retained_micro'),s.get('prior_http429b_charge_unknown_retained_micro'),s.get('prior_http429c_charge_unknown_retained_micro'))!=(150000,86016,86016,86016)):
  raise Error('accounting state mismatch')
 return r

def operations():
 _,expires=quote();out=[]
 for ident,payload,expected in OPS:
  ticket={'id':ident,'provider':'orthogonal','endpoint':'/v1/run','request_sha256':sha(canonical(payload)),
   'max_micro':150000,'evidence_sha256':PRICE_SHA,'expires_utc':expires,'category':'news' if payload['api']=='serper' else 'search','settlement':'orthogonal_price_cents'}
  out.append({'ticket':ticket,'payload':payload})
 return out

def prepare_contract():
 if Path.cwd().resolve()!=ROOT or OUTPUT.exists():raise Error('context or output mismatch')
 a=account();p0=p0_binding();ops=operations()
 c={'schema':'faithful-forecast-source-only-run-v1','status':'frozen','caps':CAPS,'accounting_contract_sha256':ACCOUNT_SHA,
  'accounting_receipt_sha256':sha(read(ACCOUNT_LOCAL)),'ledger_root':str(LEDGER),'starting_usage':a['ledger'],
  'model_reads':0,'no_retry':True,'operations':ops,'expected_actual_micro':[5000,2000],
  'execution_context':{'cwd':str(ROOT),'output_root':str(OUTPUT)},'p0_binding':p0,
  'limits':{'search_calls':2,'source_reserve_micro_per_call':150000,'no_fetch':True,'no_status':True,'no_model':True,
   'pacing_min_seconds':20,'pacing_scope':'all_provider_calls'},'component_bindings':components(),
  'qualification':'Raw source candidates only; dates, factuality, relevance and unresolved market independently unverified.'}
 seed.put(CONTRACT,c);return sha(read(CONTRACT))

def verify(expected_sha):
 cr,pr,rr=map(read,(CONTRACT,PACKET,RECEIPT));c,packet,receipt=map(obj,(cr,pr,rr));d=packet.get('internal_digest');w=packet.get('context_binding',{})
 if (sha(cr)!=expected_sha or c.get('schema')!='faithful-forecast-source-only-run-v1' or c.get('status')!='frozen' or
  c.get('caps')!=CAPS or c.get('accounting_contract_sha256')!=ACCOUNT_SHA or c.get('ledger_root')!=str(LEDGER) or
  c.get('model_reads')!=0 or c.get('no_retry') is not True or packet.get('schema_version')!='eval_contract_challenge_packet_v1' or
  packet.get('overall_state')!='ready' or packet.get('witness',{}).get('identity')!='p1_search_witness' or
  packet.get('witness',{}).get('mode')!='read_only_offline' or packet.get('challenged_contract',{}).get('raw_sha256')!=expected_sha or
  d!=sha(canonical({k:v for k,v in packet.items() if k!='internal_digest'})) or receipt.get('packet_raw_sha256')!=sha(pr) or
  receipt.get('packet_byte_count')!=len(pr) or receipt.get('packet_internal_digest')!=d or receipt.get('state')!='ready'):
  raise Error('search challenge mismatch')
 if any(w.get(k)!=c.get(k) for k in ('execution_context','p0_binding','limits','operations')):raise Error('search review scope mismatch')
 actual=components();seen=w.get('code_bindings_at_inspection',{})
 if c.get('component_bindings')!=actual or set(seen)!=set(actual):raise Error('search component drift')
 for rel,h in actual.items():
  if seen[rel]!={'sha256':h,'size':len(read(ROOT/rel))}:raise Error('search inspected bytes mismatch')
 a=account()
 if (c.get('accounting_receipt_sha256')!=sha(read(ACCOUNT_LOCAL)) or c.get('starting_usage')!=a['ledger'] or
  c.get('p0_binding')!=p0_binding() or c.get('operations')!=operations() or c.get('expected_actual_micro')!=[5000,2000] or
  c.get('execution_context')!={'cwd':str(ROOT),'output_root':str(OUTPUT)} or
  c.get('limits')!={'search_calls':2,'source_reserve_micro_per_call':150000,'no_fetch':True,'no_status':True,'no_model':True,'pacing_min_seconds':20,'pacing_scope':'all_provider_calls'}):raise Error('search inputs or limits changed')
 return c,cr,pr,rr

def execute(expected_sha):
 """Explicit live search, only after independent challenge."""
 c,cr,pr,rr=verify(expected_sha)
 if OUTPUT.exists():raise Error('output exists')
 def account_review(raw):
  try:return source_only_launch.verify(ACCOUNT,APACKET,ARECEIPT,ACCOUNT_SHA)[1]==raw
  except Exception:return False
 ledger=source_only.reopen(successor_root=str(LEDGER),contract_path=str(ACCOUNT),expected_sha=ACCOUNT_SHA,verify_challenge=account_review)
 try:
  if ledger.summary()!=c['starting_usage']:raise Error('starting usage mismatch')
  def reviewed(raw):
   try:return verify(expected_sha)[1]==raw
   except Exception:return False
  def ticket_check(ticket,raw):
   try:return verify(expected_sha)[1]==cr and any(x['ticket']==ticket and canonical(x['payload'])==raw for x in c['operations'])
   except Exception:return False
  ledger=source_only.activate(ledger,source_contract_path=str(CONTRACT),expected_sha=expected_sha,verify_challenge=reviewed,verify_ticket=ticket_check)
  from p0_launcher import durable_recorder
  rec=durable_recorder(OUTPUT)
  def save(name,value):
   try:rec(name,value)
   except BaseException:
    try:ledger.stop('search artifact persistence failed')
    finally:ledger.poisoned=True
    raise
  save('started',{'contract_sha256':expected_sha,'challenge_sha256':sha(pr),'receipt_sha256':sha(rr),'operation_ids':[x['ticket']['id'] for x in c['operations']]})
  import subprocess
  sys.path.insert(0,str(ROOT/'transport'))
  from oneshot import OneShotTransport
  def token(provider):
   if provider!='orthogonal':raise Error('only Orthogonal permitted')
   r=subprocess.run(['/usr/bin/security','find-generic-password','-s','com.maguire.orthogonal.live','-a','maguire','-w'],stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,check=False,timeout=15)
   if r.returncode or not r.stdout.strip():raise Error('credential unavailable')
   return r.stdout.strip().decode('ascii')
  transport=OneShotTransport('source-only-123',token);pacer=pace.Pacer(interval=20)
  def check():
   try:return verify(expected_sha)[1]==cr
   except Exception:return False
  def guarded(provider,endpoint,raw):
   if provider!='orthogonal' or endpoint!='/v1/run' or not check():ledger.stop('search scope drift');raise Error('search scope drift')
   return transport(provider,endpoint,raw)
  records=[];attempted=[];failure=None
  for i,x in enumerate(c['operations']):
   op=x['ticket']['id']
   try:
    pacer.wait(check)
    attempted.append(op)
    try:raw=ledger.source(op,'orthogonal','/v1/run',canonical(x['payload']),x['ticket'],guarded)
    finally:pacer.ended()
    r=ledger.receipt(op);accounting_launch.put(OUTPUT/(op+'.raw.json'),raw)
    record={'id':op,'http_status':r['http_status'],'state':r['state'],'actual_micro':r['actual_micro'],
     'response_sha256':r['response_hash'],'started_at_utc':r['started_at_utc'],'completed_at_utc':r['completed_at_utc']}
    records.append(record);save('receipt-'+str(i),record)
    if obj(raw).get('success') is not True or obj(raw).get('data') is None or r['actual_micro']>c['expected_actual_micro'][i]:
     ledger.stop('source envelope or observed price exceeded');raise Error('source semantic or price gate failed')
   except Exception as exc:
    failure={'id':op,'error_type':type(exc).__name__}
    if not ledger.summary()['stopped']:ledger.stop('search failed; no retry')
    if op in attempted and op not in [r['id'] for r in records]:
     try:r=ledger.receipt(op)
     except KeyError:r=None
     if r is not None and isinstance(r.get('response'),bytes):
      accounting_launch.put(OUTPUT/(op+'.raw.json'),r['response'])
      failure.update(http_status=r['http_status'],effect_state=r['state'],response_sha256=r['response_hash'],actual_micro=r['actual_micro'])
    break
  out={'status':'completed' if failure is None else 'stopped','records':records,'failure':failure,'attempted':attempted,'not_attempted':2-len(attempted),
   'ledger':ledger.summary(),'data_status':'raw candidates only; no news, status, causal claim or p1 established'}
  save('summary',out);return out
 except BaseException:
  try:ledger.stop('search interrupted; no retry')
  finally:ledger.poisoned=True
  raise
 finally:ledger.close()
