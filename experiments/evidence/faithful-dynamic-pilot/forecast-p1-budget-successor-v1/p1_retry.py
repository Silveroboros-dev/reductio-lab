"""Offline-only bounded confirmed-429 attempt accounting for CPI P1.

One method = one HTTP attempt; delays and refreshed status checks belong to the
reviewed caller. No source retry, no timeout retry, no semantic resampling.
This is a candidate, not a live executor or authority.
"""
import datetime as dt
import json,re,sqlite3,sys
from decimal import Decimal,InvalidOperation
from pathlib import Path
import p1_budget as p
from ledger import Ledger, Stop, canonical, digest, now_utc,positive_int,valid_hash
MAX_EXTRA=20
MAX_RETRY=3
NEWS_DB='forecast-three-case-news-ledger-20261029-02/ledger.sqlite3'
NEWS_DB_SHA='e1b8de7cc026da632ceb01020fa71afd8b33bff0a0acb383a3bad25e1ec0ae8f'
NEWS_SUMMARY='forecast-three-case-news-results-20261029-02/summary.json'
NEWS_SUMMARY_SHA='c66fee9ee7c762ee7a53516fdb2a19323ebe4b2a3d80241c6d83f627b0b416d2'
NEWS_CONTRACT_SHA='7a993fa929f9fb39bb7c6736d683020b354ffc25fabaa846f1b0093f7db2fd52'
CLAIM=p.ROOT/'forecast-cpi-p1-retry.claim.json'
class Confirmed429(Exception):pass
class RateLimitExhausted(Exception):pass

class RetryModelStage:
 """Attempt-level model facade on an already-reviewed shared RetryBase.

 `guard()` binds stage bytes, case, market freshness, budget and lineage;
 the injected transport must be one-shot with no implicit SDK retries.
 The owner closes the shared base after both model and source stages finish.
 """
 def __init__(self,base,guard,previous_sources,account=None):
  if not isinstance(base,RetryBase) or not callable(guard) or type(previous_sources) is not int or not 0<=previous_sources<=28:raise p.Error('invalid stage setup')
  self.base=base;self.guard=guard;self.previous_sources=previous_sources;self.account=account;self.kind='model'
 def _guard(self):
  try:
   if self.guard() is not True:raise p.Error('model scope or freshness invalid')
  except BaseException:
   if not self.base.summary()['stopped']:self.base.stop('p1 model scope or freshness drift')
   raise
 def summary(self):
  s=self.base.summary();s['source_attempts']+=self.previous_sources;s['previous_source_attempts']=self.previous_sources;return s
 def stop(self,reason):self.base.stop(reason)
 def count_attempt(self,logical,request,attempt,transport):
  self._guard();return self.base.count_attempt(logical,request,attempt,transport)
 def generate_attempt(self,logical,request,count_logical,attempt,transport):
  self._guard();return self.base.generate_attempt(logical,request,count_logical,attempt,transport)

def config():
 c=p.config();c.update(run_id='faithful-cpi-p1-budget-retry-20261029-02',prior_micro=2005563,max_generations=411,max_counts=340,max_sources=9,source_cap_micro=2797000)
 return c

