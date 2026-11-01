"""Four source reads: offline freeze helper and explicit reviewed live entrypoint.

Import has no external effect. The live call must be preceded by a read-only,
independent challenge. Source texts are untrusted and saved without projection.
"""
from __future__ import annotations
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent
FILES = ('forecast-budget-v1/seed_phase.py', 'forecast-budget-v1/forecast_ledger.py',
 'forecast-budget-v1/ledger_contract.json', 'budget-v2/ledger.py',
 'source-successor/bridge.py', 'source-successor/reopen.py', 'source-successor/model_stage.py',
 'model-accounting-successor/model_accounting.py', 'transport/oneshot.py',
 'forecast-source-quotes-20261029.json')
OPS = (
 ('seed-anthropic-search', 'serper', '/search', {'q':'Anthropic IPO valuation fundraising company official SEC 2026'}, 2000),
 ('seed-macro-news', 'serper', '/news', {'q':'US inflation CPI PCE Federal Reserve economic data October 2026'}, 2000),
 ('seed-openai-search', 'linkup', '/search', {'q':'OpenAI announcements and model release plans November 2026 official sources','depth':'standard','outputType':'searchResults'}, 10000),
 ('seed-opec-fetch', 'linkup', '/fetch', {'url':'https://www.opec.org/pr-detail/616-4-october-2026.html'}, 10000),
)

class Error(ValueError): pass
def sha(raw): return hashlib.sha256(raw).hexdigest()
def canonical(x): return json.dumps(x,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()
def read(path):
 p=Path(path)
 if not p.is_absolute() or p.is_symlink() or not p.is_file() or p.resolve()!=p.absolute(): raise Error('unsafe or missing input')
 return p.read_bytes()
def obj(raw):
 def pairs(items):
  d={}
  for k,v in items:
   if k in d: raise Error('duplicate JSON key')
   d[k]=v
  return d
 try: x=json.loads(raw,object_pairs_hook=pairs)
 except (ValueError,UnicodeDecodeError,TypeError) as exc: raise Error('invalid JSON') from exc
 if not isinstance(x,dict): raise Error('object required')
 return x
def put(path,raw):
 path=Path(path)
 if not path.is_absolute() or path.parent.resolve()!=path.parent.absolute(): raise Error('unsafe output')
 fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,'O_NOFOLLOW',0),0o600)
 with os.fdopen(fd,'wb') as f: f.write(raw);f.flush();os.fsync(f.fileno())
 d=os.open(path.parent,os.O_RDONLY)
 try:os.fsync(d)
 finally:os.close(d)

def _ui():
 raw=read(ROOT/'forecast-source-quotes-20261029.json'); v=obj(raw)
 if v.get('schema')!='forecast-source-ui-observations-v1': raise Error('UI price schema mismatch')
 observed=dt.datetime.fromisoformat(v['observed_at_utc'].replace('Z','+00:00'))
 if observed.utcoffset()!=dt.timedelta(0): raise Error('price observation is not UTC')
 quotes={(x['api'],x['path']):x['rate_usd'] for x in v['endpoint_quotes']}
 if any(quotes.get((api,path)) != ('0.002 per call' if cost==2000 else '0.01 per call') for _,api,path,_,cost in OPS):
  raise Error('UI price mismatch')
 return raw,(observed+dt.timedelta(minutes=15)).isoformat()

