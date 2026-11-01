"""Offline-only challenge and accounting creation for post429 successor."""
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT/'forecast-stopped-successor-v1'))
import accounting_launch as a
import post429b as p
CONTRACT=ROOT/'forecast-post429b-accounting-contract-20261029-v1.json'
PACKET=ROOT/'forecast-post429b-accounting-challenge-packet-v1.json'
RECEIPT=ROOT/'forecast-post429b-accounting-challenge-receipt-v1.json'
LOCAL_RECEIPT=ROOT/'forecast-post429b-accounting-receipt-20261029.json'
LEDGER=ROOT/'forecast-429b-recovery-ledger-20261029-01'
FILES=tuple(sorted(set(a.FILES)|set(p.dispatch_remaining.components())|{'forecast-429b-successor-v1/post429b.py','forecast-429b-successor-v1/post429b_launch.py','forecast-429-recovery-ledger-20261029-01/ledger.sqlite3','forecast-p0-remaining-model-contract-20261029-v1.json','forecast-p0-remaining-model-challenge-packet-v1.json','forecast-p0-remaining-model-challenge-receipt-v1.json','forecast-p0-remaining-results-20261029-01/00-p0-c.json','forecast-p0-remaining-results-20261029-01/00-p0-input.json','forecast-p0-remaining-results-20261029-01/p0-bundle.json'}))
class Error(ValueError):pass

def prepare_contract():
 if Path.cwd().resolve()!=ROOT or any(x.exists() for x in (CONTRACT,LEDGER,LOCAL_RECEIPT,p.CLAIM)):raise Error('wrong cwd or output already exists')
 parent=p.inspect(); bindings={name:a.sha(a.read(ROOT/name)) for name in FILES}
 context={'artifact_root':str(ROOT),'cwd':str(ROOT),'ledger_root':str(LEDGER),'claim_path':str(p.CLAIM),'receipt_path':str(LOCAL_RECEIPT)}
 c={'schema':'faithful-forecast-post429b-accounting-v1','status':'frozen','caps':p.CAPS,'parent':parent,'ledger_config':p.config(),'bridge_sha256':bindings['forecast-429b-successor-v1/post429b.py'],'ledger_root':str(LEDGER),'scope':{'mode':'accounting_only','provider_effects':'forbidden','future_cases':['case-03','case-04'],'no_retry':True},'execution_context':context,'component_bindings':bindings,'qualification':'No provider calls authorized; separate reviewed model contract required. Retain both unknown charge reservations.'}
 raw=a.canonical(c);a.put(CONTRACT,raw);return a.sha(raw)

def verify(contract_path,challenge_path,receipt_path,expected_sha):
 cr,pr,rr=map(a.read,(contract_path,challenge_path,receipt_path));c,packet,receipt=map(a.obj,(cr,pr,rr));d=packet.get('internal_digest');w=packet.get('context_binding',{})
 if (a.sha(cr)!=expected_sha or c.get('schema')!='faithful-forecast-post429b-accounting-v1' or c.get('status')!='frozen' or c.get('caps')!=p.CAPS or c.get('scope')!={'mode':'accounting_only','provider_effects':'forbidden','future_cases':['case-03','case-04'],'no_retry':True} or packet.get('schema_version')!='eval_contract_challenge_packet_v1' or packet.get('overall_state')!='ready' or packet.get('witness',{}).get('identity')!='post429b_accounting_witness' or packet.get('witness',{}).get('mode')!='read_only_offline' or packet.get('challenged_contract',{}).get('raw_sha256')!=expected_sha or d!=a.sha(a.canonical({k:v for k,v in packet.items() if k!='internal_digest'})) or receipt.get('packet_raw_sha256')!=a.sha(pr) or receipt.get('packet_byte_count')!=len(pr) or receipt.get('packet_internal_digest')!=d or receipt.get('state')!='ready'):raise Error('accounting review mismatch')
 components=c.get('component_bindings');observed=w.get('code_bindings_at_inspection',{})
 if not isinstance(components,dict) or set(components)!=set(FILES) or set(observed)!=set(FILES):raise Error('component coverage mismatch')
 for rel,h in components.items():
  raw=a.read(ROOT/rel)
  if a.sha(raw)!=h or observed[rel]!={'sha256':h,'size':len(raw)}:raise Error('component drift')
 if any(w.get(k)!=c.get(k) for k in ('execution_context','scope','parent')):raise Error('review scope mismatch')
 if c['parent']!=p.inspect() or c['ledger_root']!=str(LEDGER) or c['execution_context']!={'artifact_root':str(ROOT),'cwd':str(ROOT),'ledger_root':str(LEDGER),'claim_path':str(p.CLAIM),'receipt_path':str(LOCAL_RECEIPT)}:raise Error('parent or context mismatch')
 return c,cr,pr,rr

def execute(expected_sha):
 c,cr,pr,rr=verify(CONTRACT,PACKET,RECEIPT,expected_sha)
 if Path.cwd().resolve()!=ROOT or LEDGER.exists() or LOCAL_RECEIPT.exists():raise Error('wrong cwd or output exists')
 def reviewed(raw):
  try:return verify(CONTRACT,PACKET,RECEIPT,expected_sha)[1]==raw
  except Exception:return False
 ledger=p.create(successor_root=str(LEDGER),contract_path=str(CONTRACT),expected_sha=expected_sha,verify_challenge=reviewed)
 try:
  summary=ledger.summary()
  if (summary['stopped'],summary['exposure_micro'],summary['generation_attempts'],summary['count_attempts'],summary['source_attempts'])!=(0,1737725,255,187,14):raise Error('carry mismatch')
  out={'schema':'forecast-post429b-accounting-receipt-v1','contract_sha256':expected_sha,'challenge_sha256':a.sha(pr),'challenge_receipt_sha256':a.sha(rr),'ledger_root':str(LEDGER),'ledger':summary,'authority':'accounting-only; no provider effects','retained_http400_micro':150000,'retained_http429_micro':86016,'retained_http429b_micro':86016}
  a.put(LOCAL_RECEIPT,a.canonical(out));return out
 finally:ledger.close()
