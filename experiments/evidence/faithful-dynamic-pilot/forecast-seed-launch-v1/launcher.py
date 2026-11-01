"""Explicit seed-only model launcher; no network or credentials on import.

The frozen contract and independent read-only challenge are required before
any effect. This phase never performs source reads, confirms a thesis, chooses a
market, creates a p0 or retries a request. Actual model dispatch occurs only
inside execute(), via the governed shared ledger.
"""
from __future__ import annotations
import datetime as dt, hashlib, json, os, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
PACKETS=ROOT/'forecast-seed-packets-20261029-v3'
MANIFEST_SHA='98f4df0d19cf3b71cb8ba92d85c2831fed61eeb227e2b258fe5c90018fd480d4'
FILES=('forecast-seed-launch-v1/launcher.py','forecast-seed-launch-v1/historical.py','forecast-seed-launch-v1/historical_five.py',
 'forecast-controller-v1/exploration.py','forecast-controller-v1/forecast.py',
 'forecast-budget-v1/forecast_ledger.py','forecast-budget-v1/ledger_contract.json',
 'budget-v2/ledger.py','source-successor/bridge.py','source-successor/reopen.py',
 'source-successor/model_stage.py','model-accounting-successor/model_accounting.py',
 'transport/oneshot.py','model-launch/admission.py',
 'forecast-source-run-contract-20261029-v1.json','forecast-source-challenge-packet-v1.json',
 'forecast-source-challenge-receipt-v1.json','forecast-source-seed-20261029-01/summary.json',
 'forecast-source-seed-20261029-01/started.json',
 'forecast-source-seed-20261029-01/seed-anthropic-search.raw.json',
 'forecast-source-seed-20261029-01/seed-macro-news.raw.json',
 'forecast-source-seed-20261029-01/seed-openai-search.raw.json',
 'forecast-source-seed-20261029-01/seed-opec-fetch.raw.json',
 'forecast-source-you-20261029-01/started.json',
 'forecast-source-you-20261029-01/seed-openai-you-search.raw.json',
 'forecast-source-quotes-20261029.json','forecast-seed-packets-20261029-v3/manifest.json',
 'forecast-seed-packets-20261029-v2/manifest.json',
 'forecast-source-you-addendum-20261029-v1.json','forecast-you-challenge-packet-v1.json',
 'forecast-you-challenge-receipt-v1.json','forecast-source-you-20261029-01/summary.json',
 'forecast-you-price-20261029.json','forecast-budget-v1/you_phase.py',
 'forecast-seed-packets-20261029-v1/manifest.json',
 'dataset-draft-20261029/assembled-v2/manifest.json',
 'dataset-draft-20261029/assembled-v2/cases/case-02.json',
 'dataset-draft-20261029/assembled-v3/human/case-02-decision-line.json',
 'dataset-draft-20261029/assembled-v3/human/case-02-packet-line.json',
 'dataset-draft-20261029/assembled-v3/human/case-02-master-line.json')
FORBIDDEN=('KXCPI-26OCT-T0.2','KXGPT-ASTRA61-26NOV13','KXWTI-26NOV03-T97.99',
           'KXIPO-26-ANTHROPIC','When will OpenAI release Astra 6.1?',
           'Oil Price (WTI) on Election Day (November 3, 2026)?','Who will IPO before 2027?')
