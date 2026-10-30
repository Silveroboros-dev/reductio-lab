import copy
from reasoning_engine.action_case import run_case
from reasoning_engine.replay_sources import digest


def packet():
    inp = {'task': 'Question?', 'thesis': 'Thesis', 'initial_evidence': [], 'preconsumed_action_ids': [],
           'replay_max_actions': 1, 'replay_max_simulated_micro_usd': 20,
           'tool_catalog': [{'action_id': 'a', 'description': 'Find source A', 'quoted_micro_usd': 10, 'capture_ref': 'x'},
                            {'action_id': 'b', 'description': 'Find source B', 'quoted_micro_usd': 10, 'capture_ref': 'y'}]}
    cp = {'case_id': 'c', 'input_version': digest(inp), 'input': inp}
    rows = []
    for aid, ref in [('a', 'x'), ('b', 'y')]:
        payload = {'text': 'secret-' + aid}
        rows.append({'case_id': 'c', 'action_id': aid, 'capture_ref': ref,
                     'saved_response': {'payload': payload, 'response_sha256': digest(payload)}})
    return cp, rows


def test_three_arms_only_get_chosen_evidence_and_return_unreviewed():
    checkpoint, rows = packet()
    for arm in ('B', 'B_self', 'C'):
        requests = []
        def fake(stage, payload):
            requests.append((stage, copy.deepcopy(payload)))
            assert 'secret-b' not in str(payload)
            if stage in ('source_decision', 'source_decision_recheck'): return {'choice': 'a', 'reason': 'mock'}
            if stage == 'selection':
                available = payload['available_statements']
                selected = 'action:a' if any(x['id'] == 'action:a' for x in available) else 'source:a'
                return {'alternatives': [[selected]]}
            if stage == 'inference': return {'conclusion': 'A scripted inference.'}
            if stage == 'halter': return {'sufficient': True}
            if stage == 'value': return {'score': .5}
            if stage == 'formatter':
                choosing = 'Allowed action IDs:' in payload['question']
                return {'answer': 'a' if choosing else 'A proposed answer.', 'citations': [], 'assessments': []}
            if stage in ('baseline_initial', 'baseline_recheck'):
                return {'answer': 'A proposed answer.', 'citations': [], 'assessments': []}
            raise AssertionError(stage)
        result = run_case(checkpoint, rows, arm, fake)
        assert result['status'] in ('proposal', 'completed') and result['semantic_status'] == 'unreviewed'
        assert [x['action_id'] for x in result['history'] if x['kind'] == 'replay_retrieval'] == ['a']
        assert result['calls'] == len(requests)


def test_wrong_source_decision_is_technical_failure_without_answer():
    checkpoint, rows = packet()
    result = run_case(checkpoint, rows, 'B', lambda *_: {'choice': 'not-a-source'})
    assert result['status'] == 'technical_failure' and result['result'] is None
    assert result['calls'] == 1


def test_controller_evaluates_two_alternatives_and_selects_high_score():
    checkpoint, rows = packet()
    def fake(stage, payload):
        if stage == 'selection':
            actions=[x['id'] for x in payload['available_statements'] if x['id'].startswith('action:')]
            ids=actions if len(actions)>=2 else [x['id'] for x in payload['available_statements']][:2]
            return {'alternatives': [[ids[0]], [ids[1]]]}
        if stage == 'inference': return {'conclusion': 'Unverified inference.'}
        if stage == 'halter': return {'sufficient': True}
        if stage == 'value':
            ids=payload['trace'][-1]['selected_ids']
            return {'score': .9 if 'action:b' in ids else .2}
        if stage == 'formatter':
            choosing='Allowed action IDs:' in payload['question']
            return {'answer': 'b' if choosing else 'Unverified final.', 'citations': [], 'assessments': []}
        raise AssertionError(stage)
    result=run_case(checkpoint, rows, 'C', fake)
    decision=next(x['outcome'] for x in result['history'] if x['kind']=='model_decision')
    assert decision['selected_branch'].endswith('.1.2')
    assert len(decision['branches'])==2
    assert sum(e['event']=='model_started' and e['stage']=='value' for e in decision['events'])==2
    assert [e['action_id'] for e in result['history'] if e['kind']=='replay_retrieval']==['b']
