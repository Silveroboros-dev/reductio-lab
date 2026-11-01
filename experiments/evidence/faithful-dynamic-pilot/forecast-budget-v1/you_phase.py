"""One additional You.com source, frozen addendum and explicit live entrypoint.

This module is inert on import. Historic price evidence never authorizes this
new request. Before execution independently challenge the exact addendum.
"""
from __future__ import annotations
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parent.parent
OLD_CONTRACT_SHA='009a8d5e401213a93c2183ef48c616383c84413d6ea668cb445c3aaf7c3d0e38'
FILES=('forecast-budget-v1/you_phase.py','forecast-budget-v1/forecast_ledger.py',
 'forecast-budget-v1/ledger_contract.json','forecast-budget-v1/seed_phase.py',
 'forecast-seed-launch-v1/historical.py','budget-v2/ledger.py','source-successor/bridge.py',
 'source-successor/reopen.py','source-successor/model_stage.py',
 'model-accounting-successor/model_accounting.py','transport/oneshot.py',
 'forecast-you-price-20261029.json','forecast-source-run-contract-20261029-v1.json',
 'forecast-source-challenge-packet-v1.json','forecast-source-challenge-receipt-v1.json',
 'forecast-source-seed-20261029-01/summary.json')
OP='seed-openai-you-search'
PAYLOAD={'api':'you/search','path':'/v1/search','body':{'query':'OpenAI model releases and announcements October 2026',
 'count':5,'include_domains':['openai.com']},'query':{}}
