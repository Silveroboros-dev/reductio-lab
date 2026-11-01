"""Freeze and run the authorized six-case S-1 comparison, serially.

Inputs are exposed development evidence, not a blinded holdout. No network on
import or prepare. A separate independent frozen-contract challenge is required.
"""
import copy
import datetime as dt
import hashlib
import json
import os
import random
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import runtime
import source_stage_v2
from el.evals.faithful_engine.engine import Engine, EngineConfig, prepare_task
from el.evals.faithful_engine.baseline import _branch

def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def canonical(obj): return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
def put(path, obj):
    data=canonical(obj); fd=os.open(path, os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,'O_NOFOLLOW',0), 0o600)
    with os.fdopen(fd,'wb') as out: out.write(data);out.flush();os.fsync(out.fileno())
    fd=os.open(ROOT,os.O_RDONLY)
    try: os.fsync(fd)
    finally: os.close(fd)
    return hashlib.sha256(data).hexdigest()

def task_from_case(case, cutoff, news=None, market_rules=None, x_quotes=None):
    question = (case['question'] + '\nUser-confirmed considerations: potential return as a function of ability '
      'to create and capture value; financial sustainability as a function of prudent financial strategy; '
      'AI safety including potential management abuse. No ranking or risk tolerance has been provided. '
      'Separate evidence, inference, assumptions and unknowns; analyze plausible alternatives. '
      'Do not assume a buy/sell decision. Answer in Russian with source IDs and concrete conditions.')
    evidence=[]
    for item in case['evidence']:
        if item['id']=='G5': continue  # candidate omitted: missing share-owner approval condition
        text=item['text'].replace('A saved X post','An X post').replace('a bookmarked X thread','an X thread')
        if x_quotes and item['id'] in x_quotes:
            quoted=x_quotes[item['id']]
            if quoted['source_url']!=item['source_url'] or case['case_id'] not in quoted['case_ids']:
                raise ValueError('X excerpt does not match case and URL')
            text='The author writes: "'+quoted['excerpt']+'"'
        if market_rules and item['id'] in market_rules:
            text=market_rules[item['id']]['text_transcribed_from_index']
            if item['id']=='M3': text+='\nThe examined outcome is the listed date December 31, 2026.'
        kind='contract_rule' if item['origin']=='market_rule' else ('quote' if item['origin']=='user_relayed_market_api' else 'observation')
        source=item['source_url']+' | '+item['transcription']+' | period: '+item['source_period']
        if x_quotes and item['id'] in x_quotes: source=item['source_url']+' | exact X post excerpt | period: '+item['source_period']
        if item['id'] in ('M1','M2'): source+=' | API response relayed by user; no direct API capture in this run'
        if item['id'] in ('M3','M4','M5'): source+=' | INDEXED EXCERPT ONLY: current complete official rule not directly verified in this run'
        evidence.append({'id':item['id'],'text':text,'source':source,'kind':kind})
    for item in news or []:
        if case['case_id'] in item['case_ids']:
            evidence.append({'id':item['id'],'text':item['text'],'kind':'news',
                'source':item['source_url']+' | attributed news analysis; publication: '+item['source_publication_date']})
    questions=[
      {'id':'facts','question':'What do the supplied sources establish, and with what dates and limits?','evidence_ids':[]},
      {'id':'alternatives','question':'What are the strongest relevant alternative interpretations and conditions under which the conclusions fail?','evidence_ids':[]},
      {'id':'unknowns','question':'What is unknown and what evidence would distinguish the alternatives?','evidence_ids':[]},
      {'id':'agency','question':'How do the user-stated considerations bear on the question without deciding their priorities?','evidence_ids':[]},
    ]
    return {'case_id':case['case_id'],'question':question,'task_type':'exploration','as_of_utc':cutoff,
            'evidence':evidence,'required_questions':questions,'unavailable_evidence_ids':[]}

def build_tasks(source, cutoff, news=None, market_rules=None, x_quotes=None):
    cases=source['cases']
    if len(cases)!=6 or len({c['case_id'] for c in cases})!=6: raise ValueError('corpus scope')
    tasks=[task_from_case(c,cutoff,news,market_rules,x_quotes) for c in cases]
    for task in tasks: prepare_task(task)
    return tasks

