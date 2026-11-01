"""Offline-prepared model accounting successor for three completed HTTP 429s.

Import, inspect and tests have no external effects. No live dispatcher, credential
or authority is supplied. Historical count receipts remain in predecessor DBs.
"""
from __future__ import annotations
import datetime as dt
import hashlib, json, os, sqlite3, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
for d in ('budget-v2','forecast-budget-v1','forecast-stopped-successor-v1','forecast-source-only-v1','forecast-p1-search-v1'):
 sys.path.insert(0,str(ROOT/d))
from ledger import Ledger, Stop, canonical, digest, now_utc
import source_only

PARENT_DB='forecast-source-only-ledger-20261029-01/ledger.sqlite3'
PARENT_SHA='65245faf8eee322b190e7dac39f4cc6d2d29ba8ee84ac4f484a276dcb388aeee'
FAILED={
 'generation:p0:case-01:b:02':('forecast-recovery-ledger-20261029-01/ledger.sqlite3','ed9d2aad306864dd228c85ffe3fc4ddc092f6b3b2272139bb12743893de72de7','d3616e8dcad5edd899faec1167108b94e014b3906e4cd6b1444875e7deb4fb29'),
 'generation:p0:case-02:b:05':('forecast-429-recovery-ledger-20261029-01/ledger.sqlite3','ee8670dbc34721e39aecaf4b8fe160e38e56af53a772872b323bcef05739a02b','410a9cfd08565f144068826eb6b7c4a6d63ee6d9ac34bf851857f151d6551494'),
 'generation:p0:case-04:c:03':('forecast-429b-recovery-ledger-20261029-01/ledger.sqlite3','fe936ec04125fa108e321a7429788caede980630e1566354353c19e46f81d677','4ddc5163215128a3ba24248d9ddd1aea61d1e7c5a863158c0bf7c08cd9f04969'),
}
RESP429='e454245d288b6724dd369a9f36d4d3b2359b5fea630c862e0db16477175d6341'
CAPS={'total_usd_micro':60000000,'total_generation_attempts':835,'total_count_attempts':767,'total_source_attempts':28}
DEADLINE='2026-10-29T12:30:00Z'
class Error(Stop):pass

def _bytes(path,expected):
 p=ROOT/path
 if not p.is_file() or p.is_symlink() or p.resolve()!=p.absolute():raise Error('unsafe historical path')
 b=p.read_bytes()
 if digest(b)!=expected:raise Error('historical bytes drift')
 return b

def _connect(rel,expected):
 _bytes(rel,expected)
 return sqlite3.connect('file:'+str(ROOT/rel)+'?mode=ro&immutable=1',uri=True)

def historical_429(old_id):
 if old_id not in FAILED:raise Error('operation not in 429 allowlist')
 rel,dbsha,reqsha=FAILED[old_id];db=_connect(rel,dbsha)
 try:
  row=db.execute('select kind,state,http_status,request,request_hash,response,response_hash,actual_micro,quote_micro,related_id,provider,endpoint from effects where id=?',(old_id,)).fetchone()
  if row is None:raise Error('missing old generation')
  kind,state,status,request,rh,response,sh,actual,quote,related,provider,endpoint=row
  if (kind,state,status,rh,sh,actual,quote,provider,endpoint)!=('generation','succeeded',429,reqsha,RESP429,None,86016,'vertex','gemini-3.8-flash@global') or digest(request)!=rh or digest(response)!=sh:raise Error('429 receipt mismatch')
  wanted='count:'+old_id.removeprefix('generation:')
  if related!=wanted:raise Error('count identity mismatch')
  row=db.execute('select kind,state,http_status,request,request_hash,response,response_hash,actual_micro from effects where id=?',(related,)).fetchone()
  if row is None:raise Error('missing old count')
  ck,cs,ch,cb,cr,cresp,csh,ca=row
  if (ck,cs,ch,cr,ca)!=('count','succeeded',200,rh,0) or cb!=request or digest(cb)!=cr or digest(cresp)!=csh:raise Error('old count receipt mismatch')
  count=json.loads(cresp).get('totalTokens')
  if type(count) is not int or not 0<count<=16384:raise Error('old count out of envelope')
  for ident,states in [(old_id,['prepared','started','succeeded']),(related,['prepared','started','succeeded','accounted'])]:
   if [r[0] for r in db.execute('select state from events where effect_id=? order by seq',(ident,))]!=states:raise Error('historical sequence mismatch')
  return {'old_generation_id':old_id,'old_count_id':related,'old_db_sha256':dbsha,'request_sha256':rh,'count_response_sha256':csh,'count_tokens':count,'http_status':429}
 finally:db.close()