def prepare_contract(path):
 """Write new frozen contract offline only. Caller ensures output absent."""
 for p in ('forecast-budget-v1','budget-v2','source-successor','model-accounting-successor'):
  sys.path.insert(0,str(ROOT/p))
 import forecast_ledger as ledger
 ui_raw,expiry=_ui(); ui_sha=sha(ui_raw)
 requests=[]
 for op_id,api,api_path,body,expected_micro in OPS:
  payload={'api':api,'path':api_path,'body':body,'query':{}}
  raw=canonical(payload)
  ticket={'id':op_id,'provider':'orthogonal','endpoint':'/v1/run','request_sha256':sha(raw),
   'max_micro':150000,'evidence_sha256':ui_sha,'expires_utc':expiry,
   'category':'fetch' if api_path=='/fetch' else ('news' if api_path=='/news' else 'search'),
   'settlement':'orthogonal_price_cents'}
  requests.append({'id':op_id,'payload':payload,'ticket':ticket,'ui_expected_micro':expected_micro})
 components={rel:sha(read(ROOT/rel)) for rel in FILES}
 context={'artifact_root':str(ROOT),'cwd':str(Path.cwd().resolve()),
  'ledger_root':str(ROOT/'forecast-live-ledger-20261029-01'),
  'claim_path':str(ledger.CLAIM),'output_root':str(ROOT/'forecast-source-seed-20261029-01')}
 if context['cwd']!=str(ROOT) or Path(context['ledger_root']).exists() or Path(context['output_root']).exists():
  raise Error('source execution context unavailable')
 c={'schema':'faithful-forecast-run-contract-v1','status':'frozen',
  'caps':{'total_usd_micro':60000000,'total_generation_attempts':835,'total_count_attempts':767,'total_source_attempts':28},
  'parent':ledger.inspect_parent(),'ledger_contract_sha256':components['forecast-budget-v1/ledger_contract.json'],
  'component_bindings':components,'execution_context':context,
  'source_phase':{'requests':requests,'ui_sha256':ui_sha,'max_new_attempts':4,'timeout_seconds_per_io':420,
   'retry':'none','semantic_gate':'HTTP 200, success true and exact parsed price; preserve raw and stop on failure or price above UI',
   'model_projection':'Raw source bytes are not model inputs. Before seed stage, screen for market titles and unrelated content; keep raw unchanged and flag uncertain cases.',
   'scope':'source research before human selection; no market retrieval or model calls in this phase'},
  'later_phases':'Any model or later source phase requires separately frozen, independently reviewed inputs and dispatcher; user retains thesis acceptance.'}
 raw=canonical(c);put(path,raw)
 return {'contract_sha256':sha(raw),'context':context,'requests':requests}

def verify(contract_path,challenge_path,receipt_path,expected_contract_sha256):
 """Inspect exact context, code and local witness before importing ledger."""
 cr,pr,rr=map(read,(contract_path,challenge_path,receipt_path));c,p,r=map(obj,(cr,pr,rr))
 d=p.get('internal_digest'); w=p.get('context_binding',{})
 if (sha(cr)!=expected_contract_sha256 or c.get('schema')!='faithful-forecast-run-contract-v1' or c.get('status')!='frozen'
  or p.get('schema_version')!='eval_contract_challenge_packet_v1' or p.get('overall_state')!='ready'
  or p.get('witness',{}).get('identity')!='source_witness' or p.get('witness',{}).get('mode')!='read_only_offline'
  or p.get('challenged_contract',{}).get('raw_sha256')!=sha(cr)
  or d!=sha(canonical({k:v for k,v in p.items() if k!='internal_digest'}))
  or r.get('packet_raw_sha256')!=sha(pr) or r.get('packet_byte_count')!=len(pr) or r.get('packet_internal_digest')!=d or r.get('state')!='ready'):
  raise Error('frozen contract or independent challenge mismatch')
 components=c.get('component_bindings');observed=w.get('code_bindings_at_inspection')
 if not isinstance(components,dict) or set(components)!=set(FILES) or not isinstance(observed,dict): raise Error('code bindings missing')
 for rel,h in components.items():
  raw=read(ROOT/rel)
  if sha(raw)!=h or observed.get(rel)!={'sha256':h,'size':len(raw)}: raise Error('component changed')
 if w.get('execution_context')!=c.get('execution_context') or w.get('source_phase')!=c.get('source_phase'):
  raise Error('challenge scope/context differs')
 context=c['execution_context']; ui_raw,expiry=_ui()
 if context.get('artifact_root')!=str(ROOT) or context.get('cwd')!=str(Path.cwd().resolve()) or c['source_phase']['ui_sha256']!=sha(ui_raw):
  raise Error('execution or quote binding mismatch')
 requests=c['source_phase']['requests']
 if len(requests)!=4: raise Error('wrong source cohort')
 for rec,(op_id,api,path,body,cost) in zip(requests,OPS):
  expected={'api':api,'path':path,'body':body,'query':{}};ticket=rec['ticket']
  if (rec['id']!=op_id or rec['payload']!=expected or rec['ui_expected_micro']!=cost or
   ticket!={'id':op_id,'provider':'orthogonal','endpoint':'/v1/run','request_sha256':sha(canonical(expected)),
    'max_micro':150000,'evidence_sha256':sha(ui_raw),'expires_utc':expiry,
    'category':'fetch' if path=='/fetch' else ('news' if path=='/news' else 'search'),
    'settlement':'orthogonal_price_cents'}): raise Error('source request drift')
 if dt.datetime.now(dt.timezone.utc)>=dt.datetime.fromisoformat(expiry):raise Error('UI observation expired before dispatch')
 return c,cr,pr,rr

