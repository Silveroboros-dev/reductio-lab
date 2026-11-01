"""Exact CPI P1 launcher. Import and freeze/verify are offline and effect-free.

execute() alone is externally effectful; it requires a separately reviewed
frozen contract and existing source/accounting witness. No default invocation.
"""
import datetime as dt,importlib.metadata,json,os,random,subprocess,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
for name in ('forecast-p1-cpi-resumed-v1','forecast-p1-budget-successor-v1','forecast-p0-final-two-v1','forecast-p0-launch-v1','transport'):
 sys.path.insert(0,str(ROOT/name))
import admission_evidence as evidence,conditional_capture,conditional_news,dispatch_frozen,gate,venue_capture,status_guard
import p1_retry as retry,p1_budget as budget,retry_accounting_launch as accounting,p1_source_launch as source,pace,p0_launcher
CONTRACT=ROOT/'forecast-cpi-p1-model-contract-20261029-v1.json'
PACKET=ROOT/'forecast-cpi-p1-model-challenge-packet-v1.json'
RECEIPT=ROOT/'forecast-cpi-p1-model-challenge-receipt-v1.json'
OUTPUT=ROOT/'forecast-cpi-p1-results-20261029-01'
ACCOUNT_SHA='9e461fe6df6cfd05aabab675d4f366b4bf9843bccd138ad005f60b7c313d4f89'
SOURCE_SHA=conditional_capture.SOURCE_CONTRACT_SHA
PROJECT_SHA='8a6a45a093d29e5424feb93ea2299e13faf1e8eac56604629ec4af4702e3bef0'
FILES=(
 'forecast-p1-cpi-resumed-v1/live_launch.py','forecast-p1-cpi-resumed-v1/admission_evidence.py',
 'forecast-p1-cpi-resumed-v1/conditional_capture.py','forecast-p1-cpi-resumed-v1/conditional_news.py',
 'forecast-p1-cpi-resumed-v1/venue_capture.py','forecast-p1-cpi-resumed-v1/status_guard.py',
 'forecast-p1-cpi-resumed-v1/dispatch_frozen.py','forecast-p1-cpi-resumed-v1/orchestrate_retry.py',
 'forecast-p1-cpi-resumed-v1/runner_retry.py','forecast-p1-cpi-resumed-v1/stages.py','forecast-p1-cpi-resumed-v1/gate.py',
 'forecast-p1-budget-successor-v1/p1_retry.py','forecast-p1-budget-successor-v1/p1_budget.py',
 'forecast-p1-budget-successor-v1/retry_accounting_launch.py','forecast-p1-budget-successor-v1/p1_source_launch.py',
 'forecast-controller-v1/forecast.py','forecast-orchestrator-v1/orchestrator.py','forecast-budget-v1/forecast_ledger.py',
 'budget-v2/ledger.py','forecast-p0-final-two-v1/pace.py','forecast-p0-launch-v1/p0_launcher.py','transport/oneshot.py')
class Error(ValueError):pass

