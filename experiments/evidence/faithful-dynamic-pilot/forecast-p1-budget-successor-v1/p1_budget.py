"""CPI p1 accounting continuation after completed historical p0, offline preparation.

No live execution, credentials, provider transport or user authority are supplied.
Source and model stages each require a separately frozen, reviewed contract.
Their wrappers share one journal so source status refresh can coexist with model
execution; reviewer callbacks must enforce the actual five-minute status gate.
"""
from __future__ import annotations
import datetime as dt
import hashlib,json,os,re,sqlite3,sys
from decimal import Decimal
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
for d in ('budget-v2','forecast-budget-v1','forecast-429-resume-account-v1'):
 sys.path.insert(0,str(ROOT/d))
from ledger import Ledger, Stop, canonical, digest, now_utc
import forecast_ledger as f,resume_ledger as old
PARENT='forecast-p0-429-resume-ledger-20261029-01/ledger.sqlite3'
PARENT_SHA='43896046c4f9fa56e1bf85ff0afc47e6d5413d79047795761d6150125bfee3ba'
SUMMARY='forecast-p0-429-resume-results-20261029-01/summary.json'
CPI_RECEIPT='forecast-p0-429-resume-results-20261029-01/case-02-p0-receipt.json'
SUMMARY_SHA='7a0478f313c0aaf71fc4bfe13b33e5d525b43c05526455901e40d82d686d8ac1'
CPI_RECEIPT_SHA='d4d0c8c75d4ba5c5168f9081ea96e30befbe9e08bc1b2329aafa7e524ad6e453'
CPI_FROZEN_SHA='17285df9ffacdfe999fd420a4493b7d9e25c1ae585c4783ba7930e5be4e9f065'
CPI_INPUT_SHA='8c67563dddc6b27c5ec47e97b6823d2194244fe36bd62134644d0fb47dcb8339'
MODEL_SHA='3ac56c255fb474008b358853b5e44af5d38c2817fae8a67aae56819fbbe2e682'
CLAIM=ROOT/'forecast-p1-cpi-budget.claim.json'
CAPS={'total_usd_micro':60000000,'total_generation_attempts':835,'total_count_attempts':767,'total_source_attempts':28}
class Error(Stop):pass

def read(path,expected=None):
 p=Path(path)
 if not p.is_absolute():p=ROOT/p
 if not p.is_file() or p.is_symlink() or p.resolve()!=p.absolute():raise Error('unsafe input')
 b=p.read_bytes()
 if expected is not None and digest(b)!=expected:raise Error('input digest mismatch')
 return b

