"""Frozen recovery launch after original CPI C formatter HTTP-200 failed JSON.

Import, freeze, verify are offline; execute is externally effectful only after
independent review and an existing accounting-only successor. The first model
response remains immutable. No C/no-news model/count operation is ever repeated.
"""
import datetime as dt,importlib.metadata,json,os,random,sqlite3,subprocess,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
for name in ('forecast-p1-cpi-recovery-v1','forecast-p1-cpi-resumed-v1','forecast-p1-budget-successor-v1','forecast-p0-final-two-v1','forecast-p0-launch-v1','transport'):
 sys.path.insert(0,str(ROOT/name))
import gate,replay,recovery_ledger as book,account_launch as accounting,runner_recovery,venue_recovery
import admission_evidence,venue_capture,conditional_capture,status_guard,p1_source_launch as source,pace,p0_launcher
CONTRACT=ROOT/'forecast-cpi-p1-recovery-model-contract-20261029-v1.json'
PACKET=ROOT/'forecast-cpi-p1-recovery-model-challenge-packet-v1.json'
RECEIPT=ROOT/'forecast-cpi-p1-recovery-model-challenge-receipt-v1.json'
OUTPUT=ROOT/'forecast-cpi-p1-recovery-results-20261029-01'
ACCOUNT_SHA='8be75442e031feb9dcaa509e8550716fb09c3e50e76b15f9cf9cddcf4dcab2b8'
SOURCE_SHA=conditional_capture.SOURCE_CONTRACT_SHA
REPAIR=ROOT/'forecast-cpi-p1-posthoc-format-repair-20261029-v1.json'
REPAIR_SHA='c4e94fc345fc1d671b9a56cd8af9b8eb08784131a7c8fcf49ceb4c303c0ebd33'
PROJECT_SHA='8a6a45a093d29e5424feb93ea2299e13faf1e8eac56604629ec4af4702e3bef0'
FILES=('forecast-p1-cpi-recovery-v1/live_recovery.py','forecast-p1-cpi-recovery-v1/replay.py','forecast-p1-cpi-recovery-v1/runner_recovery.py',
 'forecast-p1-cpi-recovery-v1/recovery_ledger.py','forecast-p1-cpi-recovery-v1/account_launch.py','forecast-p1-cpi-recovery-v1/venue_recovery.py',
 'forecast-p1-cpi-resumed-v1/admission_evidence.py','forecast-p1-cpi-resumed-v1/conditional_capture.py','forecast-p1-cpi-resumed-v1/conditional_news.py',
 'forecast-p1-cpi-resumed-v1/venue_capture.py','forecast-p1-cpi-resumed-v1/status_guard.py','forecast-p1-cpi-resumed-v1/dispatch_frozen.py',
 'forecast-p1-cpi-resumed-v1/orchestrate_retry.py','forecast-p1-cpi-resumed-v1/runner_retry.py','forecast-p1-cpi-resumed-v1/stages.py','forecast-p1-cpi-resumed-v1/gate.py',
 'forecast-p1-budget-successor-v1/p1_retry.py','forecast-p1-budget-successor-v1/p1_budget.py','forecast-p1-budget-successor-v1/p1_source_launch.py',
 'forecast-p1-budget-successor-v1/retry_accounting_launch.py','forecast-controller-v1/forecast.py','forecast-orchestrator-v1/orchestrator.py',
 'forecast-budget-v1/forecast_ledger.py','budget-v2/ledger.py','forecast-p0-final-two-v1/pace.py','forecast-p0-launch-v1/p0_launcher.py','transport/oneshot.py')
class Error(ValueError):pass

