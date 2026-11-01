"""Create-only, accounting-only successor to stopped p0 HTTP429; no network.
Trusted caller boundary; separately reviewed model dispatcher and challenge are required.
"""
import json, os, re, sqlite3, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
for d in ('forecast-stopped-successor-v1','forecast-budget-v1','budget-v2','forecast-p0-launch-v1'):
 sys.path.insert(0,str(ROOT/d))
import recovery as r, forecast_ledger as f, dispatch
from ledger import Ledger, Stop, canonical, digest, now_utc
DB=ROOT/'forecast-recovery-ledger-20261029-01/ledger.sqlite3'
DB_SHA='ed9d2aad306864dd228c85ffe3fc4ddc092f6b3b2272139bb12743893de72de7'
P0_SHA='cc1b4469ea42b3a9052743023404178e72776b8a05a06825fe9e477b739cc524'
FAILED_ID='generation:p0:case-01:b:02'
FAILED_REQ='d3616e8dcad5edd899faec1167108b94e014b3906e4cd6b1444875e7deb4fb29'
FAILED_RESP='e454245d288b6724dd369a9f36d4d3b2359b5fea630c862e0db16477175d6341'
CLAIM=ROOT/'forecast-429-successor-claim.json'
CAPS=r.CAPS
class Error(Stop):pass

def inspect():
 """Read-only bind all effects, counts, original stopped journal and source lineage."""
 prior=r.inspect_stopped(); dispatch.verify(P0_SHA)
 r.read(DB,DB_SHA)
 db=sqlite3.connect('file:'+str(DB)+'?mode=ro&immutable=1',uri=True)
 try:
  row=db.execute('select stopped,exposure_micro,generation_attempts,count_attempts,source_attempts from run').fetchone()
  if row!=(1,1616450,242,174,0):raise Error('parent counters drift')
  effects=db.execute('select id,kind,state,http_status,request,request_hash,response,response_hash,quote_micro,actual_micro,related_id,detail from effects order by rowid').fetchall()
  expected=[]
  for arm,n in [('c',8),('b',2)]:
   for i in range(1,n+1):
    q=f'p0:case-01:{arm}:{i:02d}';expected.extend([('count:'+q,'count'),('generation:'+q,'generation')])
  if [(x[0],x[1]) for x in effects]!=expected:raise Error('effect ids or order mismatch')
  counts={};cost=0
  for ident,kind,state,status,req,rh,raw,sh,quote,actual,related,detail in effects:
   if state!='succeeded' or digest(req)!=rh or digest(raw)!=sh:raise Error('bad recorded effect')
   events=db.execute('select state,detail from events where effect_id=? order by seq',(ident,)).fetchall()
   if ident==FAILED_ID:
    if (status,rh,sh,quote,actual,detail)!=(429,FAILED_REQ,FAILED_RESP,86016,None,'non-200; billed status unknown') or counts.get(related)!=rh:raise Error('failed effect drift')
    if events!=[('prepared',None),('started',None),('succeeded',None)]:raise Error('failed event sequence drift')
   elif kind=='count':
    if status!=200 or actual!=0 or quote!=0 or not r.positive_int(r.obj(raw).get('totalTokens')):raise Error('count invalid')
    counts[ident]=rh
    if events!=[('prepared',None),('started',None),('succeeded',None),('accounted','0')]:raise Error('count event mismatch')
   else:
    u=r.obj(raw).get('usageMetadata',{});p=u.get('promptTokenCount');t=u.get('totalTokenCount')
    if status!=200 or not r.positive_int(p) or not r.positive_int(t) or t<p or actual!=(3*p+15*(t-p)+1)//2 or quote!=86016 or counts.get(related)!=rh:raise Error('model settlement mismatch')
    if events!=[('prepared',None),('started',None),('succeeded',None),('accounted',str(actual))]:raise Error('generation event mismatch')
    cost+=actual
  if cost!=19976:raise Error('usage mismatch')
  if db.execute('select event,reason from run_events order by seq').fetchall()!=[('forecast_started','c7382e21dbfe01240dfc33ba802bb37cff054e532f1a99b9553e1a6a90b77cbc'),('p0_model_started',P0_SHA),('stopped','p0 phase interrupted; no automatic retry')]:raise Error('run events drift')
 finally:db.close()
 r.read(DB,DB_SHA)
 return {'schema':'forecast-stopped-http429-parent-v1','db_sha256':DB_SHA,'original_p0_contract_sha256':P0_SHA,'lineage':prior,'exposure_micro':1616450,'generation_attempts':242,'count_attempts':174,'source_attempts':14,'new_settled_model_micro':19976,'http429_retained_micro':86016,'http400_retained_micro':150000,'failed_id':FAILED_ID,'failed_request_sha256':FAILED_REQ,'failed_response_sha256':FAILED_RESP,'completed_c_only':'case-01','untouched_cases':['case-02','case-03','case-04']}

