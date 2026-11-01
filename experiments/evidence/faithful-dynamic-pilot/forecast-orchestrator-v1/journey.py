"""Offline exploration/decision seam before prospective forecast.

No live effects or authority. Exact user acceptance, sources and market captures
are the responsibility of attributable independently checked caller verifiers.
"""
from __future__ import annotations
import copy, secrets, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT/'forecast-controller-v1'))
import exploration
import orchestrator as o

def prepare_exploration(task,*,verify_thought,verify_sources,verify_leads):
    """Fail before generation if supplied sources or lead timing is not admitted."""
    _=exploration.prepare_task(task)
    for fact in task['evidence']:
        if not fact.get('available_at_utc') or not fact.get('captured_at_utc'):
            raise o.EligibilityError('exploration source needs availability and capture time')
    o._verify(verify_thought,copy.deepcopy(task))
    o._verify(verify_sources,copy.deepcopy(task))
    o._verify(verify_leads,copy.deepcopy(task))
    return {'schema':'forecast-exploration-input-v1','task':copy.deepcopy(task),
            'task_sha256':o.sha(o.canonical(task))}

def run_exploration(prepared,*,generator_factory,record,clock):
    """Seed C/B then save both; only then separately expose retained leads.

    B receives C's seed-call count only. Any post-market call is counted in the
    same six-call per-arm ceiling, and produces proposals, not user choices.
    """
    if not callable(record) or not callable(generator_factory) or not callable(clock):raise o.EligibilityError('recorder, generator factory and clock required')
    if prepared.get('schema')!='forecast-exploration-input-v1' or o.sha(o.canonical(prepared['task']))!=prepared.get('task_sha256'):
        raise o.EligibilityError('frozen exploration task mismatch')
    task=copy.deepcopy(prepared['task']);exploration.prepare_task(task)
    record('exploration-input',copy.deepcopy(prepared))
    c=exploration.FaithfulEngine(generator_factory('exploration','seed','c'),max_calls=6).run(copy.deepcopy(task))
    record('exploration-c-seed',copy.deepcopy(c))
    n=c.get('calls')
    if type(n) is int and 1<=n<=6:
        b=exploration.BaselineEngine(generator_factory('exploration','seed','b'),matched_calls=n).run(copy.deepcopy(task))
    else:
        b={'status':'unavailable','reason':'c_zero_or_invalid_call_count','calls':0,'stage':'seed'}
    record('exploration-b-seed',copy.deepcopy(b))
    # Both seeds have been retained before any post-market generation. C/B
    # post-market engines are instantiated only with their own seed output.
    posts={}
    for arm,seed in (('c',c),('b',b)):
        posts[arm]=exploration.PostMarketEngine(generator_factory('exploration','post_market',arm),
                    copy.deepcopy(seed),max_total_calls=6).run(copy.deepcopy(task))
        record('exploration-'+arm+'-post-market',copy.deepcopy(posts[arm]))
    result={'schema':'forecast-exploration-result-v1','task_sha256':prepared['task_sha256'],
        'seed':{'c':copy.deepcopy(c),'b':copy.deepcopy(b)},'post_market':posts,
        'status':'unreviewed_proposals_only','no_human_decision_recorded':True}
    record('exploration-frozen',copy.deepcopy(result))
    saved=clock()
    if o.instant(saved)<o.instant(task['as_of_utc']):raise o.EligibilityError('exploration saved before its cutoff')
    receipt={**result,'frozen_content_sha256':o.sha(o.canonical(result)),'durable_before_utc':saved}
    record('exploration-receipt',copy.deepcopy(receipt));return receipt

def bind_human_decision(prepared,result,case,decision,*,verify_decision):
    """Bind a real user decision to the research packet and later case.

    A user may refine a model suggestion or author their own. The verifier is
    mandatory: the hashes alone never constitute human acceptance.
    """
    if result.get('schema')!='forecast-exploration-result-v1' or result.get('task_sha256')!=prepared.get('task_sha256'):
        raise o.EligibilityError('exploration outcome is cross-bound')
    frozen={k:v for k,v in result.items() if k not in ('frozen_content_sha256','durable_before_utc')}
    if result.get('frozen_content_sha256')!=o.sha(o.canonical(frozen)):
        raise o.EligibilityError('exploration durable-record binding mismatch')
    if o.sha(o.canonical(prepared['task']))!=prepared['task_sha256']:
        raise o.EligibilityError('exploration inputs changed')
    if case.get('case_id')!=prepared['task']['case_id']:
        raise o.EligibilityError('user decision bound to another case')
    required={'case_id','exploration_result_sha256','thesis_sha256','market_id','decided_at_utc','origin'}
    if not isinstance(decision,dict) or set(decision)!=required:
        raise o.EligibilityError('explicit human decision required')
    if (decision['case_id']!=case['case_id'] or decision['exploration_result_sha256']!=o.sha(o.canonical(result)) or
        decision['thesis_sha256']!=o.sha(case['thesis'].encode('utf-8')) or decision['market_id']!=case['contract_id']):
        raise o.EligibilityError('decision does not bind exact thesis, contract and exploration')
    if not o.instant(result['durable_before_utc'])<=o.instant(decision['decided_at_utc'])<=o.instant(case['p0_as_of_utc']):
        raise o.EligibilityError('human choice before proposal was saved or after p0 cutoff')
    o._nonempty(decision['origin'],'decision origin')
    o._verify(verify_decision,copy.deepcopy(decision),copy.deepcopy(result),copy.deepcopy(case))
    return {'schema':'forecast-decision-binding-v1','decision':copy.deepcopy(decision),
            'decision_sha256':o.sha(o.canonical(decision)),'case_sha256':o.sha(o.canonical(case)),
            'exploration_result_sha256':o.sha(o.canonical(result))}

def blindable_seed_cards(prepared,result,*,id_factory=None,shuffle=None):
    """Only seed outputs, with no market titles; identity map is private."""
    if result.get('task_sha256')!=prepared.get('task_sha256') or o.sha(o.canonical(prepared['task']))!=prepared.get('task_sha256'):
        raise o.EligibilityError('review source identity mismatch')
    if id_factory is None:id_factory=lambda:secrets.token_hex(16)
    if shuffle is None:shuffle=secrets.SystemRandom().shuffle
    cards=[];identity={}
    for arm,field in (('b','first'),('b','result'),('c','result')):
        x=result['seed'][arm];rid=o._nonempty(id_factory(),'review identity')
        if rid in identity:raise o.EligibilityError('duplicate review identity')
        identity[rid]={'arm':arm,'field':field}
        cards.append({'review_id':rid,'thought':prepared['task']['thought'],
            'evidence':copy.deepcopy(prepared['task']['evidence']),
            'status':x.get('status'),'proposal':copy.deepcopy(x.get(field))})
    shuffle(cards);return cards,identity