def inspect():
 # Previous stage validates all three predecessor journals and their lineage.
 prior=source_only.inspect()
 # Verify the historical challenge at the operation's actual timestamp. Do
 # not apply the old UI quote expiry to the present moment.
 cr=_bytes('forecast-p1-search-contract-20261029-v1.json','8e1926733aa762a39f4609d17871b38f43a05238dd9f58b9e83164827e6d7af3')
 pr=_bytes('forecast-p1-search-challenge-packet-v1.json','9b5758bf9175b4d99f30844e215406c7be1d9af3dd85f5059f543e9972d63552')
 rr=_bytes('forecast-p1-search-challenge-receipt-v1.json','84f92643917ff386985d67e9991b377053762f0cc2a658ead873e3e4d0ccfc10')
 c,packet,receipt=map(json.loads,(cr,pr,rr));d=packet.get('internal_digest')
 if (c.get('schema')!='faithful-forecast-source-only-run-v1' or c.get('status')!='frozen' or packet.get('overall_state')!='ready' or packet.get('witness',{}).get('identity')!='p1_search_witness' or packet.get('challenged_contract',{}).get('raw_sha256')!=digest(cr) or d!=digest(canonical({k:v for k,v in packet.items() if k!='internal_digest'})) or receipt.get('packet_raw_sha256')!=digest(pr) or receipt.get('packet_byte_count')!=len(pr) or receipt.get('packet_internal_digest')!=d or receipt.get('state')!='ready'):raise Error('historical search witness mismatch')
 if any(packet.get('context_binding',{}).get(k)!=c.get(k) for k in ('execution_context','p0_binding','limits','operations')):raise Error('historical source scope mismatch')
 for rel,h in c['component_bindings'].items():_bytes(rel,h)
 summary=json.loads(_bytes('forecast-p1-search-results-20261029-01/summary.json','a6dd33c0b719309042bef8154e4e6ce727f83a3aab854fd2add647cb50eddccf'))
 if summary.get('status')!='completed' or summary.get('ledger',{}).get('exposure_micro')!=1889731:raise Error('source summary mismatch')
 db=_connect(PARENT_DB,PARENT_SHA)
 try:
  if db.execute('select stopped,exposure_micro,generation_attempts,count_attempts,source_attempts from run').fetchone()!=(0,1889731,274,206,2):raise Error('source parent counters changed')
  rows=db.execute('select id,kind,state,http_status,request,request_hash,response,response_hash,actual_micro,started_at_utc from effects order by rowid').fetchall()
  expected=[('p1-openai-official-you',5000,'dc5aec7a2effa103cfe8231ec1e6bf572a97ae16ddf981c8fa5ea56e0b38453d'),('p1-openai-related-serper-news',2000,'397e23e2dd5a3cc6384716227b145e6009d25e5a4e53431b47e1e3038a3bf2c7')]
  if len(rows)!=2:raise Error('source count mismatch')
  for row,(ident,amount,h),op in zip(rows,expected,c['operations']):
   i,k,s,status,req,rh,resp,sh,a,started=row
   if (i,k,s,status,a,sh)!=(ident,'source','succeeded',200,amount,h) or digest(req)!=rh or digest(resp)!=sh:raise Error('source receipt mismatch')
   ticket=op['ticket']
   if (ticket['id']!=ident or ticket['request_sha256']!=rh or canonical(op['payload'])!=req or dt.datetime.fromisoformat(started.replace('Z','+00:00'))>=dt.datetime.fromisoformat(ticket['expires_utc'].replace('Z','+00:00'))):raise Error('historical source ticket mismatch')
   obj=json.loads(resp)
   if not obj.get('success') or int(float(obj['priceCents'])*10000)!=a:raise Error('source charge mismatch')
  failures=[historical_429(i) for i in FAILED]
 finally:db.close()
 return {'schema':'p0-429-resume-parent-v1','source_db_sha256':PARENT_SHA,'prior_lineage':prior,'exposure_micro':1889731,'generation_attempts':274,'count_attempts':206,'source_attempts':16,'retained_micro':{'http400':150000,'http429_each':[86016,86016,86016]},'failed_429':failures}

