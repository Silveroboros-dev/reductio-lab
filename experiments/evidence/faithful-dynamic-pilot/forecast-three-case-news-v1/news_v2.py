"""Offline frozen 3-case source-only successor. execute is explicit live entry."""
import datetime as dt,json,os,sqlite3,subprocess,sys
from decimal import Decimal, InvalidOperation
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
for folder in ('forecast-p1-budget-successor-v1','forecast-budget-v1','budget-v2','forecast-p0-launch-v1'):
 sys.path.insert(0,str(ROOT/folder))
import p1_budget as parent,forecast_ledger as f
from ledger import Ledger,canonical,digest,now_utc
PROPOSAL=ROOT/'forecast-p1-three-case-search-proposal-20261029-v2.json';PROPOSAL_SHA='19cfc6f063dbba4e14531da6ce23982cb0a6c18ba9416ad4ff9ab95c85901529'
PRICE=ROOT/'forecast-three-case-source-prices-20261029-v1.json';PRICE_SHA='a76481cdf1ad3ac03e400237ef29d438228c3811502b3d66aa3bec31c5368b24'
CONTRACT=ROOT/'forecast-three-case-news-contract-20261029-v2.json';PACKET=ROOT/'forecast-three-case-news-challenge-packet-v2.json';RECEIPT=ROOT/'forecast-three-case-news-challenge-receipt-v2.json'
LEDGER=ROOT/'forecast-three-case-news-ledger-20261029-02';OUTPUT=ROOT/'forecast-three-case-news-results-20261029-02';CLAIM=ROOT/'forecast-three-case-news-v2.claim.json'
FILES=('forecast-three-case-news-v1/news_v2.py','forecast-p1-budget-successor-v1/p1_budget.py','forecast-429-resume-account-v1/resume_ledger.py','forecast-budget-v1/forecast_ledger.py','budget-v2/ledger.py','transport/oneshot.py','forecast-p1-three-case-search-proposal-20261029-v2.json','forecast-three-case-source-prices-20261029-v1.json','forecast-p0-429-resume-results-20261029-01/case-01-p0-receipt.json','forecast-p0-final-two-results-20261029-01/00-p0-receipt.json','forecast-p0-429-resume-results-20261029-01/case-04-p0-receipt.json')
class Error(ValueError):pass

def read(path,expected=None):return parent.read(path,expected)
def obj(raw):
 def pairs(items):
  d={}
  for k,v in items:
   if k in d:raise Error('duplicate JSON key')
   d[k]=v
  return d
 try:v=json.loads(raw,object_pairs_hook=pairs)
 except (ValueError,UnicodeDecodeError,TypeError) as ex:raise Error('invalid JSON') from ex
 if not isinstance(v,dict):raise Error('object required')
 return v

def config():
 c=parent.config();c.update(run_id='faithful-three-case-news-20261029-02',max_generations=299,max_counts=228,max_sources=3,source_cap_micro=450000)
 return c
class Base(Ledger):
 @staticmethod
 def _validate_contract(c):
  if c!=config():raise Error('budget config mismatch')

