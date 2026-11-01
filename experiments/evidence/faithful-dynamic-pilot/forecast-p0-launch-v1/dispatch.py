"""Separately reviewed, one-shot p0 phase. Import/freeze/verify are offline.

No source reads, p1, automatic retry, or human/semantic authority. Only execute
can create model effects, after a separately attested contract and accounting
successor. Clock deadlines are conservative, not a substitute for verifying a
market remains unresolved or a release's actual publication time.
"""
import datetime as dt,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
for d in ('forecast-p0-launch-v1','forecast-seed-launch-v1','forecast-stopped-successor-v1'):
 sys.path.insert(0,str(ROOT/d))
import approved_inputs as inputs,case_binding,create_cases,p0_launcher as p,recovery_adapter as adapter,launcher as seed,accounting_launch

ACCOUNTING_SHA='c7382e21dbfe01240dfc33ba802bb37cff054e532f1a99b9553e1a6a90b77cbc'
ACCOUNTING=ROOT/'forecast-recovery-accounting-contract-20261029-v1.json'
APACKET=ROOT/'forecast-recovery-accounting-challenge-packet-v1.json'
ARECEIPT=ROOT/'forecast-recovery-accounting-challenge-receipt-v1.json'
ACCOUNTING_RECEIPT=ROOT/'forecast-recovery-accounting-receipt-20261029.json'
CONTRACT=ROOT/'forecast-p0-model-contract-20261029-v1.json'
PACKET=ROOT/'forecast-p0-model-challenge-packet-v1.json'
RECEIPT=ROOT/'forecast-p0-model-challenge-receipt-v1.json'
OUTPUT=ROOT/'forecast-p0-results-20261029-01'
LEDGER=ROOT/'forecast-recovery-ledger-20261029-01'
DEADLINE='2026-10-29T12:30:00Z'
CAPS={'total_usd_micro':60000000,'total_generation_attempts':835,'total_count_attempts':767,'total_source_attempts':28}
FILES=('forecast-p0-launch-v1/dispatch.py','forecast-p0-launch-v1/p0_launcher.py',
 'forecast-p0-launch-v1/recovery_adapter.py','forecast-p0-launch-v1/approved_inputs.py',
 'forecast-p0-launch-v1/case_binding.py','forecast-p0-launch-v1/create_cases.py',
 'forecast-orchestrator-v1/orchestrator.py','forecast-controller-v1/forecast.py',
 'forecast-stopped-successor-v1/accounting_launch.py','forecast-stopped-successor-v1/recovery.py',
 'forecast-stopped-successor-v1/ledger_contract.json','transport/oneshot.py',
 'human-test-question-acceptance-20261029-v1.json','kalshi-user-relay-20261029-v1.raw.json',
 'kalshi-user-relay-20261029-v1.provenance.json','forecast-p0-cases-20261029-v2/manifest.json',
 'forecast-p0-cases-20261029-v2/case-01.json','forecast-p0-cases-20261029-v2/case-02.json',
 'forecast-p0-cases-20261029-v2/case-03.json','forecast-p0-cases-20261029-v2/case-04.json',
 'forecast-recovery-accounting-contract-20261029-v1.json','forecast-recovery-accounting-challenge-packet-v1.json',
 'forecast-recovery-accounting-challenge-receipt-v1.json','forecast-recovery-accounting-receipt-20261029.json')
class Error(ValueError):pass
def now():return dt.datetime.now(dt.timezone.utc).isoformat()
def read(path):return p._read(path)
def obj(raw):return p._json(raw)
def sha(raw):return p.o.sha(raw)
def canonical(x):return p.o.canonical(x)
def components():
 paths=set(FILES)|set(seed.components())
 return {name:sha(read(ROOT/name)) for name in sorted(paths)}
def accounting_evidence():
 ac,ar,ap,at=accounting_launch.verify(ACCOUNTING,APACKET,ARECEIPT,ACCOUNTING_SHA)
 rr=read(ACCOUNTING_RECEIPT);r=obj(rr)
 expected={'stopped':0,'exposure_micro':1510458,'generation_attempts':232,'count_attempts':164,
  'source_attempts':14,'metadata_attempts':0,'metadata_retained_micro':0,'previous_source_attempts':14,
  'prior_http400_charge_unknown_retained_micro':150000}
 if (r.get('schema')!='forecast-recovery-accounting-receipt-v1' or r.get('contract_sha256')!=ACCOUNTING_SHA or
  r.get('challenge_sha256')!=sha(ap) or r.get('challenge_receipt_sha256')!=sha(at) or r.get('ledger_root')!=str(LEDGER) or
  r.get('ledger')!=expected or r.get('source_http400_reserve_retained_micro')!=150000):raise Error('accounting receipt mismatch')
 return r