def config():
 c=source_only.config();c.update(run_id='faithful-p0-429-resume-20261029-01',prior_micro=1889731,prior_generations=274,prior_counts=206,max_generations=329,max_counts=258,max_sources=0)
 return c

class Base(Ledger):
 @staticmethod
 def _validate_contract(c):
  if c!=config():raise Error('resume config changed')

class Accounting:
 """Accounting-only: no provider effects until a distinct reviewed stage."""
 def __init__(self,base,parent,accounting_sha):self.base=base;self.parent=parent;self.accounting_sha=accounting_sha
 def summary(self):
  s=self.base.summary();s['source_attempts']+=16;s['previous_source_attempts']=16;return s
 def close(self):self.base.close()
 def retry_failed(self,*args,**kwargs):raise Error('accounting-only; model effects forbidden')
 def count_new(self,*args,**kwargs):raise Error('accounting-only; model effects forbidden')
 def generate_new(self,*args,**kwargs):raise Error('accounting-only; model effects forbidden')

class Resume:
 """Injected transport only. No source/canary. Prior identity belongs to caller.

 Per-arm ordinals are enforced here; launcher must bind exact original model
 inputs, reconstruct its state from historical successful effects, and enforce
 matched B count / actual p0 timestamps before any network call.
 """
 def __init__(self,base,parent,clock=None):self.base=base;self.parent=parent;self.clock=clock or (lambda:dt.datetime.now(dt.timezone.utc))
 def summary(self):
  s=self.base.summary();s['source_attempts']+=16;s['previous_source_attempts']=16;return s
 def close(self):self.base.close()
 def stop(self,reason):self.base.stop(reason)
 def _before_deadline(self):
  now=self.clock()
  if not isinstance(now,dt.datetime) or now.utcoffset()!=dt.timedelta(0):raise Error('UTC clock required')
  if now>=dt.datetime.fromisoformat(DEADLINE.replace('Z','+00:00')):
   if not self.base.summary()['stopped']:self.base.stop('p0 deadline reached; no further effects')
   raise Error('p0 deadline elapsed; partial result invalid for planned event')
 def _retry_successor(self,old_id):return 'retry1:'+old_id
 def retry_failed(self,old_id,request,transport):
  self._before_deadline()
  h=historical_429(old_id);raw=canonical(request)
  if digest(raw)!=h['request_sha256']:raise Error('retry request changed')
  if self.base.db.execute('select 1 from effects where id=?',(self._retry_successor(old_id),)).fetchone():raise Error('retry already attempted')
  if request.get('generationConfig',{}).get('maxOutputTokens')!=4096 or any(x in request for x in ('tools','toolConfig','cachedContent','model')):raise Error('config drift')
  # This is an explicit external receipt reference, NOT a fake local count effect.
  ref='historical-count:'+h['old_db_sha256']+':'+h['old_count_id']+':'+h['count_response_sha256']
  c=self.base._contract
  data=self.base._execute(self._retry_successor(old_id),'generation','vertex',c['model']+'@'+c['location'],raw,self.base._model_bound(),c['model_price_evidence_sha256'],transport,ref)
  self._settle_generation(self._retry_successor(old_id),data)
  self._before_deadline()
  return data
 def _settle_generation(self,ident,raw):
  try:
   p=json.loads(raw);u=p['usageMetadata'];n=u['promptTokenCount'];total=u['totalTokenCount'];out=total-n;thought=u.get('thoughtsTokenCount');version=p.get('modelVersion')
   if type(n) is not int or type(total) is not int or n<=0 or out<=0 or (thought is not None and (type(thought) is not int or thought<0 or thought>out)):raise ValueError('usage invalid')
   self.base._settle(ident,(3*n+15*out+1)//2)
   if n>16384 or out>8192 or not isinstance(version,str) or not (version=='gemini-3.8-flash' or version.startswith('gemini-3.8-flash-')):raise ValueError('model or token envelope invalid')
  except BaseException:
   if not self.base.summary()['stopped']:self.base.stop('generation usage or persistence failure')
   raise
 def _allowed_new(self,logical):
  # No new case01/02 C, case03, or already attempted operations.
  parts=logical.split(':')
  if len(parts)!=4 or parts[0]!='p0' or parts[1] not in ('case-01','case-02','case-04') or parts[2] not in ('b','c') or not parts[3].isdigit():return False
  n=int(parts[3]);case,arm=parts[1:3]
  if parts[3]!=f'{n:02d}':return False
  return (case=='case-01' and arm=='b' and 3<=n<=8) or (case=='case-02' and arm=='b' and 6<=n<=8) or (case=='case-04' and arm=='c' and 4<=n<=23) or (case=='case-04' and arm=='b' and 1<=n<=23)
 def _require_predecessor(self,logical):
  _,case,arm,ordinal=logical.split(':');n=int(ordinal)
  if case=='case-01':first=3;retry='generation:p0:case-01:b:02'
  elif case=='case-02':first=6;retry='generation:p0:case-02:b:05'
  elif arm=='c':first=4;retry='generation:p0:case-04:c:03'
  else:
   # An external reviewed launcher verifies WTI C completion and the exact
   # matched count; require the predecessor retry at this gate as well.
   first=1;retry='generation:p0:case-04:c:03'
  if n==first:prior=self._retry_successor(retry)
  else:prior='newgeneration:'+':'.join(('p0',case,arm,f'{n-1:02d}'))
  row=self.base.db.execute('select state,http_status,actual_micro from effects where id=?',(prior,)).fetchone()
  if row is None or row[0]!='succeeded' or row[1]!=200 or row[2] is None:raise Error('prior generation not successfully settled')
 def count_new(self,logical,request,transport):
  self._before_deadline()
  if not self._allowed_new(logical):raise Error('unstarted operation scope violation')
  self._require_predecessor(logical)
  value=self.base.count('newcount:'+logical,request,transport);self._before_deadline();return value
 def generate_new(self,logical,request,transport):
  self._before_deadline()
  if not self._allowed_new(logical):raise Error('unstarted operation scope violation')
  self._require_predecessor(logical)
  value=self.base.generate('newgeneration:'+logical,request,'newcount:'+logical,transport);self._before_deadline();return value

def create(root,*,contract_path,contract_sha256,verify_challenge):
 """Offline create only; no provider or credential access. Requires real challenge."""
 root=Path(root);path=Path(contract_path)
 if not root.is_absolute() or root.exists() or root.parent.resolve()!=root.parent.absolute() or not path.is_absolute() or path.is_symlink() or path.resolve()!=path.absolute():raise Error('unsafe create inputs')
 raw=path.read_bytes();c=json.loads(raw);parent=inspect()
 if digest(raw)!=contract_sha256 or c.get('schema')!='p0-429-resume-accounting-contract-v1' or c.get('status')!='frozen' or c.get('scope')!={'mode':'accounting_only','provider_effects':'forbidden'} or c.get('parent')!=parent or c.get('config')!=config() or c.get('ledger_root')!=str(root) or c.get('caps')!=CAPS or c.get('no_source') is not True or c.get('no_canary') is not True or c.get('strict_p0_deadline_utc')!=DEADLINE or c.get('bridge_sha256')!=digest(Path(__file__).read_bytes()):raise Error('contract mismatch')
 if not callable(verify_challenge) or verify_challenge(raw) is not True:raise Error('independent challenge required')
 claim=root.parent/'forecast-p0-429-resume.claim.json';claimraw=canonical({'parent_sha256':PARENT_SHA,'contract_sha256':contract_sha256,'ledger_root':str(root)})
 fd=os.open(claim,os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,'O_NOFOLLOW',0),0o600)
 with os.fdopen(fd,'wb') as out:out.write(claimraw);out.flush();os.fsync(out.fileno())
 fd=os.open(claim.parent,os.O_RDONLY)
 try:os.fsync(fd)
 finally:os.close(fd)
 base=Base(str(root),config(),create=True)
 try:
  base.db.execute("insert into run_events(event,reason,at_utc) values ('forecast_started',?,?)",(contract_sha256,now_utc()))
  return Accounting(base,parent,contract_sha256)
 except BaseException:base.close();raise