def inspect_parent():
 prior=old.inspect();read(PARENT,PARENT_SHA)
 db=sqlite3.connect('file:'+str(ROOT/PARENT)+'?mode=ro&immutable=1',uri=True)
 try:
  if db.execute('select stopped,exposure_micro,generation_attempts,count_attempts,source_attempts from run').fetchone()!=(0,1988563,299,228,0):raise Error('completed p0 parent counters drift')
  rows=db.execute('select id,kind,state,http_status,request,request_hash,response,response_hash,actual_micro,quote_micro,related_id,started_at_utc,completed_at_utc from effects order by rowid').fetchall()
  if len(rows)!=47:raise Error('p0 effect count drift')
  counts={};used=set();total=0;retries=set()
  for i,k,state,status,req,rh,resp,sh,amount,quote,related,started,done in rows:
   if state!='succeeded' or status!=200 or digest(req)!=rh or digest(resp)!=sh or not isinstance(amount,int) or amount<0 or not started or not done or done>='2026-10-29T12:30:00':raise Error('unsettled p0 effect')
   events=db.execute('select state,detail from events where effect_id=? order by seq',(i,)).fetchall()
   if [x[0] for x in events]!=['prepared','started','succeeded','accounted'] or events[-1][1]!=str(amount):raise Error('effect transitions invalid')
   if k=='count':
    if amount!=0 or quote!=0 or not i.startswith('newcount:'):raise Error('bad count')
    token=json.loads(resp).get('totalTokens')
    if type(token) is not int or not 0<token<=16384:raise Error('bad count response')
    counts[i]=rh
   elif k=='generation':
    u=json.loads(resp)['usageMetadata'];n=u['promptTokenCount'];t=u['totalTokenCount'];model=json.loads(resp).get('modelVersion')
    if type(n) is not int or type(t) is not int or n<=0 or t<=n or n>16384 or t-n>8192 or amount!=(3*n+15*(t-n)+1)//2 or quote!=86016 or not isinstance(model,str) or not(model=='gemini-3.8-flash' or model.startswith('gemini-3.8-flash-')):raise Error('generation accounting mismatch')
    if i.startswith('retry1:'):
     oldid=i.removeprefix('retry1:');h=old.historical_429(oldid);expected='historical-count:'+h['old_db_sha256']+':'+h['old_count_id']+':'+h['count_response_sha256']
     if rh!=h['request_sha256'] or related!=expected or oldid in retries:raise Error('historical count binding mismatch')
     retries.add(oldid)
    elif i.startswith('newgeneration:'):
     if related!='newcount:'+i.removeprefix('newgeneration:') or counts.get(related)!=rh or related in used:raise Error('new count binding mismatch')
     used.add(related)
    else:raise Error('unknown generation')
    total+=amount
   else:raise Error('source or unknown effect in p0')
  if len(counts)!=22 or len(used)!=22 or retries!=set(old.FAILED) or total!=98832:raise Error('p0 reconciliation mismatch')
  ev=db.execute('select event,reason from run_events order by seq').fetchall()
  if len(ev)!=2 or [x[0] for x in ev]!=['forecast_started','model_started'] or ev[1][1]!=MODEL_SHA:raise Error('p0 stage events mismatch')
 finally:db.close()
 read('forecast-p0-429-resume-model-contract-20261029-v1.json',MODEL_SHA)
 summary=json.loads(read(SUMMARY,SUMMARY_SHA));receipt=json.loads(read(CPI_RECEIPT,CPI_RECEIPT_SHA))
 frozen=json.loads(read('forecast-p0-429-resume-results-20261029-01/case-02-p0-frozen.json',CPI_FROZEN_SHA));read('forecast-p0-429-resume-results-20261029-01/case-02-input.json',CPI_INPUT_SHA)
 if summary.get('status')!='completed_p0_only' or summary.get('contract_sha256')!=MODEL_SHA or len(summary.get('outcomes',[]))!=3 or receipt.get('case_id')!='case-02' or receipt.get('frozen_sha256')!=CPI_FROZEN_SHA or receipt.get('comparison_eligible') is not True or receipt.get('durable_before_utc')!='2026-10-29T11:51:50.322164+00:00':raise Error('p0 receipt mismatch')
 if frozen.get('case_id')!='case-02' or frozen.get('comparison_eligible') is not True or any(frozen.get(x,{}).get('status')!='proposal' or frozen[x].get('calls')!=8 for x in ('c','b')):raise Error('p0 branch mismatch')
 if not any(x==receipt for x in summary['outcomes']):raise Error('CPI receipt not in p0 summary')
 return {'schema':'p1-cpi-completed-p0-parent-v1','p0_db_sha256':PARENT_SHA,'source_lineage':prior,'p0_usage_micro':98832,'prior_micro':1988563,'prior_generations':299,'prior_counts':228,'prior_sources':16,'cpi_receipt_sha256':digest(read(CPI_RECEIPT)),'cpi_durable_utc':receipt['durable_before_utc'],'historical_reserve_micro':{'http400':150000,'http429_each':[86016,86016,86016]}}

def config():
 c=old.config();c.update(run_id='faithful-cpi-p1-budget-20261029-01',prior_micro=1988563,prior_generations=299,prior_counts=228,max_generations=391,max_counts=320,max_sources=12,source_cap_micro=2814000)
 return c
class Base(Ledger):
 @staticmethod
 def _validate_contract(c):
  if c!=config():raise Error('p1 ledger configuration drift')
class Accounting:
 def __init__(self,base,parent,account_path,account_sha):self.base=base;self.parent=parent;self.account_path=Path(account_path);self.account_sha=account_sha
 @property
 def db(self):return self.base.db
 @property
 def poisoned(self):return self.base.poisoned
 @poisoned.setter
 def poisoned(self,x):self.base.poisoned=x
 def summary(self):
  s=self.base.summary();s.update(source_attempts=s['source_attempts']+16,previous_source_attempts=16);return s
 def close(self):self.base.close()
 def stop(self,reason):self.base.stop(reason)
 def count(self,*a,**k):raise Error('accounting-only; no model')
 def generate(self,*a,**k):raise Error('accounting-only; no model')
 def source(self,*a,**k):raise Error('accounting-only; no source')
 def verify(self):
  if inspect_parent()!=self.parent or digest(read(self.account_path))!=self.account_sha:raise Error('parent or account contract changed')
  if read(CLAIM)!=canonical({'parent_sha256':PARENT_SHA,'contract_sha256':self.account_sha,'ledger_root':str(self.base.root)}):raise Error('account claim changed')
  if self.db.execute("select reason from run_events where event='forecast_started'").fetchall()!=[(self.account_sha,)]:raise Error('account stage marker drift')

