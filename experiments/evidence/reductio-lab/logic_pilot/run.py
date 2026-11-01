"""Pre-registered 8-case synthetic SI vs baseline pilot; single-shot ledger."""
from __future__ import annotations
import copy,hashlib,importlib,importlib.metadata,json,sqlite3,sys,time
from pathlib import Path
from logic_pilot.corpus import corpus,canonical,digest,SEED
from reasoning_engine.engine import EngineConfig,prepare_task
from reasoning_engine.baseline import _branch
from reasoning_engine.vertex_adapter import VertexAdapter,build_generation_request,canonical_json
from faithful_v3.engine import StrictEngine
from faithful_v3.prompts import bind_model
from research.retry_facade import RetryFacade,ledger_class
from research import live_run as legacy
from live_c3 import run as previous
from resume40.resume40_executor import save_new

HERE=Path(__file__).resolve().parents[1]; BASE=HERE.parent
RUN=BASE/'reasoning-synthetic-si-live-20261029-v1'

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def make_contract():
 old=previous.validate()
 prior=previous.RUN/'ledger/ledger.sqlite3'; state, pending=previous.ledger_data(prior)
 summary=json.loads((previous.RUN/'summary.json').read_bytes())
 if state!=(0,52194204,848,773,0) or pending or summary['recorded']!=12 or summary['ledger']['exposure_micro']!=state[1]: raise ValueError('previous cumulative head invalid')
 tasks,keys=corpus()
 if len(tasks)!=8 or len(keys)!=8 or len({x['case_id'] for x in tasks})!=8:raise ValueError('corpus scope invalid')
 # Do not include the key or outcome labels in the model-visible task.
 expected={x['case_id'] for x in tasks}
 if expected!={x['case_id'] for x in keys}:raise ValueError('key identity mismatch')
 import random
 schedule=[{'case_id':t['case_id'],'arm':a} for t in tasks for a in ('B','B_self','C')]
 random.Random(SEED+1111).shuffle(schedule)
 cfg=dict(old['config']);cfg.update(run_id='synthetic-si-pilot-20261029-v1',prior_micro=state[1],prior_generations=state[2],prior_counts=state[3],max_generations=1072,max_counts=1001,cap_micro=60000000)
 if (cfg['model'],cfg['location'],cfg['output_reserve'])!=('gemini-3.8-flash','global',66056):raise ValueError('provider or reserve drift')
 code=set(legacy.module_paths())
 for d in ('faithful_v3','logic_pilot','live_c3','resume40','report40','successor_analysis'):
  code.update((HERE/d).glob('*.py'))
 return {'schema':'synthetic-si-pilot-contract-v1','model':cfg['model'],'location':cfg['location'],
  'scope':'8 paired open development items, 4 matched pairs, binary targets, four entailment steps and 16 or 32 distractors; not holdout',
  'cases':[x['case_id'] for x in tasks],'task_sha256':digest(tasks),'answer_key_sha256':digest(keys),'schedule':schedule,
  'baseline':'B full-task single answer; B_self independently generated full-task answer followed by one self-review',
  'si':'StrictEngine with one alternative, at most two selected premises, beam one and max depth four; selection prompt explicitly requests these limits; model roles retained',
  'si_config':{'max_calls':17,'max_depth':4,'beam_width':1,'max_alternatives':1},
  'max_role_calls_by_arm':{'B':1,'B_self':2,'C':17},'max_logical_calls':160,'max_429_retries':19,
  'max_new_generation_attempts':179,'max_new_count_attempts':179,
  'model_call_limit':1072,'count_limit':1001,'generation_prior':848,'count_prior':773,
  'cap_micro':60000000,'prior_micro':52194204,'reserve_micro':519996,'reserve_is_hard_provider_cap':False,
  'config':cfg,'retry':'at most one exact-byte retry only after captured confirmed 429; 19 extra attempts global',
  'uncertain_retry':False,'on_uncertain':'stop entire run and preserve reservation',
  'timeout_seconds':420,'source_provider_calls':0,'keys_visible_to_model':False,
  'assessment':'separate formal key and independent source-only response review; failures and unknown included; exposed author-generated pilot not confirmatory',
  'input_and_run_lineage':{'predecessor_contract_sha256':sha(previous.RUN/'contract.json'),
    'predecessor_challenge_sha256':sha(previous.RUN/'challenge.json'), 'predecessor_summary_sha256':sha(previous.RUN/'summary.json'),
    'predecessor_ledger_sha256':sha(prior),'historical_old_ledger_sha256':{k:v['sha256'] for k,v in old['prior_ledgers'].items()},
    'forbidden_uncertain_request_hashes':old['forbidden_predecessor_request_hashes']},
  'code_sha256':{str(x.resolve()):sha(x) for x in sorted(code)},
  'runtime':{'python':sys.version.split()[0],'httpx':importlib.metadata.version('httpx'),'google_auth':importlib.metadata.version('google-auth'),'sqlite':sqlite3.sqlite_version}}