def inspect_parent():
 # Reuse the source-stage verifier; it compares historic quote to its evidence,
 # but does not require that old source ticket still be unexpired now.
 sys.path.insert(0,str(p.ROOT/'forecast-three-case-news-v1'))
 import news_v2
 c,_,_,_=news_v2.verify(NEWS_CONTRACT_SHA)
 summary=json.loads(p.read(NEWS_SUMMARY,NEWS_SUMMARY_SHA))
 p.read(NEWS_DB,NEWS_DB_SHA);db=sqlite3.connect('file:'+str(p.ROOT/NEWS_DB)+'?mode=ro&immutable=1',uri=True)
 try:
  if db.execute('select stopped,exposure_micro,generation_attempts,count_attempts,source_attempts from run').fetchone()!=(0,2005563,299,228,3):raise p.Error('news ledger counters mismatch')
  rows=db.execute('select id,kind,state,http_status,request,request_hash,response,response_hash,actual_micro,quote_micro,quote_metadata,started_at_utc from effects order by rowid').fetchall()
  if len(rows)!=3:raise p.Error('news source effects mismatch')
  total=0;out=[]
  for row,op in zip(rows,c['operations']):
   ident,kind,state,status,req,rh,resp,sh,amount,quote,meta,started=row;ticket=op['ticket'];data=json.loads(resp)
   if (ident,kind,state,status,quote)!=(ticket['id'],'source','succeeded',200,150000) or digest(req)!=rh or digest(resp)!=sh or canonical(op['payload'])!=req or canonical(ticket)!=meta or ticket['request_sha256']!=rh or data.get('success') is not True:raise p.Error('news receipt mismatch')
   if dt.datetime.fromisoformat(started.replace('Z','+00:00'))>=dt.datetime.fromisoformat(ticket['expires_utc'].replace('Z','+00:00')):raise p.Error('historical news ticket expired at start')
   price=Decimal(str(data['priceCents']))*10000;charged=Decimal(str(data['billing']['chargedPriceCents']))*10000
   if not price.is_finite() or price!=price.to_integral_value() or charged!=price or int(charged)!=amount:raise p.Error('news charge mismatch')
   events=db.execute('select state,detail from events where effect_id=? order by seq',(ident,)).fetchall()
   if events!=[('prepared',None),('started',None),('succeeded',None),('accounted',str(amount))]:raise p.Error('news transition mismatch')
   out.append({'id':ident,'request_sha256':rh,'response_sha256':sh,'amount_micro':amount,'started_at_utc':started});total+=amount
  if total!=17000:raise p.Error('news totals mismatch')
  if db.execute('select event,reason from run_events order by seq').fetchall()!=[('forecast_started',NEWS_CONTRACT_SHA)]:raise p.Error('news stage marker mismatch')
 finally:db.close()
 if summary.get('status')!='completed' or summary.get('ledger',{}).get('exposure_micro')!=2005563 or len(summary.get('records',[]))!=3:raise p.Error('news summary mismatch')
 old=p.inspect_parent()
 return {**old,'schema':'cpi-p1-post-news-parent-v1','prior_micro':2005563,'prior_sources':19,'news_db_sha256':NEWS_DB_SHA,'news_summary_sha256':NEWS_SUMMARY_SHA,'news_contract_sha256':NEWS_CONTRACT_SHA,'news_effects':out}