def prepare_contract():
 """Freeze exact inputs/code only; no activation, auth, ledger or provider call."""
 if Path.cwd().resolve()!=ROOT or OUTPUT.exists():raise Error('wrong context or existing output')
 r=accounting_evidence();bundle=case_binding.prepare(clock=now)
 if p.o.instant(now())>=p.o.instant(DEADLINE):raise Error('p0 cutoff event deadline elapsed')
 c={'schema':'faithful-forecast-p0-model-contract-v1','status':'frozen','caps':CAPS,
  'accounting_contract_sha256':ACCOUNTING_SHA,'accounting_receipt_sha256':sha(read(ACCOUNTING_RECEIPT)),
  'ledger_root':str(LEDGER),'starting_usage':r['ledger'],'source_reads':0,
  'execution_context':{'cwd':str(ROOT),'output_root':str(OUTPUT)},
  'case_binding':{'manifest_sha256':case_binding.MANIFEST,'bundle_sha256':sha(canonical(bundle)),
   'case_ids':[x['case']['case_id'] for x in bundle['prepared']], 'common_as_of_utc':bundle['common_as_of_utc'],
   'human_approval_sha256':inputs.APPROVAL,'user_relay_sha256':inputs.RAW,'user_relay_provenance_sha256':inputs.META},
  'limits':{'arms':['c','b'],'max_calls_per_arm':23,'match':'B gets only C call count','model':'gemini-3.8-flash',
   'location':'global','max_output_tokens':4096,'no_source':True,'no_p1':True,'no_retry':True,
   'strict_completion_before_utc':DEADLINE},
  'qualifications':['User-relayed Grok output; direct HTTP and original network bytes unverified.',
   'IPO market is partial: no valuation or primary-round condition; p0 forecasts market YES only.',
   'P0 must complete before candidate PCE release; actual news publication and unresolved status require independent checks.',
   'No user authorship of assistant proposals; user accepted test formulations; timestamp is recorded-at bound.'],
  'component_bindings':components()}
 seed.put(CONTRACT,c)
 return sha(read(CONTRACT))

def verify(expected_sha):
 """Read-only validation of independently attested frozen scope and all bytes."""
 cr,pr,rr=map(read,(CONTRACT,PACKET,RECEIPT));c,packet,receipt=map(obj,(cr,pr,rr));digest=packet.get('internal_digest');w=packet.get('context_binding',{})
 if (sha(cr)!=expected_sha or c.get('schema')!='faithful-forecast-p0-model-contract-v1' or c.get('status')!='frozen' or
  c.get('caps')!=CAPS or c.get('ledger_root')!=str(LEDGER) or c.get('source_reads')!=0 or c.get('accounting_contract_sha256')!=ACCOUNTING_SHA or
  packet.get('schema_version')!='eval_contract_challenge_packet_v1' or packet.get('overall_state')!='ready' or
  packet.get('witness',{}).get('identity')!='p0_model_witness' or packet.get('witness',{}).get('mode')!='read_only_offline' or
  packet.get('challenged_contract',{}).get('raw_sha256')!=expected_sha or digest!=sha(canonical({k:v for k,v in packet.items() if k!='internal_digest'})) or
  receipt.get('packet_raw_sha256')!=sha(pr) or receipt.get('packet_byte_count')!=len(pr) or
  receipt.get('packet_internal_digest')!=digest or receipt.get('state')!='ready'):raise Error('p0 challenge mismatch')
 if any(w.get(k)!=c.get(k) for k in ('execution_context','case_binding','limits')):raise Error('p0 review scope mismatch')
 actual=components();inspected=w.get('code_bindings_at_inspection',{})
 if c.get('component_bindings')!=actual or set(inspected)!=set(actual):raise Error('p0 component set or digest drift')
 for rel,h in actual.items():
  raw=read(ROOT/rel)
  if inspected.get(rel)!={'sha256':h,'size':len(raw)}:raise Error('p0 inspected bytes drift')
 a=accounting_evidence()
 if c.get('accounting_receipt_sha256')!=sha(read(ACCOUNTING_RECEIPT)) or c.get('starting_usage')!=a['ledger']:
  raise Error('p0 carry mismatch')
 bundle=case_binding.prepare(clock=now)
 if sha(canonical(bundle))!=c['case_binding']['bundle_sha256']:raise Error('p0 bundle drift')
 if c['execution_context']!={'cwd':str(ROOT),'output_root':str(OUTPUT)}:raise Error('p0 context mismatch')
 limits={'arms':['c','b'],'max_calls_per_arm':23,'match':'B gets only C call count','model':'gemini-3.8-flash',
   'location':'global','max_output_tokens':4096,'no_source':True,'no_p1':True,'no_retry':True,'strict_completion_before_utc':DEADLINE}
 if c['limits']!=limits:raise Error('p0 limits mismatch')
 return c,cr,pr,rr,bundle