def verify_source_receipt():
    summary=json.loads((ROOT/'source-summary.json').read_bytes())
    db=sqlite3.connect('file:'+str(ROOT/'ledger/ledger.sqlite3')+'?mode=ro&immutable=1',uri=True)
    try:
        row=db.execute("SELECT state,http_status,request,request_hash,response,response_hash,actual_micro,quote_evidence_sha FROM effects WHERE id='source:s1:serper-news:001'").fetchone()
    finally: db.close()
    if not row: raise ValueError('source effect missing')
    state,http,request,request_hash,response,response_hash,actual,price_hash=row
    expected=canonical({'api':'serper','path':'/news','body':{'q':'Anthropic IPO S-1 compute obligations governance','num':3},'query':{}})
    if (state,http,actual)!=('succeeded',200,2000) or bytes(request)!=expected:
        raise ValueError('source effect or amount mismatch')
    if hashlib.sha256(bytes(request)).hexdigest()!=request_hash or hashlib.sha256(bytes(response)).hexdigest()!=response_hash:
        raise ValueError('source raw receipt hash mismatch')
    if summary.get('request_sha256')!=request_hash or summary.get('response_sha256')!=response_hash or summary.get('actual_micro')!=actual:
        raise ValueError('source summary receipt mismatch')
    if price_hash!=sha(ROOT/'source-price.json') or json.loads(response)!=json.loads((ROOT/'serper-news-response.json').read_bytes()):
        raise ValueError('source price or response binding mismatch')
    return response_hash

