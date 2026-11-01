"""One-shot preliminary Kalshi lookup; inert until an explicit reviewed call.

Do not freeze or execute until the seed-model stage has completed and the
predecessor verifier and fresh account/endpoint quote have been reviewed. The
market results are leads, not accepted theses, fit labels or market choices.
"""
from __future__ import annotations
import datetime as dt
import hashlib,json,os,subprocess,sys
from pathlib import Path

ROOT=Path(__file__).resolve().parent.parent
OLD_CONTRACT_SHA='009a8d5e401213a93c2183ef48c616383c84413d6ea668cb445c3aaf7c3d0e38'
OP='post-seed-kalshi-market-lookup'
PAYLOAD={'api':'kalshi','path':'/markets','body':{},'query':{'limit':4,
 'tickers':'KXIPO-26-ANTHROPIC,KXWTI-26NOV03-T97.99,KXGPT-ASTRA61-26NOV13,KXCPI-26OCT-T0.2'}}
FILES=('forecast-budget-v1/market_lookup.py','forecast-budget-v1/forecast_ledger.py',
 'forecast-budget-v1/ledger_contract.json','forecast-seed-launch-v1/historical_five.py',
 'forecast-seed-launch-v1/historical_seed.py','forecast-seed-launch-v1/launcher.py',
 'forecast-seed-model-contract-20261029-v1.json','forecast-seed-model-challenge-packet-v1.json',
 'forecast-seed-model-challenge-receipt-v1.json','forecast-exploration-seed-20261029-01/summary.json',
 'forecast-source-run-contract-20261029-v1.json','budget-v2/ledger.py',
 'source-successor/bridge.py','source-successor/reopen.py','source-successor/model_stage.py',
 'model-accounting-successor/model_accounting.py','transport/oneshot.py')