class Error(ValueError):pass
def sha(raw):return hashlib.sha256(raw).hexdigest()
def canonical(x):return json.dumps(x,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()
def read(path):
 p=Path(path)
 if not p.is_absolute() or p.is_symlink() or not p.is_file() or p.resolve()!=p.absolute():raise Error('unsafe or missing input')
 return p.read_bytes()
def obj(raw):
 def pairs(xs):
  d={}
  for k,v in xs:
   if k in d:raise Error('duplicate JSON key')
   d[k]=v
  return d
 try:x=json.loads(raw,object_pairs_hook=pairs)
 except (ValueError,UnicodeDecodeError,TypeError) as exc:raise Error('invalid JSON') from exc
 if not isinstance(x,dict):raise Error('object required')
 return x
def put(path,raw):
 p=Path(path)
 if not p.is_absolute() or p.parent.resolve()!=p.parent.absolute():raise Error('unsafe output')
 fd=os.open(p,os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,'O_NOFOLLOW',0),0o600)
 with os.fdopen(fd,'wb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
 fd=os.open(p.parent,os.O_RDONLY)
 try:os.fsync(fd)
 finally:os.close(fd)

def quote():
 raw=read(ROOT/'forecast-you-price-20261029.json');q=obj(raw)
 if (q.get('schema'),q.get('api'),q.get('path'),q.get('method'),q.get('rate_usd')) != ('forecast-source-ui-observation-v1','you/search','/v1/search','POST','0.005 per call'):
  raise Error('UI price or endpoint mismatch')
 try:t=dt.datetime.fromisoformat(q['observed_at_utc'].replace('Z','+00:00'))
 except (KeyError,ValueError,AttributeError):raise Error('invalid quote time') from None
 if t.utcoffset()!=dt.timedelta(0):raise Error('quote time must be UTC')
 return raw,(t+dt.timedelta(minutes=15)).isoformat()

def prepare_addendum(path):
 """Freeze the one request and historical state without any provider call."""
 for folder in ('forecast-seed-launch-v1','forecast-budget-v1'):
  sys.path.insert(0,str(ROOT/folder))
 import historical,forecast_ledger
 parent=historical.verify(require_seed_start_state=True)
 raw,expiry=quote();qsha=sha(raw)
 ticket={'id':OP,'provider':'orthogonal','endpoint':'/v1/run','request_sha256':sha(canonical(PAYLOAD)),
  'max_micro':150000,'evidence_sha256':qsha,'expires_utc':expiry,'category':'search','settlement':'orthogonal_price_cents'}
 components={rel:sha(read(ROOT/rel)) for rel in FILES}
 context={'artifact_root':str(ROOT),'cwd':str(Path.cwd().resolve()),
  'ledger_root':str(ROOT/'forecast-live-ledger-20261029-01'),
  'claim_path':str(forecast_ledger.CLAIM),'output_root':str(ROOT/'forecast-source-you-20261029-01')}
 if context['cwd']!=str(ROOT) or Path(context['output_root']).exists():raise Error('source context unavailable')
 a={'schema':'faithful-forecast-source-addendum-v1','status':'frozen',
  'parent_contract_sha256':OLD_CONTRACT_SHA,'source_parent':parent,
  'caps':{'total_usd_micro':60000000,'total_generation_attempts':835,'total_count_attempts':767,'total_source_attempts':28},
  'prior_state':{'exposure_micro':1234590,'generation_attempts':200,'count_attempts':132,'source_attempts_total':12},
  'operation':{'id':OP,'payload':PAYLOAD,'ticket':ticket,'ui_expected_micro':5000},
  'component_bindings':components,'execution_context':context,
  'scope':'Exactly one Orthogonal /v1/run You.com search, no market or model calls. Preserve full raw response; projection and verification happen later.',
  'failure_policy':'No retry; unknown effect, bad semantic envelope or actual price above observed UI stop.'}
 data=canonical(a);put(path,data);return {'addendum_sha256':sha(data),'operation':a['operation'],'context':context}

def verify(addendum_path,challenge_path,receipt_path,expected_sha):
 """Check exact reviewed addendum; does not access live ledger or credentials."""
 ar,pr,rr=map(read,(addendum_path,challenge_path,receipt_path));a,p,r=map(obj,(ar,pr,rr));w=p.get('context_binding',{});d=p.get('internal_digest')
 if (sha(ar)!=expected_sha or a.get('schema')!='faithful-forecast-source-addendum-v1' or a.get('status')!='frozen'
  or p.get('schema_version')!='eval_contract_challenge_packet_v1' or p.get('overall_state')!='ready'
  or p.get('witness',{}).get('identity')!='you_source_witness' or p.get('witness',{}).get('mode')!='read_only_offline'
  or p.get('challenged_contract',{}).get('raw_sha256')!=sha(ar)
  or d!=sha(canonical({k:v for k,v in p.items() if k!='internal_digest'}))
  or r.get('packet_raw_sha256')!=sha(pr) or r.get('packet_byte_count')!=len(pr)
  or r.get('packet_internal_digest')!=d or r.get('state')!='ready'):
  raise Error('addendum or independent challenge mismatch')
 components=a.get('component_bindings');observed=w.get('code_bindings_at_inspection')
 if not isinstance(components,dict) or set(components)!=set(FILES) or not isinstance(observed,dict):raise Error('component binding missing')
 for rel,h in components.items():
  raw=read(ROOT/rel)
  if sha(raw)!=h or observed.get(rel)!={'sha256':h,'size':len(raw)}:raise Error('component drift')
 if w.get('execution_context')!=a.get('execution_context') or w.get('operation')!=a.get('operation') or w.get('source_parent')!=a.get('source_parent'):
  raise Error('challenge scope mismatch')
 ctx=a['execution_context'];ui,expiry=quote();op=a['operation'];ticket=op['ticket']
 expected_ticket={'id':OP,'provider':'orthogonal','endpoint':'/v1/run','request_sha256':sha(canonical(PAYLOAD)),
  'max_micro':150000,'evidence_sha256':sha(ui),'expires_utc':expiry,'category':'search','settlement':'orthogonal_price_cents'}
 if (ctx.get('artifact_root')!=str(ROOT) or ctx.get('cwd')!=str(Path.cwd().resolve()) or
  a.get('parent_contract_sha256')!=OLD_CONTRACT_SHA or a.get('caps')!={'total_usd_micro':60000000,'total_generation_attempts':835,'total_count_attempts':767,'total_source_attempts':28} or
  a.get('prior_state')!={'exposure_micro':1234590,'generation_attempts':200,'count_attempts':132,'source_attempts_total':12} or
  op!={'id':OP,'payload':PAYLOAD,'ticket':expected_ticket,'ui_expected_micro':5000}):raise Error('execution or operation binding mismatch')
 if dt.datetime.now(dt.timezone.utc)>=dt.datetime.fromisoformat(expiry):raise Error('UI observation expired')
 return a,ar,pr,rr

def execute(addendum_path,challenge_path,receipt_path,expected_sha):
 """EXPLICIT LIVE operation: one reviewed You.com search through Orthogonal."""
 a,ar,pr,rr=verify(addendum_path,challenge_path,receipt_path,expected_sha)
 for folder in ('forecast-seed-launch-v1','forecast-budget-v1','budget-v2','source-successor','model-accounting-successor','transport'):
  sys.path.insert(0,str(ROOT/folder))
 import historical,forecast_ledger
 from oneshot import OneShotTransport
 ctx=a['execution_context'];output=Path(ctx['output_root']);ledger_root=Path(ctx['ledger_root'])
 if output.exists() or ctx['claim_path']!=str(forecast_ledger.CLAIM):raise Error('output or claim mismatch')
 old_contract=ROOT/'forecast-source-run-contract-20261029-v1.json';old_raw=read(old_contract)
 def original_challenge(raw):
  try:return raw==old_raw and historical.verify(require_seed_start_state=True)==a['source_parent']
  except Exception:return False
 def ticket_check(ticket,raw):
  try:
   verify(addendum_path,challenge_path,receipt_path,expected_sha)
   return ticket==a['operation']['ticket'] and raw==canonical(PAYLOAD)
  except Exception:return False
 ledger=forecast_ledger.reopen_successor(successor_root=str(ledger_root),claim_path=str(forecast_ledger.CLAIM),
  ledger_contract_path=str(ROOT/'forecast-budget-v1/ledger_contract.json'),run_contract_path=str(old_contract),
  expected_contract_sha256=OLD_CONTRACT_SHA,verify_challenge=original_challenge,verify_ticket=ticket_check)
 try:
  s=ledger.summary()
  if (s['stopped'],s['exposure_micro'],s['generation_attempts'],s['count_attempts'],s['source_attempts'])!=(0,1234590,200,132,12):
   raise Error('ledger not in reviewed pre-effect state')
  output.mkdir(mode=0o700)
  put(output/'started.json',canonical({'addendum_sha256':sha(ar),'challenge_sha256':sha(pr),'receipt_sha256':sha(rr),'operation_id':OP}))
  def token(provider):
   if provider!='orthogonal':raise Error('only Orthogonal permitted')
   r=subprocess.run(['/usr/bin/security','find-generic-password','-s','com.maguire.orthogonal.live','-a','maguire','-w'],stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,check=False,timeout=15)
   if r.returncode or not r.stdout.strip():raise Error('credential unavailable')
   return r.stdout.strip().decode('ascii')
  transport=OneShotTransport('source-only-123',token)
  failure=None;record=None
  try:
   raw=ledger.source(OP,'orthogonal','/v1/run',canonical(PAYLOAD),a['operation']['ticket'],transport)
   receipt=ledger.receipt(OP);put(output/(OP+'.raw.json'),raw);response=obj(raw)
   record={'id':OP,'http_status':receipt['http_status'],'state':receipt['state'],'actual_micro':receipt['actual_micro'],
    'response_sha256':receipt['response_hash'],'started_at_utc':receipt['started_at_utc'],'completed_at_utc':receipt['completed_at_utc']}
   if response.get('success') is not True or response.get('data') is None or receipt['actual_micro']>5000:
    ledger.stop('You source semantic failure or price above UI observation')
    raise Error('source envelope or price gate failed')
  except Exception as exc:
   failure={'id':OP,'error_type':type(exc).__name__}
   if not ledger.summary()['stopped']:ledger.stop('You source failed; no retry')
  summary={'status':'completed' if failure is None else 'stopped','record':record,'failure':failure,'ledger':ledger.summary(),
   'source_data_status':'raw captured only; date, relevance, authenticity and market-title-free projection not yet reviewed'}
  put(output/'summary.json',canonical(summary));return summary
 finally:ledger.close()
