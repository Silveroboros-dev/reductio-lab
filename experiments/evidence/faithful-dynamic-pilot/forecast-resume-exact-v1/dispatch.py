"""Offline freeze/review and explicitly invoked continuation dispatcher.

Import, prepare_contract and verify do not call model/source APIs. Execute is
an externally effectful, one-shot operation and requires independent review.
It resumes only the three previously failed p0 branches. Historical 429s are
confirmed responses, not uncertain effects. Source and canary calls are denied.
"""
from __future__ import annotations
import datetime as dt, importlib.metadata, importlib.util, json, os, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
for folder in ('forecast-resume-exact-v1','forecast-429-resume-account-v1','forecast-p1-search-v1','forecast-p0-final-two-v1','forecast-p0-launch-v1','forecast-seed-launch-v1'):
 sys.path.insert(0,str(ROOT/folder))
import resume,resume_ledger as ledger,search,pace,p0_launcher
# A predecessor also uses the generic name ``bridge``. Preserve that module
# identity for its own imports and load this adapter under a unique name.
_bridge_spec=importlib.util.spec_from_file_location('resume429_bridge',ROOT/'forecast-resume-exact-v1/bridge.py')
bridge=importlib.util.module_from_spec(_bridge_spec)
_bridge_spec.loader.exec_module(bridge)
# The predecessor search module imports a different ``accounting_launch``.
# Load the new accounting module under an unambiguous module identity.
_account_spec=importlib.util.spec_from_file_location('resume429_accounting_launch',ROOT/'forecast-429-resume-account-v1/accounting_launch.py')
accounting_launch=importlib.util.module_from_spec(_account_spec)
_account_spec.loader.exec_module(accounting_launch)

CONTRACT=ROOT/'forecast-p0-429-resume-model-contract-20261029-v1.json'
ACCOUNT=ROOT/'forecast-p0-429-resume-accounting-contract-20261029-v1.json'
APACKET=ROOT/'forecast-p0-429-resume-accounting-challenge-packet-v1.json'
ARECEIPT=ROOT/'forecast-p0-429-resume-accounting-challenge-receipt-v1.json'
ALOCAL=ROOT/'forecast-p0-429-resume-accounting-receipt-20261029.json'
PACKET=ROOT/'forecast-p0-429-resume-challenge-packet-v1.json'
RECEIPT=ROOT/'forecast-p0-429-resume-challenge-receipt-v1.json'
LEDGER_ROOT=ROOT/'forecast-p0-429-resume-ledger-20261029-01'
OUTPUT=ROOT/'forecast-p0-429-resume-results-20261029-01'
USER='forecast-429-resume-user-request-20261029-v1.json'
USER_SHA='4bceddf16cabfcbd5784338e97fe214c8a9c70ecf6f6d0f11c53a9a8e1be2d7e'
PROJECT_SHA='8a6a45a093d29e5424feb93ea2299e13faf1e8eac56604629ec4af4702e3bef0'
ORDER=('case-02','case-01','case-04')
DEADLINE='2026-10-29T12:30:00Z'
EXTRA_FILES=('forecast-resume-exact-v1/dispatch.py','forecast-resume-exact-v1/resume.py',
 'forecast-resume-exact-v1/bridge.py','forecast-resume-exact-v1/test_resume.py',
 'forecast-resume-exact-v1/test_bridge.py','forecast-resume-exact-v1/test_dispatch.py','forecast-429-resume-account-v1/resume_ledger.py',
 'forecast-429-resume-account-v1/test_resume_ledger.py','forecast-429-resume-account-v1/accounting_launch.py',
 'forecast-429-resume-account-v1/freeze_accounting.py',
 'forecast-p0-429-resume-accounting-contract-20261029-v1.json',
 'forecast-p0-429-resume-accounting-challenge-packet-v1.json','forecast-p0-429-resume-accounting-challenge-receipt-v1.json',
 'forecast-p0-429-resume-accounting-receipt-20261029.json','forecast-p0-429-resume.claim.json',
 'forecast-source-only-ledger-20261029-01/ledger.sqlite3',
 'forecast-p1-search-results-20261029-01/summary.json','forecast-p1-search-results-20261029-01/p1-openai-official-you.raw.json',
 'forecast-p1-search-results-20261029-01/p1-openai-related-serper-news.raw.json',
 'forecast-p1-search-contract-20261029-v1.json','forecast-p1-search-challenge-packet-v1.json',
 'forecast-p1-search-challenge-receipt-v1.json','forecast-p0-results-20261029-01/00-p0-input.json',
 'forecast-p0-results-20261029-01/00-p0-c.json','forecast-p0-remaining-results-20261029-01/00-p0-input.json',
 'forecast-p0-remaining-results-20261029-01/00-p0-c.json','forecast-p0-final-two-results-20261029-01/01-p0-input.json',
 'forecast-recovery-ledger-20261029-01/ledger.sqlite3','forecast-429-recovery-ledger-20261029-01/ledger.sqlite3',
 'forecast-429b-recovery-ledger-20261029-01/ledger.sqlite3',USER)
