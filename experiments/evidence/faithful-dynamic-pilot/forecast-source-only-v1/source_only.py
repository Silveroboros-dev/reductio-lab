"""Create-only, accounting-only successor to stopped p0 HTTP429; no network.
Trusted caller boundary; separately reviewed model dispatcher and challenge are required.
"""
import json, os, re, sqlite3, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
for d in ('forecast-stopped-successor-v1','forecast-budget-v1','budget-v2','forecast-p0-launch-v1','forecast-429-successor-v1','forecast-p0-remaining-v1','forecast-429b-successor-v1','forecast-p0-final-two-v1'):
 sys.path.insert(0,str(ROOT/d))
import recovery as r, forecast_ledger as f, dispatch, post429, dispatch_remaining, post429b, dispatch_final_two
from ledger import Ledger, Stop, canonical, digest, now_utc
DB=ROOT/'forecast-429b-recovery-ledger-20261029-01/ledger.sqlite3'
DB_SHA='fe936ec04125fa108e321a7429788caede980630e1566354353c19e46f81d677'
P0_SHA='110f6dca66ad8d2554cb8db4432a9d5395a2ec67f742930dced4cfb6f4d994df'
FAILED_ID='generation:p0:case-04:c:03'
FAILED_REQ='4ddc5163215128a3ba24248d9ddd1aea61d1e7c5a863158c0bf7c08cd9f04969'
FAILED_RESP='e454245d288b6724dd369a9f36d4d3b2359b5fea630c862e0db16477175d6341'
CLAIM=ROOT/'forecast-source-only-successor-claim.json'
CAPS=r.CAPS
class Error(Stop):pass

def source_history():
 rows=[]
 for rel in ('live-source-ledger-20261029-01/ledger.sqlite3','live-source-ledger-20261029-02/ledger.sqlite3','forecast-live-ledger-20261029-01/ledger.sqlite3'):
  db=sqlite3.connect('file:'+str(ROOT/rel)+'?mode=ro&immutable=1',uri=True)
  try:rows.extend([{'id':i,'request_sha256':h} for i,h in db.execute("select id,request_hash from effects where kind in ('source','metadata') order by rowid")])
  finally:db.close()
 if len(rows)!=14 or len({x['id'] for x in rows})!=14:raise Error('historical sources mismatch')
 return rows

def inspect():
 """Read-only bind all effects, counts, original stopped journal and source lineage."""
 prior=post429b.inspect(); dispatch_final_two.verify(P0_SHA)
 r.read(DB,DB_SHA)
 db=sqlite3.connect('file:'+str(DB)+'?mode=ro&immutable=1',uri=True)
 try:
  row=db.execute('select stopped,exposure_micro,generation_attempts,count_attempts,source_attempts from run').fetchone()
  if row!=(1,1882731,274,206,0):raise Error('parent counters drift')
  effects=db.execute('select id,kind,state,http_status,request,request_hash,response,response_hash,quote_micro,actual_micro,related_id,detail from effects order by rowid').fetchall()
  expected=[]
  for case,arm,n in [('03','c',8),('03','b',8),('04','c',3)]:
   for i in range(1,n+1):
    q=f'p0:case-{case}:{arm}:{i:02d}';expected.extend([('count:'+q,'count'),('generation:'+q,'generation')])
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
  if cost!=58990:raise Error('usage mismatch')
  if db.execute('select event,reason from run_events order by seq').fetchall()!=[('forecast_started','8775185149d0fcb0c3cdb0d7069b9d35ef1551c92ad700a7022c390da5247fc7'),('p0_model_started',P0_SHA),('stopped','remaining p0 interrupted; no automatic retry')]:raise Error('run events drift')
 finally:db.close()
 r.read(DB,DB_SHA)
 return {'schema':'forecast-stopped-http429-parent-v1','db_sha256':DB_SHA,'original_p0_contract_sha256':P0_SHA,'lineage':prior,'exposure_micro':1882731,'generation_attempts':274,'count_attempts':206,'source_attempts':14,'new_settled_model_micro':58990,'http429_retained_micro':86016,'http400_retained_micro':150000,'failed_id':FAILED_ID,'failed_request_sha256':FAILED_REQ,'failed_response_sha256':FAILED_RESP,'completed_pair':'case-03','incomplete_case':'case-04','source_history':source_history()}

def config():
 c=r.obj(r.read(ROOT/'forecast-stopped-successor-v1/ledger_contract.json'))
 c.update(run_id='faithful-forecast-source-only-20261029-01',prior_micro=1882731,prior_generations=274,prior_counts=206)
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
  s=self._base.summary();s.update(source_attempts=s['source_attempts']+14,previous_source_attempts=14,prior_http400_charge_unknown_retained_micro=150000,prior_http429_charge_unknown_retained_micro=86016,prior_http429b_charge_unknown_retained_micro=86016,prior_http429c_charge_unknown_retained_micro=86016);return s
 def count(self,*a,**k):raise Error('accounting-only: provider calls forbidden')
 def generate(self,*a,**k):raise Error('accounting-only: provider calls forbidden')
 def source(self,*a,**k):raise Error('accounting-only: source calls forbidden')

def check_contract(path,expected,verify):
 raw=r.read(path,expected);c=r.obj(raw);parent=inspect()
 if (c.get('schema')!='faithful-forecast-source-only-accounting-v1' or c.get('status')!='frozen' or c.get('caps')!=CAPS or c.get('parent')!=parent or c.get('ledger_config')!=config() or c.get('bridge_sha256')!=digest(r.read(Path(__file__))) or c.get('scope')!={'mode':'accounting_only','provider_effects':'forbidden','max_new_sources':14,'no_retry':True}):raise Error('contract mismatch')
 if not callable(verify) or verify(raw) is not True:raise Error('independent accounting challenge required')
 return parent

