"""Verified create-only accounting stage. No provider effects or credentials."""
import json,os,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT/'forecast-429-resume-account-v1'))
import resume_ledger as r
CONTRACT=ROOT/'forecast-p0-429-resume-accounting-contract-20261029-v1.json'
PACKET=ROOT/'forecast-p0-429-resume-accounting-challenge-packet-v1.json'
CHALLENGE_RECEIPT=ROOT/'forecast-p0-429-resume-accounting-challenge-receipt-v1.json'
OUTPUT=ROOT/'forecast-p0-429-resume-accounting-receipt-20261029.json'
LEDGER=ROOT/'forecast-p0-429-resume-ledger-20261029-01'
FILES=('forecast-429-resume-account-v1/resume_ledger.py','forecast-429-resume-account-v1/freeze_accounting.py','forecast-429-resume-account-v1/accounting_launch.py')
def read(p):
 p=Path(p)
 if not p.is_absolute() or p.is_symlink() or p.resolve()!=p.absolute() or not p.is_file():raise r.Error('unsafe file')
 return p.read_bytes()
def verify(expected):
 cr,pr,rr=map(read,(CONTRACT,PACKET,CHALLENGE_RECEIPT));c,p,receipt=map(json.loads,(cr,pr,rr));d=p.get('internal_digest')
 if (r.digest(cr)!=expected or c.get('schema')!='p0-429-resume-accounting-contract-v1' or c.get('status')!='frozen' or c.get('scope')!={'mode':'accounting_only','provider_effects':'forbidden'} or c.get('ledger_root')!=str(LEDGER) or c.get('caps')!=r.CAPS or c.get('parent')!=r.inspect() or c.get('config')!=r.config() or c.get('strict_p0_deadline_utc')!=r.DEADLINE or c.get('no_source') is not True or c.get('no_canary') is not True or
 p.get('schema_version')!='eval_contract_challenge_packet_v1' or p.get('overall_state')!='ready' or p.get('witness',{}).get('identity')!='p0_resume_accounting_witness' or p.get('witness',{}).get('mode')!='read_only_offline' or p.get('challenged_contract',{}).get('raw_sha256')!=expected or d!=r.digest(r.canonical({k:v for k,v in p.items() if k!='internal_digest'})) or receipt.get('packet_raw_sha256')!=r.digest(pr) or receipt.get('packet_byte_count')!=len(pr) or receipt.get('packet_internal_digest')!=d or receipt.get('state')!='ready'):raise r.Error('accounting witness mismatch')
 b=c.get('component_bindings');observed=p.get('context_binding',{}).get('code_bindings_at_inspection')
 if not isinstance(b,dict) or set(b)!=set(FILES) or not isinstance(observed,dict):raise r.Error('accounting bindings missing')
 for name,h in b.items():
  value=read(ROOT/name)
  if r.digest(value)!=h or observed.get(name)!={'sha256':h,'size':len(value)}:raise r.Error('accounting component drift')
 if any(p.get('context_binding',{}).get(k)!=c.get(k) for k in ('ledger_root','caps','scope','parent','config')):raise r.Error('witness context mismatch')
 return c,cr,pr,rr
def execute(expected):
 c,cr,pr,rr=verify(expected)
 if Path.cwd().resolve()!=ROOT or OUTPUT.exists() or LEDGER.exists():raise r.Error('accounting destination unavailable')
 def reviewed(raw):
  try:return verify(expected)[1]==raw
  except Exception:return False
 a=r.create(LEDGER,contract_path=CONTRACT,contract_sha256=expected,verify_challenge=reviewed)
 try:
  if not isinstance(a,r.Accounting):raise r.Error('not accounting-only')
  s=a.summary()
  if (s['stopped'],s['exposure_micro'],s['generation_attempts'],s['count_attempts'],s['source_attempts'])!=(0,1889731,274,206,16):raise r.Error('carry mismatch')
  out={'schema':'p0-429-resume-accounting-receipt-v1','contract_sha256':expected,'challenge_sha256':r.digest(pr),'challenge_receipt_sha256':r.digest(rr),'ledger_root':str(LEDGER),'ledger':s,'authority':'accounting-only; no provider effects','retained_unknown_micro':{'http400':150000,'http429_each':[86016,86016,86016]}}
  fd=os.open(OUTPUT,os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,'O_NOFOLLOW',0),0o600)
  with os.fdopen(fd,'wb') as f:f.write(r.canonical(out));f.flush();os.fsync(f.fileno())
  fd=os.open(ROOT,os.O_RDONLY)
  try:os.fsync(fd)
  finally:os.close(fd)
  return out
 finally:a.close()
