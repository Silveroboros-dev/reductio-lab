"""CPI P1 accounting-only create. Import and execution have no provider effects."""
import json,os,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT/'forecast-p1-budget-successor-v1'))
import p1_budget as p
CONTRACT=ROOT/'forecast-p1-cpi-accounting-contract-20261029-v1.json'
PACKET=ROOT/'forecast-p1-cpi-accounting-challenge-packet-v1.json'
CHALLENGE_RECEIPT=ROOT/'forecast-p1-cpi-accounting-challenge-receipt-v1.json'
OUTPUT=ROOT/'forecast-p1-cpi-accounting-receipt-20261029.json'
LEDGER=ROOT/'forecast-p1-cpi-ledger-20261029-01'
FILES=('forecast-p1-budget-successor-v1/p1_budget.py','forecast-p1-budget-successor-v1/freeze_accounting.py','forecast-p1-budget-successor-v1/p1_accounting_launch.py')
def verify(expected):
 cr,pr,rr=map(p.read,(CONTRACT,PACKET,CHALLENGE_RECEIPT));c,witness,receipt=map(json.loads,(cr,pr,rr));d=witness.get('internal_digest')
 if (p.digest(cr)!=expected or c.get('schema')!='cpi-p1-accounting-contract-v1' or c.get('status')!='frozen' or c.get('scope')!={'mode':'accounting_only','provider_effects':'forbidden'} or c.get('ledger_root')!=str(LEDGER) or c.get('caps')!=p.CAPS or c.get('parent')!=p.inspect_parent() or c.get('config')!=p.config() or witness.get('schema_version')!='eval_contract_challenge_packet_v1' or witness.get('overall_state')!='ready' or witness.get('witness',{}).get('identity')!='cpi_p1_accounting_witness' or witness.get('witness',{}).get('mode')!='read_only_offline' or witness.get('challenged_contract',{}).get('raw_sha256')!=expected or d!=p.digest(p.canonical({k:v for k,v in witness.items() if k!='internal_digest'})) or receipt.get('packet_raw_sha256')!=p.digest(pr) or receipt.get('packet_byte_count')!=len(pr) or receipt.get('packet_internal_digest')!=d or receipt.get('state')!='ready'):raise p.Error('accounting review mismatch')
 b=c.get('component_bindings');observed=witness.get('context_binding',{}).get('code_bindings_at_inspection')
 if not isinstance(b,dict) or set(b)!=set(FILES) or not isinstance(observed,dict):raise p.Error('component bindings invalid')
 for name,h in b.items():
  raw=p.read(ROOT/name)
  if p.digest(raw)!=h or observed.get(name)!={'sha256':h,'size':len(raw)}:raise p.Error('code bytes changed')
 if any(witness.get('context_binding',{}).get(k)!=c.get(k) for k in ('ledger_root','caps','scope','parent','config')):raise p.Error('review context mismatch')
 return c,cr,pr,rr
def execute(expected):
 c,cr,pr,rr=verify(expected)
 if Path.cwd().resolve()!=ROOT or OUTPUT.exists() or LEDGER.exists():raise p.Error('destination unavailable')
 def reviewed(raw):
  try:return verify(expected)[1]==raw
  except Exception:return False
 account=p.create(LEDGER,contract_path=CONTRACT,contract_sha=expected,verify_challenge=reviewed)
 try:
  s=account.summary()
  if (s['stopped'],s['exposure_micro'],s['generation_attempts'],s['count_attempts'],s['source_attempts'])!=(0,1988563,299,228,16):raise p.Error('carry mismatch')
  out={'schema':'cpi-p1-accounting-receipt-v1','contract_sha256':expected,'challenge_sha256':p.digest(pr),'challenge_receipt_sha256':p.digest(rr),'ledger_root':str(LEDGER),'ledger':s,'authority':'accounting-only; no provider effects','retained_unknown_micro':{'http400':150000,'http429_each':[86016,86016,86016]}}
  fd=os.open(OUTPUT,os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,'O_NOFOLLOW',0),0o600)
  with os.fdopen(fd,'wb') as f:f.write(p.canonical(out));f.flush();os.fsync(f.fileno())
  fd=os.open(ROOT,os.O_RDONLY)
  try:os.fsync(fd)
  finally:os.close(fd)
  return out
 finally:account.close()