class Error(ValueError):pass
def sha(b):return hashlib.sha256(b).hexdigest()
def canonical(v):return json.dumps(v,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()
def read(p):
 p=Path(p)
 if not p.is_absolute() or p.is_symlink() or not p.is_file() or p.resolve()!=p.absolute():raise Error('unsafe evidence path')
 return p.read_bytes()
def obj(b):
 def pairs(xs):
  d={}
  for k,v in xs:
   if k in d:raise Error('duplicate key')
   d[k]=v
  return d
 try:x=json.loads(b,object_pairs_hook=pairs)
 except (ValueError,UnicodeDecodeError,TypeError):raise Error('invalid JSON') from None
 if not isinstance(x,dict):raise Error('JSON object required')
 return x
def put(path,value):
 raw=canonical(value);p=Path(path)
 if not p.is_absolute() or p.parent.resolve()!=p.parent.absolute():raise Error('unsafe output')
 fd=os.open(p,os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,'O_NOFOLLOW',0),0o600)
 try:
  with os.fdopen(fd,'wb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
 except BaseException:raise
 d=os.open(p.parent,os.O_RDONLY)
 try:os.fsync(d)
 finally:os.close(d)
def instant(x):
 try:r=dt.datetime.fromisoformat(x.replace('Z','+00:00'))
 except (ValueError,AttributeError):raise Error('bad timestamp') from None
 if r.utcoffset()!=dt.timedelta(0):raise Error('UTC required')
 return r
def pointer(value,path):
 if not isinstance(path,str) or not path.startswith('/'):raise Error('JSON pointer required')
 for token in path.split('/')[1:]:
  token=token.replace('~1','/').replace('~0','~')
  try:value=value[int(token)] if isinstance(value,list) else value[token]
  except (ValueError,IndexError,KeyError,TypeError):raise Error('JSON pointer unresolved') from None
 return value

def tasks(as_of_utc):
 """Create exact title-free model projections from verified source packets."""
 t=instant(as_of_utc);mraw=read(PACKETS/'manifest.json');m=obj(mraw)
 if sha(mraw)!=MANIFEST_SHA or m.get('schema')!='forecast-seed-packets-v1' or len(m.get('cases',[]))!=4:
  raise Error('seed manifest mismatch')
 if m.get('supersedes_manifest_sha256')!=sha(read(ROOT/'forecast-seed-packets-20261029-v2/manifest.json')):
  raise Error('seed predecessor mismatch')
 source_summary=obj(read(ROOT/m['source_summary_path']))
 if sha(read(ROOT/m['source_summary_path']))!=m['source_summary_sha256'] or source_summary.get('status')!='completed':
  raise Error('source completion mismatch')
 receipts={r['id']:r for r in source_summary['settled_records']}
 supplemental_raw=read(ROOT/m['supplemental_source_summary_path']);supplemental=obj(supplemental_raw)
 if sha(supplemental_raw)!=m['supplemental_source_summary_sha256'] or supplemental.get('status')!='completed':
  raise Error('supplemental source completion mismatch')
 receipts[supplemental['record']['id']]=supplemental['record']
 source_contract=obj(read(ROOT/'forecast-source-run-contract-20261029-v1.json'))
 requests={r['id']:r['payload'] for r in source_contract['source_phase']['requests']}
 you_addendum=obj(read(ROOT/'forecast-source-you-addendum-20261029-v1.json'))
 requests[you_addendum['operation']['id']]=you_addendum['operation']['payload']
 expected=[('case-01','development','seed-anthropic-search'),('case-02','diagnostic','seed-macro-news'),
           ('case-03','diagnostic','seed-openai-you-search'),('case-04','diagnostic','seed-opec-fetch')]
 output=[]
 for rec,(cid,split,op) in zip(m['cases'],expected):
  if (rec.get('case_id'),rec.get('split'),rec.get('source_effect_id'))!=(cid,split,op):raise Error('case sequence mismatch')
  card_raw=read(PACKETS/rec['input_path']);card=obj(card_raw)
  raw=read(ROOT/rec['raw_path']);source=obj(raw);receipt=receipts.get(op,{})
  if (sha(card_raw)!=rec['input_sha256'] or sha(raw)!=rec['raw_sha256'] or
   receipt.get('response_sha256')!=rec['raw_sha256'] or receipt.get('state')!='succeeded' or
   card.get('schema')!='forecast-seed-case-v1' or card.get('case_id')!=cid or card.get('split')!=split or
   len(card.get('evidence',[]))!=rec['evidence_count']):raise Error('case or raw binding mismatch')
  thought=card['thought'];origin=thought.get('origin')
  if cid=='case-01':
   if origin!='prior_user_approved' or thought.get('human_confirmed') is not True:raise Error('development approval missing')
   a=read(ROOT/'dataset-draft-20261029/assembled-v3/human/case-02-decision-line.json');approved=obj(a)
   old=obj(read(ROOT/'dataset-draft-20261029/assembled-v2/cases/case-02.json'))
   master=obj(read(ROOT/'dataset-draft-20261029/assembled-v3/human/case-02-master-line.json'))
   packet=obj(read(ROOT/'dataset-draft-20261029/assembled-v3/human/case-02-packet-line.json'))
   prior=[e['text'] for e in old['task']['initial_evidence'] if e.get('id')=='thesis']
   if (thought.get('acceptance_sha256')!=sha(a) or thought.get('text') not in prior or approved.get('final_verdict')!='approve'
     or master.get('canonical_human_approval')!=approved or master['canonical_proposal']['proposed_normalized_claim']['contractible_version']!=thought['text']
     or packet['normalized_claim']['contractible_version']!=thought['text']):raise Error('development human-thesis provenance mismatch')
  elif origin!='assistant_proposal_unaccepted' or thought.get('human_confirmed') is not False:
   raise Error('diagnostic input must remain unaccepted operator proposal')
  if not isinstance(thought.get('text'),str) or not thought['text'].strip():raise Error('thought missing')
  evidence=[]
  for e in card['evidence']:
   if e.get('source_effect_id')!=op or e.get('raw_sha256')!=sha(raw):raise Error('excerpt cross-binding')
   start=e.get('byte_offset');length=e.get('byte_length');text=e.get('text')
   if type(start) is not int or type(length) is not int or start<0 or length<=0 or not isinstance(text,str) or raw[start:start+length]!=text.encode():
    raise Error('excerpt raw offsets mismatch')
   value=pointer(source,e.get('json_pointer'))
   url=e.get('source_url');req=requests.get(op,{})
   url_bound=(isinstance(url,str) and (url in raw.decode('utf-8') or
     (req.get('path')=='/fetch' and req.get('body',{}).get('url')==url)))
   if not isinstance(value,str) or text not in value or not url_bound:
    raise Error('excerpt pointer or source URL mismatch')
   if e.get('published_at_utc') is not None:raise Error('this cohort has no verified publication times')
   if e.get('captured_at_utc')!=receipt['completed_at_utc'] or e.get('available_at_observed_utc')!=receipt['completed_at_utc'] or instant(e['captured_at_utc'])>t:
    raise Error('source availability mismatch')
   if not isinstance(e.get('source_type'),str) or not isinstance(e.get('validation_status'),str):raise Error('source attribution missing')
   source_label=e['source_type']+'; source '+e['source_url']+'; '+e['validation_status']
   if e.get('reported_date_literal'):source_label+='; provider-reported relative date: '+e['reported_date_literal']
   evidence.append({'id':e['id'],'text':text,'source':source_label,
      'available_at_utc':e['available_at_observed_utc'],'captured_at_utc':e['captured_at_utc']})
  projected={'case_id':cid,'thought':thought['text'],'thought_origin':origin,'as_of_utc':as_of_utc,
             'evidence':evidence,'market_leads':[]}
  alltext=canonical(projected).decode().casefold()
  if any(term.casefold() in alltext for term in FORBIDDEN):raise Error('known market title or ID leaked into seed')
  output.append({'case_id':cid,'split':split,'task':projected,'task_sha256':sha(canonical(projected)),
    'case_raw_sha256':sha(card_raw),'source_raw_sha256':sha(raw),'source_effect_id':op})
 return output

def components():
 m=obj(read(PACKETS/'manifest.json'))
 paths=set(FILES)
 for rec in m['cases']:
  paths.update((str((PACKETS/rec['input_path']).relative_to(ROOT)),rec['raw_path']))
 return {p:sha(read(ROOT/p)) for p in sorted(paths)}

def prepare_contract(path):
 """Offline create-only freeze; obtains no credentials and executes no calls."""
 if Path.cwd().resolve()!=ROOT:raise Error('artifact root cwd required')
 sys.path.insert(0,str(ROOT/'forecast-seed-launch-v1'))
 import historical_five
 parent=historical_five.verify()
 now=dt.datetime.now(dt.timezone.utc).isoformat()
 rows=tasks(now)
 output=ROOT/'forecast-exploration-seed-20261029-01'
 if output.exists():raise Error('seed result already exists')
 context={'artifact_root':str(ROOT),'cwd':str(ROOT),'ledger_root':str(ROOT/'forecast-live-ledger-20261029-01'),
          'output_root':str(output),'input_root':str(PACKETS)}
 c={'schema':'faithful-forecast-seed-model-contract-v1','status':'frozen',
    'caps':{'total_usd_micro':60000000,'total_generation_attempts':835,'total_count_attempts':767,'total_source_attempts':28},
    'scope':{'cases':4,'slots':8,'model':'gemini-3.8-flash','location':'global','max_calls_per_slot':6,
     'timeout_seconds_per_io':420,'retries':0,'source_reads':0,'seed_only':True,
     'human_acceptance_or_market_selection':False},
    'starting_usage':{'exposure_micro':1239590,'generation_attempts':200,'count_attempts':132,'source_attempts':13},
    'source_binding':parent,'as_of_utc':now,'task_bindings':rows,
    'component_bindings':components(),'execution_context':context,
    'limitations':['case-01 prior-approved development; other thoughts operator-proposed and unaccepted',
     'source excerpts curated after observing results; no blind semantic adjudication',
     'post-market discovery, human thesis acceptance, and prospective forecast are not this phase']}
 put(path,c);raw=read(path)
 return {'contract_sha256':sha(raw),'source_binding':parent,'case_ids':[r['case_id'] for r in rows]}

def verify(contract_path,challenge_path,receipt_path,expected_contract_sha256):
 """Read-only complete binding check; no project imports or credentials."""
 cr,pr,rr=map(read,(contract_path,challenge_path,receipt_path));c,p,r=map(obj,(cr,pr,rr))
 d=p.get('internal_digest');w=p.get('context_binding',{})
 if (sha(cr)!=expected_contract_sha256 or c.get('schema')!='faithful-forecast-seed-model-contract-v1' or c.get('status')!='frozen'
  or p.get('schema_version')!='eval_contract_challenge_packet_v1' or p.get('overall_state')!='ready'
  or p.get('witness',{}).get('identity')!='seed_model_witness' or p.get('witness',{}).get('mode')!='read_only_offline'
  or p.get('challenged_contract',{}).get('raw_sha256')!=sha(cr) or d!=sha(canonical({k:v for k,v in p.items() if k!='internal_digest'}))
  or r.get('packet_raw_sha256')!=sha(pr) or r.get('packet_byte_count')!=len(pr) or r.get('packet_internal_digest')!=d or r.get('state')!='ready'):
  raise Error('seed model challenge mismatch')
 components_bound=c.get('component_bindings');observed=w.get('code_bindings_at_inspection')
 if not isinstance(components_bound,dict) or components_bound!=components() or not isinstance(observed,dict):raise Error('component binding mismatch')
 for rel,h in components_bound.items():
  b=read(ROOT/rel)
  if observed.get(rel)!={'sha256':h,'size':len(b)}:raise Error('independent component mismatch')
 context=c.get('execution_context',{})
 if context!=w.get('execution_context') or context.get('cwd')!=str(Path.cwd().resolve()) or context.get('artifact_root')!=str(ROOT):
  raise Error('seed execution context mismatch')
 if c.get('task_bindings')!=tasks(c['as_of_utc']) or w.get('task_bindings')!=c.get('task_bindings') or w.get('source_binding')!=c.get('source_binding'):
  raise Error('seed inputs or source witness mismatch')
 if c.get('caps')!={'total_usd_micro':60000000,'total_generation_attempts':835,'total_count_attempts':767,'total_source_attempts':28}:
  raise Error('global caps mismatch')
 if c.get('scope')!={'cases':4,'slots':8,'model':'gemini-3.8-flash','location':'global','max_calls_per_slot':6,
     'timeout_seconds_per_io':420,'retries':0,'source_reads':0,'seed_only':True,'human_acceptance_or_market_selection':False}:
  raise Error('seed scope mismatch')
 return {'contract':c,'contract_raw':cr,'challenge_raw':pr,'receipt_raw':rr,'paths':(Path(contract_path),Path(challenge_path),Path(receipt_path))}

def execute(contract_path,challenge_path,receipt_path,expected_contract_sha256):
 """Explicit LIVE model operation. Four cases, one C and one B each."""
 ctx=verify(contract_path,challenge_path,receipt_path,expected_contract_sha256);c=ctx['contract']
 for d in ('forecast-seed-launch-v1','forecast-controller-v1','forecast-budget-v1','budget-v2',
           'source-successor','model-accounting-successor','transport'):
  sys.path.insert(0,str(ROOT/d))
 import historical_five,exploration,forecast_ledger
 from ledger import Stop
 from oneshot import OneShotTransport
 if historical_five.verify()!=c['source_binding']:raise Error('historical source evidence drift')
 output=Path(c['execution_context']['output_root'])
 if output.exists():raise Error('output already exists')
 for row in c['task_bindings']:exploration.prepare_task(row['task'])
 # Historical verification checked the old quote only at each old effect's
 # start. No source operations are authorized by this model-only phase.
 old_contract=read(ROOT/'forecast-source-run-contract-20261029-v1.json')
 def challenge_old(raw):return raw==old_contract
 def deny_source(*args):return False
 ledger=forecast_ledger.reopen_successor(successor_root=c['execution_context']['ledger_root'],
    claim_path=str(forecast_ledger.CLAIM),ledger_contract_path=str(ROOT/'forecast-budget-v1/ledger_contract.json'),
    run_contract_path=str(ROOT/'forecast-source-run-contract-20261029-v1.json'),
    expected_contract_sha256=historical_five.SOURCE_SHA,verify_challenge=challenge_old,verify_ticket=deny_source)
 try:
  if ledger.summary()!= {'stopped':0,'exposure_micro':1239590,'generation_attempts':200,'count_attempts':132,
       'source_attempts':13,'metadata_attempts':0,'metadata_retained_micro':0,'previous_source_attempts':8}:
   raise Error('starting shared ledger counts changed')
  # Resolve/refresh ADC only after reviewed scope and source lineage, and before
  # consuming the one-shot marker. This is authentication, not a model call.
  import google.auth
  from google.auth.transport.requests import Request
  creds,project=google.auth.default(scopes=['https://www.googleapis.com/auth/cloud-platform'])
  if not project:raise Error('project unavailable')
  if not creds.valid:creds.refresh(Request())
  if not creds.token:raise Error('credential unavailable')
  ledger.db.execute('BEGIN IMMEDIATE')
  try:
   if ledger.db.execute("SELECT 1 FROM run_events WHERE event='exploration_seed_started'").fetchone():raise Error('seed model stage already started')
   if ledger.db.execute("SELECT 1 FROM effects WHERE kind IN ('count','generation') LIMIT 1").fetchone():raise Error('model effects already present')
   ledger.db.execute("INSERT INTO run_events(event,reason,at_utc) VALUES ('exploration_seed_started',?,?)",(expected_contract_sha256,dt.datetime.now(dt.timezone.utc).isoformat()))
   ledger.db.execute('COMMIT')
  except BaseException:
   if ledger.db.in_transaction:ledger.db.execute('ROLLBACK')
   raise
  output.mkdir(mode=0o700)
  def persist(name,value):
   try:put(output/name,value)
   except BaseException:
    try:ledger.stop('seed artifact persistence failed')
    finally:ledger.poisoned=True
    raise
  persist('started.json',{'contract_sha256':sha(ctx['contract_raw']),'challenge_sha256':sha(ctx['challenge_raw']),
                          'receipt_sha256':sha(ctx['receipt_raw']),'case_ids':[x['case_id'] for x in c['task_bindings']]})
  # No token or project ID is persisted.
  def token(provider):
   if provider!='vertex':raise Error('source calls prohibited')
   if not creds.valid:creds.refresh(Request())
   if not creds.token:raise Error('credential unavailable')
   return creds.token
  transport=OneShotTransport(project,token)
  def guarded(provider,endpoint,raw):
   if provider!='vertex':raise Error('source calls prohibited')
   if tuple(read(p) for p in ctx['paths'])!=(ctx['contract_raw'],ctx['challenge_raw'],ctx['receipt_raw']):
    ledger.stop('seed contract drift');raise Error('contract drift')
   if components()!=c['component_bindings']:
    ledger.stop('seed component drift');raise Error('component drift')
   return transport(provider,endpoint,raw)
  results=[];stopped=None
  for i,row in enumerate(c['task_bindings']):
   counts={}
   def make_generator(arm):
    counts[arm]=0
    def call(stage,payload):
     counts[arm]+=1;identity=f"seed:{row['case_id']}:{arm}:{counts[arm]:02d}"
     request=exploration.build_request(stage,payload)
     ledger.count('count:'+identity,request,guarded)
     raw=ledger.generate('generation:'+identity,request,'count:'+identity,guarded)
     return exploration.parse_response(json.loads(raw))
    return call
   pair={'case_id':row['case_id'],'split':row['split'],'task_sha256':row['task_sha256']}
   try:
    persist(f'{i:02d}-c-started.json',{'case_id':row['case_id'],'arm':'c'})
    cc=exploration.FaithfulEngine(make_generator('c'),max_calls=6).run(row['task'])
    persist(f'{i:02d}-c.json',cc);pair['c']=cc
    n=cc.get('calls')
    if type(n) is int and 1<=n<=6:
     persist(f'{i:02d}-b-started.json',{'case_id':row['case_id'],'arm':'b','matched_calls':n})
     bb=exploration.BaselineEngine(make_generator('b'),matched_calls=n).run(row['task'])
    else:bb={'status':'unavailable','reason':'c_zero_or_invalid_call_count','calls':0}
    persist(f'{i:02d}-b.json',bb);pair['b']=bb
   except Stop as exc:
    pair['status']='stopped';pair['error_type']=type(exc).__name__;stopped=i
   except Exception as exc:
    pair['status']='technical_failure';pair['error_type']=type(exc).__name__
    if ledger.summary()['stopped']:stopped=i
   persist(f'{i:02d}-pair.json',pair);results.append(pair)
   if stopped is not None:break
  summary={'requested_cases':4,'attempted_cases':len(results),'not_attempted_cases':4-len(results),
           'stop_index':stopped,'ledger':ledger.summary(),'results':results,
           'status':'seed_proposals_only','review':'not human-adjudicated','post_market':'not started'}
  persist('summary.json',summary);return summary
 finally:ledger.close()