def _contract(path,expected,verify,root):
 raw=read(path,expected);c=json.loads(raw);parent=inspect_parent()
 if c.get('schema')!='cpi-p1-accounting-contract-v1' or c.get('status')!='frozen' or c.get('parent')!=parent or c.get('config')!=config() or c.get('ledger_root')!=str(root) or c.get('caps')!=CAPS or c.get('scope')!={'mode':'accounting_only','provider_effects':'forbidden'} or c.get('bridge_sha256')!=digest(Path(__file__).read_bytes()):raise Error('accounting contract mismatch')
 if not callable(verify) or verify(raw) is not True:raise Error('independent accounting review required')
 return raw,parent

def create(root,*,contract_path,contract_sha,verify_challenge):
 root=Path(root)
 if not root.is_absolute() or root.exists() or root.parent.resolve()!=root.parent.absolute() or CLAIM.exists():raise Error('unsafe new destination')
 raw,parent=_contract(contract_path,contract_sha,verify_challenge,root);claim=canonical({'parent_sha256':PARENT_SHA,'contract_sha256':contract_sha,'ledger_root':str(root)})
 fd=os.open(CLAIM,os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,'O_NOFOLLOW',0),0o600)
 with os.fdopen(fd,'wb') as f0:f0.write(claim);f0.flush();os.fsync(f0.fileno())
 fd=os.open(CLAIM.parent,os.O_RDONLY)
 try:os.fsync(fd)
 finally:os.close(fd)
 base=Base(str(root),config(),create=True)
 try:
  base.db.execute("insert into run_events(event,reason,at_utc) values ('forecast_started',?,?)",(contract_sha,now_utc()))
  return Accounting(base,parent,contract_path,contract_sha)
 except BaseException:base.close();raise

def reopen(root,*,contract_path,contract_sha,verify_challenge):
 """Only untouched accounting is reopenable. No implicit interrupted-stage resume."""
 root=Path(root)
 if not root.is_absolute() or root.is_symlink() or root.resolve()!=root.absolute() or not root.is_dir():raise Error('unsafe existing ledger')
 _,parent=_contract(contract_path,contract_sha,verify_challenge,root)
 claim=canonical({'parent_sha256':PARENT_SHA,'contract_sha256':contract_sha,'ledger_root':str(root)})
 if read(CLAIM)!=claim:raise Error('claim mismatch')
 base=Base(str(root),config(),create=False)
 try:
  if base.summary()!={'stopped':0,'exposure_micro':1988563,'generation_attempts':299,'count_attempts':228,'source_attempts':0,'metadata_attempts':0,'metadata_retained_micro':0} or base.db.execute('select 1 from effects limit 1').fetchone() or base.db.execute('select event,reason from run_events').fetchall()!=[('forecast_started',contract_sha)]:raise Error('account stage already used')
  return Accounting(base,parent,contract_path,contract_sha)
 except BaseException:base.close();raise