class RetryBase(Ledger):
 @staticmethod
 def _validate_contract(c):
  if c!=config():raise ValueError('p1 retry config mismatch')
 def _start(self,op_id,kind,provider,endpoint,request,quote,proof,related_id=None,quote_metadata=None):
  if self.poisoned:raise Stop('journal failure')
  if self.db.execute('select contract_hash from run where id=1').fetchone()!=(digest(canonical(self._contract)),):self.poisoned=True;raise Stop('contract changed')
  if not isinstance(op_id,str) or not op_id or not isinstance(request,bytes) or not positive_int(quote) or not valid_hash(proof):raise ValueError('start metadata invalid')
  c=self._contract;db=self.db;db.execute('begin immediate')
  try:
   stopped,exposure,gens,counts,sources=db.execute('select stopped,exposure_micro,generation_attempts,count_attempts,source_attempts from run').fetchone()
   if stopped:raise Stop('journal stopped')
   unsettled=db.execute("select id,kind,state,http_status,actual_micro from effects where state in ('prepared','started','uncertain') or (state='succeeded' and actual_micro is null)").fetchall()
   for ident,k,state,status,amount in unsettled:
    if not(state=='succeeded' and status==429 and k in ('count','generation') and db.execute("select 1 from run_events where event='confirmed_model_429' and reason=?",(ident,)).fetchone()):raise Stop('unreconciled effect blocks dispatch')
   if db.execute('select 1 from effects where id=?',(op_id,)).fetchone():raise Stop('attempt already used')
   if exposure+quote>c['cap_micro']:raise Stop('total budget exceeded')
   if kind in ('source','metadata'):
    used=db.execute("select coalesce(sum(coalesce(actual_micro,quote_micro)),0) from effects where kind in ('source','metadata')").fetchone()[0]
    if used+quote>c['source_cap_micro'] or kind!='source' or sources>=c['max_sources']:raise Stop('source budget exceeded')
    sources+=1
   elif kind=='count':
    if counts>=c['max_counts']:raise Stop('count budget exceeded')
    counts+=1
   elif kind=='generation':
    if gens>=c['max_generations']:raise Stop('generation budget exceeded')
    previous=db.execute("select id,http_status,request_hash from effects where kind='generation' and related_id=?",(related_id,)).fetchall()
    if any(status!=429 or oldhash!=digest(request) or not db.execute("select 1 from run_events where event='confirmed_model_429' and reason=?",(ident,)).fetchone() for ident,status,oldhash in previous):raise Stop('count already used by non-429 generation')
    gens+=1
   else:raise ValueError('invalid effect kind')
   # A suffix is an actual extra physical attempt; cap globally for model calls.
   if kind in ('count','generation') and '~retry' in op_id:
    extra=db.execute("select count(*) from effects where kind in ('count','generation') and instr(id,'~retry')>0").fetchone()[0]
    if extra>=MAX_EXTRA:raise RateLimitExhausted('shared extra-attempt budget exhausted')
   db.execute('insert into effects (id,kind,provider,endpoint,request,request_hash,quote_micro,quote_evidence_sha,state,related_id,quote_metadata,started_at_utc) values (?,?,?,?,?,?,?,?,?,?,?,?)',(op_id,kind,provider,endpoint,request,digest(request),quote,proof,'started',related_id,quote_metadata,now_utc()))
   db.execute("insert into events(effect_id,state) values (?, 'prepared')",(op_id,));db.execute("insert into events(effect_id,state) values (?, 'started')",(op_id,))
   db.execute('update run set exposure_micro=?,generation_attempts=?,count_attempts=?,source_attempts=? where id=1',(exposure+quote,gens,counts,sources));db.execute('commit')
  except BaseException:
   if db.in_transaction:db.execute('rollback')
   raise
 def _id(self,logical,n):return logical if n==0 else logical+'~retry'+str(n)
 def _validate_attempt(self,logical,request,n,kind):
  if type(n) is not int or not 0<=n<=MAX_RETRY:raise RateLimitExhausted('per-operation retries exhausted')
  prefix='count:' if kind=='count' else 'generation:'
  if not re.fullmatch(prefix+r'p1:case-02:(?:news|no_news):(?:b|c):(?:0[1-9]|1[0-9]|2[0-3])',logical):raise p.Error('invalid logical id')
  raw=canonical(request)
  if digest(raw) in {x[2] for x in p.old.FAILED.values()}:raise p.Error('old failed request prohibited')
  existing=self.db.execute('select id,http_status,request_hash,request,state from effects where id=? or id glob ? order by id',(logical,logical+'~retry[1-3]')).fetchall()
  if n==0:
   if existing:raise p.Error('logical operation already started')
  else:
   if len(existing)!=n:raise p.Error('retry sequence incomplete or already started')
   for idx in range(n):
    ident=self._id(logical,idx);row=next((x for x in existing if x[0]==ident),None)
    if row is None or row[1]!=429 or row[2]!=digest(raw) or row[3]!=raw or row[4]!='succeeded' or not self.db.execute("select 1 from run_events where event='confirmed_model_429' and reason=?",(ident,)).fetchone():raise p.Error('predecessor is not exact captured 429')
  return raw,self._id(logical,n)
 def _one(self,ident,kind,endpoint,raw,quote,proof,transport,related=None,attempt=0):
  try:return self._execute(ident,kind,'vertex',endpoint,raw,quote,proof,transport,related)
  except Stop:
   row=self.db.execute('select state,http_status,response,response_hash,actual_micro from effects where id=?',(ident,)).fetchone()
   if row is None or row[0]!='succeeded' or row[1]!=429 or row[4] is not None or digest(row[2])!=row[3]:raise
   try:e=json.loads(row[2])['error']
   except (ValueError,KeyError,TypeError):raise
   if e.get('code')!=429 or e.get('status')!='RESOURCE_EXHAUSTED':raise
   self.db.execute('begin immediate')
   try:
    if self.db.execute('select stopped from run').fetchone()!=(1,):raise Stop('unexpected 429 stopped state')
    self.db.execute("insert into run_events(event,reason,at_utc) values ('confirmed_model_429',?,?)",(ident,now_utc()))
    self.db.execute('update run set stopped=0');self.db.execute('commit')
   except BaseException:
    if self.db.in_transaction:self.db.execute('rollback')
    raise
   extra=self.db.execute("select count(*) from effects where kind in ('count','generation') and instr(id,'~retry')>0").fetchone()[0]
   if attempt>=MAX_RETRY or extra>=MAX_EXTRA:raise RateLimitExhausted('confirmed 429 retries exhausted')
   raise Confirmed429('confirmed 429; exact retry possible')
 def count_attempt(self,logical,request,attempt,transport):
  raw,ident=self._validate_attempt(logical,request,attempt,'count');answer=self._one(ident,'count','countTokens',raw,0,self._contract['count_price_evidence_sha256'],transport,attempt=attempt)
  try:
   n=json.loads(answer)['totalTokens']
   if type(n) is not int or not 0<n<=16384:raise ValueError('count invalid')
  except (KeyError,TypeError,ValueError):self._stop(ident,'invalid count');raise Stop('count invalid')
  self._settle(ident,0);return n
 def generate_attempt(self,logical,request,count_logical,attempt,transport):
  raw,ident=self._validate_attempt(logical,request,attempt,'generation')
  if request.get('generationConfig',{}).get('maxOutputTokens')!=4096 or any(k in request for k in ('model','tools','toolConfig','cachedContent')):raise p.Error('model config mismatch')
  if count_logical!='count:'+logical.removeprefix('generation:'):raise p.Error('count logical identity mismatch')
  rows=self.db.execute("select id,request_hash,response from effects where (id=? or id glob ?) and kind='count' and state='succeeded' and http_status=200 and actual_micro=0",(count_logical,count_logical+'~retry[1-3]')).fetchall()
  if len(rows)!=1 or rows[0][1]!=digest(raw):raise p.Error('missing unique matching successful count')
  cid=rows[0][0];c=self._contract;answer=self._one(ident,'generation',c['model']+'@'+c['location'],raw,self._model_bound(),c['model_price_evidence_sha256'],transport,cid,attempt)
  try:
   data=json.loads(answer);u=data['usageMetadata'];n=u['promptTokenCount'];total=u['totalTokenCount'];out=total-n;thought=u.get('thoughtsTokenCount');version=data.get('modelVersion')
   if type(n) is not int or type(total) is not int or n<=0 or out<=0 or (thought is not None and (type(thought) is not int or thought<0 or thought>out)):raise ValueError('bad usage')
   self._settle(ident,(3*n+15*out+1)//2)
   if n>16384 or out>8192 or not isinstance(version,str) or not(version==c['model'] or version.startswith(c['model']+'-')):raise ValueError('model or token limit invalid')
  except BaseException:
   if not self.summary()['stopped']:self.stop('model usage/identity failure')
   raise
  return answer

class RetryAccounting(p.Accounting):
 def summary(self):
  s=self.base.summary();s.update(source_attempts=s['source_attempts']+19,previous_source_attempts=19);return s
 def verify(self):
  if inspect_parent()!=self.parent or digest(p.read(self.account_path))!=self.account_sha:raise p.Error('post-news parent or account changed')
  if p.read(CLAIM)!=canonical({'parent_sha256':NEWS_DB_SHA,'contract_sha256':self.account_sha,'ledger_root':str(self.base.root)}):raise p.Error('retry account claim changed')
  if self.db.execute("select reason from run_events where event='forecast_started'").fetchall()!=[(self.account_sha,)]:raise p.Error('account marker drift')

class RetrySourceStage(p.Stage):
 def __init__(self,account,stage_path,stage_sha,verify_stage,verify_ticket):
  self.account=account;self.path=Path(stage_path);self.sha=stage_sha;self.kind='source';self.verify_stage=verify_stage
  p.f.ForecastLedger.__init__(self,account.base,p.read(CLAIM),account.parent,account.account_path,account.account_sha,verify_ticket)
 def source(self,op,provider,endpoint,request,ticket,transport):
  if op in {x['id'] for x in self.account.parent['news_effects']}:raise p.Error('completed news source identity prohibited')
  self._guard();c=json.loads(p.read(self.path,self.sha));matches=[x for x in c['operations'] if x.get('ticket')==ticket and canonical(x.get('payload'))==request]
  if len(matches)!=1 or (provider,endpoint)!=('orthogonal','/v1/run'):raise p.Error('source operation not frozen')
  old_ids={x['id'] for x in self._parent['source_lineage']['prior_lineage']['source_history']};old_ids.update(('p1-openai-official-you','p1-openai-related-serper-news','post-seed-kalshi-market-lookup'))
  if op in old_ids or digest(request)==p.old.source_only.r.FAILED_REQUEST_SHA:raise p.Error('old source operation prohibited')
  required={'id','provider','endpoint','request_sha256','max_micro','evidence_sha256','expires_utc','category','settlement'}
  if not isinstance(ticket,dict) or set(ticket)!=required or not isinstance(request,bytes) or not request or len(request)>32768 or (ticket['id'],ticket['provider'],ticket['endpoint'],ticket['request_sha256'],ticket['settlement'])!=(op,provider,endpoint,digest(request),'orthogonal_price_cents') or ticket['category'] not in ('market','fetch','search','news') or ticket['max_micro']!=150000 or not valid_hash(ticket['evidence_sha256']):raise p.Error('source ticket invalid')
  expiry=dt.datetime.fromisoformat(ticket['expires_utc'].replace('Z','+00:00'))
  if expiry.utcoffset()!=dt.timedelta(0) or expiry<=dt.datetime.now(dt.timezone.utc) or self._verify_ticket(ticket,request) is not True:raise p.Error('source ticket expired or unverified')
  raw=self._base._execute(op,'source',provider,endpoint,request,ticket['max_micro'],ticket['evidence_sha256'],transport,quote_metadata=canonical(ticket))
  try:
   data=json.loads(raw);price=Decimal(str(data['priceCents']))*10000;charged=Decimal(str(data['billing']['chargedPriceCents']))*10000
   if not price.is_finite() or not charged.is_finite() or price<0 or charged<0 or price!=price.to_integral_value() or charged!=charged.to_integral_value():raise ValueError('source billing invalid')
   amount=int(charged)
  except (KeyError,ValueError,TypeError,InvalidOperation):
   self._base._stop(op,'source billing invalid; reserve retained');raise p.Error('source billing invalid') from None
  self._base._settle(op,amount)
  if data.get('success') is not True or amount!=int(price):self.stop('source semantic or billing mismatch');raise p.Error('source semantic or billing mismatch')
  return raw

def check_account_contract(path,expected,verify,root):
 raw=p.read(path,expected);c=json.loads(raw);parent=inspect_parent()
 if c.get('schema')!='cpi-p1-retry-accounting-contract-v1' or c.get('status')!='frozen' or c.get('parent')!=parent or c.get('config')!=config() or c.get('ledger_root')!=str(root) or c.get('caps')!=p.CAPS or c.get('scope')!={'mode':'accounting_only','provider_effects':'forbidden'} or c.get('retry_bridge_sha256')!=digest(Path(__file__).read_bytes()) or c.get('budget_bridge_sha256')!=digest(Path(p.__file__).read_bytes()):raise p.Error('retry account contract mismatch')
 if not callable(verify) or verify(raw) is not True:raise p.Error('independent accounting review required')
 return raw,parent

def create(root,*,contract_path,contract_sha,verify_challenge):
 import os
 root=Path(root)
 if not root.is_absolute() or root.exists() or root.parent.resolve()!=root.parent.absolute() or CLAIM.exists():raise p.Error('unsafe new retry account destination')
 _,parent=check_account_contract(contract_path,contract_sha,verify_challenge,root);claim=canonical({'parent_sha256':NEWS_DB_SHA,'contract_sha256':contract_sha,'ledger_root':str(root)})
 fd=os.open(CLAIM,os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,'O_NOFOLLOW',0),0o600)
 with os.fdopen(fd,'wb') as f:f.write(claim);f.flush();os.fsync(f.fileno())
 fd=os.open(CLAIM.parent,os.O_RDONLY)
 try:os.fsync(fd)
 finally:os.close(fd)
 base=RetryBase(str(root),config(),create=True)
 try:
  base.db.execute("insert into run_events(event,reason,at_utc) values ('forecast_started',?,?)",(contract_sha,now_utc()))
  return RetryAccounting(base,parent,contract_path,contract_sha)
 except BaseException:base.close();raise