def create(*,successor_root,contract_path,expected_sha,verify_challenge):
 parent=check_contract(contract_path,expected_sha,verify_challenge);root=Path(successor_root)
 if r.obj(r.read(contract_path,expected_sha)).get('ledger_root')!=str(root):raise Error('ledger root not bound')
 if not root.is_absolute() or root.exists() or root.parent.resolve()!=root.parent.absolute() or CLAIM.exists():raise Error('unsafe create or existing successor claim')
 claim=canonical({'schema':'forecast-source-only-claim-v1','parent_db_sha256':DB_SHA,'contract_sha256':expected_sha,'ledger_root':str(root)})
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
 claim=r.read(CLAIM);expected=canonical({'schema':'forecast-source-only-claim-v1','parent_db_sha256':DB_SHA,'contract_sha256':expected_sha,'ledger_root':str(root)})
 if claim!=expected or not root.is_absolute() or root.is_symlink() or root.resolve()!=root.absolute():raise Error('claim or path mismatch')
 base=Base(str(root),config(),create=False)
 try:
  if base.summary()['stopped'] or base.db.execute('select 1 from effects limit 1').fetchone() or base.db.execute("select 1 from run_events where event='source_started'").fetchone():raise Error('successor is not unused accounting-only')
  return Accounting(base,claim,parent,contract_path,expected_sha,lambda *_:False)
 except BaseException:base.close();raise

class Source(r.RecoveryLedger):
 """Only separately challenged exact source operations; model effects forbidden."""
 def __init__(self,base,claim,parent,accounting_path,accounting_sha,source_path,source_sha,external_verifier):
  self._source_path=Path(source_path);self._source_sha=source_sha;self._external_verifier=external_verifier
  super().__init__(base,claim,parent,accounting_path,accounting_sha,self._ticket)
 def verify_parent(self):
  r.read(CLAIM,self._claim_sha)
  if inspect()!=self._parent:raise Error('stopped predecessor changed')
  return self._parent
 def summary(self):return Accounting.summary(self)
 def _guard(self):
  f.ForecastLedger._guard(self);r.read(self._source_path,self._source_sha)
  if self.db.execute("select reason from run_events where event='source_started'").fetchall()!=[(self._source_sha,)]:raise Error('source stage binding drift')
 def _ticket(self,ticket,request):
  c=r.obj(r.read(self._source_path,self._source_sha))
  matches=[x for x in c['operations'] if x.get('ticket')==ticket and canonical(x.get('payload'))==request]
  return len(matches)==1 and self._external_verifier(ticket,request) is True
 def count(self,*a,**k):raise Error('source-only: model calls forbidden')
 def generate(self,*a,**k):raise Error('source-only: model calls forbidden')
 def source(self,op,provider,endpoint,request,ticket,transport):
  old=self._parent['source_history']
  if op in {x['id'] for x in old} or digest(request) in {x['request_sha256'] for x in old} or self.db.execute("select 1 from effects where kind='source' and request_hash=?",(digest(request),)).fetchone():raise Error('previous source operation cannot be repeated')
  raw=super().source(op,provider,endpoint,request,ticket,transport)
  try:
   if r.obj(raw).get('success') is not True:raise Error('source envelope not successful')
  except BaseException:
   self.stop('source envelope failed; do not retry');raise
  return raw

def activate(accounting,*,source_contract_path,expected_sha,verify_challenge,verify_ticket):
 if not isinstance(accounting,Accounting):raise Error('accounting-only successor required')
 accounting._guard();raw=r.read(source_contract_path,expected_sha);c=r.obj(raw)
 if (c.get('schema')!='faithful-forecast-source-only-run-v1' or c.get('status')!='frozen' or c.get('caps')!=CAPS or c.get('accounting_contract_sha256')!=accounting._contract_sha or c.get('ledger_root')!=str(accounting.root) or c.get('starting_usage')!=accounting.summary() or c.get('model_reads')!=0 or c.get('no_retry') is not True):raise Error('source contract mismatch')
 ops=c.get('operations')
 if not isinstance(ops,list) or not 1<=len(ops)<=14 or any(not isinstance(x,dict) or set(x)!={'ticket','payload'} or not isinstance(x['ticket'],dict) for x in ops):raise Error('invalid source operation list')
 old=accounting._parent['source_history'];oldids={x['id'] for x in old};oldhashes={x['request_sha256'] for x in old};seen=set();seen_hashes=set()
 for x in ops:
  ticket=x['ticket'];h=digest(canonical(x['payload']));ident=ticket.get('id')
  if not isinstance(ident,str) or not ident or ident in seen or ident in oldids or h in oldhashes or h in seen_hashes or ticket.get('request_sha256')!=h:raise Error('source operation repeat or binding mismatch')
  seen.add(ident);seen_hashes.add(h)
 if not callable(verify_challenge) or verify_challenge(raw) is not True or not callable(verify_ticket):raise Error('independent source challenge and ticket verifier required')
 db=accounting.db;db.execute('begin immediate')
 try:
  if accounting.summary()['stopped'] or db.execute('select 1 from effects limit 1').fetchone() or db.execute("select 1 from run_events where event='source_started'").fetchone():raise Error('source stage not unused')
  db.execute("insert into run_events(event,reason,at_utc) values ('source_started',?,?)",(expected_sha,now_utc()));db.execute('commit')
 except BaseException:
  if db.in_transaction:db.execute('rollback')
  raise
 return Source(accounting._base,r.read(CLAIM),accounting._parent,accounting._contract_path,accounting._contract_sha,source_contract_path,expected_sha,verify_ticket)