class Error(ValueError):pass

def now():return dt.datetime.now(dt.timezone.utc).isoformat()
def instant(s):
 try:v=dt.datetime.fromisoformat(s.replace('Z','+00:00'))
 except (ValueError,AttributeError):raise Error('invalid UTC timestamp') from None
 if v.utcoffset()!=dt.timedelta(0):raise Error('UTC required')
 return v
def read(path):
 p=Path(path)
 if not p.is_absolute() or p.is_symlink() or not p.is_file() or p.resolve()!=p.absolute():raise Error('unsafe input')
 return p.read_bytes()
def obj(b):
 def unique(items):
  d={}
  for k,v in items:
   if k in d:raise Error('duplicate JSON key')
   d[k]=v
  return d
 try:x=json.loads(b,object_pairs_hook=unique)
 except (ValueError,TypeError,UnicodeDecodeError):raise Error('invalid JSON') from None
 if not isinstance(x,dict):raise Error('object required')
 return x

def runtime():
 return {'python_executable':sys.executable,'python_version':sys.version.split()[0],
  'httpx_version':importlib.metadata.version('httpx'),'google_auth_version':importlib.metadata.version('google-auth')}
def components():
 prior=search.components();names=set(prior)|set(EXTRA_FILES)
 return {name:resume.sha(read(ROOT/name)) for name in sorted(names)}
def expected_limits():
 return {'model':'gemini-3.8-flash','location':'global','case_order':list(ORDER),'max_new_generations':55,
  'max_new_counts':52,'max_new_sources':0,'max_old_429_attempts_each':1,'no_canary':True,
  'no_prior_success_replay_effect':True,'pacing_seconds':20,'timeout_seconds':420,
  'strict_p0_completion_before_utc':DEADLINE,'model_version_behavior':'stop if inconsistent',
  'p1':'not authorized by this phase'}
def scope():
 return {'cases':['case-01','case-02','case-04'],'allowed_retries':list(ledger.FAILED),'max_retry_per_old':1,
  'max_new_generations':55,'max_new_counts':52,'source_calls':0,'canary_calls':0,'strict_p0_deadline_utc':DEADLINE}
def accounting_evidence():
 ah=resume.sha(read(ACCOUNT))
 _,ar,ap,at=accounting_launch.verify(ah)
 r=obj(read(ALOCAL));s=r.get('ledger',{})
 if (r.get('schema')!='p0-429-resume-accounting-receipt-v1' or r.get('contract_sha256')!=ah or
  r.get('challenge_sha256')!=resume.sha(ap) or r.get('challenge_receipt_sha256')!=resume.sha(at) or
  r.get('ledger_root')!=str(LEDGER_ROOT) or (s.get('stopped'),s.get('exposure_micro'),s.get('generation_attempts'),s.get('count_attempts'),s.get('source_attempts'))!=(0,1889731,274,206,16)):
  raise Error('accounting receipt mismatch')
 return ah,r