def evidence():
 proposal=obj(read(PROPOSAL,PROPOSAL_SHA));price=obj(read(PRICE,PRICE_SHA))
 if proposal.get('schema')!='three-existing-case-post-p0-news-search-proposal-v1' or proposal.get('status')!='offline_proposal_only' or price.get('schema')!='three-case-source-ui-prices-v1':raise Error('proposal or price schema mismatch')
 cases=proposal['cases'];observations=price['observations']
 if [x['case_id'] for x in cases]!=['case-01','case-03','case-04'] or {(x['api'],x['path'],x['rate_usd']) for x in observations}!={('serper','/news','0.002 per call'),('you/search','/v1/search','0.005 per call'),('linkup','/search','0.01 per call')}:raise Error('scope or price drift')
 paths=('forecast-p0-429-resume-results-20261029-01/case-01-p0-receipt.json','forecast-p0-final-two-results-20261029-01/00-p0-receipt.json','forecast-p0-429-resume-results-20261029-01/case-04-p0-receipt.json')
 bindings=[]
 for x,name in zip(cases,paths):
  raw=read(ROOT/name);receipt=obj(raw)
  if receipt.get('durable_before_utc')!=x['durable_before_utc']:raise Error('p0 timestamp mismatch')
  bindings.append({'case_id':x['case_id'],'path':str(ROOT/name),'sha256':digest(raw),'durable_before_utc':x['durable_before_utc']})
 observed=dt.datetime.fromisoformat(price['observed_at_utc'].replace('Z','+00:00'))
 if observed.utcoffset()!=dt.timedelta(0):raise Error('price time invalid')
 expires=(observed+dt.timedelta(minutes=15)).isoformat();ops=[]
 old_ids={x['id'] for x in parent.old.inspect()['prior_lineage']['source_history']};old_hashes={x['request_sha256'] for x in parent.old.inspect()['prior_lineage']['source_history']}
 db=sqlite3.connect('file:'+str(ROOT/parent.old.PARENT_DB)+'?mode=ro&immutable=1',uri=True)
 try:
  for i,h in db.execute("select id,request_hash from effects where kind='source'"):old_ids.add(i);old_hashes.add(h)
 finally:db.close()
 for x in cases:
  payload=x['payload'];raw=canonical(payload);op='postp0-news-'+x['case_id'];h=digest(raw)
  if op in old_ids or h in old_hashes:raise Error('old source operation repeated')
  ticket={'id':op,'provider':'orthogonal','endpoint':'/v1/run','request_sha256':h,'max_micro':150000,'evidence_sha256':PRICE_SHA,'expires_utc':expires,'category':'news' if payload['api']=='serper' else 'search','settlement':'orthogonal_price_cents'}
  ops.append({'case_id':x['case_id'],'payload':payload,'ticket':ticket})
 return ops,bindings

def prepare():
 if Path.cwd().resolve()!=ROOT or any(p.exists() for p in (CONTRACT,LEDGER,OUTPUT,CLAIM)):raise Error('wrong context or output exists')
 ops,bindings=evidence();c={'schema':'three-case-p1-news-contract-v1','status':'frozen','caps':parent.CAPS,'parent':parent.inspect_parent(),'config':config(),'scope':{'source_ops':3,'no_model':True,'no_retry':True,'no_canary':True,'no_fetch':True,'no_status':True},'operations':ops,'p0_bindings':bindings,'execution_context':{'cwd':str(ROOT),'ledger_root':str(LEDGER),'output_root':str(OUTPUT),'claim':str(CLAIM)},'component_bindings':{x:digest(read(ROOT/x)) for x in FILES},'qualification':'Raw discovery candidates only: not proof of publication time, causality, or unresolved market.'}
 raw=canonical(c);put(CONTRACT,raw);return digest(raw)

def put(path,raw):
 path=Path(path);fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,'O_NOFOLLOW',0),0o600)
 with os.fdopen(fd,'wb') as f0:f0.write(raw);f0.flush();os.fsync(f0.fileno())
 fd=os.open(path.parent,os.O_RDONLY)
 try:os.fsync(fd)
 finally:os.close(fd)