def now():return dt.datetime.now(dt.timezone.utc).isoformat()
def runtime():return {'python_executable':sys.executable,'python_version':sys.version.split()[0],'httpx_version':importlib.metadata.version('httpx'),'google_auth_version':importlib.metadata.version('google-auth')}
def components():return {name:gate.sha((ROOT/name).read_bytes()) for name in FILES}
def immutable_scope():
 pre=evidence.inspect();return {'schema':'cpi-p1-retry-model-contract-v1','status':'frozen','account_contract_sha256':ACCOUNT_SHA,
  'caps':budget.CAPS,'case_id':'case-02','cpi_receipt_sha256':pre['admission']['p0_receipt_sha256'],'no_canary':True,
  'retry_bridge_sha256':gate.sha(Path(retry.__file__).read_bytes()),'max_generations':112,'max_counts':112,
  'max_additional_attempts':20,'max_retry_per_operation':3,'arms':['c_no_news','b_no_news','c_news','b_news'],
  'source_contract_sha256':SOURCE_SHA,'prefreeze_sha256':evidence.PRE_SHA,'dispatch_contract_sha256':evidence.DISPATCH_SHA,
  'conditional_release_amendment_sha256':conditional_news.AMENDMENT_SHA,
  'gateway_observation_amendment_sha256':dispatch_frozen.GATEWAY_AMENDMENT_SHA,
  'scope':{'source':'seven remaining exact status observations only','source_retry':False,'generation_retries':'confirmed 429 only','pacing_seconds':20,'timeout_seconds':420,'max_status_age_seconds':300,'overall_cost_cap_usd':60,'overall_source_attempt_cap':28},
  'starting_usage':{'generation_attempts':299,'count_attempts':228,'source_attempts':21,'exposure_micro':2015563,'stopped':0},
  'execution_context':{'cwd':str(ROOT),'output_root':str(OUTPUT),'ledger_root':str(accounting.LEDGER)},
  'runtime':runtime(),'component_bindings':components(),'project_sha256':PROJECT_SHA,
  'qualification':'Exploratory; release timestamp assumes BEA embargo respected; actual earliest public visibility and upstream market cache age are unknown.'}
def freeze():
 if Path.cwd().resolve()!=ROOT or CONTRACT.exists() or OUTPUT.exists():raise Error('wrong directory or existing output')
 accounting.verify(ACCOUNT_SHA);source.verify(SOURCE_SHA)
 data=gate.canonical(immutable_scope());fd=os.open(CONTRACT,os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,'O_NOFOLLOW',0),0o600)
 with os.fdopen(fd,'wb') as f:f.write(data);f.flush();os.fsync(f.fileno())
 return gate.sha(data)
def verify(expected):
 raw=CONTRACT.read_bytes();pr=PACKET.read_bytes();rr=RECEIPT.read_bytes();c,w,r=map(json.loads,(raw,pr,rr));internal=w.get('internal_digest')
 if gate.sha(raw)!=expected or c!=immutable_scope() or gate.canonical(c)!=raw:raise Error('model contract drift')
 if (w.get('schema_version')!='eval_contract_challenge_packet_v1' or w.get('overall_state')!='ready' or w.get('witness',{}).get('identity')!='cpi_p1_model_witness' or w.get('witness',{}).get('mode')!='read_only_offline' or w.get('challenged_contract',{}).get('raw_sha256')!=expected or internal!=gate.sha(gate.canonical({k:v for k,v in w.items() if k!='internal_digest'})) or r.get('packet_raw_sha256')!=gate.sha(pr) or r.get('packet_byte_count')!=len(pr) or r.get('packet_internal_digest')!=internal or r.get('state')!='ready'):raise Error('independent model review missing')
 observed=w.get('context_binding',{}).get('code_bindings_at_inspection',{})
 if set(observed)!=set(FILES):raise Error('reviewed component set mismatch')
 for name,h in c['component_bindings'].items():
  if observed.get(name)!={'sha256':h,'size':len((ROOT/name).read_bytes())}:raise Error('reviewed code changed')
 if w.get('context_binding',{}).get('scope')!=c['scope'] or w.get('context_binding',{}).get('starting_usage')!=c['starting_usage']:raise Error('reviewed execution scope mismatch')
 return c,raw,pr,rr