def config():
 c=r.obj(r.read(ROOT/'forecast-stopped-successor-v1/ledger_contract.json'))
 c.update(run_id='faithful-forecast-post429-20261029-01',prior_micro=1616450,prior_generations=242,prior_counts=174)
 return c
class Base(Ledger):
 @staticmethod
 def _validate_contract(c):
  if c!=config():raise Error('post429 ledger configuration drift')

class Accounting(f.ForecastLedger):
 def verify_parent(self):
  r.read(CLAIM,self._claim_sha)
  if inspect()!=self._parent:raise Error('post429 predecessor changed')
  return self._parent
 def summary(self):
  s=self._base.summary();s.update(source_attempts=s['source_attempts']+14,previous_source_attempts=14,prior_http400_charge_unknown_retained_micro=150000,prior_http429_charge_unknown_retained_micro=86016);return s
 def count(self,*a,**k):raise Error('accounting-only: provider calls forbidden')
 def generate(self,*a,**k):raise Error('accounting-only: provider calls forbidden')
 def source(self,*a,**k):raise Error('accounting-only: source calls forbidden')

class Model(r.ModelOnlyLedger):
 def verify_parent(self):
  r.read(CLAIM,self._claim_sha)
  if inspect()!=self._parent:raise Error('post429 predecessor changed')
  return self._parent
 def summary(self):return Accounting.summary(self)
 def _guard(self):
  f.ForecastLedger._guard(self)
  r.read(self._model_path,self._model_sha)
  if self.db.execute("select reason from run_events where event='p0_model_started'").fetchall()!=[(self._model_sha,)]:raise Error('model marker drift')
 def _id(self,op,prefix,request):
  if not isinstance(op,str) or not re.fullmatch(prefix+r':p0:case-0[234]:[cb]:(?:0[1-9]|1[0-9]|2[0-3])',op):raise Error('case or attempt outside permitted scope')
  if digest(canonical(request))==FAILED_REQ:raise Error('failed model request cannot be repeated')
 def count(self,op,request,transport):self._id(op,'count',request);return super().count(op,request,transport)
 def generate(self,op,request,count_id,transport):
  self._id(op,'generation',request)
  if count_id!='count:'+op.removeprefix('generation:'):raise Error('count binding mismatch')
  return super().generate(op,request,count_id,transport)

def check_contract(path,expected,verify):
 raw=r.read(path,expected);c=r.obj(raw);parent=inspect()
 if (c.get('schema')!='faithful-forecast-post429-accounting-v1' or c.get('status')!='frozen' or c.get('caps')!=CAPS or c.get('parent')!=parent or c.get('ledger_config')!=config() or c.get('bridge_sha256')!=digest(r.read(Path(__file__))) or c.get('scope')!={'mode':'accounting_only','provider_effects':'forbidden','future_cases':['case-02','case-03','case-04'],'no_retry':True}):raise Error('contract mismatch')
 if not callable(verify) or verify(raw) is not True:raise Error('independent accounting challenge required')
 return parent

