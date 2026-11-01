"""Create accounting-only successor after independent review. No network code."""
from __future__ import annotations
import hashlib,json,os,sys
from pathlib import Path

ROOT=Path(__file__).resolve().parent.parent
FILES=('forecast-stopped-successor-v1/accounting_launch.py','forecast-stopped-successor-v1/recovery.py',
 'forecast-stopped-successor-v1/ledger_contract.json','forecast-budget-v1/forecast_ledger.py',
 'forecast-budget-v1/ledger_contract.json','forecast-source-run-contract-20261029-v1.json',
 'forecast-market-source-addendum-20261029-v1.json','forecast-market-challenge-packet-v1.json',
 'forecast-market-challenge-receipt-v1.json','forecast-source-market-leads-20261029-01/started.json',
 'forecast-source-market-leads-20261029-01/summary.json','forecast-exploration-seed-20261029-01/summary.json',
 'forecast-live-ledger-20261029-01/ledger.sqlite3','budget-v2/ledger.py',
 'source-successor/bridge.py','source-successor/reopen.py','source-successor/model_stage.py',
 'model-accounting-successor/model_accounting.py')
CAPS={'total_usd_micro':60000000,'total_generation_attempts':835,'total_count_attempts':767,'total_source_attempts':28}
class Error(ValueError):pass
def sha(b):return hashlib.sha256(b).hexdigest()
def canonical(x):return json.dumps(x,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()
def read(path):
 p=Path(path)
 if not p.is_absolute() or p.is_symlink() or not p.is_file() or p.resolve()!=p.absolute():raise Error('unsafe input')
 return p.read_bytes()
def obj(raw):
 def pairs(items):
  d={}
  for k,v in items:
   if k in d:raise Error('duplicate JSON key')
   d[k]=v
  return d
 try:x=json.loads(raw,object_pairs_hook=pairs)
 except (ValueError,TypeError,UnicodeDecodeError) as exc:raise Error('invalid JSON') from exc
 if not isinstance(x,dict):raise Error('object required')
 return x
def put(path,raw):
 p=Path(path)
 if not p.is_absolute() or p.parent.resolve()!=p.parent.absolute():raise Error('unsafe output path')
 fd=os.open(p,os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,'O_NOFOLLOW',0),0o600)
 with os.fdopen(fd,'wb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
 fd=os.open(p.parent,os.O_RDONLY)
 try:os.fsync(fd)
 finally:os.close(fd)

def prepare_contract(path):
 """Write concrete accounting-only contract after read-only prior reconcile."""
 if Path.cwd().resolve()!=ROOT:raise Error('artifact root cwd required')
 sys.path.insert(0,str(ROOT/'forecast-stopped-successor-v1'))
 import recovery
 parent=recovery.inspect_stopped();bindings={p:sha(read(ROOT/p)) for p in FILES}
 context={'artifact_root':str(ROOT),'cwd':str(ROOT),
  'ledger_root':str(ROOT/'forecast-recovery-ledger-20261029-01'),
  'claim_path':str(recovery.CLAIM),'receipt_path':str(ROOT/'forecast-recovery-accounting-receipt-20261029.json')}
 if Path(context['ledger_root']).exists() or Path(context['receipt_path']).exists():raise Error('accounting output exists')
 c={'schema':'faithful-forecast-post400-contract-v1','status':'frozen','caps':CAPS,'parent':parent,
  'ledger_contract_sha256':bindings['forecast-stopped-successor-v1/ledger_contract.json'],
  'prohibited_request_sha256':recovery.FAILED_REQUEST_SHA,
  'scope':{'mode':'accounting_only','provider_effects':'forbidden'},
  'execution_context':context,'component_bindings':bindings,
  'qualification':'No source/model calls are authorized by this contract; an independently challenged P0 model contract is required before activation.'}
 raw=canonical(c);put(path,raw);return {'contract_sha256':sha(raw),'execution_context':context,'parent':parent}

def verify(contract_path,challenge_path,receipt_path,expected_sha):
 """No credentials, no SQLite writes. Challenge is attributed, not a signature."""
 cr,pr,rr=map(read,(contract_path,challenge_path,receipt_path));c,p,r=map(obj,(cr,pr,rr));d=p.get('internal_digest');w=p.get('context_binding',{})
 if (sha(cr)!=expected_sha or c.get('schema')!='faithful-forecast-post400-contract-v1' or c.get('status')!='frozen'
  or c.get('caps')!=CAPS or c.get('scope')!={'mode':'accounting_only','provider_effects':'forbidden'}
  or p.get('schema_version')!='eval_contract_challenge_packet_v1' or p.get('overall_state')!='ready'
  or p.get('witness',{}).get('identity')!='recovery_accounting_witness' or p.get('witness',{}).get('mode')!='read_only_offline'
  or p.get('challenged_contract',{}).get('raw_sha256')!=sha(cr)
  or d!=sha(canonical({k:v for k,v in p.items() if k!='internal_digest'}))
  or r.get('packet_raw_sha256')!=sha(pr) or r.get('packet_byte_count')!=len(pr)
  or r.get('packet_internal_digest')!=d or r.get('state')!='ready'):
  raise Error('accounting challenge mismatch')
 components=c.get('component_bindings');observed=w.get('code_bindings_at_inspection')
 if not isinstance(components,dict) or set(components)!=set(FILES) or not isinstance(observed,dict):raise Error('component bindings missing')
 for rel,h in components.items():
  b=read(ROOT/rel)
  if sha(b)!=h or observed.get(rel)!={'sha256':h,'size':len(b)}:raise Error('component binding mismatch')
 if any(w.get(k)!=c.get(k) for k in ('execution_context','scope','parent')):raise Error('review context mismatch')
 context=c['execution_context']
 if context.get('artifact_root')!=str(ROOT) or context.get('cwd')!=str(Path.cwd().resolve()):raise Error('execution context mismatch')
 return c,cr,pr,rr

def execute(contract_path,challenge_path,receipt_path,expected_sha):
 """Create only a local accounting ledger. This operation makes no API call."""
 c,cr,pr,rr=verify(contract_path,challenge_path,receipt_path,expected_sha)
 sys.path.insert(0,str(ROOT/'forecast-stopped-successor-v1'))
 import recovery
 ctx=c['execution_context'];ledger_root=Path(ctx['ledger_root']);receipt=Path(ctx['receipt_path'])
 if ledger_root.exists() or receipt.exists() or ctx['claim_path']!=str(recovery.CLAIM):raise Error('output or claim mismatch')
 def reviewed(raw):
  try:
   verify(contract_path,challenge_path,receipt_path,expected_sha)
   return raw==cr
  except Exception:return False
 recovery.CLAIM.parent.mkdir(mode=0o700,exist_ok=True)
 ledger=recovery.create_successor(successor_root=str(ledger_root),claim_path=str(recovery.CLAIM),run_contract_path=str(contract_path),
  expected_contract_sha256=expected_sha,verify_challenge=reviewed,verify_ticket=lambda *_:False)
 try:
  if not isinstance(ledger,recovery.AccountingOnlyLedger):raise Error('accounting-only adapter required')
  summary=ledger.summary()
  if (summary.get('stopped'),summary.get('exposure_micro'),summary.get('generation_attempts'),summary.get('count_attempts'),summary.get('source_attempts'))!=(0,1510458,232,164,14):
   raise Error('accounting carry mismatch')
  result={'schema':'forecast-recovery-accounting-receipt-v1','contract_sha256':sha(cr),'challenge_sha256':sha(pr),
   'challenge_receipt_sha256':sha(rr),'ledger_root':str(ledger_root),'ledger':summary,
   'authority':'accounting-only; no provider effects','source_http400_reserve_retained_micro':150000}
  put(receipt,canonical(result));return result
 finally:ledger.close()