def now():return dt.datetime.now(dt.timezone.utc).isoformat()
def runtime():return {'python_executable':sys.executable,'python_version':sys.version.split()[0],'httpx_version':importlib.metadata.version('httpx'),'google_auth_version':importlib.metadata.version('google-auth')}
def components():return {name:gate.sha((ROOT/name).read_bytes()) for name in FILES}
def initial_status():
 db=sqlite3.connect('file:'+str(book.PARENT)+'?mode=ro',uri=True);db.row_factory=sqlite3.Row
 try:r=db.execute("select * from effects where id='p1-cpi-status-03'").fetchone()
 finally:db.close()
 if r is None:raise Error('missing last status')
 r=dict(r);raw=bytes(r['response'])
 if gate.sha(raw)!=r['response_hash'] or r['response_hash']!='05914342b0d2992d7e7d257fcbec4ed206f409e2e41f64fd8c48358491563e48':raise Error('last status mismatch')
 status=venue_capture.extract(raw);status.update(source_op_id=r['id'],response_sha256=r['response_hash'],observed_at_utc=r['completed_at_utc'],captured_at_utc=r['completed_at_utc'])
 return status

def scope():
 pre=admission_evidence.inspect();parent=book.inspect_parent()
 if gate.sha(REPAIR.read_bytes())!=REPAIR_SHA or REPAIR.read_bytes()!=gate.canonical(replay.repaired_outcome()):raise Error('posthoc derivative mismatch')
 return {'schema':'cpi-p1-recovery-model-contract-v1','status':'frozen','account_contract_sha256':ACCOUNT_SHA,'source_contract_sha256':SOURCE_SHA,
  'parent':parent,'prefreeze_sha256':admission_evidence.PRE_SHA,'dispatch_contract_sha256':admission_evidence.DISPATCH_SHA,'posthoc_repair_sha256':REPAIR_SHA,
  'case_id':'case-02','arms':['b_no_news','c_news','b_news'],'b_no_news_matched_calls':8,
  'scope':{'no_successful_model_repeat':True,'no_formatter_repeat':True,'no_count_repeat':True,'no_canary':True,
   'status_operations':[f'p1-cpi-status-{n:02d}' for n in range(4,9)],'source_retry':False,
   'only_confirmed_429_retry':True,'max_extra_attempts':20,'max_retries_per_operation':3,
   'pacing_seconds':20,'timeout_seconds':420,'status_max_age_seconds':300,'overall_source_attempt_cap':28,'overall_usd_cap':60},
  'starting_usage':{'generation_attempts':307,'count_attempts':236,'source_attempts':23,'exposure_micro':2033331,'stopped':0},
  'execution_context':{'cwd':str(ROOT),'output_root':str(OUTPUT),'ledger_root':str(book.LEDGER)},'runtime':runtime(),
  'component_bindings':components(),'project_sha256':PROJECT_SHA,
  'qualification':'Original C/no-news HTTP200 is strict invalid JSON; one-character deterministic repair is post-hoc, not preregistered strict output. PCE time assumes embargo respected and actual first visibility is unknown. Orthogonal gateway cache age unknown.'}
def freeze():
 if Path.cwd().resolve()!=ROOT or CONTRACT.exists() or OUTPUT.exists() or not book.LEDGER.is_dir():raise Error('recovery account, cwd, or output state invalid')
 accounting.verify(ACCOUNT_SHA);source.verify(SOURCE_SHA);data=gate.canonical(scope());fd=os.open(CONTRACT,os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,'O_NOFOLLOW',0),0o600)
 with os.fdopen(fd,'wb') as f:f.write(data);f.flush();os.fsync(f.fileno())
 return gate.sha(data)
def verify(expected):
 raw=CONTRACT.read_bytes();pr=PACKET.read_bytes();rr=RECEIPT.read_bytes();c,w,r=map(json.loads,(raw,pr,rr));internal=w.get('internal_digest')
 if gate.sha(raw)!=expected or c!=scope() or gate.canonical(c)!=raw:raise Error('recovery model contract drift')
 if (w.get('schema_version')!='eval_contract_challenge_packet_v1' or w.get('overall_state')!='ready' or w.get('witness',{}).get('identity')!='cpi_p1_recovery_model_witness' or w.get('witness',{}).get('mode')!='read_only_offline' or w.get('challenged_contract',{}).get('raw_sha256')!=expected or internal!=gate.sha(gate.canonical({k:v for k,v in w.items() if k!='internal_digest'})) or r.get('packet_raw_sha256')!=gate.sha(pr) or r.get('packet_byte_count')!=len(pr) or r.get('packet_internal_digest')!=internal or r.get('state')!='ready'):raise Error('independent recovery review missing')
 observed=w.get('context_binding',{}).get('code_bindings_at_inspection',{})
 if set(observed)!=set(FILES):raise Error('reviewed component set mismatch')
 for name,h in c['component_bindings'].items():
  if observed.get(name)!={'sha256':h,'size':len((ROOT/name).read_bytes())}:raise Error('reviewed code changed')
 if w.get('context_binding',{}).get('scope')!=c['scope'] or w.get('context_binding',{}).get('starting_usage')!=c['starting_usage']:raise Error('reviewed scope mismatch')
 return c,raw,pr,rr