def execute(contract_path,challenge_path,receipt_path,expected_contract_sha256):
 """EXPLICIT LIVE operation: four one-shot source reads, no model calls."""
 c,cr,pr,rr=verify(contract_path,challenge_path,receipt_path,expected_contract_sha256)
 for folder in ('forecast-budget-v1','budget-v2','source-successor','model-accounting-successor','transport'):
  sys.path.insert(0,str(ROOT/folder))
 import forecast_ledger
 from oneshot import OneShotTransport
 ctx=c['execution_context']; out=Path(ctx['output_root']); ledger_path=Path(ctx['ledger_root'])
 if out.exists() or ledger_path.exists() or ctx['claim_path']!=str(forecast_ledger.CLAIM):raise Error('source output/claim mismatch')
 # Binding each ticket prevents another request from borrowing this price quote.
 def ticket_check(ticket,raw):
  try:
   verify(contract_path,challenge_path,receipt_path,expected_contract_sha256)
   return any(ticket==r['ticket'] and raw==canonical(r['payload']) for r in c['source_phase']['requests'])
  except Exception:return False
 def challenge_check(raw):
  try:
   verify(contract_path,challenge_path,receipt_path,expected_contract_sha256)
   return raw==cr
  except Exception:return False
 forecast_ledger.CLAIM.parent.mkdir(mode=0o700,exist_ok=True)
 ledger=forecast_ledger.create_successor(successor_root=str(ledger_path),claim_path=str(forecast_ledger.CLAIM),
  ledger_contract_path=str(ROOT/'forecast-budget-v1/ledger_contract.json'),run_contract_path=str(contract_path),
  expected_contract_sha256=expected_contract_sha256,verify_challenge=challenge_check,verify_ticket=ticket_check)
 try:
  out.mkdir(mode=0o700)
  def token(provider):
   if provider!='orthogonal':raise Error('only Orthogonal allowed')
   v=subprocess.run(['/usr/bin/security','find-generic-password','-s','com.maguire.orthogonal.live','-a','maguire','-w'],
                    stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,check=False,timeout=15)
   if v.returncode or not v.stdout.strip():raise Error('configured credential unavailable')
   return v.stdout.strip().decode('ascii')
  transport=OneShotTransport('source-only-123',token)
  put(out/'started.json',canonical({'contract_sha256':sha(cr),'challenge_sha256':sha(pr),'receipt_sha256':sha(rr),
   'operation_ids':[r['id'] for r in c['source_phase']['requests']]}))
  records=[];failure=None
  for rec in c['source_phase']['requests']:
   op=rec['id']
   try:
    raw=ledger.source(op,'orthogonal','/v1/run',canonical(rec['payload']),rec['ticket'],transport)
    receipt=ledger.receipt(op)
    # Full response is also durably available in the ledger; this file aids review.
    put(out/(op+'.raw.json'),raw)
    response=obj(raw)
    if response.get('success') is not True or response.get('data') is None or receipt['actual_micro']>rec['ui_expected_micro']:
     ledger.stop('source semantic failure or billed price above UI observation')
     raise Error('source semantic failure or price exceeded displayed rate')
    records.append({'id':op,'http_status':receipt['http_status'],'state':receipt['state'],
     'actual_micro':receipt['actual_micro'],'response_sha256':receipt['response_hash'],
     'started_at_utc':receipt['started_at_utc'],'completed_at_utc':receipt['completed_at_utc']})
   except Exception as exc:
    failure={'id':op,'error_type':type(exc).__name__}
    if not ledger.summary()['stopped']: ledger.stop('source phase failure; no retry')
    break
  summary={'status':'completed' if failure is None else 'stopped','settled_records':records,
   'failure':failure,'not_attempted':len(c['source_phase']['requests'])-len(records)-(1 if failure else 0),
   'ledger':ledger.summary(),'source_data_status':'raw captured; timestamps, relevance and market-title-free projection not yet verified'}
  put(out/'summary.json',canonical(summary));return summary
 finally:ledger.close()