def verify(expected):
 cr,pr,rr=map(read,(CONTRACT,PACKET,RECEIPT));c,w,receipt=map(obj,(cr,pr,rr));d=w.get('internal_digest')
 if (digest(cr)!=expected or c.get('schema')!='three-case-p1-news-contract-v1' or c.get('status')!='frozen' or c.get('caps')!=parent.CAPS or c.get('parent')!=parent.inspect_parent() or c.get('config')!=config() or c.get('scope')!={'source_ops':3,'no_model':True,'no_retry':True,'no_canary':True,'no_fetch':True,'no_status':True} or w.get('schema_version')!='eval_contract_challenge_packet_v1' or w.get('overall_state')!='ready' or w.get('witness',{}).get('identity')!='three_case_news_witness_v2' or w.get('witness',{}).get('mode')!='read_only_offline' or w.get('challenged_contract',{}).get('raw_sha256')!=expected or d!=digest(canonical({k:v for k,v in w.items() if k!='internal_digest'})) or receipt.get('packet_raw_sha256')!=digest(pr) or receipt.get('packet_byte_count')!=len(pr) or receipt.get('packet_internal_digest')!=d or receipt.get('state')!='ready'):raise Error('contract challenge mismatch')
 ops,bindings=evidence();context={'cwd':str(ROOT),'ledger_root':str(LEDGER),'output_root':str(OUTPUT),'claim':str(CLAIM)}
 if c.get('operations')!=ops or c.get('p0_bindings')!=bindings or c.get('execution_context')!=context or any(w.get('context_binding',{}).get(k)!=c.get(k) for k in ('scope','operations','p0_bindings','execution_context','parent','config')):raise Error('source scope drift')
 refs=c.get('component_bindings');seen=w.get('context_binding',{}).get('code_bindings_at_inspection')
 if not isinstance(refs,dict) or set(refs)!=set(FILES) or not isinstance(seen,dict):raise Error('bindings missing')
 for name,h in refs.items():
  raw=read(ROOT/name)
  if digest(raw)!=h or seen.get(name)!={'sha256':h,'size':len(raw)}:raise Error('component mismatch')
 return c,cr,pr,rr

class Source(f.ForecastLedger):
 def __init__(self,base,claim,parent_data,contract_sha,ticket_verifier):super().__init__(base,claim,parent_data,CONTRACT,contract_sha,ticket_verifier)
 def summary(self):
  x=self._base.summary();x['source_attempts']+=16;x['previous_source_attempts']=16;return x
 def verify_parent(self):
  if read(CLAIM)!=canonical({'parent_sha256':parent.PARENT_SHA,'contract_sha256':self._contract_sha,'ledger_root':str(LEDGER)}) or parent.inspect_parent()!=self._parent:raise Error('parent drift')
 def _guard(self):
  try:
   self.verify_parent();read(CONTRACT,self._contract_sha)
   if self.db.execute("select reason from run_events where event='forecast_started'").fetchall()!=[(self._contract_sha,)]:raise Error('stage marker mismatch')
  except BaseException:
   try:self.stop('source contract or lineage mismatch')
   finally:self.poisoned=True
   raise
 def count(self,*a,**k):raise Error('source-only')
 def generate(self,*a,**k):raise Error('source-only')
 def source(self,op,provider,endpoint,request,ticket,transport):
  if (provider,endpoint)!=('orthogonal','/v1/run'):raise Error('source endpoint denied')
  self._guard()
  required={'id','provider','endpoint','request_sha256','max_micro','evidence_sha256','expires_utc','category','settlement'}
  if not isinstance(ticket,dict) or set(ticket)!=required or not isinstance(request,bytes) or not request or len(request)>32768:raise Error('source ticket invalid')
  if (ticket['id'],ticket['provider'],ticket['endpoint'],ticket['request_sha256'],ticket['settlement'])!=(op,provider,endpoint,digest(request),'orthogonal_price_cents') or ticket['category'] not in ('news','search') or ticket['max_micro']!=150000 or not f.valid_hash(ticket['evidence_sha256']):raise Error('source ticket mismatch')
  expiry=dt.datetime.fromisoformat(ticket['expires_utc'].replace('Z','+00:00'))
  if expiry.utcoffset()!=dt.timedelta(0) or expiry<=dt.datetime.now(dt.timezone.utc) or self._verify_ticket(ticket,request) is not True:raise Error('source price expired or ticket not verified')
  raw=self._base._execute(op,'source',provider,endpoint,request,ticket['max_micro'],ticket['evidence_sha256'],transport,quote_metadata=canonical(ticket))
  try:
   data=obj(raw);price=Decimal(str(data['priceCents']))*10000
   if not price.is_finite() or price<0 or price!=price.to_integral_value():raise ValueError('priceCents invalid')
   charged=data.get('billing',{}).get('chargedPriceCents')
   if charged is None:raise ValueError('chargedPriceCents unavailable')
   billed=Decimal(str(charged))*10000
   if not billed.is_finite() or billed<0 or billed!=billed.to_integral_value():raise ValueError('chargedPriceCents invalid')
   amount=int(billed)
  except (KeyError,ValueError,TypeError,InvalidOperation):
   self._base._stop(op,'source billing invalid; reserve retained');raise Error('source billing invalid') from None
  self._base._settle(op,amount)
  if data.get('success') is not True or amount!=int(price):
   self.stop('source semantic error or billing mismatch');raise Error('source envelope or billing mismatch')
  return raw

