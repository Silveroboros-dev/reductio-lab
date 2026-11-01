"""Create-only recovery accounting freeze; no external effects."""
import os
from pathlib import Path
import recovery_ledger as q
from ledger import canonical,digest

def freeze():
 if Path.cwd().resolve()!=q.ROOT or any(x.exists() for x in (q.ACCOUNT,q.LEDGER,q.CLAIM)):raise q.p.Error('account output exists or context wrong')
 import replay
 if q.p.read(q.REPAIR,q.REPAIR_SHA)!=canonical(replay.repaired_outcome()):raise q.p.Error('repair proof mismatch')
 files=('forecast-p1-cpi-recovery-v1/recovery_ledger.py','forecast-p1-cpi-recovery-v1/replay.py','forecast-p1-cpi-recovery-v1/freeze_account.py','forecast-p1-cpi-recovery-v1/account_launch.py')
 bindings={f:digest((q.ROOT/f).read_bytes()) for f in files}
 c={'schema':'cpi-p1-format-recovery-account-v1','status':'frozen','parent':q.inspect_parent(),'config':q.config(),'ledger_root':str(q.LEDGER),'caps':q.p.CAPS,'scope':{'mode':'accounting_only','provider_effects':'forbidden'},'recovery_bridge_sha256':bindings[files[0]],'posthoc_repair_sha256':q.REPAIR_SHA,'policy':{'no_successful_repeats':True,'no_uncertain_repeats':True,'no_canary':True,'format_repair':'posthoc_one_character_only','source_attempts_max':5,'confirmed_429_extra_attempts_max':20,'confirmed_429_retries_per_operation':3},'component_bindings':bindings,'qualification':'The original strict formatter remains unparseable; derivative is an explicitly post-hoc format repair. Source and model stages require separately reviewed authority.'}
 raw=canonical(c);fd=os.open(q.ACCOUNT,os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,'O_NOFOLLOW',0),0o600)
 with os.fdopen(fd,'wb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
 fd=os.open(q.ROOT,os.O_RDONLY)
 try:os.fsync(fd)
 finally:os.close(fd)
 return {'contract':str(q.ACCOUNT),'sha256':digest(raw),'ledger_root':str(q.LEDGER)}
if __name__=='__main__':print(freeze())
