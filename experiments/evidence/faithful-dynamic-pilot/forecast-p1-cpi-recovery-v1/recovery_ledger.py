"""Offline candidate successor for P1 after a malformed HTTP-200 formatter.

No network effects occur by import or construction. Previous journal and raw
formatter remain immutable; only previously unstarted arms are admitted. Caller
must supply reviewed stage guards, one-shot transport, and creation authority.
"""
import datetime as dt,json,sqlite3,sys
from decimal import Decimal,InvalidOperation
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT/'forecast-p1-budget-successor-v1'))
import p1_retry as r
import p1_budget as p
from ledger import canonical,digest,valid_hash,Stop
PARENT=ROOT/'forecast-cpi-p1-retry-ledger-20261029-01/ledger.sqlite3'
PARENT_SHA='d185bdb6e46a35d6f1a0bdfc6a4a92bbb9b37da000f7eca5c62e1c2a187ffe9c'
INPUT=ROOT/'forecast-cpi-p1-results-20261029-01/p1-input.json'
INPUT_SHA='2aeb0312e915137f8aa70319e840ca45b86233cdb8ef63847797eaac2cbbeda5'
SOURCE=ROOT/'forecast-cpi-p1-source-contract-20261029-v2.json'
SOURCE_SHA='eea71b32f48b997cce6784b3563e02a336736b2b4a4fb10de2cae38d26cd628a'
FAILED='generation:p1:case-02:no_news:c:08'
FAILED_REQUEST_SHA='3cf24c524f4eae37a82fa4d5566cc494717f37d2f74eff20468e76b76b9337cc'
FAILED_RESPONSE_SHA='dd0fd4d1d601050ab8d991c26dc80d2794f0e19bb10e01e8d0650c5a87eb08ad'

def config():
 c=r.config();c.update(run_id='faithful-cpi-p1-format-recovery-20261029-01',prior_micro=2033331,prior_generations=307,prior_counts=236,max_sources=5,source_cap_micro=2787000)
 return c

def inspect_parent():
 p.read(PARENT,PARENT_SHA);p.read(INPUT,INPUT_SHA);source=json.loads(p.read(SOURCE,SOURCE_SHA));r.inspect_parent()
 d=sqlite3.connect('file:'+str(PARENT)+'?mode=ro&immutable=1',uri=True)
 try:
  if d.execute('select stopped,exposure_micro,generation_attempts,count_attempts,source_attempts from run').fetchone()!=(1,2033331,307,236,4):raise p.Error('recovery parent carry mismatch')
  events=d.execute('select event,reason from run_events order by seq').fetchall()
  if events!=[('forecast_started','9e461fe6df6cfd05aabab675d4f366b4bf9843bccd138ad005f60b7c313d4f89'),('source_started',SOURCE_SHA),('model_started','ed93e5c7501a25b25a89c4054058743ac247310afd2b81b9df1e549c011890e1'),('stopped','p1 interrupted or market state unverified; no automatic retry')]:raise p.Error('recovery parent stage mismatch')
  rows=d.execute('select id,kind,state,http_status,request,request_hash,response,response_hash,actual_micro,related_id from effects order by rowid').fetchall()
  if len(rows)!=20:raise p.Error('unexpected recovery effects')
  expected_models={f'{kind}:p1:case-02:no_news:c:{i:02d}' for i in range(1,9) for kind in ('count','generation')}
  seen=set();sources=[];total=0
  for ident,kind,state,status,req,rh,resp,sh,cost,related in rows:
   if state!='succeeded' or status!=200 or type(cost) is not int or cost<0 or digest(req)!=rh or digest(resp)!=sh:raise p.Error('uncertain, failed or damaged predecessor effect')
   if d.execute('select state,detail from events where effect_id=? order by seq',(ident,)).fetchall()!=[('prepared',None),('started',None),('succeeded',None),('accounted',str(cost))]:raise p.Error('predecessor event transitions invalid')
   obj=json.loads(resp)
   if kind in ('count','generation'):
    if ident not in expected_models or ident in seen:raise p.Error('unexpected prior model operation')
    if kind=='count':
     if cost!=0 or type(obj.get('totalTokens')) is not int or obj['totalTokens']<=0:raise p.Error('prior count invalid')
    else:
     u=obj.get('usageMetadata',{});n=u.get('promptTokenCount');all_tokens=u.get('totalTokenCount');model=obj.get('modelVersion')
     if type(n) is not int or type(all_tokens) is not int or n<=0 or all_tokens<=n or n>16384 or all_tokens-n>8192 or not isinstance(model,str) or not(model=='gemini-3.8-flash' or model.startswith('gemini-3.8-flash-')) or (3*n+15*(all_tokens-n)+1)//2!=cost:raise p.Error('prior generation usage invalid')
    seen.add(ident)
   elif kind=='source':
    price=Decimal(str(obj['priceCents']))*10000;charge=Decimal(str(obj['billing']['chargedPriceCents']))*10000
    if obj.get('success') is not True or not price.is_finite() or price!=charge or charge!=charge.to_integral_value() or int(charge)!=cost:raise p.Error('prior source billing invalid')
    sources.append(ident)
   else:raise p.Error('unexpected predecessor kind')
   total+=cost
  if total!=27768:raise p.Error('predecessor settlement total mismatch')
  if seen!=expected_models or sources!=['p1-cpi-bea-fetch','p1-cpi-status-01','p1-cpi-status-02','p1-cpi-status-03']:raise p.Error('source or model identities differ')
  by_id={x[0]:x for x in rows}
  for i in range(1,9):
   cid=f'count:p1:case-02:no_news:c:{i:02d}';gid=f'generation:p1:case-02:no_news:c:{i:02d}';ct=by_id[cid];g=by_id[gid]
   if ct[4]!=g[4] or ct[5]!=g[5] or ct[8]!=0 or g[9]!=cid:raise p.Error('count/generation pairing invalid')
  bad=by_id[FAILED]
  if (bad[5],bad[7],bad[8])!=(FAILED_REQUEST_SHA,FAILED_RESPONSE_SHA,3120):raise p.Error('formatter receipt changed')
  result=json.loads(bad[6]);text=result['candidates'][0]['content']['parts'][0]['text']
  try:json.loads(text)
  except json.JSONDecodeError:pass
  else:raise p.Error('formatter was not malformed')
 finally:d.close()
 return {'schema':'cpi-p1-format-recovery-parent-v1','parent_db_sha256':PARENT_SHA,'p1_input_sha256':INPUT_SHA,'source_contract_sha256':SOURCE_SHA,'failed_generation_id':FAILED,'failed_request_sha256':FAILED_REQUEST_SHA,'failed_response_sha256':FAILED_RESPONSE_SHA,'failed_actual_micro':3120,'prior_micro':2033331,'prior_generations':307,'prior_counts':236,'prior_sources':23,'remaining_source_ids':[f'p1-cpi-status-{n:02d}' for n in range(4,9)],'strict_result':'unparseable; corrected formatting only a separately audited post-hoc derivative'}

