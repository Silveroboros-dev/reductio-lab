"""Freeze a private CPI P1 accounting-only contract; no provider effects."""
import os,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT/'forecast-p1-budget-successor-v1'))
import p1_budget as p
CONTRACT=ROOT/'forecast-p1-cpi-accounting-contract-20261029-v1.json'
LEDGER=ROOT/'forecast-p1-cpi-ledger-20261029-01'
def freeze():
 if Path.cwd().resolve()!=ROOT or CONTRACT.exists() or LEDGER.exists() or p.CLAIM.exists():raise p.Error('wrong context or existing output')
 parent=p.inspect_parent();files=('forecast-p1-budget-successor-v1/p1_budget.py','forecast-p1-budget-successor-v1/freeze_accounting.py','forecast-p1-budget-successor-v1/p1_accounting_launch.py')
 bindings={x:p.digest((ROOT/x).read_bytes()) for x in files}
 c={'schema':'cpi-p1-accounting-contract-v1','status':'frozen','parent':parent,'config':p.config(),'ledger_root':str(LEDGER),'caps':p.CAPS,'scope':{'mode':'accounting_only','provider_effects':'forbidden'},'bridge_sha256':bindings[files[0]],'component_bindings':bindings,'qualification':'No future news or status is fixed here. Model and source stages each require separate exact contract and independent challenge; share same ledger.'}
 raw=p.canonical(c);fd=os.open(CONTRACT,os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,'O_NOFOLLOW',0),0o600)
 with os.fdopen(fd,'wb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
 fd=os.open(ROOT,os.O_RDONLY)
 try:os.fsync(fd)
 finally:os.close(fd)
 return {'contract':str(CONTRACT),'sha256':p.digest(raw),'ledger_root':str(LEDGER)}
if __name__=='__main__':print(freeze())
