"""Create-only successor of a stopped HTTP-400 forecast ledger.

No provider calls or state writes on import/inspection. The completed but
non-200 operation keeps its original response, event state and reservation;
this module never retries it or rewrites the stopped predecessor.
"""
from __future__ import annotations
import datetime as dt,json,os,sys
from decimal import Decimal
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
for d in ('forecast-budget-v1','forecast-seed-launch-v1','budget-v2','source-successor','model-accounting-successor'):
 sys.path.insert(0,str(ROOT/d))
import forecast_ledger as f
import model_accounting,reopen
from ledger import Ledger,Stop,canonical,digest,now_utc,positive_int

PARENT_DB_SHA='ba7f80c158e12448ced843b5ce90114b1e46a424732e4b1e299e369ebbf70da3'
MARKET_CONTRACT_SHA='22847be8774c12d29afa93fd2fedc337eaedee30805bf32c34632592f8dda603'
MARKET_PACKET_SHA='9da74471c2fe0a442cba9cd39b371d422febf673881918135e1deadbcbed0401'
MARKET_RECEIPT_SHA='e2f28310e04f3aadae7c7e54c7ebe3ffc33cdfa50043851c3b0b3372afb7ab5b'
MARKET_STARTED_SHA='b48e6fdbd760e1874e99ee4ff41f5aa5952a763c9f5981005ee3b1f3f8341749'
MARKET_SUMMARY_SHA='737dfdc2fda6c8522ac007036fbd6a0b7793fbf49d62b41d8625f3f49b30719e'
FAILED_OP='post-seed-kalshi-market-lookup'
FAILED_REQUEST_SHA='525fa4f4d6d15c97f7941aabbe150c5a471c95cdb6b95fbaa73d0190b5a87b35'
FAILED_RESPONSE_SHA='aaad58eebda2af28db264af8f3ef5121e3586ccd927b93f0916e4aef2b2b958f'
FAILED_TICKERS=frozenset(('KXIPO-26-ANTHROPIC','KXWTI-26NOV03-T97.99','KXGPT-ASTRA61-26NOV13','KXCPI-26OCT-T0.2'))
CLAIM=ROOT/'forecast-stopped-successor-claims'/(PARENT_DB_SHA+'.claim.json')
CAPS={'total_usd_micro':60000000,'total_generation_attempts':835,'total_count_attempts':767,'total_source_attempts':28}
class Error(Stop):pass

def read(path,expected=None):return f.read(path,expected)
def obj(raw):return f.obj(raw)

def _reviewed_market():
 ar=read(ROOT/'forecast-market-source-addendum-20261029-v1.json',MARKET_CONTRACT_SHA)
 pr=read(ROOT/'forecast-market-challenge-packet-v1.json',MARKET_PACKET_SHA)
 rr=read(ROOT/'forecast-market-challenge-receipt-v1.json',MARKET_RECEIPT_SHA)
 a,p,r=map(obj,(ar,pr,rr));d=p.get('internal_digest');w=p.get('context_binding',{})
 if (a.get('schema')!='faithful-forecast-market-addendum-v1' or a.get('status')!='frozen' or a.get('caps')!=CAPS
  or p.get('schema_version')!='eval_contract_challenge_packet_v1' or p.get('overall_state')!='ready'
  or p.get('witness',{}).get('identity')!='market_source_witness' or p.get('witness',{}).get('mode')!='read_only_offline'
  or p.get('challenged_contract',{}).get('raw_sha256')!=MARKET_CONTRACT_SHA
  or d!=digest(canonical({k:v for k,v in p.items() if k!='internal_digest'}))
  or r.get('packet_raw_sha256')!=MARKET_PACKET_SHA or r.get('packet_byte_count')!=len(pr)
  or r.get('packet_internal_digest')!=d or r.get('state')!='ready'):
  raise Error('market contract or independent review mismatch')
 if any(w.get(k)!=a.get(k) for k in ('execution_context','operation','seed_parent','starting_usage')):raise Error('market scope mismatch')
 components=a.get('component_bindings',{});observed=w.get('code_bindings_at_inspection',{})
 if not components or set(components)!=set(observed):raise Error('market component coverage mismatch')
 for rel,h in components.items():
  raw=read(ROOT/rel,h)
  if observed[rel]!={'sha256':h,'size':len(raw)}:raise Error('market component binding mismatch')
 started=obj(read(ROOT/'forecast-source-market-leads-20261029-01/started.json',MARKET_STARTED_SHA))
 if started!={'addendum_sha256':MARKET_CONTRACT_SHA,'challenge_sha256':MARKET_PACKET_SHA,'receipt_sha256':MARKET_RECEIPT_SHA,'operation_id':FAILED_OP}:
  raise Error('market start binding mismatch')
 summary_raw=read(ROOT/'forecast-source-market-leads-20261029-01/summary.json',MARKET_SUMMARY_SHA);summary=obj(summary_raw)
 if (summary.get('status')!='stopped' or summary.get('record') is not None or
     summary.get('failure')!={'error_type':'Stop','id':FAILED_OP}):raise Error('market gate failure mismatch')
 return a,summary