def reopen(root,*,contract_path,contract_sha256,verify_challenge):
 """Open an untouched accounting successor; a started stage cannot be reopened."""
 root=Path(root);path=Path(contract_path)
 if not root.is_absolute() or root.is_symlink() or root.resolve()!=root.absolute() or not root.is_dir() or not path.is_absolute() or path.is_symlink() or path.resolve()!=path.absolute() or not path.is_file():raise Error('unsafe reopen inputs')
 raw=path.read_bytes();c=json.loads(raw);parent=inspect()
 if digest(raw)!=contract_sha256 or c.get('schema')!='p0-429-resume-accounting-contract-v1' or c.get('status')!='frozen' or c.get('scope')!={'mode':'accounting_only','provider_effects':'forbidden'} or c.get('parent')!=parent or c.get('config')!=config() or c.get('ledger_root')!=str(root) or c.get('caps')!=CAPS or c.get('bridge_sha256')!=digest(Path(__file__).read_bytes()) or c.get('strict_p0_deadline_utc')!=DEADLINE or c.get('no_source') is not True or c.get('no_canary') is not True:raise Error('reopen contract mismatch')
 if not callable(verify_challenge) or verify_challenge(raw) is not True:raise Error('independent challenge required')
 claim=root.parent/'forecast-p0-429-resume.claim.json'
 if not claim.is_file() or claim.is_symlink() or claim.read_bytes()!=canonical({'parent_sha256':PARENT_SHA,'contract_sha256':contract_sha256,'ledger_root':str(root)}):raise Error('claim mismatch')
 base=Base(str(root),config(),create=False)
 try:
  if base.summary()!= {'stopped':0,'exposure_micro':1889731,'generation_attempts':274,'count_attempts':206,'source_attempts':0,'metadata_attempts':0,'metadata_retained_micro':0} or base.db.execute('select 1 from effects limit 1').fetchone() or base.db.execute('select event,reason from run_events').fetchall()!=[('forecast_started',contract_sha256)]:raise Error('accounting successor not untouched')
  return Accounting(base,parent,contract_sha256)
 except BaseException:base.close();raise

