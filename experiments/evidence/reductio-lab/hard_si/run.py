"""Frozen 12-case SI study with five arms and bounded premise interventions."""
from __future__ import annotations
import copy,hashlib,importlib,importlib.metadata,json,random,sqlite3,sys,time
from pathlib import Path
from hard_si.corpus import build,canonical,digest,SEED
from hard_si.runtime import Adapter,generation_request,ledger_type
from reasoning_engine.engine import EngineConfig,prepare_task
from reasoning_engine.baseline import _branch,_format_problem,_coverage
from reasoning_engine.vertex_adapter import canonical_json
from faithful_v3.engine import StrictEngine
from faithful_v3.prompts import bind_model
from research.retry_facade import RetryFacade
from research import live_run as legacy
from live_c3 import run as old
from logic_repair import run as predecessor
from resume40.resume40_executor import save_new

HERE=Path(__file__).resolve().parents[1];BASE=HERE.parent
RUN=BASE/'reasoning-hard-si-20261029-v1'
ARMS=('B_low','B_medium','B_self','C','B_budget')
LIMITS={'B_low':1,'B_medium':1,'B_self':2,'B_budget':20,'C':43}
LEVELS={'B_low':'LOW','B_medium':'MEDIUM','B_self':'MEDIUM','B_budget':'MEDIUM','C':'LOW'}

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def contract():
 prev=predecessor.validate(); prior=predecessor.RUN/'ledger/ledger.sqlite3'
 state,pending=old.ledger_data(prior);summary=json.loads((predecessor.RUN/'summary.json').read_bytes())
 if state!=(0,52675629,1062,986,0) or pending or summary.get('recorded')!=9 or summary.get('status')!='completed_unreviewed' or summary['ledger']['exposure_micro']!=state[1]:raise ValueError('previous head invalid')
 records=summary.get('records',[]);wanted={(x['case_id'],x['arm']) for x in prev['schedule']}
 if len(records)!=9 or len({(x['case_id'],x['arm']) for x in records})!=9 or {(x['case_id'],x['arm']) for x in records}!=wanted:raise ValueError('predecessor schedule mismatch')
 for rec in records:
  p=predecessor.RUN/(rec['slot']+'.outcome.json');obj=json.loads(p.read_bytes())
  if sha(p)!=rec['outcome_sha256'] or (obj['case_id'],obj['arm'])!=(rec['case_id'],rec['arm']):raise ValueError('predecessor outcome mismatch')
 tasks,keys,pairs=build()
 if len(tasks)!=12 or len(keys)!=12 or len(pairs)!=6 or len({x['case_id'] for x in tasks})!=12:raise ValueError('corpus scope error')
 # Fixed per-case schedule: all four methods are shuffled, B_budget always after C.
 ordered=list(tasks);random.Random(SEED+7777).shuffle(ordered);schedule=[]
 for task in ordered:
  arms=['B_low','B_medium','B_self','C'];random.Random(SEED+int(task['case_id'][-8:],16)).shuffle(arms)
  schedule.extend({'case_id':task['case_id'],'arm':a} for a in arms+['B_budget'])
 if len(schedule)!=60 or len({(x['case_id'],x['arm']) for x in schedule})!=60:raise ValueError('invalid schedule')
 cfg=dict(prev['config']);cfg.update(run_id='hard-si-20261029-v1',prior_micro=state[1],prior_generations=state[2],prior_counts=state[3],max_generations=1910,max_counts=1834,cap_micro=60000000)
 if (cfg['model'],cfg['location'],cfg['output_reserve'],cfg['input_limit'])!=('gemini-3.8-flash','global',66056,16384):raise ValueError('model or token envelope drift')
 code=set(legacy.module_paths())
 for d in ('faithful_v3','logic_pilot','logic_repair','live_c3','resume40','report40','successor_analysis','hard_si'):
  code.update((HERE/d).glob('*.py'))
 baseline=old.contract()
 return {'schema':'hard-si-contract-v1','case_count':12,'pair_count':6,'arms':list(ARMS),'schedule':schedule,
  'model':'gemini-3.8-flash','location':'global','thinking_levels':LEVELS,'role_call_limits':LIMITS,
  'si_config':{'max_calls':43,'max_depth':6,'beam_width':1,'max_alternatives':2},
  'proof_observations':'one or two selected IDs per inference; recorded ancestry is not proof of entailment',
  'budget_baseline':'independent MEDIUM answer then repeat own recheck while accumulated settled generation micro < same-case C settled generation micro, up to 20 calls; one-call overshoot allowed; never see C response or key',
  'cases':[x['case_id'] for x in tasks],'task_sha256':digest(tasks),'answer_key_sha256':digest(keys),'pairs_sha256':digest(pairs),
  'interventions':{'case_ids':pairs[0]['case_ids'],'selector':'first recorded SI inference using the key terminal rule and a second premise containing that rule antecedent; missing becomes unavailable',
    'operation':'two LOW inference calls: exact selected premises, then same premises with terminal authorization polarity reversed; fixed instruction; not a replay of uncertain request',
    'calls_max':4,'interpretation':'sensitivity of the output to edited input, not proof of latent faithfulness'},
  'counts':{'logical_generations_max':808,'global_confirmed_429_retry_max':40,'new_generation_attempt_max':848,'new_count_attempt_max':848,
            'previous_generation_attempts':1062,'previous_count_attempts':986,'cumulative_generation_limit':1910,'cumulative_count_limit':1834},
  'budget':{'cumulative_cap_micro':60000000,'prior_exposure_micro':52675629,'reserve_micro_per_generation':519996,
            'reserve_is_hard_provider_cap':False,'invoice':'unverified','previous_uncertain_reserves_retained':True},
  'config':cfg,'retry_policy':'at most one exact retry after captured confirmed 429, global extra attempts <= 40; no retry uncertain',
  'timeout_seconds':420,'source_provider_calls':0,'review':'case/arm outcome-blind semantic review; automated truth key not a human golden; 6 pair clusters, exploratory',
  'lineage':{'predecessor_contract_sha256':sha(predecessor.RUN/'contract.json'),'predecessor_challenge_sha256':sha(predecessor.RUN/'challenge.json'),
   'predecessor_summary_sha256':sha(predecessor.RUN/'summary.json'),'predecessor_ledger_sha256':sha(prior),
   'old_ledger_sha256':{k:v['sha256'] for k,v in baseline['prior_ledgers'].items()},
   'other_ledger_sha256':{str(old.RUN/'ledger/ledger.sqlite3'):sha(old.RUN/'ledger/ledger.sqlite3'), str(predecessor.predecessor.RUN/'ledger/ledger.sqlite3'):sha(predecessor.predecessor.RUN/'ledger/ledger.sqlite3')},
   'forbidden_uncertain_request_hashes':baseline['forbidden_predecessor_request_hashes']},
  'code_sha256':{str(p.resolve()):sha(p) for p in sorted(code)},
  'runtime':{'python':sys.version.split()[0],'httpx':importlib.metadata.version('httpx'),'google_auth':importlib.metadata.version('google-auth'),'sqlite':sqlite3.sqlite_version}}

