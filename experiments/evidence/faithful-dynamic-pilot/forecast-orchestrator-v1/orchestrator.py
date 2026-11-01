"""Offline, injected prospective forecast orchestration.

No provider, credentials, model client or authority. Caller must independently
verify human decisions, rules, timing, prior records, persistence and costs.
Local timestamp/hash checks cannot prove external source authenticity or that
the model has not learned an event in its weights.
"""
from __future__ import annotations
import copy, datetime as dt, hashlib, json, math, secrets, sys
from pathlib import Path

ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT/'forecast-controller-v1'))
import forecast

class EligibilityError(ValueError): pass

def canonical(value):
    return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode('utf-8')

def sha(raw): return hashlib.sha256(raw).hexdigest()

def instant(value):
    if not isinstance(value,str): raise EligibilityError('timestamp required')
    try: t=dt.datetime.fromisoformat(value.replace('Z','+00:00'))
    except ValueError: raise EligibilityError('invalid timestamp') from None
    if t.utcoffset()!=dt.timedelta(0): raise EligibilityError('UTC timestamp required')
    return t

def _nonempty(v,label):
    if not isinstance(v,str) or not v.strip(): raise EligibilityError(label+' required')
    return v

def _verify(fn,*args):
    if not callable(fn) or fn(*args) is not True:
        raise EligibilityError('attributed verification required')

def prepare_case(case,*,verify_human,verify_rules):
    """Return exact content-bound case and initial task; performs no effects.

    Verifiers must check independently attributable decisions and full source
    bytes; a Python callback that blindly returns true is not evidence.
    """
    required={'case_id','event_group_id','thesis','contract_id','rules_primary',
        'rules_secondary','rules_capture_sha256','rules_capture_source','rules_captured_at_utc',
        'close_time_utc','p0_as_of_utc','baseline_evidence','human_approval'}
    if not isinstance(case,dict) or set(case)!=required: raise EligibilityError('case schema mismatch')
    for key in ('case_id','event_group_id','thesis','contract_id','rules_primary','rules_capture_source'):
        _nonempty(case[key],key)
    if not isinstance(case['rules_secondary'],str):raise EligibilityError('secondary rules required, empty allowed')
    h=case['rules_capture_sha256']
    if not isinstance(h,str) or len(h)!=64 or any(c not in '0123456789abcdef' for c in h):raise EligibilityError('capture sha required')
    t0=instant(case['p0_as_of_utc']); rc=instant(case['rules_captured_at_utc']); close=instant(case['close_time_utc'])
    if rc>t0 or close<=t0:raise EligibilityError('rules snapshot or expiry incompatible with p0')
    approval=case['human_approval']
    if not isinstance(approval,dict) or approval.get('thesis_sha256')!=sha(case['thesis'].encode('utf-8')):
        raise EligibilityError('approval must bind exact thesis')
    # This timestamp is when the approval evidence was recorded, not a claim
    # about the exact time of the user's underlying message.
    if instant(approval.get('approval_recorded_at_utc'))>t0:raise EligibilityError('approval record after p0 cutoff')
    _verify(verify_human,copy.deepcopy(case)); _verify(verify_rules,copy.deepcopy(case))
    facts=case['baseline_evidence']
    if not isinstance(facts,list):raise EligibilityError('baseline list required')
    for e in facts:
        if not isinstance(e,dict) or e.get('kind') not in ('context','market_quote'):
            raise EligibilityError('no p1 intervention may appear at p0')
        if not e.get('available_at_utc') or not e.get('captured_at_utc'):
            raise EligibilityError('baseline availability and capture times required')
        a=instant(e['available_at_utc']);c=instant(e['captured_at_utc'])
        if a>c or c>t0:raise EligibilityError('baseline unavailable at p0')
        if e.get('published_at_utc') and instant(e['published_at_utc'])>a:raise EligibilityError('baseline publication after availability')
    rules=[{'id':'rule:primary','kind':'rule','text':case['rules_primary'],
            'source':case['rules_capture_source']+'; capture sha256 '+h,'captured_at_utc':case['rules_captured_at_utc']}]
    if case['rules_secondary'].strip():
        rules.append({'id':'rule:secondary','kind':'rule','text':case['rules_secondary'],
            'source':case['rules_capture_source']+'; capture sha256 '+h,'captured_at_utc':case['rules_captured_at_utc']})
    task={'case_id':case['case_id'],'contract_id':case['contract_id'],
        'question':'The user approved the formulation of this thesis, not its truth: '+case['thesis']+'. Its truth is uncertain. Given the exact market rules, what is P(YES for this specific contract)? Do not assume the thesis is true.',
        'as_of_utc':case['p0_as_of_utc'],'phase':'p0','condition':'no_news',
        'evidence':rules+copy.deepcopy(facts),'prior_forecast':None}
    forecast.prepare_task(task)
    return {'case':copy.deepcopy(case),'case_sha256':sha(canonical(case)),
            'task':task,'task_sha256':sha(canonical(task))}