def execute(expected):
 c,cr,pr,rr=verify(expected)
 if Path.cwd().resolve()!=ROOT or OUTPUT.exists():raise Error('wrong context or output exists')
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
 def account_review(raw):
  try:return accounting.verify(ACCOUNT_SHA)[1]==raw
  except Exception:return False
 base=book.reopen(contract_sha=ACCOUNT_SHA,verify_challenge=account_review)
 try:
  def reviewed():
   try:return verify(expected)[1]==cr
   except Exception:return False
  stage=None
  class AccountView:
   def verify(self):
    if not reviewed():raise Error('recovery contract no longer valid')
   def summary(self):return stage.summary()
  guard=status_guard.Guard(account=AccountView(),clock=now,verify_status=lambda s,case,at:venue_recovery.verify_status(s,case,at,recovery_db=book.LEDGER/'ledger.sqlite3'))
  stage=book.RecoveryStage(base,guard.verify_scope,reviewed)
  if any(stage.summary().get(k)!=v for k,v in c['starting_usage'].items()):raise Error('starting recovery usage drift')
  status=initial_status()
  if not guard.verify_status(status,guard.case,status['captured_at_utc']):raise Error('last recorded status invalid')
  pre=admission_evidence.inspect();source_contract=json.loads(source.CONTRACT.read_bytes());operations=[x for x in source_contract['operations'] if x['kind']=='status_refresh' and x['ticket']['id'] in c['scope']['status_operations']]
  if [x['ticket']['id'] for x in operations]!=c['scope']['status_operations']:raise Error('remaining source operations differ')
  def ticket_valid(ticket,raw):
   try:return source.verify(SOURCE_SHA)[1]==source.CONTRACT.read_bytes() and any(x['ticket']==ticket and gate.canonical(x['payload'])==raw for x in operations)
   except Exception:return False
  record=p0_launcher.durable_recorder(OUTPUT);record('started',{'model_contract_sha256':expected,'challenge_sha256':gate.sha(pr),'challenge_receipt_sha256':gate.sha(rr),'started_at_utc':now(),'qualification':c['qualification']})
  transport=OneShotTransport(project,token)
  def model_transport(provider,endpoint,raw):
   if provider!='vertex' or endpoint not in ('countTokens','gemini-3.8-flash@global'):raise Error('model route mismatch')
   return transport(provider,endpoint,raw)
  def source_transport(provider,endpoint,raw):
   if provider!='orthogonal' or endpoint!='/v1/run':raise Error('source route mismatch')
   return transport(provider,endpoint,raw)
  refresh=venue_recovery.make_refresher(stage,operations,transport=source_transport,verify_ticket=ticket_valid,record=record)
  out=runner_recovery.run(pre['admission'],status,ledger=stage,transport=model_transport,refresh_status=refresh,
   verify_status=guard.verify_status,verify_admission=admission_evidence.verify_admission,
   verify_ledger=lambda x:x is stage and reviewed(),record=record,clock=now,pacer=pace.Pacer(interval=20),
   confirmed429=book.r.Confirmed429,rate_limit_exhausted=book.r.RateLimitExhausted,sleep=time.sleep,jitter=random.random)
  record('run-result',{'result':out,'ledger':stage.summary(),'qualification':c['qualification']});return out
 except BaseException:
  if not base.summary()['stopped']:base.stop('recovery interrupted; no automatic repeat')
  raise
 finally:base.close()