def prepare():
 if RUN.exists() or RUN.is_symlink() or RUN.parent.resolve()!=RUN.parent.absolute():raise ValueError('unsafe or existing run')
 c=make_contract();tasks,keys=corpus();RUN.mkdir(mode=0o700)
 save_new(RUN/'tasks.json',tasks);save_new(RUN/'answer-key.json',keys);save_new(RUN/'contract.json',c)
 print('prepared contract',sha(RUN/'contract.json'),flush=True)

def validate():
 frozen=json.loads((RUN/'contract.json').read_bytes())
 if canonical(frozen)!=canonical(make_contract()):raise ValueError('contract/previous/runtime drift')
 tasks,keys=corpus()
 if json.loads((RUN/'tasks.json').read_bytes())!=tasks or json.loads((RUN/'answer-key.json').read_bytes())!=keys:raise ValueError('corpus or key drift')
 challenge=json.loads((RUN/'challenge.json').read_bytes())
 if (challenge.get('status')!='ready' or challenge.get('mode')!='independent_offline_code_review'
     or challenge.get('contract_sha256')!=sha(RUN/'contract.json')
     or challenge.get('reviewed_code_sha256')!=digest(frozen['code_sha256'])
     or challenge.get('blockers')!=[] or not challenge.get('reviewer')):
  raise ValueError('bound offline challenge missing or has blockers')
 return frozen