def activate(accounting,*,model_contract_path,expected_sha256,verify_challenge):
 """Activate only a separately frozen, independently challenged model stage."""
 if not isinstance(accounting,Accounting):raise Error('accounting-only ledger required')
 path=Path(model_contract_path)
 if not path.is_absolute() or path.is_symlink() or path.resolve()!=path.absolute() or not path.is_file():raise Error('unsafe model contract path')
 raw=path.read_bytes();c=json.loads(raw)
 expected_scope={'cases':['case-01','case-02','case-04'],'allowed_retries':list(FAILED),'max_retry_per_old':1,'max_new_generations':55,'max_new_counts':52,'source_calls':0,'canary_calls':0,'strict_p0_deadline_utc':DEADLINE}
 if digest(raw)!=expected_sha256 or c.get('schema')!='p0-429-exact-resume-model-contract-v1' or c.get('status')!='frozen' or c.get('accounting_contract_sha256')!=accounting.accounting_sha or c.get('caps')!=CAPS or c.get('scope')!=expected_scope or c.get('starting_usage')!=accounting.summary() or c.get('bridge_sha256')!=digest(Path(__file__).read_bytes()):raise Error('model-stage contract mismatch')
 if not callable(verify_challenge) or verify_challenge(raw) is not True:raise Error('independent model-stage challenge required')
 db=accounting.base.db;db.execute('begin immediate')
 try:
  if accounting.base.summary()['stopped'] or db.execute('select 1 from effects limit 1').fetchone() or db.execute("select 1 from run_events where event='model_started'").fetchone():raise Error('model stage already claimed or stopped')
  db.execute("insert into run_events(event,reason,at_utc) values ('model_started',?,?)",(expected_sha256,now_utc()));db.execute('commit')
 except BaseException:
  if db.in_transaction:db.execute('rollback')
  raise
 return Resume(accounting.base,accounting.parent)
