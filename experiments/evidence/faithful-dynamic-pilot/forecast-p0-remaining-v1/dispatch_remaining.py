"""Separately challenged continuation of untouched p0 case02–04 only.

No effects at import, freeze or verification. The interrupted case01, failed
request and both prior cost reservations remain bound in the predecessor.
"""
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
for d in ('forecast-p0-remaining-v1','forecast-p0-launch-v1','forecast-429-successor-v1','forecast-seed-launch-v1'):
 sys.path.insert(0,str(ROOT/d))
import remaining_binding as rem,p0_launcher as p,recovery_adapter as adapter,dispatch as prior,post429,post429_launch,launcher as seed

ACCOUNT_SHA='b0e2e6ffeff7e2b05f3c3ad37bab0bdbd758429b412b8c62e43586bc0d1360b4'
ACCOUNT=post429_launch.CONTRACT;APACKET=post429_launch.PACKET;ARECEIPT=post429_launch.RECEIPT
ACCOUNT_LOCAL=post429_launch.LOCAL_RECEIPT;LEDGER=post429_launch.LEDGER
CONTRACT=ROOT/'forecast-p0-remaining-model-contract-20261029-v1.json'
PACKET=ROOT/'forecast-p0-remaining-model-challenge-packet-v1.json'
RECEIPT=ROOT/'forecast-p0-remaining-model-challenge-receipt-v1.json'
OUTPUT=ROOT/'forecast-p0-remaining-results-20261029-01'
DEADLINE=prior.DEADLINE;CAPS=prior.CAPS
FILES=('forecast-p0-remaining-v1/dispatch_remaining.py','forecast-p0-remaining-v1/remaining_binding.py',
 'forecast-post429-accounting-contract-20261029-v1.json','forecast-post429-accounting-challenge-packet-v1.json',
 'forecast-post429-accounting-challenge-receipt-v1.json','forecast-post429-accounting-receipt-20261029.json',
 'forecast-p0-model-contract-20261029-v1.json','forecast-p0-model-challenge-packet-v1.json',
 'forecast-p0-model-challenge-receipt-v1.json','forecast-p0-results-20261029-01/started.json')
class Error(ValueError):pass
read=prior.read;obj=prior.obj;sha=prior.sha;canonical=prior.canonical;now=prior.now

def components():
 paths=set(FILES)|set(post429_launch.FILES)
 return {name:sha(read(ROOT/name)) for name in sorted(paths)}

def accounting_evidence():
 _,ar,ap,at=post429_launch.verify(ACCOUNT,APACKET,ARECEIPT,ACCOUNT_SHA)
 r=obj(read(ACCOUNT_LOCAL));expected={'stopped':0,'exposure_micro':1616450,'generation_attempts':242,'count_attempts':174,
  'source_attempts':14,'metadata_attempts':0,'metadata_retained_micro':0,'previous_source_attempts':14,
  'prior_http400_charge_unknown_retained_micro':150000,'prior_http429_charge_unknown_retained_micro':86016}
 if (r.get('schema')!='forecast-post429-accounting-receipt-v1' or r.get('contract_sha256')!=ACCOUNT_SHA or
  r.get('challenge_sha256')!=sha(ap) or r.get('challenge_receipt_sha256')!=sha(at) or r.get('ledger_root')!=str(LEDGER) or
  r.get('ledger')!=expected or r.get('retained_http400_micro')!=150000 or r.get('retained_http429_micro')!=86016):raise Error('429 accounting carry mismatch')
 return r

def prepare_contract():
 """Freeze exact continuation, no activation or calls."""
 if Path.cwd().resolve()!=ROOT or OUTPUT.exists() or p.o.instant(now())>=p.o.instant(DEADLINE):raise Error('context, output or deadline')
 a=accounting_evidence();info=rem.build(clock=now);bundle=info['bundle']
 scope={k:v for k,v in info.items() if k!='bundle'}
 c={'schema':'faithful-forecast-post429-model-v1','status':'frozen','caps':CAPS,'accounting_contract_sha256':ACCOUNT_SHA,
  'accounting_receipt_sha256':sha(read(ACCOUNT_LOCAL)),'ledger_root':str(LEDGER),'starting_usage':a['ledger'],
  'case_ids':list(rem.EXPECTED),'source_reads':0,'no_retry':True,
  'execution_context':{'cwd':str(ROOT),'output_root':str(OUTPUT)},'original_binding':scope,
  'limits':{'arms':['c','b'],'max_calls_per_arm':23,'match':'B gets only C call count','model':'gemini-3.8-flash',
   'location':'global','max_output_tokens':4096,'no_source':True,'no_p1':True,'strict_completion_before_utc':DEADLINE},
  'qualifications':['Case01 C exists but B and completed pair do not; neither will be repeated.',
   'Original p0 prompts, evidence, exact cases and common as-of are preserved; actual execution time is later.',
   'Grok user relay is not independently verified API response; market status and terms could change.',
   'Both HTTP400 and HTTP429 unknown charge reservations remain in exposure.'],
  'component_bindings':components()}
 seed.put(CONTRACT,c);return sha(read(CONTRACT))