def execute():
 f=validate()
 if any((RUN/x).exists() for x in ('dispatch.json','ledger','summary.json')) or list(RUN.glob('*.outcome.json')):raise ValueError('already dispatched')
 tasks,_=corpus();by_case={x['case_id']:x for x in tasks}
 import google.auth
 from google.auth.transport.requests import Request
 creds,project=google.auth.default(scopes=['https://www.googleapis.com/auth/cloud-platform'])
 if not project or hashlib.sha256(project.encode()).hexdigest()!=legacy.PROJECT_SHA:raise ValueError('provider project mismatch')
 sys.path.insert(0,str(legacy.OLD/'forecast-p1-budget-successor-v1'));sys.path.insert(0,str(legacy.OLD/'transport'))
 retry=importlib.import_module('p1_retry');oneshot=importlib.import_module('oneshot');retry.MAX_EXTRA=19
 def token(provider):
  if provider!='vertex':raise ValueError('provider denied')
  if not creds.valid:creds.refresh(Request())
  if not creds.token:raise ValueError('token missing')
  return creds.token
 transport=oneshot.OneShotTransport(project,token)
 save_new(RUN/'dispatch.json',{'contract_sha256':sha(RUN/'contract.json'),'challenge_sha256':sha(RUN/'challenge.json'),'mode':'single_shot'})
 base=ledger_class(retry,f['config'])(str(RUN/'ledger'),f['config'],create=True)
 facade=RetryFacade(base,retry);forbidden=set(f['input_and_run_lineage']['forbidden_uncertain_request_hashes']);last_end=0.0
 def guard(provider,endpoint,raw):
  nonlocal last_end
  if provider!='vertex' or endpoint not in ('countTokens','gemini-3.8-flash@global'):raise ValueError('endpoint denied')
  if hashlib.sha256(raw).hexdigest() in forbidden:base.stop('prior uncertain request forbidden');raise ValueError('prior uncertain bytes')
  validate()
  delay=1.0-(time.monotonic()-last_end)
  if delay>0:time.sleep(delay)
  try:return transport(provider,endpoint,raw)
  finally:last_end=time.monotonic()
 adapter=VertexAdapter(facade,guard);records=[];last_failure=None
 try:
  for idx,item in enumerate(f['schedule'],1):
   if base.summary()['stopped'] or base.poisoned:break
   cid,arm=item['case_id'],item['arm'];task=by_case[cid];prepared=prepare_task(task)
   slot=hashlib.sha256(canonical({'case_id':cid,'arm':arm,'protocol':'synthetic-pilot-v1'})).hexdigest()
   role_calls=[];ordinal=0
   def requester(request):
    nonlocal ordinal
    ordinal+=1
    if ordinal>f['max_role_calls_by_arm'][arm]:raise ValueError('role call cap')
    req=copy.deepcopy(request)
    if arm=='C' and req['stage']=='selection':
     req['instruction']+=' Return exactly one alternative in the alternatives array, selecting at most two available statement IDs.'
     req['prompt_version']+='-synthetic-single-alternative-v1'
    raw=canonical_json(build_generation_request(req));raw_hash=hashlib.sha256(raw).hexdigest()
    if raw_hash in forbidden:base.stop('prior uncertain request forbidden');raise ValueError('prior uncertain bytes')
    op=f'{slot}:{arm}:{ordinal:03d}'; rec={'ordinal':ordinal,'stage':req['stage'],'operation_id':op,'request_sha256':raw_hash}
    role_calls.append(rec)
    try:
     result=adapter.complete(req,operation_id=op).content
     if arm=='C' and req['stage']=='selection':
      alts=result.get('alternatives')
      if not isinstance(alts,list) or len(alts)!=1 or not isinstance(alts[0],list) or not 1<=len(alts[0])<=2:raise ValueError('SI selection must contain one alternative with one or two premise IDs')
     return result
    finally:
     rec['effects']=[{'id':a,'kind':b,'state':c,'http_status':d,'response_sha256':e,'actual_micro':g,'quote_micro':h} for a,b,c,d,e,g,h in base.db.execute('select id,kind,state,http_status,response_hash,actual_micro,quote_micro from effects where id in (?,?,?,?) order by rowid',('count:'+op,'count:'+op+'~retry1','generation:'+op,'generation:'+op+'~retry1')).fetchall()]
   model=bind_model(requester)
   if arm=='C':out=StrictEngine(model,EngineConfig(**f['si_config'])).run(task)
   else:out=_branch(arm,prepared,model,self_check=arm=='B_self')
   unsettled=any(e['state'] in ('started','prepared','uncertain') or (e['state']=='succeeded' and e['actual_micro'] is None) for call in role_calls for e in call.get('effects',[]))
   packet={'schema':'synthetic-si-outcome-v1','case_id':cid,'arm':arm,'task_sha256':prepared['input_sha256'],'outcome':out,'calls':role_calls,'unsettled_effect':unsettled}
   h=save_new(RUN/(slot+'.outcome.json'),packet)
   records.append({'case_id':cid,'arm':arm,'slot':slot,'status':out['status'],'reason':out.get('reason'),'model_role_calls':ordinal,'outcome_sha256':h,'unsettled_effect':unsettled})
   print(f'{idx}/24 {cid} {arm}: {out["status"]}; calls={ordinal}; exposure=${base.summary()["exposure_micro"]/1e6:.6f}',flush=True)
   if unsettled or base.summary()['stopped'] or base.poisoned:break
   failure=out.get('reason') if out['status']=='technical_failure' else None
   if failure and failure==last_failure and 'RateLimit' not in failure:base.stop('repeated technical failure');break
   last_failure=failure
  summary={'status':'completed_unreviewed' if len(records)==24 else 'incomplete','total':24,'recorded':len(records),'records':records,'ledger':base.summary(),'semantic_review':'pending','automatic_resume':False}
  save_new(RUN/'summary.json',summary);return summary
 except BaseException:
  if not base.summary()['stopped']:base.stop('interrupted, no auto resume')
  if not (RUN/'summary.json').exists():save_new(RUN/'summary.json',{'status':'incomplete','total':24,'recorded':len(records),'records':records,'ledger':base.summary(),'automatic_resume':False})
  raise
 finally:base.close()

if __name__=='__main__':
 if sys.argv[1:]==['prepare']:prepare()
 elif sys.argv[1:]==['execute']:print(json.dumps(execute(),ensure_ascii=False))
 elif sys.argv[1:]==['inspect']:print(json.dumps(make_contract(),ensure_ascii=False))
 else:raise SystemExit('Use inspect, prepare, execute')