def execute(expected):
 c,cr,pr,rr=verify(expected)
 if Path.cwd().resolve()!=ROOT or OUTPUT.exists():raise Error('wrong context or output exists')
 # Never print or persist provider credential values.
 import google.auth
 from google.auth.transport.requests import Request
 from oneshot import OneShotTransport
 creds,project=google.auth.default(scopes=['https://www.googleapis.com/auth/cloud-platform'])
 if not project or gate.sha(project.encode())!=PROJECT_SHA:raise Error('Google project mismatch')
 def token(provider):
  if provider=='vertex':
   if not creds.valid:creds.refresh(Request())
   if not creds.token:raise Error('Vertex credential unavailable')
   return creds.token
  if provider=='orthogonal':
   x=subprocess.run(['/usr/bin/security','find-generic-password','-s','com.maguire.orthogonal.live','-a','maguire','-w'],stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,check=False,timeout=15)
   if x.returncode or not x.stdout.strip():raise Error('Orthogonal credential unavailable')
   return x.stdout.strip().decode('ascii')
  raise Error('unexpected provider')
 def reviewed_account(raw):
  try:return accounting.verify(ACCOUNT_SHA)[1]==raw
  except Exception:return False
 def reviewed_source(raw):
  try:return source.verify(SOURCE_SHA)[1]==raw
  except Exception:return False
 source_contract=json.loads(source.CONTRACT.read_bytes())
 def ticket_ok(ticket,raw):return reviewed_source(source.CONTRACT.read_bytes()) and any(x['ticket']==ticket and gate.canonical(x['payload'])==raw for x in source_contract['operations'])
 def historical_ticket(ticket,raw,started):
  try:return ticket_ok(ticket,raw) and gate.o.instant(started)<gate.o.instant(ticket['expires_utc'])
  except Exception:return False
 account,source_stage=retry.reopen_after_source(accounting.LEDGER,contract_path=accounting.CONTRACT,contract_sha=ACCOUNT_SHA,verify_challenge=reviewed_account,source_path=source.CONTRACT,source_sha=SOURCE_SHA,verify_source_challenge=reviewed_source,verify_historical_ticket=historical_ticket,verify_ticket=ticket_ok)
 try:
  current=account.summary()
  if any(current.get(k)!=v for k,v in c['starting_usage'].items()):raise Error('starting ledger drift')
  guard=status_guard.Guard(account=account,clock=now,verify_status=venue_capture.verify_status)
  pre=evidence.inspect()
  if not guard.verify_status(pre['initial_status'],guard.case,pre['t1']):raise Error('initial status evidence invalid')
  def reviewed_model(raw):
   try:return verify(expected)[1]==raw
   except Exception:return False
  model=retry.activate_model(account,stage_path=CONTRACT,stage_sha=expected,verify_challenge=reviewed_model,verify_scope=guard.verify_scope)
  record=p0_launcher.durable_recorder(OUTPUT)
  record('started',{'model_contract_sha256':expected,'challenge_sha256':gate.sha(pr),'challenge_receipt_sha256':gate.sha(rr),'started_at_utc':now(),'qualification':c['qualification']})
  transport=OneShotTransport(project,token)
  def model_transport(provider,endpoint,raw):
   if provider!='vertex' or endpoint not in ('countTokens','gemini-3.8-flash@global'):raise Error('model route mismatch')
   return transport(provider,endpoint,raw)
  def source_transport(provider,endpoint,raw):
   if provider!='orthogonal' or endpoint!='/v1/run':raise Error('source route mismatch')
   return transport(provider,endpoint,raw)
  def operation(op):return any(op==x for x in pre['remaining_status_operations']) and ticket_ok(op['ticket'],gate.canonical(op['payload']))
  def dispatch_review(raw):return raw==evidence.DISPATCH.read_bytes() and gate.sha(raw)==evidence.DISPATCH_SHA and reviewed_model(cr)
  out=dispatch_frozen.run(prefreeze=pre,contract_bytes=evidence.DISPATCH.read_bytes(),contract_sha256=evidence.DISPATCH_SHA,verify_contract=dispatch_review,
   model_stage=model,source_stage=source_stage,model_transport=model_transport,source_transport=source_transport,
   decode_status=venue_capture.decode,verify_operation=operation,verify_news=evidence.verify_news,verify_status=guard.verify_status,
   verify_admission=evidence.verify_admission,verify_ledger=lambda facade:facade.account is account and account.verify() is None,
   record=record,clock=now,pacer=pace.Pacer(interval=20),confirmed429=retry.Confirmed429,rate_limit_exhausted=retry.RateLimitExhausted,
   sleep=time.sleep,jitter=random.random)
  record('run-result',{'result':out,'ledger':account.summary(),'qualification':c['qualification']});return out
 except BaseException:
  if not account.summary()['stopped']:account.stop('CPI p1 interrupted; no automatic recovery')
  raise
 finally:account.close()