class RecoveryBase(r.RetryBase):
 @staticmethod
 def _validate_contract(c):
  if c!=config():raise ValueError('recovery contract mismatch')
 def _admit(self,logical,kind):
  prefix='count:' if kind=='count' else 'generation:'
  if not isinstance(logical,str) or not logical.startswith(prefix):raise p.Error('wrong model identity')
  parts=logical.split(':')
  if len(parts)!=6 or parts[1:3]!=['p1','case-02'] or (parts[3],parts[4]) not in (('no_news','b'),('news','c'),('news','b')) or not (parts[5].isdigit() and parts[5]==f'{int(parts[5]):02d}' and 1<=int(parts[5])<=23):raise p.Error('operation is old or outside recovery scope')
 def count_attempt(self,logical,request,attempt,transport):
  self._admit(logical,'count');return super().count_attempt(logical,request,attempt,transport)
 def generate_attempt(self,logical,request,count_logical,attempt,transport):
  self._admit(logical,'generation');return super().generate_attempt(logical,request,count_logical,attempt,transport)

class RecoveryStage:
 def __init__(self,base,guard,source_guard):
  if not isinstance(base,RecoveryBase) or not callable(guard) or not callable(source_guard):raise p.Error('recovery guards required')
  self.base=base;self.guard=guard;self.source_guard=source_guard;self.kind='model'
 def _guard(self):
  try:
   if self.guard() is not True:raise p.Error('unreviewed scope or stale status')
  except BaseException:
   if not self.base.summary()['stopped']:self.base.stop('recovery guard failure')
   raise
 def summary(self):
  s=self.base.summary();s['source_attempts']+=23;s['previous_source_attempts']=23;return s
 def stop(self,reason):self.base.stop(reason)
 def count_attempt(self,*args):self._guard();return self.base.count_attempt(*args)
 def generate_attempt(self,*args):self._guard();return self.base.generate_attempt(*args)
 def status_source(self,ident,transport,verify_ticket):
  try:
   if self.source_guard() is not True:raise p.Error('unreviewed source scope')
  except BaseException:
   if not self.base.summary()['stopped']:self.base.stop('recovery source guard failure')
   raise
  if ident not in [f'p1-cpi-status-{n:02d}' for n in range(4,9)] or not callable(verify_ticket):raise p.Error('status identity prohibited')
  c=json.loads(p.read(SOURCE,SOURCE_SHA));matches=[x for x in c['operations'] if x.get('ticket',{}).get('id')==ident and x.get('kind')=='status_refresh']
  if len(matches)!=1:raise p.Error('status not uniquely frozen')
  op=matches[0];ticket=op['ticket'];raw=canonical(op['payload'])
  if op['payload']!={'api':'kalshi','path':'/markets','body':{},'query':{'tickers':'KXCPI-26OCT-T0.2'}} or ticket['request_sha256']!=digest(raw) or ticket['max_micro']!=150000 or ticket['provider']!='orthogonal' or ticket['endpoint']!='/v1/run' or not valid_hash(ticket['evidence_sha256']) or dt.datetime.now(dt.timezone.utc)>=dt.datetime.fromisoformat(ticket['expires_utc']) or verify_ticket(ticket,raw) is not True:raise p.Error('status ticket invalid')
  answer=self.base._execute(ident,'source','orthogonal','/v1/run',raw,150000,ticket['evidence_sha256'],transport,quote_metadata=canonical(ticket))
  try:
   data=json.loads(answer);price=Decimal(str(data['priceCents']))*10000;charge=Decimal(str(data['billing']['chargedPriceCents']))*10000
   if not price.is_finite() or not charge.is_finite() or price<0 or charge<0 or price!=price.to_integral_value() or charge!=charge.to_integral_value():raise ValueError('bad billing')
  except (KeyError,ValueError,TypeError,InvalidOperation):self.base._stop(ident,'status billing invalid; reserve retained');raise p.Error('status billing invalid') from None
  self.base._settle(ident,int(charge))
  if data.get('success') is not True or price!=charge:self.base.stop('status charge or envelope mismatch');raise p.Error('status charge or envelope mismatch')
  return answer
 def receipt(self,ident):return self.base.receipt(ident)