def prepare():
    if (ROOT/'model-contract.json').exists() or (ROOT/'model-dispatch.json').exists(): raise ValueError('already prepared')
    source_summary=json.loads((ROOT/'source-summary.json').read_bytes())
    if source_summary.get('state')!='succeeded' or source_summary.get('http_status')!=200: raise ValueError('source not settled')
    source_raw_hash=verify_source_receipt()
    raw=(ROOT/'source_candidates.json').read_bytes();source=json.loads(raw)
    if sha(ROOT/'sec-s1-original.html')!=source['s1_raw_sha256']: raise ValueError('original S-1 binding mismatch')
    news=json.loads((ROOT/'orthogonal-reviewed-candidates.json').read_bytes())
    if news['source_response_sha256']!=sha(ROOT/'serper-news-response.json'):raise ValueError('news discovery binding mismatch')
    markets=json.loads((ROOT/'source_market_rules.json').read_bytes())
    if markets['status']!='NOT_CURRENT_UI_VERIFIED':raise ValueError('market source status unexpected')
    market_map={m['source_candidate_id']:m for m in markets['markets']}
    x_file=ROOT/'x-verbatim-excerpts.json'
    x_obj=json.loads(x_file.read_bytes()) if x_file.exists() else {'items':[]}
    x_by_id={x['id']:x for x in x_obj['items']}
    x_quotes={case_id:x_by_id[xid] for case_id,xid in {'L3':'X1','C5':'X2','C6':'X3'}.items() if xid in x_by_id}
    cutoff=dt.datetime.now(dt.timezone.utc).isoformat(); tasks=build_tasks(source,cutoff,news['candidates'],market_map,x_quotes)
    human_input={'source':'user response in this chat to question about personal evaluation criteria',
         'question':'Что вам важнее при оценке Anthropic и какие исходные предположения проверить?',
         'exact_response':'потенциальная доходность (как следствие способности компании create and capture value), финансовая устойвость (как следствие of prudent financial strategy), безопасность ИИ (в том числе как следствие отсутствия злоупотребелний со стороны менеджмента).',
         'user_rankings':'not provided','prior_case_choices':'not provided','capture':'direct user answer, not model inference'}
    human_input_hash=put(ROOT/'human-input.json',human_input)
    task_hash=put(ROOT/'tasks-frozen.json',tasks)
    order=list(tasks);random.Random(20261029).shuffle(order);schedule=[]
    for t in order:
        arms=['A','B','C'];random.Random(20261029+int(hashlib.sha256(t['case_id'].encode()).hexdigest()[:8],16)).shuffle(arms)
        schedule.extend({'case_id':t['case_id'],'arm':a} for a in arms)
    if len(schedule)!=18 or len({(x['case_id'],x['arm']) for x in schedule})!=18: raise ValueError('schedule invalid')
    # Human exposure assignments are separate from the paired model schedule.
    assignments=list('AABBCC');random.Random(129102026).shuffle(assignments)
    human=[{'case_id':t['case_id'],'first_arm':arm} for t,arm in zip(order,assignments)]
    human_hash=put(ROOT/'human-assignment-private.json',human)
    rubric={'schema':'s1-rubric-v1','dimensions':['source_accuracy_and_dates','supported_inference',
         'material_alternatives','justified_unknown','user_values_preserved','checkable_citations','false_positive_and_failure'],
         'review_rule':'blind human expert if available; otherwise explicitly non-independent model-assisted review',
         'failures_and_unknowns_in_denominator':True,'human_agency_claim':'one participant, six non-equivalent exposed cases; exploratory only',
         'user_review':'record original and post-answer views before seeing other arms; may be pending',
         'contra_probe':'two fresh inference calls per available C case, one control and one with a selected premise removed; not a semantic proof',
         'source_coverage_is_structural_only':True,
         'expected_source_ids_by_case':{'S1-01-liquidity':['L1','L4','L5'],
           'S1-02-loss-cash':['F1','F2','F3','F4'], 'S1-03-compute':['C2','C3','C4','C5'],
           'S1-04-customers':['D1','D3','D5'], 'S1-05-market-rules':['M1','M2','M3','M4','M5'],
           'S1-06-governance':['G1','G2','G3','G4']},
         'coverage_limit':'ID selection/citation does not prove the semantic claim is correct; an unselected item may be irrelevant',
         'orthogonal_news':'two independently read attributed interpretations ON1/ON2 included; Reuters unavailable; other search snippets excluded'}
    rubric_hash=put(ROOT/'rubric-frozen.json',rubric)
    repo=Path('/Users/rk/.codex/worktrees/faithful-dynamic-pilot/fitcheck-core')
    deps=[ROOT/'runtime.py',ROOT/'model_stage.py',repo/'el/evals/faithful_engine/engine.py',
          repo/'el/evals/faithful_engine/prompts.py',repo/'el/evals/faithful_engine/baseline.py']
    contract={'schema':'s1-model-run-contract-v1','tasks_sha256':task_hash,'rubric_sha256':rubric_hash,
        'human_assignment_sha256':human_hash,'human_input_sha256':human_input_hash,'source_candidates_sha256':sha(ROOT/'source_candidates.json'),
        'original_s1_sha256':sha(ROOT/'sec-s1-original.html'),'source_summary_sha256':sha(ROOT/'source-summary.json'),
        'source_raw_response_sha256':source_raw_hash,'orthogonal_reviewed_sha256':sha(ROOT/'orthogonal-reviewed-candidates.json'),
        'market_rules_sha256':sha(ROOT/'source_market_rules.json'),'x_verbatim_sha256':sha(x_file) if x_file.exists() else None,
        'source_response_sha256':sha(ROOT/'serper-news-response.json'),'source_cutoff':cutoff,'case_count':6,
        'schedule':schedule,'model':'gemini-3.8-flash@global','thinking':'LOW','max_output_tokens':4096,
        'engine_config':{'max_calls':13,'max_depth':3,'beam_width':1,'max_alternatives':1},
        'branch_A':'baseline_initial, one call','branch_B':'baseline_counterfactual, one call',
        'branch_C':'SI-inspired model roles, v2; up to 13 calls; model semantic judgments unverified',
        'interventions':'up to 12 calls following comparisons; control and delete one selected premise; missing eligible step marked unavailable',
        'caps':{'cumulative_micro':60000000,'prior_micro':56609714,'new_max_micro':10000000,
                'new_generation_attempts':130,'new_count_attempts':130,'source_attempts':1,'source_reserve_micro':10000},
        'retry':'one identical retry only on captured explicit 429, no uncertain retry; global extra attempts <=28',
        'model_runtime_no_implicit_retry':True,'timeout_seconds':420,'task_semantics':'exposed development case, not holdout',
        'full_s1_available_to_human':True,'branch_input_scope':'identical curated packet; SI inference sees selected premises only',
        'prior_cannot_be_fully_reconciled_to_invoice':True,'human_values':'user provided explicitly; ranking unknown',
        'source_limitations':'G5 excluded due to missing approval condition; M3-M5 indexed excerpts without direct current primary verification',
        'code_sha256':{**source_stage_v2.dependencies(), **{str(p):sha(p) for p in deps}},'predecessor':runtime.predecessor_snapshot()}
    put(ROOT/'model-contract.json',contract)
    print('prepared frozen comparison',sha(ROOT/'model-contract.json'),flush=True)

def validate():
    contract=json.loads((ROOT/'model-contract.json').read_bytes());challenge=json.loads((ROOT/'model-challenge.json').read_bytes())
    if challenge.get('status')!='ready' or challenge.get('blockers')!=[] or challenge.get('contract_sha256')!=sha(ROOT/'model-contract.json'):
        raise ValueError('independent challenge absent or stale')
    pairs=[('tasks-frozen.json','tasks_sha256'),('rubric-frozen.json','rubric_sha256'),
      ('human-assignment-private.json','human_assignment_sha256'),('human-input.json','human_input_sha256'),('source_candidates.json','source_candidates_sha256'),
      ('sec-s1-original.html','original_s1_sha256'),('source-summary.json','source_summary_sha256'),
      ('serper-news-response.json','source_response_sha256'),('orthogonal-reviewed-candidates.json','orthogonal_reviewed_sha256'),
      ('source_market_rules.json','market_rules_sha256')]
    for fn,key in pairs:
        if sha(ROOT/fn)!=contract[key]:raise ValueError('frozen input drift: '+fn)
    if contract['x_verbatim_sha256'] and sha(ROOT/'x-verbatim-excerpts.json')!=contract['x_verbatim_sha256']:raise ValueError('X evidence drift')
    if verify_source_receipt()!=contract['source_raw_response_sha256']:raise ValueError('source receipt drift')
    if contract['predecessor']!=runtime.predecessor_snapshot():raise ValueError('predecessor drift')
    for filename,h in contract['code_sha256'].items():
        if sha(Path(filename))!=h:raise ValueError('code drift')
    return contract