def prepare():
 if RUN.exists() or RUN.is_symlink() or RUN.parent.resolve()!=RUN.parent.absolute():raise ValueError('unsafe or existing run')
 f=contract();tasks,keys,pairs=build();RUN.mkdir(mode=0o700)
 save_new(RUN/'tasks.json',tasks);save_new(RUN/'answer-key.json',keys);save_new(RUN/'pairs.json',pairs);save_new(RUN/'contract.json',f)
 print('prepared contract',sha(RUN/'contract.json'),flush=True)

def validate():
 frozen=json.loads((RUN/'contract.json').read_bytes())
 if canonical(frozen)!=canonical(contract()):raise ValueError('contract/runtime/predecessor drift')
 tasks,keys,pairs=build()
 for fn,value in (('tasks.json',tasks),('answer-key.json',keys),('pairs.json',pairs)):
  if json.loads((RUN/fn).read_bytes())!=value:raise ValueError('frozen corpus mismatch')
 challenge=json.loads((RUN/'challenge.json').read_bytes())
 if (challenge.get('status')!='ready' or challenge.get('mode')!='independent_offline_code_review' or challenge.get('blockers')!=[]
  or challenge.get('contract_sha256')!=sha(RUN/'contract.json') or challenge.get('reviewed_code_sha256')!=digest(frozen['code_sha256'])
  or not challenge.get('reviewer')):raise ValueError('independent challenge invalid')
 return frozen