def reopen_after_source(root,*,contract_path,contract_sha,verify_challenge,source_path,source_sha,verify_source_challenge,verify_historical_ticket,verify_ticket):
 """Reopen after fully settled source-only effects; never reopen after model start.

 Existing source IDs remain consumed; only unused exact status operations from
 the same reviewed stage may be executed. Any 429, 400, unknown bill, pending
 effect, or unrecorded effect forbids reopening.
 """
 root=Path(root)
 if not root.is_absolute() or root.is_symlink() or root.resolve()!=root.absolute() or not root.is_dir():raise Error('unsafe existing ledger')
 _,parent=_contract(contract_path,contract_sha,verify_challenge,root)
 if read(CLAIM)!=canonical({'parent_sha256':PARENT_SHA,'contract_sha256':contract_sha,'ledger_root':str(root)}):raise Error('claim mismatch')
 raw=read(source_path,source_sha);c=json.loads(raw)
 if c.get('schema')!='cpi-p1-source-contract-v1' or c.get('status')!='frozen' or c.get('account_contract_sha256')!=contract_sha or c.get('caps')!=CAPS or c.get('case_id')!='case-02' or c.get('cpi_receipt_sha256')!=parent['cpi_receipt_sha256'] or c.get('no_retry') is not True or c.get('no_canary') is not True or c.get('bridge_sha256')!=digest(Path(__file__).read_bytes()) or not callable(verify_source_challenge) or verify_source_challenge(raw) is not True or not callable(verify_historical_ticket) or not callable(verify_ticket):raise Error('source stage review mismatch')
 base=Base(str(root),config(),create=False)
 try:
  db=base.db;ev=db.execute('select event,reason from run_events order by seq').fetchall()
  if ev!=[('forecast_started',contract_sha),('source_started',source_sha)]:raise Error('unexpected or already-started model stage')
  rows=db.execute('select id,kind,state,http_status,request,request_hash,response,response_hash,actual_micro,quote_micro,quote_metadata,started_at_utc from effects order by rowid').fetchall();total=0;seen=set()
  if not 1<=len(rows)<=12:raise Error('source observations absent or above cap')
  for ident,kind,state,status,req,rh,response,sh,amount,quote,meta,started in rows:
   matches=[x for x in c['operations'] if x.get('ticket',{}).get('id')==ident and canonical(x.get('payload'))==req and canonical(x.get('ticket'))==meta]
   if len(matches)!=1 or ident in seen or kind!='source' or state!='succeeded' or status!=200 or digest(req)!=rh or digest(response)!=sh or quote!=150000 or type(amount) is not int or amount<0:raise Error('source effect or contract mismatch')
   ticket=matches[0]['ticket']
   started_at=dt.datetime.fromisoformat(started.replace('Z','+00:00'));expires=dt.datetime.fromisoformat(ticket['expires_utc'].replace('Z','+00:00'))
   if started_at.utcoffset()!=dt.timedelta(0) or expires.utcoffset()!=dt.timedelta(0) or started_at>=expires or verify_historical_ticket(ticket,req,started) is not True:raise Error('historical source ticket invalid')
   data=json.loads(response);d=Decimal(str(data['priceCents']))*10000
   if data.get('success') is not True or not d.is_finite() or d!=d.to_integral_value() or int(d)!=amount:raise Error('source receipt cost mismatch')
   events=db.execute('select state,detail from events where effect_id=? order by seq',(ident,)).fetchall()
   if events!=[('prepared',None),('started',None),('succeeded',None),('accounted',str(amount))]:raise Error('source effect transition mismatch')
   seen.add(ident);total+=amount
  s=base.summary()
  if (s['stopped'],s['exposure_micro'],s['generation_attempts'],s['count_attempts'],s['source_attempts'])!=(0,1988563+total,299,228,len(rows)) or total>2814000:raise Error('source successor accounting mismatch')
  account=Accounting(base,parent,contract_path,contract_sha)
  return account,Stage(account,source_path,source_sha,'source',verify_source_challenge,verify_ticket)
 except BaseException:base.close();raise

