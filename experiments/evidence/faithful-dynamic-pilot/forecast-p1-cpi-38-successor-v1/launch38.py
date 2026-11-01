"""Create-only reviewed continuation of original CPI news C/B experiment.

freeze()/verify() are offline. execute() is externally effectful, starts a new
ledger, and requires the exact independent witness; it must be invoked only
once. Original P1 journals and responses are read-only and never repeated.
"""
import datetime as dt,importlib.metadata,json,os,random,sqlite3,subprocess,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
for name in ('forecast-p1-cpi-38-successor-v1','forecast-p1-cpi-recovery-v1','forecast-p1-cpi-resumed-v1','forecast-p1-budget-successor-v1','forecast-p0-final-two-v1','forecast-p0-launch-v1','transport'):
 sys.path.insert(0,str(ROOT/name))
import ledger38,runner38,venue38,guard38,reconstruct,history
import gate,admission_evidence,venue_capture,conditional_capture,p1_source_launch as source,pace,p0_launcher
CONTRACT=ROOT/'forecast-cpi-p1-38-model-contract-20261029-v1.json'
PACKET=ROOT/'forecast-cpi-p1-38-model-challenge-packet-v1.json'
RECEIPT=ROOT/'forecast-cpi-p1-38-model-challenge-receipt-v1.json'
SOURCE=ROOT/'forecast-cpi-p1-status38-source-contract-20261029-v1.json'
SOURCE_SHA='18cf777fd3ad03dfbb815383563a14ba3c4a3ad9dc0929d8f7a61a83585e6e33'
LEDGER=ROOT/'forecast-cpi-p1-38-successor-ledger-20261029-01'
CLAIM=ROOT/'forecast-cpi-p1-38-successor.claim.json'
OUTPUT=ROOT/'forecast-cpi-p1-38-successor-results-20261029-01'
PROJECT_SHA='8a6a45a093d29e5424feb93ea2299e13faf1e8eac56604629ec4af4702e3bef0'
FILES=('forecast-p1-cpi-38-successor-v1/launch38.py','forecast-p1-cpi-38-successor-v1/ledger38.py','forecast-p1-cpi-38-successor-v1/runner38.py',
 'forecast-p1-cpi-38-successor-v1/venue38.py','forecast-p1-cpi-38-successor-v1/guard38.py','forecast-p1-cpi-38-successor-v1/reconstruct.py','forecast-p1-cpi-38-successor-v1/history.py',
 'forecast-p1-cpi-recovery-v1/recovery_ledger.py','forecast-p1-cpi-recovery-v1/replay.py','forecast-p1-cpi-resumed-v1/gate.py',
 'forecast-p1-cpi-resumed-v1/admission_evidence.py','forecast-p1-cpi-resumed-v1/conditional_capture.py','forecast-p1-cpi-resumed-v1/conditional_news.py',
 'forecast-p1-cpi-resumed-v1/venue_capture.py','forecast-p1-cpi-resumed-v1/status_guard.py','forecast-p1-cpi-resumed-v1/dispatch_frozen.py',
 'forecast-p1-cpi-resumed-v1/orchestrate_retry.py','forecast-p1-cpi-resumed-v1/runner_retry.py','forecast-p1-cpi-resumed-v1/stages.py',
 'forecast-p1-budget-successor-v1/p1_retry.py','forecast-p1-budget-successor-v1/p1_budget.py','forecast-p1-budget-successor-v1/p1_source_launch.py',
 'forecast-p1-budget-successor-v1/retry_accounting_launch.py','forecast-controller-v1/forecast.py','forecast-orchestrator-v1/orchestrator.py',
 'forecast-budget-v1/forecast_ledger.py','budget-v2/ledger.py','forecast-p0-final-two-v1/pace.py','forecast-p0-launch-v1/p0_launcher.py','transport/oneshot.py')
class Error(ValueError):pass

