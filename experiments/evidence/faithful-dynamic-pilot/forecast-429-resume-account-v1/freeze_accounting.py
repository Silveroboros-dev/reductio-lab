"""Freeze accounting-only contract; no provider, auth or ledger writes."""
import hashlib,os,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT/'forecast-429-resume-account-v1'))
import resume_ledger as r
CONTRACT=ROOT/'forecast-p0-429-resume-accounting-contract-20261029-v1.json'
LEDGER=ROOT/'forecast-p0-429-resume-ledger-20261029-01'
def freeze():
 if Path.cwd().resolve()!=ROOT or CONTRACT.exists() or LEDGER.exists() or (ROOT/'forecast-p0-429-resume.claim.json').exists():raise r.Error('wrong context or existing output')
 p=r.inspect()
 files=('forecast-429-resume-account-v1/resume_ledger.py','forecast-429-resume-account-v1/freeze_accounting.py','forecast-429-resume-account-v1/accounting_launch.py')
 bindings={name:r.digest((ROOT/name).read_bytes()) for name in files}
 x={'schema':'p0-429-resume-accounting-contract-v1','status':'frozen','parent':p,'config':r.config(),'ledger_root':str(LEDGER),'caps':r.CAPS,'no_source':True,'no_canary':True,'strict_p0_deadline_utc':r.DEADLINE,'scope':{'mode':'accounting_only','provider_effects':'forbidden'},'bridge_sha256':bindings[files[0]],'component_bindings':bindings,'qualification':'Historical 429 count receipts are external read-only bindings; no new count is charged for retries. Separate independently challenged model stage is mandatory.'}
 raw=r.canonical(x);fd=os.open(CONTRACT,os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,'O_NOFOLLOW',0),0o600)
 with os.fdopen(fd,'wb') as out:out.write(raw);out.flush();os.fsync(out.fileno())
 fd=os.open(ROOT,os.O_RDONLY)
 try:os.fsync(fd)
 finally:os.close(fd)
 return {'contract':str(CONTRACT),'sha256':r.digest(raw),'ledger_root':str(LEDGER)}
if __name__=='__main__':print(freeze())