def verify(expected_sha):
 cr,pr,rr=map(read,(CONTRACT,PACKET,RECEIPT));c,packet,receipt=map(obj,(cr,pr,rr));dg=packet.get('internal_digest');w=packet.get('context_binding',{})
 if (sha(cr)!=expected_sha or c.get('schema')!='faithful-forecast-post429-model-v1' or c.get('status')!='frozen' or
  c.get('caps')!=CAPS or c.get('ledger_root')!=str(LEDGER) or c.get('accounting_contract_sha256')!=ACCOUNT_SHA or
  c.get('case_ids')!=list(rem.EXPECTED) or c.get('source_reads')!=0 or c.get('no_retry') is not True or
  packet.get('schema_version')!='eval_contract_challenge_packet_v1' or packet.get('overall_state')!='ready' or
  packet.get('witness',{}).get('identity')!='p0_remaining_witness' or packet.get('witness',{}).get('mode')!='read_only_offline' or
  packet.get('challenged_contract',{}).get('raw_sha256')!=expected_sha or dg!=sha(canonical({k:v for k,v in packet.items() if k!='internal_digest'})) or
  receipt.get('packet_raw_sha256')!=sha(pr) or receipt.get('packet_byte_count')!=len(pr) or receipt.get('packet_internal_digest')!=dg or receipt.get('state')!='ready'):raise Error('remaining model challenge mismatch')
 if any(w.get(k)!=c.get(k) for k in ('execution_context','original_binding','limits')):raise Error('remaining review scope mismatch')
 actual=components();seen=w.get('code_bindings_at_inspection',{})
 if c.get('component_bindings')!=actual or set(seen)!=set(actual):raise Error('remaining code drift')
 for rel,h in actual.items():
  if seen.get(rel)!={'sha256':h,'size':len(read(ROOT/rel))}:raise Error('remaining inspected bytes mismatch')
 a=accounting_evidence()
 if c.get('accounting_receipt_sha256')!=sha(read(ACCOUNT_LOCAL)) or c.get('starting_usage')!=a['ledger']:raise Error('remaining accounting binding mismatch')
 info=rem.build(clock=now);bundle=info.pop('bundle')
 if c.get('original_binding')!=info or tuple(x['case']['case_id'] for x in bundle['prepared'])!=rem.EXPECTED:raise Error('remaining inputs drift')
 if c.get('execution_context')!={'cwd':str(ROOT),'output_root':str(OUTPUT)}:raise Error('remaining execution context mismatch')
 limits={'arms':['c','b'],'max_calls_per_arm':23,'match':'B gets only C call count','model':'gemini-3.8-flash',
   'location':'global','max_output_tokens':4096,'no_source':True,'no_p1':True,'strict_completion_before_utc':DEADLINE}
 if c.get('limits')!=limits:raise Error('remaining limits mismatch')
 return c,cr,pr,rr,bundle

def execute(expected_sha):
 c,cr,pr,rr,bundle=verify(expected_sha)
 if OUTPUT.exists() or p.o.instant(now())>=p.o.instant(DEADLINE):raise Error('deadline or output')
 def account_review(raw):
  try:return post429_launch.verify(ACCOUNT,APACKET,ARECEIPT,ACCOUNT_SHA)[1]==raw
  except Exception:return False
 ledger=post429.reopen(successor_root=str(LEDGER),contract_path=str(ACCOUNT),expected_sha=ACCOUNT_SHA,verify_challenge=account_review)
 try:
  if ledger.summary()!=c['starting_usage']:raise Error('starting usage mismatch')
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
  ledger=post429.activate(ledger,model_contract_path=str(CONTRACT),expected_sha=expected_sha,verify_challenge=reviewed)
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
  factory=adapter.generator_factory(ledger,case_ids=c['case_ids'],transport=transport,verify_p0_binding=check)
  def record_and_deadline(name,value):
   record(name,value)
   if name.endswith('p0-receipt') and p.o.instant(value['durable_before_utc'])>=p.o.instant(DEADLINE):
    ledger.stop('p0 completed after candidate release deadline');raise Error('p0 deadline exceeded')
  result=p.run(bundle,verify_bundle=lambda x:check() and sha(canonical(x))==c['original_binding']['bundle_sha256'],
   generator_factory=factory,record=record_and_deadline,clock=now)
  record('summary',{'contract_sha256':expected_sha,'ledger':ledger.summary(),'batch':result,'status':'three_case_p0_only_no_human_review'})
  return result
 except BaseException:
  try:ledger.stop('remaining p0 interrupted; no automatic retry')
  finally:ledger.poisoned=True
  raise
 finally:ledger.close()