def reopen(root,*,contract_path,contract_sha,verify_challenge):
 root=Path(root)
 if not root.is_absolute() or root.is_symlink() or root.resolve()!=root.absolute() or not root.is_dir():raise p.Error('unsafe retry account')
 _,parent=check_account_contract(contract_path,contract_sha,verify_challenge,root)
 if p.read(CLAIM)!=canonical({'parent_sha256':NEWS_DB_SHA,'contract_sha256':contract_sha,'ledger_root':str(root)}):raise p.Error('retry account claim mismatch')
 base=RetryBase(str(root),config(),create=False)
 try:
  s=base.summary()
  if (s['stopped'],s['exposure_micro'],s['generation_attempts'],s['count_attempts'],s['source_attempts'])!=(0,2005563,299,228,0) or base.db.execute('select 1 from effects limit 1').fetchone() or base.db.execute('select event,reason from run_events').fetchall()!=[('forecast_started',contract_sha)]:raise p.Error('retry account already used')
  return RetryAccounting(base,parent,contract_path,contract_sha)
 except BaseException:base.close();raise

def reopen_after_source(root,*,contract_path,contract_sha,verify_challenge,source_path,source_sha,verify_source_challenge,verify_historical_ticket,verify_ticket):
 """Resume a fully settled source stage once, prior to any model stage.

 Later status operations remain the same independently frozen stage, with new
 unique operation IDs. Failed/ambiguous source effects prevent this reopen.
 """
 root=Path(root)
 if not root.is_absolute() or root.is_symlink() or root.resolve()!=root.absolute() or not root.is_dir():raise p.Error('unsafe retry account')
 _,parent=check_account_contract(contract_path,contract_sha,verify_challenge,root)
 if p.read(CLAIM)!=canonical({'parent_sha256':NEWS_DB_SHA,'contract_sha256':contract_sha,'ledger_root':str(root)}):raise p.Error('retry account claim mismatch')
 raw=p.read(source_path,source_sha);c=json.loads(raw)
 if c.get('schema')!='cpi-p1-source-contract-v1' or c.get('status')!='frozen' or c.get('account_contract_sha256')!=contract_sha or c.get('caps')!=p.CAPS or c.get('case_id')!='case-02' or c.get('cpi_receipt_sha256')!=parent['cpi_receipt_sha256'] or c.get('no_retry') is not True or c.get('no_canary') is not True or c.get('bridge_sha256')!=digest(Path(p.__file__).read_bytes()) or not callable(verify_source_challenge) or verify_source_challenge(raw) is not True or not callable(verify_historical_ticket) or not callable(verify_ticket):raise p.Error('source review mismatch')
 base=RetryBase(str(root),config(),create=False)
 try:
  db=base.db
  if db.execute('select event,reason from run_events order by seq').fetchall()!=[('forecast_started',contract_sha),('source_started',source_sha)]:raise p.Error('source stage or model state invalid')
  rows=db.execute('select id,kind,state,http_status,request,request_hash,response,response_hash,actual_micro,quote_micro,quote_metadata,started_at_utc from effects order by rowid').fetchall();seen=set();total=0
  if not 1<=len(rows)<=9:raise p.Error('source observations missing or over cap')
  for ident,kind,state,status,req,rh,resp,sh,amount,quote,meta,started in rows:
   matches=[x for x in c['operations'] if x.get('ticket',{}).get('id')==ident and canonical(x.get('payload'))==req and canonical(x.get('ticket'))==meta]
   if len(matches)!=1 or ident in seen or (kind,state,status,quote)!=('source','succeeded',200,150000) or digest(req)!=rh or digest(resp)!=sh or type(amount) is not int or amount<0:raise p.Error('source effect invalid')
   ticket=matches[0]['ticket'];start=dt.datetime.fromisoformat(started.replace('Z','+00:00'));expiry=dt.datetime.fromisoformat(ticket['expires_utc'].replace('Z','+00:00'))
   if start.utcoffset()!=dt.timedelta(0) or expiry.utcoffset()!=dt.timedelta(0) or start>=expiry or verify_historical_ticket(ticket,req,started) is not True:raise p.Error('historical source ticket invalid')
   data=json.loads(resp);price=Decimal(str(data['priceCents']))*10000;charged=Decimal(str(data['billing']['chargedPriceCents']))*10000
   if data.get('success') is not True or not price.is_finite() or not charged.is_finite() or price!=price.to_integral_value() or charged!=price or int(charged)!=amount:raise p.Error('source billing invalid')
   events=db.execute('select state,detail from events where effect_id=? order by seq',(ident,)).fetchall()
   if events!=[('prepared',None),('started',None),('succeeded',None),('accounted',str(amount))]:raise p.Error('source transition invalid')
   seen.add(ident);total+=amount
  s=base.summary()
  if (s['stopped'],s['exposure_micro'],s['generation_attempts'],s['count_attempts'],s['source_attempts'])!=(0,2005563+total,299,228,len(rows)) or total>2797000:raise p.Error('source carry invalid')
  account=RetryAccounting(base,parent,contract_path,contract_sha)
  return account,RetrySourceStage(account,source_path,source_sha,verify_source_challenge,verify_ticket)
 except BaseException:base.close();raise