def run_p0(prepared,*,generator_factory,record,clock):
    """C then B on equal task; B receives C's call count, never C output.

    `record` must durably create each object and raise on write failure. The
    generator must journal and settle every count/generation externally. No
    resumability after interruption is implied by this helper.
    """
    if not callable(record) or not callable(clock) or not callable(generator_factory):raise EligibilityError('durable recorder, generator factory and clock required')
    if sha(canonical(prepared['case']))!=prepared['case_sha256'] or sha(canonical(prepared['task']))!=prepared['task_sha256']:
        raise EligibilityError('prepared case drift')
    record('p0-input',copy.deepcopy(prepared))
    c=forecast.FaithfulEngine(generator_factory('p0','no_news','c'),max_calls=23).run(copy.deepcopy(prepared['task']))
    record('p0-c',copy.deepcopy(c))
    n=c.get('calls')
    if type(n) is not int or not 1<=n<=23:
        return {'status':'unavailable','reason':'c_zero_or_invalid_call_count','case_sha256':prepared['case_sha256']}
    b=forecast.BaselineEngine(generator_factory('p0','no_news','b'),matched_calls=n).run(copy.deepcopy(prepared['task']))
    record('p0-b',copy.deepcopy(b))
    completed=clock();instant(completed)
    if not instant(prepared['task']['as_of_utc'])<=instant(completed)<instant(prepared['case']['close_time_utc']):
        raise EligibilityError('p0 completed outside open interval')
    out={'schema':'forecast-p0-v1','case_sha256':prepared['case_sha256'],'task_sha256':prepared['task_sha256'],
         'completed_at_utc':completed,'c':copy.deepcopy(c),'b':copy.deepcopy(b),
         'limitation':'B first in later phases is conditional on B matched p0, not a full simple trajectory.'}
    record('p0-frozen',copy.deepcopy(out))
    # The recorder has returned only after durable p0 write; sample the clock
    # afterwards so an intervention cannot fall into the persistence gap.
    persisted_before=clock(); instant(persisted_before)
    if not instant(completed)<=instant(persisted_before)<instant(prepared['case']['close_time_utc']):
        raise EligibilityError('p0 durable record outside open interval')
    receipt={**out,'frozen_content_sha256':sha(canonical(out)),
             'durable_before_utc':persisted_before}
    record('p0-receipt',copy.deepcopy(receipt))
    return receipt

def prepare_p1(prepared,p0,intervention,*,t1,verify_p0,verify_intervention,verify_unresolved):
    """Strict prospective timing. Reject unknown timestamps; no post-resolution replay."""
    if not isinstance(p0,dict) or p0.get('schema')!='forecast-p0-v1' or p0.get('case_sha256')!=prepared.get('case_sha256') or p0.get('task_sha256')!=prepared.get('task_sha256'):
        raise EligibilityError('p0 lineage mismatch')
    if sha(canonical(prepared['case']))!=prepared['case_sha256'] or sha(canonical(prepared['task']))!=prepared['task_sha256']:
        raise EligibilityError('prepared bytes changed')
    _verify(verify_p0,copy.deepcopy(p0),copy.deepcopy(prepared))
    frozen={k:v for k,v in p0.items() if k not in ('frozen_content_sha256','durable_before_utc')}
    if p0.get('frozen_content_sha256')!=sha(canonical(frozen)):
        raise EligibilityError('p0 durable-record binding mismatch')
    if instant(p0['completed_at_utc'])>instant(p0['durable_before_utc']):
        raise EligibilityError('p0 timestamp ordering invalid')
    t0=instant(p0['durable_before_utc']); end=instant(t1)
    if end<=t0 or end>=instant(prepared['case']['close_time_utc']):
        raise EligibilityError('p1 outside prospective open interval')
    _verify(verify_unresolved,copy.deepcopy(prepared['case']),t1)
    if not isinstance(intervention,list) or not intervention:
        raise EligibilityError('empty intervention: retain pending/unknown')
    baseline_texts={x['text'].strip() for x in prepared['task']['evidence']}
    baseline_ids={x['id'] for x in prepared['task']['evidence']}
    for e in intervention:
        if not isinstance(e,dict) or e.get('kind')!='news':raise EligibilityError('intervention must be news')
        if e.get('id') in baseline_ids or not isinstance(e.get('text'),str) or e['text'].strip() in baseline_texts:
            raise EligibilityError('intervention duplicates baseline identity or exact text')
        pub=instant(e.get('published_at_utc')); avail=instant(e.get('available_at_utc')); capture=instant(e.get('captured_at_utc'))
        if not (t0<pub<=avail<=capture<=end):
            raise EligibilityError('intervention was not provably new and available after all p0')
    _verify(verify_intervention,copy.deepcopy(intervention),t1)
    try:
        cp=copy.deepcopy(p0['c']['result']);bp=copy.deepcopy(p0['b']['result'])
    except (KeyError,TypeError):raise EligibilityError('missing own frozen prior: do not reconstruct') from None
    result={}
    for procedure,prior in (('c',cp),('b',bp)):
        for condition in ('no_news','news'):
            task=copy.deepcopy(prepared['task']);task.update(phase='p1',condition=condition,as_of_utc=t1,prior_forecast=copy.deepcopy(prior))
            if condition=='news':task['evidence']+=copy.deepcopy(intervention)
            forecast.prepare_task(task)
            result[procedure+'_'+condition]=task
    return {'schema':'forecast-p1-input-v1','case_sha256':prepared['case_sha256'],
            'p0_sha256':sha(canonical(p0)),'intervention_sha256':sha(canonical(intervention)),
            't1':t1,'tasks':result}