def execute():
    c=validate()
    if (ROOT/'model-dispatch.json').exists() or (ROOT/'model-summary.json').exists():raise ValueError('model already dispatched')
    put(ROOT/'model-dispatch.json',{'contract_sha256':sha(ROOT/'model-contract.json'),'challenge_sha256':sha(ROOT/'model-challenge.json'),
                                   'started_utc':dt.datetime.now(dt.timezone.utc).isoformat()})
    run=runtime.Runtime(ROOT/'ledger',transport=runtime.build_live_transport(),resume=True)
    tasks={t['case_id']:t for t in json.loads((ROOT/'tasks-frozen.json').read_bytes())}
    records=[];c_outcomes={};probes=[]
    try:
        for idx,entry in enumerate(c['schedule'],1):
            validate()
            if run.summary()['stopped'] or run.ledger.poisoned:break
            case_id,arm=entry['case_id'],entry['arm'];task=tasks[case_id];gen=run.generator(case_id,arm)
            if arm=='C':
                result=Engine(gen,EngineConfig(**c['engine_config'])).run(task);c_outcomes[case_id]=result
            else:
                def selected(stage,payload):
                    return gen('baseline_counterfactual' if arm=='B' and stage=='baseline_initial' else stage,payload)
                result=_branch(arm,prepare_task(task),selected,self_check=False)
            name=f'{case_id}-{arm}.outcome.json';h=put(ROOT/name,{'case_id':case_id,'arm':arm,'outcome':result})
            records.append({'case_id':case_id,'arm':arm,'file':name,'sha256':h,'status':result['status'],'calls':result['calls']})
            print(f'{idx}/18 {case_id} {arm} {result["status"]} calls={result["calls"]}',flush=True)
            if run.summary()['stopped'] or run.ledger.poisoned:break
        # Probe only after completing the core comparisons. A missing eligible
        # selected premise is reported, never replaced by a made-up probe.
        if len(records)==18 and not run.summary()['stopped']:
            for case_id,result in c_outcomes.items():
                returned={x.get('ordinal') for x in result.get('events',[]) if x.get('event')=='model_returned' and x.get('stage')=='inference'}
                candidates=[x for x in result.get('events',[]) if x.get('event')=='model_started'
                            and x.get('stage')=='inference' and x.get('ordinal') in returned
                            and len(x.get('payload',{}).get('selected_texts',[]))>=2]
                if not candidates:
                    probes.append({'case_id':case_id,'status':'unavailable','reason':'no inference with at least two selected premises'});continue
                original=copy.deepcopy(candidates[0]['payload']);changed=copy.deepcopy(original)
                removed=changed['selected_texts'].pop()
                gen=run.generator(case_id,'probe')
                try:
                    control=gen('inference',original)
                    edited=gen('inference',changed)
                    p={'case_id':case_id,'status':'completed','removed_premise':removed,'control_input':original,
                       'edited_input':changed,'control_result':control,'edited_result':edited,
                       'qualification':'sensitivity only, not proof of entailment or causal faithfulness'}
                except Exception as exc:
                    p={'case_id':case_id,'status':'technical_failure','error_type':type(exc).__name__}
                put(ROOT/f'{case_id}-probe.json',p);probes.append(p)
                if run.summary()['stopped'] or run.ledger.poisoned:break
        put(ROOT/'model-summary.json',{'status':'completed_unreviewed' if len(records)==18 else 'incomplete',
            'assignments_planned':18,'assignments_recorded':len(records),'records':records,
            'probes':[{'case_id':p['case_id'],'status':p['status']} for p in probes],
            'ledger':run.summary(),'semantic_review':'pending','human_agency_review':'pending'})
        print('model stage complete',json.dumps(run.summary()),flush=True)
    except BaseException:
        if not run.summary()['stopped']:run.ledger.stop('model stage interrupted; no automatic restart')
        raise
    finally:run.close()

if __name__=='__main__': {'prepare':prepare,'execute':execute}[sys.argv[1]]()