def gate_files(f,frozen_sha,challenge_sha,corpus_shas):
 # Only bound immutable files are reread here; do not re-hash prior dynamic temp files.
 if sha(RUN/'contract.json')!=frozen_sha or sha(RUN/'challenge.json')!=challenge_sha:raise ValueError('contract/challenge drift')
 for fn,h in corpus_shas.items():
  if sha(RUN/fn)!=h:raise ValueError('corpus drift')
 if sha(predecessor.RUN/'ledger/ledger.sqlite3')!=f['lineage']['predecessor_ledger_sha256'] or sha(predecessor.RUN/'summary.json')!=f['lineage']['predecessor_summary_sha256']:raise ValueError('predecessor drift')
 for name,h in f['lineage']['old_ledger_sha256'].items():
  if sha(BASE/name/'ledger/ledger.sqlite3')!=h:raise ValueError('historical ledger drift')
 for path,h in f['lineage']['other_ledger_sha256'].items():
  if sha(path)!=h:raise ValueError('historical successor ledger drift')
 for path,h in f['code_sha256'].items():
  if sha(path)!=h:raise ValueError('code drift')

def _step_prompt(req,arm):
 req=copy.deepcopy(req)
 if arm=='C' and req['stage']=='selection':
  req['instruction']+=' Return at most two alternatives; each alternative contains one or two available IDs.'
  req['prompt_version']+='-hard-si-v1'
 if arm=='C' and req['stage']=='halter':
  req['instruction']+=(' Judge semantic answerability independently of YES/NO label or explanation; output formatting occurs later. '
      'A bare unambiguous authorization or non-authorization conclusion is sufficient. '
      'Do not accept a no-proof claim solely because selected premises omit other statements.')
  req['prompt_version']+='-hard-si-v1'
 if arm=='C' and req['stage']=='formatter':
  req['instruction']+=(' If the final inference states authorization, start the answer YES; if it states non-authorization, start NO. '
      'Render only the final inference. The selected trace is presented separately.')
  req['prompt_version']+='-hard-si-v1'
 return req

def _allowed(prepared):
 ids={x['id'] for x in prepared['evidence']}
 if 'thesis' in prepared:ids.add('input:thesis')
 return ids,{x['id'] for x in prepared['required_questions']}

def budget_baseline(prepared,generate,spent,target):
 """Own-answer rechecks until actual reported C spend is reached; max 20 calls."""
 history=[];last=None;problem=None
 allowed,questions=_allowed(prepared)
 for i in range(20):
  if i and spent()>=target:break
  stage='baseline_initial' if i==0 else 'baseline_recheck'
  payload=copy.deepcopy(prepared) if i==0 else {'prepared_task':copy.deepcopy(prepared),'previous_response':copy.deepcopy(last)}
  try:raw=generate(stage,copy.deepcopy(payload))
  except Exception as exc:
   history.append({'stage':stage,'payload':payload,'error':type(exc).__name__});problem='callback_failed:'+type(exc).__name__;break
  history.append({'stage':stage,'payload':payload,'response':copy.deepcopy(raw)})
  problem=_format_problem(raw,allowed,questions)
  if problem:break
  last=copy.deepcopy(raw)
 status='technical_failure' if problem else ('completed' if all(x['status']=='assessed' for x in _coverage(prepared,last)) else 'incomplete')
 return {'branch':'B_budget','status':status,'reason':problem or 'model_proposal_requires_semantic_review',
         'calls':len(history),'responses':history,'final_result':None if problem else last,'semantic_status':'unreviewed',
         'target_c_micro':target,'reported_spend_micro':spent(),'match_rule':'stop after reaching C spend or 20 calls; one-call overshoot possible'}