class Stage(f.ForecastLedger):
 def __init__(self,account,stage_path,stage_sha,kind,verify_stage,verify_ticket=None):
  self.account=account;self.path=Path(stage_path);self.sha=stage_sha;self.kind=kind;self.verify_stage=verify_stage
  super().__init__(account.base,read(CLAIM),account.parent,account.account_path,account.account_sha,verify_ticket)
 def summary(self):return self.account.summary()
 def verify_parent(self):return self.account.verify()
 def _guard(self):
  try:
   self.account.verify();raw=read(self.path,self.sha)
   if self.verify_stage(raw) is not True or self.db.execute('select reason from run_events where event=?',(self.kind+'_started',)).fetchall()!=[(self.sha,)]:raise Error('stage authority drift')
  except BaseException:
   try:self.stop('p1 stage lineage or contract changed')
   finally:self.poisoned=True
   raise
 def source(self,op,provider,endpoint,request,ticket,transport):
  if self.kind!='source':raise Error('source-only stage required')
  c=json.loads(read(self.path,self.sha));matches=[x for x in c['operations'] if x.get('ticket')==ticket and canonical(x.get('payload'))==request]
  if len(matches)!=1:raise Error('source operation not frozen')
  # Explicit repeated status reads are separate time-scoped operations, never a
  # repeat of an uncertain/failed effect. Base enforces unique op IDs.
  old_ids={x['id'] for x in self._parent['source_lineage']['prior_lineage']['source_history']}
  old_ids.update(('p1-openai-official-you','p1-openai-related-serper-news','post-seed-kalshi-market-lookup'))
  if op in old_ids:raise Error('old source identity prohibited')
  if digest(request)==old.source_only.r.FAILED_REQUEST_SHA:raise Error('failed source request prohibited')
  raw=super().source(op,provider,endpoint,request,ticket,transport)
  if provider=='orthogonal' and json.loads(raw).get('success') is not True:self.stop('source semantic failure');raise Error('source envelope failure')
  return raw
 def count(self,op,request,transport):
  if self.kind!='model' or not re.fullmatch(r'count:p1:case-02:(?:news|no_news):(?:b|c):(?:0[1-9]|1[0-9]|2[0-3])',op):raise Error('model count scope invalid')
  if digest(canonical(request)) in {x[2] for x in old.FAILED.values()}:raise Error('old failed request prohibited')
  return super().count(op,request,transport)
 def generate(self,op,request,count_id,transport):
  if self.kind!='model' or not re.fullmatch(r'generation:p1:case-02:(?:news|no_news):(?:b|c):(?:0[1-9]|1[0-9]|2[0-3])',op) or count_id!='count:'+op.removeprefix('generation:'):raise Error('model generation scope invalid')
  if digest(canonical(request)) in {x[2] for x in old.FAILED.values()}:raise Error('old failed request prohibited')
  return super().generate(op,request,count_id,transport)

def activate(account,*,stage_path,stage_sha,kind,verify_challenge,verify_ticket=None):
 if not isinstance(account,Accounting) or kind not in ('source','model'):raise Error('account or stage kind invalid')
 account.verify();raw=read(stage_path,stage_sha);c=json.loads(raw)
 if c.get('schema')!='cpi-p1-'+kind+'-contract-v1' or c.get('status')!='frozen' or c.get('account_contract_sha256')!=account.account_sha or c.get('caps')!=CAPS or c.get('case_id')!='case-02' or c.get('cpi_receipt_sha256')!=account.parent['cpi_receipt_sha256'] or c.get('no_retry') is not True or c.get('no_canary') is not True or c.get('bridge_sha256')!=digest(Path(__file__).read_bytes()):raise Error('p1 stage contract mismatch')
 if kind=='source' and (not isinstance(c.get('operations'),list) or not 1<=len(c['operations'])<=12 or not callable(verify_ticket)):raise Error('source operation or ticket missing')
 if kind=='source':
  ids=set();hash_kinds={}
  for op in c['operations']:
   if not isinstance(op,dict) or set(op)!={'ticket','payload','kind'} or op['kind'] not in ('event','status_refresh') or not isinstance(op['ticket'],dict):raise Error('source operation shape')
   ticket=op['ticket'];ident=ticket.get('id');h=digest(canonical(op['payload']))
   if not isinstance(ident,str) or not ident or ident in ids or ticket.get('request_sha256')!=h:raise Error('source operation identity invalid')
   if (ticket.get('provider'),ticket.get('endpoint'),ticket.get('settlement'))!=('orthogonal','/v1/run','orthogonal_price_cents'):raise Error('only priced Orthogonal source route supported')
   if op['kind']=='status_refresh' and ticket.get('category')!='market':raise Error('refresh must be market status')
   if h in hash_kinds and (op['kind']!='status_refresh' or hash_kinds[h]!='status_refresh'):raise Error('only distinct status observations may share request bytes')
   ids.add(ident);hash_kinds[h]=op['kind']
 if kind=='model' and (c.get('max_generations')!=92 or c.get('max_counts')!=92 or c.get('arms')!=['c_no_news','b_no_news','c_news','b_news']):raise Error('p1 model scope mismatch')
 if not callable(verify_challenge) or verify_challenge(raw) is not True:raise Error('independent stage review required')
 db=account.db;db.execute('begin immediate')
 try:
  if account.base.summary()['stopped'] or db.execute('select 1 from run_events where event=?',(kind+'_started',)).fetchone():raise Error('stage stopped or already claimed')
  db.execute('insert into run_events(event,reason,at_utc) values (?,?,?)',(kind+'_started',stage_sha,now_utc()));db.execute('commit')
 except BaseException:
  if db.in_transaction:db.execute('rollback')
  raise
 return Stage(account,stage_path,stage_sha,kind,verify_challenge,verify_ticket)