def prepare_contract():
 """Create-only exact model run contract; no ledger or API calls."""
 if Path.cwd().resolve()!=ROOT or CONTRACT.exists() or not LEDGER_ROOT.exists() or OUTPUT.exists() or instant(now())>=instant(DEADLINE):raise Error('context, output or deadline')
 if resume.sha(read(ROOT/USER))!=USER_SHA:raise Error('human request evidence mismatch')
 ah,a=accounting_evidence();parent=ledger.inspect();replayed=[resume.verify_replay(case) for case in ORDER]
 c={'schema':'p0-429-exact-resume-model-contract-v1','status':'frozen','parent':parent,'scope':scope(),
  'accounting_contract_sha256':ah,'accounting_receipt_sha256':resume.sha(read(ALOCAL)),
  'starting_usage':a['ledger'],'bridge_sha256':resume.sha(read(ROOT/'forecast-429-resume-account-v1/resume_ledger.py')),
  'ledger_root':str(LEDGER_ROOT),'caps':ledger.CAPS,'user_request_sha256':USER_SHA,'project_sha256':PROJECT_SHA,
  'runtime':runtime(),'replay_checks':replayed,'limits':expected_limits(),
  'execution_context':{'cwd':str(ROOT),'output_root':str(OUTPUT)},'component_bindings':components(),
  'scope_qualification':'Original user question asks to complete old experiment by repeating failed calls only. Operator interprets this as one retry of each confirmed 429 plus previously unstarted necessary steps; successful generations and countTokens are replayed from receipts without provider calls. No new data are introduced. Output timestamps reflect actual completion; as-of is historical input cutoff only. Exact user message UTC time unknown.'}
 raw=resume.canonical(c);fd=os.open(CONTRACT,os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,'O_NOFOLLOW',0),0o600)
 with os.fdopen(fd,'wb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
 fd=os.open(ROOT,os.O_RDONLY)
 try:os.fsync(fd)
 finally:os.close(fd)
 return resume.sha(raw)

def verify(expected_sha):
 """Read-only full code, parent, human request, and independent witness check."""
 cr,pr,rr=(read(x) for x in (CONTRACT,PACKET,RECEIPT));c,p,r=map(obj,(cr,pr,rr));digest=p.get('internal_digest');w=p.get('context_binding',{})
 if (resume.sha(cr)!=expected_sha or c.get('schema')!='p0-429-exact-resume-model-contract-v1' or c.get('status')!='frozen' or
  p.get('schema_version')!='eval_contract_challenge_packet_v1' or p.get('overall_state')!='ready' or
  p.get('witness',{}).get('identity')!='p0_429_resume_witness' or p.get('witness',{}).get('mode')!='read_only_offline' or
  p.get('challenged_contract',{}).get('raw_sha256')!=expected_sha or digest!=resume.sha(resume.canonical({k:v for k,v in p.items() if k!='internal_digest'})) or
  r.get('packet_raw_sha256')!=resume.sha(pr) or r.get('packet_byte_count')!=len(pr) or r.get('packet_internal_digest')!=digest or r.get('state')!='ready'):
  raise Error('independent challenge mismatch')
 comps=components();observed=w.get('code_bindings_at_inspection',{})
 if c.get('component_bindings')!=comps or set(observed)!=set(comps):raise Error('component binding changed')
 for rel,h in comps.items():
  if observed.get(rel)!={'sha256':h,'size':len(read(ROOT/rel))}:raise Error('witness code binding mismatch')
 ah,a=accounting_evidence()
 if (c.get('parent')!=ledger.inspect() or c.get('scope')!=scope() or c.get('caps')!=ledger.CAPS or c.get('ledger_root')!=str(LEDGER_ROOT) or
  c.get('accounting_contract_sha256')!=ah or c.get('accounting_receipt_sha256')!=resume.sha(read(ALOCAL)) or c.get('starting_usage')!=a['ledger'] or
  c.get('bridge_sha256')!=resume.sha(read(ROOT/'forecast-429-resume-account-v1/resume_ledger.py')) or c.get('limits')!=expected_limits() or c.get('runtime')!=runtime() or
  c.get('user_request_sha256')!=USER_SHA or resume.sha(read(ROOT/USER))!=USER_SHA or c.get('project_sha256')!=PROJECT_SHA or
  c.get('execution_context')!={'cwd':str(ROOT),'output_root':str(OUTPUT)} or
  c.get('replay_checks')!=[resume.verify_replay(case) for case in ORDER]):raise Error('contract or replay inputs drift')
 if any(w.get(k)!=c.get(k) for k in ('parent','scope','limits','execution_context','replay_checks','user_request_sha256','project_sha256','runtime')):raise Error('witness scope mismatch')
 return c,cr,pr,rr

class PacedLedger:
 """Wait before, not inside, a counted provider effect."""
 def __init__(self,base,gate):self.base=base;self.gate=gate;self.pacer=pace.Pacer(interval=20)
 def _call(self,fn,*args):
  self.pacer.wait(self.gate)
  try:return fn(*args)
  finally:self.pacer.ended()
 def retry_failed(self,*args):return self._call(self.base.retry_failed,*args)
 def count_new(self,*args):return self._call(self.base.count_new,*args)
 def generate_new(self,*args):return self._call(self.base.generate_new,*args)

def execute(expected_sha):
 """One-shot live continuation; call only after full offline challenge."""
 c,cr,pr,rr=verify(expected_sha)
 if not LEDGER_ROOT.is_dir() or OUTPUT.exists() or instant(now())>=instant(DEADLINE):raise Error('accounting absent, already started or deadline elapsed')
 # ADC discovery only here; never print credential material or project ID.
 import google.auth
 from google.auth.transport.requests import Request
 sys.path.insert(0,str(ROOT/'transport'))
 from oneshot import OneShotTransport
 creds,project=google.auth.default(scopes=['https://www.googleapis.com/auth/cloud-platform'])
 if not project or resume.sha(project.encode())!=PROJECT_SHA:raise Error('Google project changed')
 if not creds.valid:creds.refresh(Request())
 if not creds.token:raise Error('credential unavailable')
 def reviewed_account(raw):
  try:return accounting_launch.verify(c['accounting_contract_sha256'])[1]==raw
  except Exception:return False
 accounting=ledger.reopen(str(LEDGER_ROOT),contract_path=str(ACCOUNT),contract_sha256=c['accounting_contract_sha256'],verify_challenge=reviewed_account)
 book=accounting;record=None
 try:
  if book.summary()!=c['starting_usage']:raise Error('starting budget drift')
  def reviewed_model(raw):
   try:return verify(expected_sha)[1]==raw and instant(now())<instant(DEADLINE)
   except Exception:return False
  book=ledger.activate(accounting,model_contract_path=str(CONTRACT),expected_sha256=expected_sha,verify_challenge=reviewed_model)
  record=p0_launcher.durable_recorder(OUTPUT)
  record('started',{'contract_sha256':expected_sha,'challenge_sha256':resume.sha(pr),'receipt_sha256':resume.sha(rr),'started_at_utc':now()})
  def gate():
   try:return verify(expected_sha)[1]==cr and instant(now())<instant(DEADLINE)
   except Exception:return False
  def token(provider):
   if provider!='vertex':raise Error('source provider prohibited')
   if not creds.valid:creds.refresh(Request())
   if not creds.token:raise Error('credential unavailable')
   return creds.token
  underlying=OneShotTransport(project,token)
  def transport(provider,endpoint,raw):
   if provider!='vertex' or endpoint not in ('countTokens','gemini-3.8-flash@global') or not gate():raise Error('provider or frozen context violation')
   return underlying(provider,endpoint,raw)
  paced=PacedLedger(book,gate)
  def check_binding(binding,stage,request):return gate() and resume.sha(resume.canonical(request))==binding.get('request_sha256')
  generate=bridge.generator(paced,transport,check_binding)
  outcomes=[]
  for case in ORDER:
   outcome=resume.run_case(case,generate=generate,verify_live=lambda b,r:gate() and resume.sha(resume.canonical(r))==b.get('request_sha256'),record=record,clock=now)
   outcomes.append(outcome)
  result={'schema':'p0-429-resume-summary-v1','status':'completed_p0_only','contract_sha256':expected_sha,'outcomes':outcomes,'ledger':book.summary(),'completed_at_utc':now()}
  record('summary',result);return result
 except BaseException:
  if not book.summary()['stopped']:
   (book.stop if hasattr(book,'stop') else book.base.stop)('resumption interrupted; no automatic further retry')
  raise
 finally:book.close()