def create(*,successor_root,contract_path,expected_sha,verify_challenge):
 parent=check_contract(contract_path,expected_sha,verify_challenge);root=Path(successor_root)
 if r.obj(r.read(contract_path,expected_sha)).get('ledger_root')!=str(root):raise Error('ledger root not bound')
 if not root.is_absolute() or root.exists() or root.parent.resolve()!=root.parent.absolute() or CLAIM.exists():raise Error('unsafe create or existing successor claim')
 claim=canonical({'schema':'forecast-post429-claim-v1','parent_db_sha256':DB_SHA,'contract_sha256':expected_sha,'ledger_root':str(root)})
 fd=os.open(CLAIM,os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,'O_NOFOLLOW',0),0o600)
 with os.fdopen(fd,'wb') as out:out.write(claim);out.flush();os.fsync(out.fileno())
 fd=os.open(CLAIM.parent,os.O_RDONLY)
 try:os.fsync(fd)
 finally:os.close(fd)
 base=Base(str(root),config(),create=True)
 try:
  base.db.execute("insert into run_events(event,reason,at_utc) values ('forecast_started',?,?)",(expected_sha,now_utc()))
  return Accounting(base,claim,parent,contract_path,expected_sha,lambda *_:False)
 except BaseException:base.close();raise

def reopen(*,successor_root,contract_path,expected_sha,verify_challenge):
 parent=check_contract(contract_path,expected_sha,verify_challenge);root=Path(successor_root)
 if r.obj(r.read(contract_path,expected_sha)).get('ledger_root')!=str(root):raise Error('ledger root not bound')
 claim=r.read(CLAIM);expected=canonical({'schema':'forecast-post429-claim-v1','parent_db_sha256':DB_SHA,'contract_sha256':expected_sha,'ledger_root':str(root)})
 if claim!=expected or not root.is_absolute() or root.is_symlink() or root.resolve()!=root.absolute():raise Error('claim or path mismatch')
 base=Base(str(root),config(),create=False)
 try:
  if base.summary()['stopped'] or base.db.execute('select 1 from effects limit 1').fetchone() or base.db.execute("select 1 from run_events where event='p0_model_started'").fetchone():raise Error('successor is not unused accounting-only')
  return Accounting(base,claim,parent,contract_path,expected_sha,lambda *_:False)
 except BaseException:base.close();raise

def activate(accounting,*,model_contract_path,expected_sha,verify_challenge):
 if not isinstance(accounting,Accounting):raise Error('accounting-only successor required')
 accounting._guard();raw=r.read(model_contract_path,expected_sha);c=r.obj(raw)
 if (c.get('schema')!='faithful-forecast-post429-model-v1' or c.get('status')!='frozen' or c.get('caps')!=CAPS or c.get('accounting_contract_sha256')!=accounting._contract_sha or c.get('ledger_root')!=str(accounting.root) or c.get('starting_usage')!=accounting.summary() or c.get('case_ids')!=['case-02','case-03','case-04'] or c.get('source_reads')!=0 or c.get('no_retry') is not True):raise Error('model contract mismatch')
 if not callable(verify_challenge) or verify_challenge(raw) is not True:raise Error('independent model challenge required')
 db=accounting.db;db.execute('begin immediate')
 try:
  if accounting.summary()['stopped'] or db.execute('select 1 from effects limit 1').fetchone() or db.execute("select 1 from run_events where event='p0_model_started'").fetchone():raise Error('model stage not unused')
  db.execute("insert into run_events(event,reason,at_utc) values ('p0_model_started',?,?)",(expected_sha,now_utc()));db.execute('commit')
 except BaseException:
  if db.in_transaction:db.execute('rollback')
  raise
 return Model(accounting._base,r.read(CLAIM),accounting._parent,accounting._contract_path,accounting._contract_sha,lambda *_:False,model_contract_path,expected_sha)