class Error(ValueError):pass
def sha(raw):return hashlib.sha256(raw).hexdigest()
def canonical(x):return json.dumps(x,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()
def read(path):
 p=Path(path)
 if not p.is_absolute() or p.is_symlink() or not p.is_file() or p.resolve()!=p.absolute():raise Error('unsafe or missing input')
 return p.read_bytes()
def obj(raw):
 def pairs(items):
  d={}
  for k,v in items:
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

def quote(path):
 """A new price observation must identify this provider endpoint and UTC time."""
 raw=read(path);q=obj(raw)
 if (q.get('schema'),q.get('api'),q.get('path'),q.get('method'),q.get('provider_method'),q.get('rate_usd'),q.get('endpoint_url')) != (
   'forecast-source-ui-observation-v1','kalshi','/markets','POST','GET','Free',
   'https://www.orthogonal.com/discover/kalshi/26336e71-0806-4771-b1e0-2913fcd8cf03'):
  raise Error('UI quote does not describe the exact market endpoint')
 try:t=dt.datetime.fromisoformat(q['observed_at_utc'].replace('Z','+00:00'))
 except (KeyError,ValueError,AttributeError):raise Error('invalid quote time') from None
 now=dt.datetime.now(dt.timezone.utc)
 if t.utcoffset()!=dt.timedelta(0) or t>now or now>=t+dt.timedelta(minutes=15):
  raise Error('fresh UTC quote required')
 return raw,(t+dt.timedelta(minutes=15)).isoformat()

def prepare_addendum(path,quote_path):
 """Freeze only after seed completion; never performs any provider effect."""
 if Path.cwd().resolve()!=ROOT:raise Error('artifact root cwd required')
 for folder in ('forecast-seed-launch-v1','forecast-budget-v1'):
  sys.path.insert(0,str(ROOT/folder))
 import historical_seed,forecast_ledger
 # The verifier must check the complete seed contract/challenge and all settled
 # effects under a read-only lock. Its exact bytes become part of this addendum.
 parent=historical_seed.verify()
 summary=obj(read(ROOT/'forecast-exploration-seed-20261029-01/summary.json'))
 if (summary.get('status')!='seed_proposals_only' or summary.get('requested_cases')!=4 or
     summary.get('attempted_cases')!=4 or summary.get('not_attempted_cases')!=0 or summary.get('stop_index') is not None):
  raise Error('seed phase has not finished all four cases')
 usage=summary.get('ledger',{})
 if (usage.get('stopped')!=0 or usage.get('source_attempts')!=13 or
     not 200<=usage.get('generation_attempts',-1)<835 or not 132<=usage.get('count_attempts',-1)<767 or
     not 1239590<=usage.get('exposure_micro',-1)<60000000):raise Error('seed usage invalid or cap reached')
 quote_path=Path(quote_path)
 if not quote_path.resolve().is_relative_to(ROOT):raise Error('quote evidence must be in artifact root')
 ui,expiry=quote(quote_path);ui_rel=str(quote_path.relative_to(ROOT))
 ticket={'id':OP,'provider':'orthogonal','endpoint':'/v1/run','request_sha256':sha(canonical(PAYLOAD)),
  'max_micro':150000,'evidence_sha256':sha(ui),'expires_utc':expiry,'category':'market','settlement':'orthogonal_price_cents'}
 components={p:sha(read(ROOT/p)) for p in FILES};components[ui_rel]=sha(ui)
 context={'artifact_root':str(ROOT),'cwd':str(ROOT),'ledger_root':str(ROOT/'forecast-live-ledger-20261029-01'),
  'claim_path':str(forecast_ledger.CLAIM),'output_root':str(ROOT/'forecast-source-market-leads-20261029-01')}
 if Path(context['output_root']).exists():raise Error('market output exists')
 a={'schema':'faithful-forecast-market-addendum-v1','status':'frozen','parent_contract_sha256':OLD_CONTRACT_SHA,
  'caps':{'total_usd_micro':60000000,'total_generation_attempts':835,'total_count_attempts':767,'total_source_attempts':28},
  'seed_parent':parent,'starting_usage':usage,'operation':{'id':OP,'payload':PAYLOAD,'ticket':ticket,'ui_expected_micro':0},
  'quote_path':ui_rel,'component_bindings':components,'execution_context':context,
  'scope':'One Kalshi lookup through Orthogonal after completed seed phase; raw captures are preliminary market leads, not accepted theses or fit decisions.',
  'failure_policy':'No retry; unknown effect, bad semantic envelope or actual charge above observed Free stops the source run.'}
 raw=canonical(a);put(path,raw);return {'addendum_sha256':sha(raw),'operation':a['operation'],'context':context,'starting_usage':usage}

def verify(path,challenge_path,receipt_path,expected_sha):
 """Verify addendum and reviewer, without opening ledger or fetching secrets."""
 ar,pr,rr=map(read,(path,challenge_path,receipt_path));a,p,r=map(obj,(ar,pr,rr));w=p.get('context_binding',{});d=p.get('internal_digest')
 if (sha(ar)!=expected_sha or a.get('schema')!='faithful-forecast-market-addendum-v1' or a.get('status')!='frozen'
  or p.get('schema_version')!='eval_contract_challenge_packet_v1' or p.get('overall_state')!='ready'
  or p.get('witness',{}).get('identity')!='market_source_witness' or p.get('witness',{}).get('mode')!='read_only_offline'
  or p.get('challenged_contract',{}).get('raw_sha256')!=sha(ar)
  or d!=sha(canonical({k:v for k,v in p.items() if k!='internal_digest'}))
  or r.get('packet_raw_sha256')!=sha(pr) or r.get('packet_byte_count')!=len(pr)
  or r.get('packet_internal_digest')!=d or r.get('state')!='ready'):
  raise Error('addendum or independent challenge mismatch')
 components=a.get('component_bindings');observed=w.get('code_bindings_at_inspection');qpath=a.get('quote_path')
 if not isinstance(qpath,str) or Path(qpath).is_absolute() or not (ROOT/qpath).resolve().is_relative_to(ROOT):raise Error('unsafe quote path')
 if not isinstance(components,dict) or set(components)!=set(FILES)|{qpath} or not isinstance(observed,dict):raise Error('component bindings missing')
 for rel,h in components.items():
  raw=read(ROOT/rel)
  if sha(raw)!=h or observed.get(rel)!={'sha256':h,'size':len(raw)}:raise Error('component drift')
 if (w.get('execution_context')!=a.get('execution_context') or w.get('operation')!=a.get('operation') or
  w.get('seed_parent')!=a.get('seed_parent') or w.get('starting_usage')!=a.get('starting_usage')):
  raise Error('challenge context mismatch')
 ctx=a['execution_context'];ui,expiry=quote(ROOT/qpath);op=a['operation']
 expected={'id':OP,'provider':'orthogonal','endpoint':'/v1/run','request_sha256':sha(canonical(PAYLOAD)),
  'max_micro':150000,'evidence_sha256':sha(ui),'expires_utc':expiry,'category':'market','settlement':'orthogonal_price_cents'}
 if (ctx.get('artifact_root')!=str(ROOT) or ctx.get('cwd')!=str(Path.cwd().resolve()) or
  a.get('parent_contract_sha256')!=OLD_CONTRACT_SHA or a.get('caps')!={'total_usd_micro':60000000,'total_generation_attempts':835,'total_count_attempts':767,'total_source_attempts':28} or
  op!={'id':OP,'payload':PAYLOAD,'ticket':expected,'ui_expected_micro':0}):raise Error('operation binding mismatch')
 return a,ar,pr,rr

def execute(path,challenge_path,receipt_path,expected_sha):
 """Explicit LIVE action, one request only, after a separate ready challenge."""
 a,ar,pr,rr=verify(path,challenge_path,receipt_path,expected_sha)
 for folder in ('forecast-seed-launch-v1','forecast-budget-v1','budget-v2','source-successor','model-accounting-successor','transport'):
  sys.path.insert(0,str(ROOT/folder))
 import historical_seed,forecast_ledger
 from oneshot import OneShotTransport
 ctx=a['execution_context'];out=Path(ctx['output_root'])
 if out.exists() or ctx['claim_path']!=str(forecast_ledger.CLAIM):raise Error('output or claim mismatch')
 old_contract=ROOT/'forecast-source-run-contract-20261029-v1.json';old_raw=read(old_contract)
 def predecessor(raw):
  try:return raw==old_raw and historical_seed.verify()==a['seed_parent']
  except Exception:return False
 def ticket_check(ticket,raw):
  try:
   verify(path,challenge_path,receipt_path,expected_sha)
   return ticket==a['operation']['ticket'] and raw==canonical(PAYLOAD)
  except Exception:return False
 ledger=forecast_ledger.reopen_successor(successor_root=ctx['ledger_root'],claim_path=str(forecast_ledger.CLAIM),
  ledger_contract_path=str(ROOT/'forecast-budget-v1/ledger_contract.json'),run_contract_path=str(old_contract),
  expected_contract_sha256=OLD_CONTRACT_SHA,verify_challenge=predecessor,verify_ticket=ticket_check)
 try:
  if ledger.summary()!=a['starting_usage']:raise Error('ledger usage changed since reviewed seed phase')
  out.mkdir(mode=0o700)
  put(out/'started.json',canonical({'addendum_sha256':sha(ar),'challenge_sha256':sha(pr),'receipt_sha256':sha(rr),'operation_id':OP}))
  def token(provider):
   if provider!='orthogonal':raise Error('only Orthogonal allowed')
   r=subprocess.run(['/usr/bin/security','find-generic-password','-s','com.maguire.orthogonal.live','-a','maguire','-w'],stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,check=False,timeout=15)
   if r.returncode or not r.stdout.strip():raise Error('credential unavailable')
   return r.stdout.strip().decode('ascii')
  transport=OneShotTransport('source-only-123',token);failure=None;record=None
  try:
   raw=ledger.source(OP,'orthogonal','/v1/run',canonical(PAYLOAD),a['operation']['ticket'],transport)
   receipt=ledger.receipt(OP);put(out/(OP+'.raw.json'),raw);response=obj(raw)
   record={'id':OP,'http_status':receipt['http_status'],'state':receipt['state'],'actual_micro':receipt['actual_micro'],
    'response_sha256':receipt['response_hash'],'started_at_utc':receipt['started_at_utc'],'completed_at_utc':receipt['completed_at_utc']}
   if response.get('success') is not True or response.get('data') is None or receipt['actual_micro']!=0:
    ledger.stop('market source semantic failure or charge above Free observation')
    raise Error('market source envelope or price gate failed')
  except Exception as exc:
   failure={'id':OP,'error_type':type(exc).__name__}
   if not ledger.summary()['stopped']:ledger.stop('market lookup failed; no retry')
  result={'status':'completed' if failure is None else 'stopped','record':record,'failure':failure,
          'ledger':ledger.summary(),'evidence_status':'preliminary raw leads; identity, rules, open status and fit require separate review'}
  put(out/'summary.json',canonical(result));return result
 finally:ledger.close()