def run_p1(bundle,*,expected_bundle_sha256,verify_bundle,generator_factory,record):
    if not callable(record) or not callable(generator_factory):raise EligibilityError('durable recorder and generator factory required')
    if sha(canonical(bundle))!=expected_bundle_sha256:raise EligibilityError('frozen p1 bundle changed')
    _verify(verify_bundle,copy.deepcopy(bundle))
    record('p1-input',copy.deepcopy(bundle));results={}
    for condition in ('no_news','news'):
        ct=copy.deepcopy(bundle['tasks']['c_'+condition]);bt=copy.deepcopy(bundle['tasks']['b_'+condition])
        # Equal evidence and task identity; only each system's own prior may differ.
        if any(ct[k]!=bt[k] for k in ct if k!='prior_forecast'):raise EligibilityError('unmatched information')
        c=forecast.FaithfulEngine(generator_factory('p1',condition,'c'),max_calls=23).run(ct);record('p1-c-'+condition,copy.deepcopy(c))
        n=c.get('calls')
        if type(n) is not int or not 1<=n<=23:
            results[condition]={'c':c,'b':{'status':'unavailable','reason':'c_zero_or_invalid_call_count'}};continue
        b=forecast.BaselineEngine(generator_factory('p1',condition,'b'),matched_calls=n).run(bt);record('p1-b-'+condition,copy.deepcopy(b))
        results[condition]={'c':c,'b':b}
    out={'schema':'forecast-p1-result-v1','input_sha256':sha(canonical(bundle)),
         'results':results,'limitation':'B-first p1 is conditional on B-matched p0; not a complete independent cheap trajectory.'}
    record('p1-frozen',copy.deepcopy(out));return out

def review_cards(prepared,bundle,p1,*,id_factory=None,shuffle=None):
    """Return blindable cards and separate private map; no claim of human review."""
    if id_factory is None:id_factory=lambda:secrets.token_hex(16)
    if shuffle is None:shuffle=secrets.SystemRandom().shuffle
    if p1.get('input_sha256')!=sha(canonical(bundle)) or bundle.get('case_sha256')!=prepared.get('case_sha256'):
        raise EligibilityError('review packet lineage mismatch')
    cards=[];identity={}
    for condition in ('no_news','news'):
        for arm,field in (('b','first'),('b','result'),('c','result')):
            x=p1['results'][condition][arm];rid=_nonempty(id_factory(),'review identity')
            if rid in identity:raise EligibilityError('duplicate review identity')
            identity[rid]={'condition':condition,'arm':arm,'field':field}
            cards.append({'review_id':rid,'thesis':prepared['case']['thesis'],
                'contract_id':prepared['case']['contract_id'],'status':x.get('status'),
                'evidence':copy.deepcopy(bundle['tasks'][arm+'_'+condition]['evidence']),
                'forecast':copy.deepcopy(x.get(field))})
    shuffle(cards)
    return cards,identity