def _intervention_payload(outcome,key):
 """Locate first matching actual SI call solely by recorded selected IDs and text."""
 events=outcome.get('events',[]);rule_id=key['terminal_rule_id'];source=key['terminal_text'];ante=key['terminal_condition']
 # Branch records repeat shared ancestors. Index by inference ordinal so each
 # actual model call is considered once, in execution order.
 steps_by_ordinal={}
 for branch in outcome.get('branches',[]):
  for step in branch.get('steps',[]):
   ordinal=step.get('inference_call_ordinal')
   if type(ordinal) is int and ordinal > 0:
    steps_by_ordinal.setdefault(ordinal,step)
 for ordinal,step in sorted(steps_by_ordinal.items()):
  selected=step.get('selected_ids')
  if not isinstance(selected,list):continue
  if len(selected)!=2 or rule_id not in selected:continue
  ev=next((e for e in events if e.get('event')=='model_started' and e.get('stage')=='inference' and e.get('ordinal')==ordinal),None)
  if not ev:continue
  payload=copy.deepcopy(ev['payload']);texts=payload.get('selected_texts',[])
  matches=[i for i,x in enumerate(texts) if x.get('text')==source]
  if len(matches)!=1 or len(texts)!=2:continue
  idx=matches[0];other=texts[1-idx]
  if ante not in other.get('text',''):continue
  mod=copy.deepcopy(payload);text=mod['selected_texts'][idx]['text']
  if 'then it is not authorized' in text:mod['selected_texts'][idx]['text']=text.replace('then it is not authorized','then it is authorized',1)
  elif 'then it is authorized' in text:mod['selected_texts'][idx]['text']=text.replace('then it is authorized','then it is not authorized',1)
  else:raise ValueError('unknown terminal rule')
  return {'inference_ordinal':ordinal,'rule_id':rule_id,'control':payload,'edited':mod}
 return None

def _summary_status(assignments_recorded,probe_records):
 """Summarize assignment and intervention completion without hiding probe gaps."""
 if assignments_recorded!=60:return 'incomplete'
 if len(probe_records)!=2:return 'incomplete_interventions'
 statuses=[probe.get('status') for probe in probe_records]
 if any(status not in ('completed','unavailable') for status in statuses):
  return 'incomplete_interventions'
 if all(status=='completed' for status in statuses):return 'completed_unreviewed'
 return 'completed_with_unavailable_interventions'

