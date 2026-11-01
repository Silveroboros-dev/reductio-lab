"""Create accounting-only recovery successor after independent challenge."""
import json,os
from pathlib import Path
import recovery_ledger as q
from ledger import canonical,digest
PACKET=q.ROOT/'forecast-cpi-p1-format-recovery-account-challenge-packet-v1.json'
RECEIPT=q.ROOT/'forecast-cpi-p1-format-recovery-account-challenge-receipt-v1.json'
OUTPUT=q.ROOT/'forecast-cpi-p1-format-recovery-account-receipt-20261029-v1.json'
FILES=('forecast-p1-cpi-recovery-v1/recovery_ledger.py','forecast-p1-cpi-recovery-v1/replay.py','forecast-p1-cpi-recovery-v1/freeze_account.py','forecast-p1-cpi-recovery-v1/account_launch.py')

def verify(expected):
 cr,pr,rr=map(q.p.read,(q.ACCOUNT,PACKET,RECEIPT));c,w,receipt=map(json.loads,(cr,pr,rr));d=w.get('internal_digest')
 if digest(cr)!=expected or c.get('schema')!='cpi-p1-format-recovery-account-v1' or c.get('status')!='frozen' or c.get('scope')!={'mode':'accounting_only','provider_effects':'forbidden'} or c.get('parent')!=q.inspect_parent() or c.get('config')!=q.config() or c.get('ledger_root')!=str(q.LEDGER) or w.get('schema_version')!='eval_contract_challenge_packet_v1' or w.get('overall_state')!='ready' or w.get('witness',{}).get('identity')!='cpi_p1_format_recovery_account_witness' or w.get('witness',{}).get('mode')!='read_only_offline' or w.get('challenged_contract',{}).get('raw_sha256')!=expected or d!=digest(canonical({k:v for k,v in w.items() if k!='internal_digest'})) or receipt.get('packet_raw_sha256')!=digest(pr) or receipt.get('packet_byte_count')!=len(pr) or receipt.get('packet_internal_digest')!=d or receipt.get('state')!='ready':raise q.p.Error('recovery accounting challenge mismatch')
 observed=w.get('context_binding',{}).get('code_bindings_at_inspection',{});bound=c.get('component_bindings',{})
 if set(bound)!=set(FILES):raise q.p.Error('recovery component binding mismatch')
 for name in FILES:
  raw=q.p.read(q.ROOT/name);h=digest(raw)
  if bound[name]!=h or observed.get(name)!={'sha256':h,'size':len(raw)}:raise q.p.Error('recovery code changed')
 if any(w.get('context_binding',{}).get(k)!=c.get(k) for k in ('ledger_root','caps','scope','parent','config','policy','posthoc_repair_sha256')):raise q.p.Error('review context mismatch')
 return c,cr,pr,rr

def execute(expected):
 c,cr,pr,rr=verify(expected)
 if Path.cwd().resolve()!=q.ROOT or OUTPUT.exists() or q.LEDGER.exists():raise q.p.Error('recovery output exists')
 def reviewed(raw):
  try:return verify(expected)[1]==raw
  except Exception:return False
 base=q.create(contract_sha=expected,verify_challenge=reviewed)
 try:
  st=base.summary()
  if (st['stopped'],st['exposure_micro'],st['generation_attempts'],st['count_attempts'],st['source_attempts'])!=(0,2033331,307,236,0):raise q.p.Error('recovery carry mismatch')
  st.update(source_attempts=23,previous_source_attempts=23)
  out={'schema':'cpi-p1-format-recovery-account-receipt-v1','contract_sha256':expected,'challenge_sha256':digest(pr),'challenge_receipt_sha256':digest(rr),'ledger_root':str(q.LEDGER),'ledger':st,'authority':'accounting-only; no provider effects'}
  fd=os.open(OUTPUT,os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,'O_NOFOLLOW',0),0o600)
  with os.fdopen(fd,'wb') as f:f.write(canonical(out));f.flush();os.fsync(f.fileno())
  fd=os.open(q.ROOT,os.O_RDONLY)
  try:os.fsync(fd)
  finally:os.close(fd)
  return out
 finally:base.close()