def execute(expected_sha):
 """Activate once and perform reviewed model-only p0; never calls sources."""
 c,cr,pr,rr,bundle=verify(expected_sha)
 if OUTPUT.exists() or p.o.instant(now())>=p.o.instant(DEADLINE):raise Error('p0 unavailable or deadline elapsed')
 def account_review(raw):
  try:return accounting_launch.verify(ACCOUNTING,APACKET,ARECEIPT,ACCOUNTING_SHA)[1]==raw
  except Exception:return False
 accounting=adapter.reopen(successor_root=str(LEDGER),run_contract_path=str(ACCOUNTING),
  expected_contract_sha256=ACCOUNTING_SHA,verify_recovery_challenge=account_review)
 ledger=accounting
 try:
  if accounting.summary()!=c['starting_usage']:raise Error('ledger starting usage changed')
  import google.auth
  from google.auth.transport.requests import Request
  sys.path.insert(0,str(ROOT/'transport'))
  from oneshot import OneShotTransport
  creds,project=google.auth.default(scopes=['https://www.googleapis.com/auth/cloud-platform'])
  if not project:raise Error('project unavailable')
  if not creds.valid:creds.refresh(Request())
  if not creds.token:raise Error('credential unavailable')
  def reviewed(raw):
   try:return verify(expected_sha)[1]==raw and p.o.instant(now())<p.o.instant(DEADLINE)
   except Exception:return False
  ledger=adapter.activate(accounting,model_contract_path=str(CONTRACT),expected_model_contract_sha256=expected_sha,verify_p0_challenge=reviewed)
  record=adapter.stop_on_record_error(ledger,p.durable_recorder(OUTPUT))
  record('started',{'contract_sha256':expected_sha,'challenge_sha256':sha(pr),'receipt_sha256':sha(rr),'started_at_utc':now()})
  def token(provider):
   if provider!='vertex':raise Error('source token prohibited')
   if not creds.valid:creds.refresh(Request())
   if not creds.token:raise Error('credential unavailable')
   return creds.token
  transport=OneShotTransport(project,token)
  def check():
   try:return verify(expected_sha)[1]==cr and p.o.instant(now())<p.o.instant(DEADLINE)
   except Exception:return False
  factory=adapter.generator_factory(ledger,case_ids=c['case_binding']['case_ids'],transport=transport,verify_p0_binding=check)
  def guarded_record(name,value):
   record(name,value)
   if name.endswith('p0-receipt') and p.o.instant(value['durable_before_utc'])>=p.o.instant(DEADLINE):
    ledger.stop('p0 completed after candidate release deadline');raise Error('p0 deadline exceeded')
  result=p.run(bundle,verify_bundle=lambda x:check() and sha(canonical(x))==c['case_binding']['bundle_sha256'],
   generator_factory=factory,record=guarded_record,clock=now)
  record('summary',{'contract_sha256':expected_sha,'ledger':ledger.summary(),'batch':result,'status':'p0_only_no_human_review'})
  return result
 except BaseException:
  try:ledger.stop('p0 phase interrupted; no automatic retry')
  finally:ledger.poisoned=True
  raise
 finally:ledger.close()