def inspect_stopped():
 """Validate settled predecessor state and keep HTTP outcome distinct from gate."""
 # This checks the older lineage (including the original eight Orthogonal
 # sources and pre-forecast model usage) using its own read-only locks.
 prior=f.inspect_parent()
 a,summary=_reviewed_market()
 seed=a.get('seed_parent',{})
 seed_summary_raw=read(ROOT/'forecast-exploration-seed-20261029-01/summary.json',seed.get('seed_summary_sha256'))
 seed_summary=obj(seed_summary_raw)
 if (seed.get('schema')!='forecast-completed-seed-binding-v1' or seed.get('ledger')!=a.get('starting_usage') or
  seed.get('ledger')!=seed_summary.get('ledger') or seed.get('model_generation_count')!=32 or seed.get('model_usage_micro')!=120868 or
  (seed_summary.get('requested_cases'),seed_summary.get('attempted_cases'),seed_summary.get('not_attempted_cases'),seed_summary.get('stop_index'))!=(4,4,0,None)):
  raise Error('seed binding or completed results mismatch')
 previous_root=ROOT/'forecast-live-ledger-20261029-01';db_path=previous_root/'ledger.sqlite3'
 read(db_path,PARENT_DB_SHA)
 cfg=obj(read(ROOT/'forecast-budget-v1/ledger_contract.json'))
 base=reopen._ReadOnlyBase(previous_root,cfg)
 try:
  db=base.db;b,h=db.execute('SELECT contract,contract_hash FROM run WHERE id=1').fetchone()
  if bytes(b)!=canonical(cfg) or h!=digest(bytes(b)):raise Error('predecessor contract mismatch')
  state=db.execute('SELECT stopped,exposure_micro,generation_attempts,count_attempts,source_attempts FROM run').fetchone()
  if state!=(1,1510458,232,164,6):raise Error('stopped ledger counters mismatch')
  bound=base.summary();bound.update(source_attempts=14,previous_source_attempts=8)
  if summary.get('ledger')!=bound:raise Error('market stopped summary disagrees')
  sources=db.execute("SELECT id,provider,endpoint,state,http_status,request,request_hash,response,response_hash,quote_micro,actual_micro,quote_metadata,started_at_utc,completed_at_utc,detail FROM effects WHERE kind='source' ORDER BY rowid").fetchall()
  old=obj(read(ROOT/'forecast-source-run-contract-20261029-v1.json')); ops=old['source_phase']['requests']
  you=obj(read(ROOT/'forecast-source-you-addendum-20261029-v1.json')); ops=ops+[you['operation']]
  expected_ids=[x['id'] for x in ops]+[FAILED_OP]
  if [x[0] for x in sources]!=expected_ids:raise Error('unexpected source identity or ordering')
  source_cost=0
  for row,op in zip(sources[:5],ops):
   ident,provider,endpoint,st,status,req,rh,response,sh,quote,actual,metadata,start,end,detail=row
   ticket=op['ticket']; expected=canonical(op['payload'])
   if (provider!='orthogonal' or endpoint!='/v1/run' or st!='succeeded' or status!=200 or req!=expected or rh!=digest(req)
    or digest(response)!=sh or type(actual) is not int or actual<0 or quote!=150000 or obj(metadata)!=ticket
    or Decimal(str(obj(response).get('priceCents')))*10000!=actual or obj(response).get('success') is not True):
    raise Error('previous source settlement mismatch')
   quote_path=ROOT/('forecast-you-price-20261029.json' if ident=='seed-openai-you-search' else 'forecast-source-quotes-20261029.json')
   quote_raw=read(quote_path);quote_obj=obj(quote_raw)
   observed=dt.datetime.fromisoformat(quote_obj['observed_at_utc'].replace('Z','+00:00'))
   started=dt.datetime.fromisoformat(start.replace('Z','+00:00'));ended=dt.datetime.fromisoformat(end.replace('Z','+00:00'))
   expires=dt.datetime.fromisoformat(ticket['expires_utc'].replace('Z','+00:00'))
   if digest(quote_raw)!=ticket['evidence_sha256'] or not observed<=started<expires or ended<started:
    raise Error('previous source quote was not valid at effect start')
   previous_dir='forecast-source-you-20261029-01' if ident=='seed-openai-you-search' else 'forecast-source-seed-20261029-01'
   if read(ROOT/previous_dir/(ident+'.raw.json'))!=response:raise Error('previous source raw bytes changed')
   ev=db.execute('SELECT state,detail FROM events WHERE effect_id=? ORDER BY seq',(ident,)).fetchall()
   if ev!=[('prepared',None),('started',None),('succeeded',None),('accounted',str(actual))]:raise Error('source event chain mismatch')
   source_cost+=actual
  if source_cost!=29000:raise Error('prior source cost mismatch')
  row=sources[-1];ident,provider,endpoint,st,status,req,rh,response,sh,quote,actual,metadata,start,end,detail=row
  op=a['operation']
  if (ident!=FAILED_OP or provider!='orthogonal' or endpoint!='/v1/run' or st!='succeeded' or status!=400 or
   req!=canonical(op['payload']) or rh!=FAILED_REQUEST_SHA or digest(req)!=rh or digest(response)!=FAILED_RESPONSE_SHA or sh!=FAILED_RESPONSE_SHA or
   quote!=150000 or actual is not None or obj(metadata)!=op['ticket'] or detail!='non-200; billed status unknown' or
   obj(response)!={'success':False,'error':'Expected string, received number'}):raise Error('HTTP 400 effect or retained reserve mismatch')
  market_quote_raw=read(ROOT/a['quote_path']);market_quote=obj(market_quote_raw)
  observed=dt.datetime.fromisoformat(market_quote['observed_at_utc'].replace('Z','+00:00'))
  started=dt.datetime.fromisoformat(start.replace('Z','+00:00'));ended=dt.datetime.fromisoformat(end.replace('Z','+00:00'))
  expires=dt.datetime.fromisoformat(op['ticket']['expires_utc'].replace('Z','+00:00'))
  if digest(market_quote_raw)!=op['ticket']['evidence_sha256'] or not observed<=started<expires or ended<started:
   raise Error('market quote was not valid at effect start')
  ev=db.execute('SELECT state,detail FROM events WHERE effect_id=? ORDER BY seq',(FAILED_OP,)).fetchall()
  if ev!=[('prepared',None),('started',None),('succeeded',None)]:raise Error('HTTP effect and gate states conflated')
  effects=db.execute("SELECT id,kind,state,http_status,request,request_hash,response,response_hash,quote_micro,actual_micro,related_id FROM effects WHERE kind IN ('count','generation') ORDER BY rowid").fetchall()
  if len(effects)!=64:raise Error('unexpected seed model effects')
  expected_ids=[]
  for i,pair in enumerate(seed_summary['results']):
   if obj(read(ROOT/'forecast-exploration-seed-20261029-01'/f'{i:02d}-pair.json'))!=pair:raise Error('seed pair drift')
   for arm in ('c','b'):
    result=pair.get(arm)
    if not isinstance(result,dict) or obj(read(ROOT/'forecast-exploration-seed-20261029-01'/f'{i:02d}-{arm}.json'))!=result:
     raise Error('seed arm result mismatch')
    n=result.get('calls')
    if type(n) is not int or not 0<=n<=6:raise Error('seed arm call count invalid')
    for ordinal in range(1,n+1):
     identity=f"seed:{pair['case_id']}:{arm}:{ordinal:02d}"
     expected_ids.extend([('count:'+identity,'count'),('generation:'+identity,'generation')])
  if [(x[0],x[1]) for x in effects]!=expected_ids:raise Error('seed effect order or identity mismatch')
  counted={};sums={'generation':0,'count':0};cost=0
  for ident,kind,st,status,request,rh,response,response_hash,reserve,actual,related in effects:
   if (kind not in sums or st!='succeeded' or status!=200 or not isinstance(request,bytes) or
    digest(request)!=rh or digest(response)!=response_hash or type(actual) is not int or actual<0):raise Error('unsettled model effect')
   sums[kind]+=1;x=obj(response)
   if kind=='count':
    if actual!=0 or reserve!=0 or not positive_int(x.get('totalTokens')):raise Error('bad seed count')
    counted[ident]=rh
   else:
    u=x.get('usageMetadata',{});p=u.get('promptTokenCount');t=u.get('totalTokenCount')
    if (not positive_int(p) or not positive_int(t) or t<p or reserve!=86016 or
     not isinstance(x.get('modelVersion'),str) or not (x['modelVersion']=='gemini-3.8-flash' or x['modelVersion'].startswith('gemini-3.8-flash-')) or
     counted.get(related)!=rh or (3*p+15*(t-p)+1)//2!=actual):raise Error('seed model cost mismatch')
    cost+=actual
   ev=db.execute('SELECT state,detail FROM events WHERE effect_id=? ORDER BY seq',(ident,)).fetchall()
   if ev!=[('prepared',None),('started',None),('succeeded',None),('accounted',str(actual))]:raise Error('seed event sequence mismatch')
  if sums!={'generation':32,'count':32} or cost!=120868:raise Error('seed usage totals mismatch')
  if db.execute('SELECT event,reason FROM run_events ORDER BY seq').fetchall()!=[('forecast_started',old_contract_sha()),('exploration_seed_started',seed['seed_contract_sha256'])]:
   raise Error('prior stage marker mismatch')
  read(db_path,PARENT_DB_SHA)
 finally:base.close()
 return {'schema':'forecast-stopped-http400-parent-v1','parent_db_sha256':PARENT_DB_SHA,
  'market_addendum_sha256':MARKET_CONTRACT_SHA,'market_challenge_sha256':MARKET_PACKET_SHA,
  'market_summary_sha256':MARKET_SUMMARY_SHA,'seed_binding':seed,'previous_lineage':prior,
  'prior_micro':1510458,'prior_generations':232,'prior_counts':164,'prior_sources':14,
  'failed_operation':{'id':FAILED_OP,'request_sha256':FAILED_REQUEST_SHA,'response_sha256':FAILED_RESPONSE_SHA,
   'effect_state':'succeeded','http_status':400,'gate_state':'failed','charged_micro':None,'retained_micro':150000,
   'prohibition':'Do not repeat this operation or the same four-ticker set through this provider route.'}}

def old_contract_sha():return '009a8d5e401213a93c2183ef48c616383c84413d6ea668cb445c3aaf7c3d0e38'

class RecoveryBase(Ledger):
 @staticmethod
 def _validate_contract(c):
  expected=obj(read(ROOT/'forecast-stopped-successor-v1/ledger_contract.json'))
  if c!=expected or (c['cap_micro'],c['prior_micro'],c['prior_generations'],c['prior_counts'],c['max_generations'],c['max_counts'],c['max_sources'],c['source_cap_micro'])!=(60000000,1510458,232,164,835,767,14,2821000):
   raise ValueError('recovery cap or carry mismatch')
  if (c['model'],c['location'],c['input_limit'],c['output_reserve'],c['max_output_tokens'],c['input_rate_half_micro'],c['output_rate_half_micro'])!=('gemini-3.8-flash','global',16384,8192,4096,3,15):raise ValueError('model pricing mismatch')

class RecoveryLedger(f.ForecastLedger):
 def verify_parent(self):
  read(CLAIM,self._claim_sha)
  if inspect_stopped()!=self._parent:raise Error('stopped predecessor changed')
  return self._parent
 def summary(self):
  s=self._base.summary();s['source_attempts']+=14;s['previous_source_attempts']=14
  s['prior_http400_charge_unknown_retained_micro']=150000
  rows=self.db.execute("SELECT quote_metadata FROM effects WHERE kind='source'").fetchall()
  s['metadata_attempts']=sum(1 for (v,) in rows if v and obj(v).get('category')=='metadata')
  return s
 def receipt(self,op):
  if op in {f'source:case-{i:02}:serper' for i in range(1,9)}:
   self.verify_parent();old=model_accounting._open_parent()
   try:return old.receipt(op)
   finally:old.close()
  ids={'seed-anthropic-search','seed-macro-news','seed-openai-search','seed-opec-fetch','seed-openai-you-search',FAILED_OP}
  if op in ids:
   self.verify_parent();cfg=obj(read(ROOT/'forecast-budget-v1/ledger_contract.json'));old=reopen._ReadOnlyBase(ROOT/'forecast-live-ledger-20261029-01',cfg)
   try:return old.receipt(op)
   finally:old.close()
  return self._base.receipt(op)
 def source(self,op_id,provider,endpoint,request,ticket,transport):
  inherited={'seed-anthropic-search','seed-macro-news','seed-openai-search','seed-opec-fetch','seed-openai-you-search',FAILED_OP}
  if op_id in inherited or (isinstance(request,bytes) and digest(request)==FAILED_REQUEST_SHA):raise Error('predecessor source identity or failed request cannot be reused')
  if provider=='orthogonal' and endpoint=='/v1/run':
   try:
    payload=obj(request);query=payload.get('query',{});tickers=query.get('tickers') if isinstance(query,dict) else None
    if isinstance(tickers,str):tickers=frozenset(x.strip() for x in tickers.split(',') if x.strip())
    elif isinstance(tickers,list):tickers=frozenset(str(x).strip() for x in tickers)
    else:tickers=frozenset()
    if payload.get('api')=='kalshi' and payload.get('path')=='/markets' and tickers==FAILED_TICKERS:
     raise Error('same failed four-market request cannot be re-encoded as a retry')
   except (TypeError,ValueError):
    raise Error('invalid source payload') from None
  return super().source(op_id,provider,endpoint,request,ticket,transport)

class AccountingOnlyLedger(RecoveryLedger):
 """Preparation only: no provider effects are enabled by accounting freeze."""
 def count(self,*args,**kwargs):raise Error('accounting-only successor: model effects forbidden')
 def generate(self,*args,**kwargs):raise Error('accounting-only successor: model effects forbidden')
 def source(self,*args,**kwargs):raise Error('accounting-only successor: source effects forbidden')

class ModelOnlyLedger(RecoveryLedger):
 """P0 stage only after a separately reviewed frozen model contract."""
 def __init__(self,base,claim,parent,accounting_path,accounting_sha,verify_ticket,model_path,model_sha):
  super().__init__(base,claim,parent,accounting_path,accounting_sha,verify_ticket)
  self._model_path=Path(model_path);self._model_sha=model_sha
 def _guard(self):
  super()._guard()
  try:
   read(self._model_path,self._model_sha)
   if self.db.execute("SELECT reason FROM run_events WHERE event='p0_model_started'").fetchall()!=[(self._model_sha,)]:
    raise Error('p0 model stage binding drift')
  except BaseException:
   try:self.stop('p0 model contract drift')
   finally:self.poisoned=True
   raise
 def source(self,*args,**kwargs):raise Error('p0 model stage prohibits source effects')

def activate_model_stage(accounting,*,model_contract_path,expected_model_contract_sha256,verify_challenge):
 """Activate reviewed P0 only; caller separately verifies semantic inputs/scope.

 The callback must check independent witness, code, human decisions and exact
 snapshots, not merely return True. This wrapper is not a security boundary.
 """
 if not isinstance(accounting,AccountingOnlyLedger):raise Error('accounting-only ledger required')
 accounting._guard()
 raw=read(model_contract_path,expected_model_contract_sha256);model=obj(raw)
 if (model.get('schema')!='faithful-forecast-p0-model-contract-v1' or model.get('status')!='frozen' or
  model.get('caps')!=CAPS or model.get('accounting_contract_sha256')!=accounting._contract_sha or
  model.get('ledger_root')!=str(accounting.root) or model.get('starting_usage')!=accounting.summary() or
  model.get('source_reads')!=0):raise Error('p0 contract or starting state mismatch')
 if not callable(verify_challenge) or verify_challenge(raw) is not True:raise Error('independent p0 challenge required')
 db=accounting.db;db.execute('BEGIN IMMEDIATE')
 try:
  if accounting.summary()['stopped'] or db.execute("SELECT 1 FROM run_events WHERE event='p0_model_started'").fetchone() or db.execute('SELECT 1 FROM effects LIMIT 1').fetchone():
   raise Error('p0 already started or unexpected effects')
  db.execute("INSERT INTO run_events(event,reason,at_utc) VALUES ('p0_model_started',?,?)",(expected_model_contract_sha256,now_utc()))
  db.execute('COMMIT')
 except BaseException:
  if db.in_transaction:db.execute('ROLLBACK')
  raise
 return ModelOnlyLedger(accounting._base,read(CLAIM),accounting._parent,accounting._contract_path,
  accounting._contract_sha,accounting._verify_ticket,model_contract_path,expected_model_contract_sha256)

def _check_contract(path,expected_sha,verify_challenge):
 raw=read(path,expected_sha);contract=obj(raw);parent=inspect_stopped();cfgraw=read(ROOT/'forecast-stopped-successor-v1/ledger_contract.json')
 if (contract.get('schema')!='faithful-forecast-post400-contract-v1' or contract.get('status')!='frozen' or
   contract.get('caps')!=CAPS or contract.get('parent')!=parent or contract.get('ledger_contract_sha256')!=digest(cfgraw) or
   contract.get('prohibited_request_sha256')!=FAILED_REQUEST_SHA or
   contract.get('scope')!={'mode':'accounting_only','provider_effects':'forbidden'}):raise Error('recovery contract or parent mismatch')
 if not callable(verify_challenge) or verify_challenge(raw) is not True:raise Error('independent recovery challenge required')
 return parent,obj(cfgraw)

def create_successor(*,successor_root,claim_path,run_contract_path,expected_contract_sha256,verify_challenge,verify_ticket):
 parent,cfg=_check_contract(run_contract_path,expected_contract_sha256,verify_challenge)
 if not callable(verify_ticket):raise Error('source ticket verifier required')
 root=Path(successor_root);claim=Path(claim_path)
 if not root.is_absolute() or root.parent.resolve()!=root.parent.absolute() or root.exists() or claim!=CLAIM or claim.parent.resolve()!=claim.parent.absolute():raise Error('unsafe successor or claim path')
 claim_data=canonical({'schema':'faithful-forecast-post400-claim-v1','parent':parent,'ledger_root':str(root),'run_contract_sha256':expected_contract_sha256})
 fd=os.open(claim,os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,'O_NOFOLLOW',0),0o600)
 with os.fdopen(fd,'wb') as stream:stream.write(claim_data);stream.flush();os.fsync(stream.fileno())
 fd=os.open(claim.parent,os.O_RDONLY)
 try:os.fsync(fd)
 finally:os.close(fd)
 base=RecoveryBase(str(root),cfg,create=True)
 try:
  base.db.execute('BEGIN IMMEDIATE')
  base.db.execute("INSERT INTO run_events(event,reason,at_utc) VALUES ('forecast_started',?,?)",(expected_contract_sha256,now_utc()))
  base.db.execute('COMMIT')
  return AccountingOnlyLedger(base,claim_data,parent,run_contract_path,expected_contract_sha256,verify_ticket)
 except BaseException:
  if base.db.in_transaction:base.db.execute('ROLLBACK')
  base.close();raise

def reopen_successor(*,successor_root,claim_path,run_contract_path,expected_contract_sha256,verify_challenge,verify_ticket):
 parent,cfg=_check_contract(run_contract_path,expected_contract_sha256,verify_challenge)
 root=Path(successor_root);claim=Path(claim_path)
 if not callable(verify_ticket) or not root.is_absolute() or root.is_symlink() or root.resolve()!=root.absolute() or not root.is_dir() or claim!=CLAIM:raise Error('unsafe successor or claim')
 claim_data=read(claim)
 if claim_data!=canonical({'schema':'faithful-forecast-post400-claim-v1','parent':parent,'ledger_root':str(root),'run_contract_sha256':expected_contract_sha256}):raise Error('recovery claim mismatch')
 ro=reopen._ReadOnlyBase(root,cfg)
 try:f._check_resumable(ro,cfg,expected_contract_sha256)
 finally:ro.close()
 base=RecoveryBase(str(root),cfg,create=False)
 try:
  f._check_resumable(base,cfg,expected_contract_sha256)
  return AccountingOnlyLedger(base,claim_data,parent,run_contract_path,expected_contract_sha256,verify_ticket)
 except BaseException:base.close();raise