def now():return dt.datetime.now(dt.timezone.utc).isoformat()
def runtime():return {'python_executable':sys.executable,'python_version':sys.version.split()[0],'httpx_version':importlib.metadata.version('httpx'),'google_auth_version':importlib.metadata.version('google-auth')}
def read_source():
 raw=SOURCE.read_bytes()
 if gate.sha(raw)!=SOURCE_SHA:raise Error('source contract mismatch')
 c=json.loads(raw);ops=c['operations'];price=ROOT/'forecast-cpi-p1-source-ui-prices-20261029-v2.json'
 if gate.sha(price.read_bytes())!=c['price_observation_sha256'] or len(ops)!=13 or [x['ticket']['id'] for x in ops]!=[f'p1-cpi-status-{i:02d}' for i in range(6,19)]:raise Error('source operations or pricing mismatch')
 for op in ops:
  t=op['ticket'];rawreq=gate.canonical(op['payload'])
  if op['kind']!='status_refresh' or op['payload']!={'api':'kalshi','path':'/markets','body':{},'query':{'tickers':'KXCPI-26OCT-T0.2'}} or t['request_sha256']!=gate.sha(rawreq) or t['evidence_sha256']!=c['price_observation_sha256'] or t['max_micro']!=150000:raise Error('source operation drift')
 return c

def scope():
 parent=ledger38.inspect_parent();pre=admission_evidence.inspect();src=read_source()
 return {'schema':'cpi-p1-38-news-continuation-v1','status':'frozen','parent':parent,'source_contract_sha256':SOURCE_SHA,
  'prefreeze_sha256':admission_evidence.PRE_SHA,'dispatch_contract_sha256':admission_evidence.DISPATCH_SHA,
  'case_id':'case-02','arms':['c_news','b_news'],'source_ids':[x['ticket']['id'] for x in src['operations']],
  'scope':{'no_old_model_or_count_repeats':True,'no_source_retry':True,'no_canary':True,'only_confirmed_429_retry':True,'max_extra_attempts':20,'max_retries_per_operation':3,'pacing_seconds':20,'timeout_seconds':420,'status_max_age_seconds':300,'overall_source_attempt_cap':38,'overall_usd_cap':60,'max_generations':411,'max_counts':340},
  'starting_usage':{'generation_attempts':315,'count_attempts':244,'source_attempts':25,'exposure_micro':2069419,'stopped':0},
  'execution_context':{'cwd':str(ROOT),'output_root':str(OUTPUT),'ledger_root':str(LEDGER)},'config':ledger38.config(),'runtime':runtime(),
  'component_bindings':{n:gate.sha((ROOT/n).read_bytes()) for n in FILES},'project_sha256':PROJECT_SHA,
  'qualification':'No-news C format repair is post-hoc; its original response was invalid JSON. B/no-news was reconstructed offline from successful raw responses. BEA timing assumes embargo respected; gateway upstream cache age unknown.'}

def freeze():
 if Path.cwd().resolve()!=ROOT or CONTRACT.exists() or CLAIM.exists() or LEDGER.exists() or OUTPUT.exists():raise Error('successor context unavailable')
 source.verify(conditional_capture.SOURCE_CONTRACT_SHA);data=gate.canonical(scope());fd=os.open(CONTRACT,os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,'O_NOFOLLOW',0),0o600)
 with os.fdopen(fd,'wb') as f:f.write(data);f.flush();os.fsync(f.fileno())
 return gate.sha(data)

def verify(expected):
 raw=CONTRACT.read_bytes();pr=PACKET.read_bytes();rr=RECEIPT.read_bytes();c,w,r=map(json.loads,(raw,pr,rr));inside=w.get('internal_digest')
 if gate.sha(raw)!=expected or c!=scope() or gate.canonical(c)!=raw:raise Error('contract drift')
 if (w.get('schema_version')!='eval_contract_challenge_packet_v1' or w.get('overall_state')!='ready' or w.get('witness',{}).get('identity')!='cpi_p1_38_model_witness' or w.get('witness',{}).get('mode')!='read_only_offline' or w.get('challenged_contract',{}).get('raw_sha256')!=expected or inside!=gate.sha(gate.canonical({k:v for k,v in w.items() if k!='internal_digest'})) or r.get('packet_raw_sha256')!=gate.sha(pr) or r.get('packet_byte_count')!=len(pr) or r.get('packet_internal_digest')!=inside or r.get('state')!='ready'):raise Error('independent review missing')
 observed=w.get('context_binding',{}).get('code_bindings_at_inspection',{})
 if set(observed)!=set(FILES):raise Error('reviewed component set mismatch')
 for name,h in c['component_bindings'].items():
  if observed.get(name)!={'sha256':h,'size':len((ROOT/name).read_bytes())}:raise Error('reviewed code changed')
 if w.get('context_binding',{}).get('scope')!=c['scope'] or w.get('context_binding',{}).get('starting_usage')!=c['starting_usage']:raise Error('review scope mismatch')
 return c,raw,pr,rr