def execute():
 f=validate()
 if any((RUN/x).exists() for x in ('dispatch.json','ledger','summary.json')) or list(RUN.glob('*.outcome.json')):raise ValueError('run already started')
 tasks,keys,_=build();bycase={x['case_id']:x for x in tasks};bykey={x['case_id']:x for x in keys}
 import google.auth
 from google.auth.transport.requests import Request
 creds,project=google.auth.default(scopes=['https://www.googleapis.com/auth/cloud-platform'])
 if not project or hashlib.sha256(project.encode()).hexdigest()!=legacy.PROJECT_SHA:raise ValueError('provider project mismatch')
 sys.path.insert(0,str(legacy.OLD/'forecast-p1-budget-successor-v1'));sys.path.insert(0,str(legacy.OLD/'transport'))
 retry=importlib.import_module('p1_retry');oneshot=importlib.import_module('oneshot');retry.MAX_EXTRA=40
 def token(provider):
  if provider!='vertex':raise ValueError('provider denied')
  if not creds.valid:creds.refresh(Request())
  if not creds.token:raise ValueError('token unavailable')
  return creds.token
 transport=oneshot.OneShotTransport(project,token)
 fsha=sha(RUN/'contract.json');csha=sha(RUN/'challenge.json');corpus_shas={x:sha(RUN/x) for x in ('tasks.json','answer-key.json','pairs.json')}
 save_new(RUN/'dispatch.json',{'contract_sha256':fsha,'challenge_sha256':csha,'mode':'single_shot'})
 base=ledger_type(retry,f['config'])(str(RUN/'ledger'),f['config'],create=True);facade=RetryFacade(base,retry)
 forbidden=set(f['lineage']['forbidden_uncertain_request_hashes']);last_end=0.0
 def guard(provider,endpoint,raw):
  nonlocal last_end
  if provider!='vertex' or endpoint not in ('countTokens','gemini-3.8-flash@global'):raise ValueError('endpoint denied')
  if hashlib.sha256(raw).hexdigest() in forbidden:base.stop('prior uncertain request forbidden');raise ValueError('prior uncertain bytes')
  gate_files(f,fsha,csha,corpus_shas)
  wait=1.0-(time.monotonic()-last_end)
  if wait>0:time.sleep(wait)
  try:return transport(provider,endpoint,raw)
  finally:last_end=time.monotonic()
 adapter=Adapter(facade,guard);records=[];probe_records=[];c_costs={};c_results={};last_failure=None
 def callback_for(cid,arm,slot,level,limit):
  calls=[]
  def requester(req):
   if len(calls)>=limit:raise ValueError('role call cap')
   request=_step_prompt(req,arm);ordinal=len(calls)+1
   raw=canonical_json(generation_request(request,level));rh=hashlib.sha256(raw).hexdigest()
   if rh in forbidden:base.stop('prior uncertain request forbidden');raise ValueError('prior uncertain bytes')
   tag='C' if arm=='C' else 'B_self' if arm=='B_self' else 'B'
   op=f'{slot}:{tag}:{ordinal:03d}';row={'ordinal':ordinal,'stage':request['stage'],'operation_id':op,'request_sha256':rh,'thinking_level':level};calls.append(row)
   try:
    result=adapter.complete(request,op,level).content
    if arm=='C' and request['stage']=='selection':
     alts=result.get('alternatives')
     if not isinstance(alts,list) or len(alts)>2 or any(not isinstance(x,list) or not 1<=len(x)<=2 for x in alts):raise ValueError('selection alternatives violate two-premise cap')
    return result
   finally:
    row['effects']=[{'id':a,'kind':b,'state':c,'http_status':d,'response_sha256':e,'actual_micro':g,'quote_micro':h} for a,b,c,d,e,g,h in base.db.execute('select id,kind,state,http_status,response_hash,actual_micro,quote_micro from effects where id in (?,?,?,?) order by rowid',('count:'+op,'count:'+op+'~retry1','generation:'+op,'generation:'+op+'~retry1')).fetchall()]
  def spent():return sum(e['actual_micro'] or 0 for call in calls for e in call.get('effects',[]) if e['kind']=='generation')
  return bind_model(requester),calls,spent
 def unsettled(calls):return any(e['state'] in ('prepared','started','uncertain') or (e['state']=='succeeded' and e['actual_micro'] is None) for call in calls for e in call.get('effects',[]))
 try:
  for idx,item in enumerate(f['schedule'],1):
   if base.summary()['stopped'] or base.poisoned:break
   cid,arm=item['case_id'],item['arm'];task=bycase[cid];prepared=prepare_task(task)
   slot=hashlib.sha256(canonical({'case_id':cid,'arm':arm,'protocol':'hard-si-v1'})).hexdigest()
   model,calls,spent=callback_for(cid,arm,slot,LEVELS[arm],LIMITS[arm])
   if arm=='C':out=StrictEngine(model,EngineConfig(**f['si_config'])).run(task);c_costs[cid]=spent();c_results[cid]=out
   elif arm=='B_budget':
    if cid not in c_costs:raise ValueError('budget baseline before C')
    out=budget_baseline(prepared,model,spent,c_costs[cid])
   else:out=_branch(arm,prepared,model,self_check=arm=='B_self')
   pending=unsettled(calls);packet={'schema':'hard-si-outcome-v1','case_id':cid,'arm':arm,'task_sha256':prepared['input_sha256'],
    'outcome':out,'calls':calls,'unsettled_effect':pending}
   h=save_new(RUN/(slot+'.outcome.json'),packet)
   records.append({'case_id':cid,'arm':arm,'slot':slot,'status':out['status'],'reason':out.get('reason'),
                   'role_calls':len(calls),'actual_micro_known':spent(),'outcome_sha256':h,'unsettled_effect':pending})
   print(f'{idx}/60 {cid} {arm}: {out["status"]}, calls={len(calls)}, exposure=${base.summary()["exposure_micro"]/1e6:.6f}',flush=True)
   if pending or base.summary()['stopped'] or base.poisoned:break
   failure=out.get('reason') if out['status']=='technical_failure' else None
   if failure and failure==last_failure and 'RateLimit' not in failure:base.stop('repeated identical technical failure');break
   last_failure=failure
  # Predetermined intervention cases, regardless of model answer; skip structurally unavailable steps.
  if len(records)==60 and not base.summary()['stopped'] and not base.poisoned:
   for n,cid in enumerate(f['interventions']['case_ids'],1):
    sample=_intervention_payload(c_results[cid],bykey[cid])
    probe={'case_id':cid,'status':'unavailable' if sample is None else 'not_started','reason':'matching selected SI step absent' if sample is None else None,'calls':[]}
    if sample is not None:
     slot=hashlib.sha256(canonical({'case_id':cid,'arm':'probe','protocol':'hard-si-v1'})).hexdigest()
     model,calls,_=callback_for(cid,'C',slot,'LOW',2);probe['source_inference_ordinal']=sample['inference_ordinal'];probe['rule_id']=sample['rule_id']
     for variant in ('control','edited'):
      try:response=model('inference',sample[variant]);probe.setdefault('results',[]).append({'variant':variant,'payload':sample[variant],'response':response})
      except Exception as exc:probe.setdefault('results',[]).append({'variant':variant,'payload':sample[variant],'error':type(exc).__name__});break
      if base.summary()['stopped'] or base.poisoned:break
     probe['calls']=calls;probe['status']='completed' if len(probe.get('results',[]))==2 and all('response' in x for x in probe['results']) else 'incomplete'
    h=save_new(RUN/(hashlib.sha256(canonical({'case_id':cid,'arm':'probe'})).hexdigest()+'.probe.json'),probe)
    probe_records.append({'case_id':cid,'status':probe['status'],'sha256':h})
    print(f'probe {n}/2: {probe["status"]}; exposure=${base.summary()["exposure_micro"]/1e6:.6f}',flush=True)
    if base.summary()['stopped'] or base.poisoned:break
  result={'status':_summary_status(len(records),probe_records),
   'assignments_total':60,'assignments_recorded':len(records),'records':records,
   'interventions_total':2,'interventions_recorded':len(probe_records),'interventions':probe_records,
   'ledger':base.summary(),'semantic_review':'pending','automatic_resume':False}
  save_new(RUN/'summary.json',result);return result
 except BaseException:
  if not base.summary()['stopped']:base.stop('interrupted; no automatic resume')
  if not (RUN/'summary.json').exists():save_new(RUN/'summary.json',{'status':'incomplete','assignments_total':60,'assignments_recorded':len(records),'records':records,'interventions':probe_records,'ledger':base.summary(),'automatic_resume':False})
  raise
 finally:base.close()

if __name__=='__main__':
 if sys.argv[1:]==['prepare']:prepare()
 elif sys.argv[1:]==['execute']:print(json.dumps(execute(),ensure_ascii=False))
 elif sys.argv[1:]==['inspect']:print(json.dumps(contract(),ensure_ascii=False))
 else:raise SystemExit('Use inspect, prepare, execute')