def activate_source(account,*,stage_path,stage_sha,verify_challenge,verify_ticket):
 if not isinstance(account,RetryAccounting):raise p.Error('retry accounting required')
 account.verify();raw=p.read(stage_path,stage_sha);c=json.loads(raw);ops=c.get('operations')
 if c.get('schema')!='cpi-p1-source-contract-v1' or c.get('status')!='frozen' or c.get('account_contract_sha256')!=account.account_sha or c.get('caps')!=p.CAPS or c.get('case_id')!='case-02' or c.get('cpi_receipt_sha256')!=account.parent['cpi_receipt_sha256'] or c.get('no_retry') is not True or c.get('no_canary') is not True or c.get('bridge_sha256')!=digest(Path(p.__file__).read_bytes()) or not isinstance(ops,list) or not 1<=len(ops)<=9 or not callable(verify_ticket):raise p.Error('source contract scope mismatch')
 ids=set();hash_kinds={}
 for x in ops:
  if not isinstance(x,dict) or set(x)!={'ticket','payload','kind'} or x['kind'] not in ('event','status_refresh') or not isinstance(x['ticket'],dict):raise p.Error('source operation shape')
  t=x['ticket'];ident=t.get('id');h=digest(canonical(x['payload']))
  if not isinstance(ident,str) or not ident or ident in ids or t.get('request_sha256')!=h or (t.get('provider'),t.get('endpoint'),t.get('settlement'))!=('orthogonal','/v1/run','orthogonal_price_cents') or (x['kind']=='status_refresh' and t.get('category')!='market'):raise p.Error('source operation identity invalid')
  if h in hash_kinds and (x['kind']!='status_refresh' or hash_kinds[h]!='status_refresh'):raise p.Error('only status observations may share bytes')
  ids.add(ident);hash_kinds[h]=x['kind']
 if not callable(verify_challenge) or verify_challenge(raw) is not True:raise p.Error('independent source review required')
 db=account.db;db.execute('begin immediate')
 try:
  if account.base.summary()['stopped'] or db.execute("select 1 from run_events where event='source_started'").fetchone():raise p.Error('source stage already claimed or stopped')
  db.execute("insert into run_events(event,reason,at_utc) values ('source_started',?,?)",(stage_sha,now_utc()));db.execute('commit')
 except BaseException:
  if db.in_transaction:db.execute('rollback')
  raise
 return RetrySourceStage(account,stage_path,stage_sha,verify_challenge,verify_ticket)