def execute(expected):
 """EXPLICIT live entry: 3 frozen Orthogonal requests, no hidden retry."""
 c,cr,pr,rr=verify(expected)
 if Path.cwd().resolve()!=ROOT or any(p.exists() for p in (LEDGER,OUTPUT,CLAIM)):raise Error('destination exists')
 claim=canonical({'parent_sha256':parent.PARENT_SHA,'contract_sha256':expected,'ledger_root':str(LEDGER)});put(CLAIM,claim)
 base=Base(str(LEDGER),config(),create=True)
 try:
  base.db.execute("insert into run_events(event,reason,at_utc) values ('forecast_started',?,?)",(expected,now_utc()))
  def check(ticket,raw):return verify(expected)[1]==cr and any(x['ticket']==ticket and canonical(x['payload'])==raw for x in c['operations'])
  ledger=Source(base,claim,c['parent'],expected,check);OUTPUT.mkdir(mode=0o700)
  put(OUTPUT/'started.json',canonical({'contract_sha256':expected,'challenge_sha256':digest(pr),'receipt_sha256':digest(rr),'operations':[x['ticket']['id'] for x in c['operations']]}))
  def token(provider):
   if provider!='orthogonal':raise Error('model denied')
   v=subprocess.run(['/usr/bin/security','find-generic-password','-s','com.maguire.orthogonal.live','-a','maguire','-w'],stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,check=False,timeout=15)
   if v.returncode or not v.stdout.strip():raise Error('configured credential unavailable')
   return v.stdout.strip().decode('ascii')
  sys.path.insert(0,str(ROOT/'transport'));from oneshot import OneShotTransport
  transport=OneShotTransport('source-only-123',token);records=[];failure=None
  for op in c['operations']:
   ident=op['ticket']['id']
   try:
    raw=ledger.source(ident,'orthogonal','/v1/run',canonical(op['payload']),op['ticket'],transport);rec=ledger.receipt(ident);put(OUTPUT/(ident+'.raw.json'),raw)
    expected_micro={'case-01':2000,'case-03':5000,'case-04':10000}[op['case_id']]
    if rec['actual_micro']>expected_micro:ledger.stop('observed charge above UI price');raise Error('price above observed UI')
    records.append({'case_id':op['case_id'],'id':ident,'http_status':rec['http_status'],'actual_micro':rec['actual_micro'],'response_sha256':rec['response_hash'],'started_at_utc':rec['started_at_utc'],'completed_at_utc':rec['completed_at_utc']})
   except Exception as exc:
    failure={'id':ident,'error_type':type(exc).__name__}
    if not ledger.summary()['stopped']:ledger.stop('source phase failure; no retry')
    break
  summary={'status':'completed' if failure is None else 'stopped','records':records,'failure':failure,'ledger':ledger.summary(),'data_status':'raw discovery only; not independently verified news'};put(OUTPUT/'summary.json',canonical(summary));return summary
 finally:base.close()