def initial_status():
 db=sqlite3.connect('file:'+str(reconstruct.PARENT)+'?mode=ro',uri=True);db.row_factory=sqlite3.Row
 try:r=dict(db.execute("select * from effects where id='p1-cpi-status-05'").fetchone())
 finally:db.close()
 raw=bytes(r['response'])
 if gate.sha(raw)!=r['response_hash'] or r['response_hash']!='0f8cff07c0f2288c7df936fc5101c15e324572ab816a9c738195c09aad8c8633':raise Error('parent status drift')
 status=venue_capture.extract(raw);status.update(source_op_id=r['id'],response_sha256=r['response_hash'],observed_at_utc=r['completed_at_utc'],captured_at_utc=r['completed_at_utc']);return status

def execute(expected):
 c,cr,pr,rr=verify(expected)
 if Path.cwd().resolve()!=ROOT or CLAIM.exists() or LEDGER.exists() or OUTPUT.exists():raise Error('successor already started or context invalid')
 # The price ticket expires independently of market-status freshness.
 src=read_source();expiry=gate.o.instant(src['operations'][0]['ticket']['expires_utc'])
 if gate.o.instant(now())>=expiry:raise Error('price evidence expired; fresh price and successor contract required')
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
 claim=gate.canonical({'parent_sha256':reconstruct.PARENT_SHA,'contract_sha256':expected,'ledger_root':str(LEDGER)})
 fd=os.open(CLAIM,os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,'O_NOFOLLOW',0),0o600)
 with os.fdopen(fd,'wb') as f:f.write(claim);f.flush();os.fsync(f.fileno())
 base=ledger38.Base(str(LEDGER),ledger38.config(),create=True)
 try:
  def reviewed():
   try:return verify(expected)[1]==cr and CLAIM.read_bytes()==claim
   except Exception:return False
  stage=None
  class AccountView:
   def verify(self):
    if not reviewed():raise Error('reviewed contract drift')
   def summary(self):return stage.summary()
  guard=guard38.Guard(account=AccountView(),clock=now,verify_status=lambda s,case,at:venue38.verify_status(s,case,at,successor_db=LEDGER/'ledger.sqlite3',operations=src['operations']))
  stage=ledger38.Stage(base,guard.verify_scope,reviewed,src['operations'])
  if any(stage.summary().get(k)!=v for k,v in c['starting_usage'].items()):raise Error('starting budget mismatch')
  status=initial_status()
  if not guard.verify_status(status,guard.case,status['captured_at_utc']):raise Error('predecessor status invalid')
  pre=admission_evidence.inspect();record=p0_launcher.durable_recorder(OUTPUT)
  record('started',{'contract_sha256':expected,'challenge_sha256':gate.sha(pr),'challenge_receipt_sha256':gate.sha(rr),'started_at_utc':now(),'qualification':c['qualification']})
  transport=OneShotTransport(project,token)
  def model_transport(provider,endpoint,raw):
   if provider!='vertex' or endpoint not in ('countTokens','gemini-3.8-flash@global'):raise Error('model route mismatch')
   return transport(provider,endpoint,raw)
  def source_transport(provider,endpoint,raw):
   if provider!='orthogonal' or endpoint!='/v1/run':raise Error('source route mismatch')
   return transport(provider,endpoint,raw)
  def ticket_ok(ticket,raw):return reviewed() and any(x['ticket']==ticket and gate.canonical(x['payload'])==raw for x in src['operations'])
  refresh=venue38.refresher(stage,src['operations'],transport=source_transport,verify_ticket=ticket_ok,record=record)
  out=runner38.run(pre['admission'],status,ledger=stage,transport=model_transport,refresh_status=refresh,
   verify_status=guard.verify_status,verify_admission=admission_evidence.verify_admission,verify_ledger=lambda x:x is stage and reviewed(),
   record=record,clock=now,pacer=pace.Pacer(interval=20),confirmed429=ledger38.retry.Confirmed429,
   rate_limit_exhausted=ledger38.retry.RateLimitExhausted,sleep=time.sleep,jitter=random.random)
  record('run-result',{'result':out,'ledger':stage.summary(),'qualification':c['qualification']});return out
 except BaseException:
  if not base.summary()['stopped']:base.stop('successor interrupted; no automatic repeat')
  raise
 finally:base.close()