def activate_model(account,*,stage_path,stage_sha,verify_challenge,verify_scope):
 if not isinstance(account,RetryAccounting) or not callable(verify_scope):raise p.Error('retry account or freshness guard absent')
 account.verify();raw=p.read(stage_path,stage_sha);c=json.loads(raw)
 if c.get('schema')!='cpi-p1-retry-model-contract-v1' or c.get('status')!='frozen' or c.get('account_contract_sha256')!=account.account_sha or c.get('caps')!=p.CAPS or c.get('case_id')!='case-02' or c.get('cpi_receipt_sha256')!=account.parent['cpi_receipt_sha256'] or c.get('no_canary') is not True or c.get('retry_bridge_sha256')!=digest(Path(__file__).read_bytes()) or c.get('max_generations')!=112 or c.get('max_counts')!=112 or c.get('max_additional_attempts')!=MAX_EXTRA or c.get('max_retry_per_operation')!=MAX_RETRY or c.get('arms')!=['c_no_news','b_no_news','c_news','b_news']:raise p.Error('retry model contract mismatch')
 if not callable(verify_challenge) or verify_challenge(raw) is not True:raise p.Error('independent model review required')
 db=account.db;db.execute('begin immediate')
 try:
  if account.base.summary()['stopped'] or db.execute("select 1 from run_events where event='model_started'").fetchone():raise p.Error('model stage already claimed or stopped')
  db.execute("insert into run_events(event,reason,at_utc) values ('model_started',?,?)",(stage_sha,now_utc()));db.execute('commit')
 except BaseException:
  if db.in_transaction:db.execute('rollback')
  raise
 def guard():
  account.verify()
  return digest(p.read(stage_path))==stage_sha and verify_challenge(raw) is True and db.execute("select reason from run_events where event='model_started'").fetchall()==[(stage_sha,)] and verify_scope() is True
 return RetryModelStage(account.base,guard,19,account)