CLAIM=ROOT/'forecast-cpi-p1-format-recovery.claim.json'
LEDGER=ROOT/'forecast-cpi-p1-format-recovery-ledger-20261029-01'
ACCOUNT=ROOT/'forecast-cpi-p1-format-recovery-account-contract-20261029-v1.json'
REPAIR=ROOT/'forecast-cpi-p1-posthoc-repair-20261029-v1.json'
REPAIR_SHA='c4e94fc345fc1d671b9a56cd8af9b8eb08784131a7c8fcf49ceb4c303c0ebd33'

def account_contract(path,sha,verify_challenge):
 raw=p.read(path,sha);c=json.loads(raw)
 if c.get('schema')!='cpi-p1-format-recovery-account-v1' or c.get('status')!='frozen' or c.get('scope')!={'mode':'accounting_only','provider_effects':'forbidden'} or c.get('parent')!=inspect_parent() or c.get('config')!=config() or c.get('ledger_root')!=str(LEDGER) or c.get('caps')!=p.CAPS or c.get('recovery_bridge_sha256')!=digest(Path(__file__).read_bytes()) or c.get('posthoc_repair_sha256')!=REPAIR_SHA or c.get('policy')!={'no_successful_repeats':True,'no_uncertain_repeats':True,'no_canary':True,'format_repair':'posthoc_one_character_only','source_attempts_max':5,'confirmed_429_extra_attempts_max':20,'confirmed_429_retries_per_operation':3}:raise p.Error('recovery account contract mismatch')
 import replay
 if p.read(REPAIR,REPAIR_SHA)!=canonical(replay.repaired_outcome()):raise p.Error('posthoc derivative does not reconstruct')
 if not callable(verify_challenge) or verify_challenge(raw) is not True:raise p.Error('independent accounting challenge required')
 return raw,c

def create(*,contract_sha,verify_challenge):
 import os
 if Path.cwd().resolve()!=ROOT or LEDGER.exists() or CLAIM.exists():raise p.Error('unsafe recovery account destination')
 account_contract(ACCOUNT,contract_sha,verify_challenge)
 claim=canonical({'parent_sha256':PARENT_SHA,'contract_sha256':contract_sha,'ledger_root':str(LEDGER)})
 fd=os.open(CLAIM,os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,'O_NOFOLLOW',0),0o600)
 with os.fdopen(fd,'wb') as f:f.write(claim);f.flush();os.fsync(f.fileno())
 fd=os.open(ROOT,os.O_RDONLY)
 try:os.fsync(fd)
 finally:os.close(fd)
 base=RecoveryBase(str(LEDGER),config(),create=True)
 try:base.db.execute("insert into run_events(event,reason,at_utc) values ('forecast_started',?,?)",(contract_sha,r.now_utc()));return base
 except BaseException:base.close();raise

def reopen(*,contract_sha,verify_challenge):
 if Path.cwd().resolve()!=ROOT or not LEDGER.is_dir() or LEDGER.is_symlink() or LEDGER.resolve()!=LEDGER.absolute():raise p.Error('unsafe recovery account path')
 account_contract(ACCOUNT,contract_sha,verify_challenge)
 if p.read(CLAIM)!=canonical({'parent_sha256':PARENT_SHA,'contract_sha256':contract_sha,'ledger_root':str(LEDGER)}):raise p.Error('recovery claim mismatch')
 base=RecoveryBase(str(LEDGER),config(),create=False)
 try:
  s=base.summary()
  if (s['stopped'],s['exposure_micro'],s['generation_attempts'],s['count_attempts'],s['source_attempts'])!=(0,2033331,307,236,0) or base.db.execute('select 1 from effects limit 1').fetchone() or base.db.execute('select event,reason from run_events').fetchall()!=[('forecast_started',contract_sha)]:raise p.Error('recovery account already used')
  return base
 except BaseException:base.close();raise
