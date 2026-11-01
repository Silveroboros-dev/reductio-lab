"""Research-only case runner over saved, explicitly selected source actions.

The injected callback must journal every effect and enforce run-wide authority.
This code never calls a provider, grants authority or judges semantic quality.
"""
from __future__ import annotations

import copy
import json
from typing import Any, Callable

from .baseline import _branch
from .engine import Engine, EngineConfig, prepare_task
from .replay_sources import ReplayCase


def _task(visible: dict, *, choosing: bool) -> dict:
    question = visible['question']
    if visible.get('information_cutoff'):
        question += '\nInformation boundary: ' + visible['information_cutoff']
    evidence = []
    for item in visible['observed']:
        evidence.append({'id': 'source:' + item['action_id'], 'kind': 'observation',
            'source': 'saved response for ' + item['action_id'],
            'raw_ref': 'sha256:' + item['response']['response_sha256'],
            'text': json.dumps(item['response']['payload'], ensure_ascii=False, sort_keys=True)})
    if choosing:
        question += ('\nRemaining source actions: ' + str(visible['remaining_actions']) +
                     '; simulated replay spent (micro-USD): ' + str(visible['simulated_spent_micro_usd']))
        ids = [x['action_id'] for x in visible['available_actions']]
        question += ('\nAction descriptions specify available choices, not retrieved results or established source facts. Never assume unseen results. Decide the next research action. Return exactly STOP or one action ID as '
                     'the formatter answer, without other words. Include extra JSON fields reason and expected_result, describing the reason and what a selected action may reveal. STOP means do not retrieve more data. '
                     'Allowed action IDs: ' + ', '.join(ids))
        for action in visible['available_actions']:
            evidence.append({'id': 'action:' + action['action_id'], 'kind': 'observation',
                'source': 'saved action description', 'text': json.dumps(action, ensure_ascii=False, sort_keys=True)})
    return {'case_id': 'case', 'task_type': 'exploration', 'question': question,
            'thesis': {'text': visible['thesis'], 'version': 'retained-input', 'origin': 'research case; no new approval'},
            'evidence': evidence, 'required_questions': []}


def _decision_response(value: Any, allowed: set[str]) -> str:
    if not isinstance(value, dict) or not isinstance(value.get('choice'), str):
        raise ValueError('invalid source decision')
    choice = value['choice']
    if choice not in allowed | {'STOP'}:
        raise ValueError('source decision is not available')
    return choice


def run_case(checkpoint: dict, catalog: list[dict], arm: str,
             generate: Callable[[str, dict], dict]) -> dict:
    """Execute one assigned arm using fake or separately authorized model callback.

    B is one-shot per decision; B_self rechecks each decision. C uses all five
    faithful-style model roles for each decision and the final answer. Source
    retrieval is only local replay; no unchosen response enters any payload.
    """
    if arm not in {'B', 'B_self', 'C'}:
        raise ValueError('unknown arm')
    replay = ReplayCase(checkpoint, catalog)
    history, model_calls = [], 0
    def call(stage, payload):
        nonlocal model_calls
        model_calls += 1
        return generate(stage, copy.deepcopy(payload))
    try:
        while True:
            visible = replay.visible()
            available = {x['action_id'] for x in visible['available_actions']}
            if not available:
                break
            if arm == 'C':
                # Leave eight calls each for another two-branch decision and final answer.
                future_actions = min(visible['remaining_actions'] - 1, len(available) - 1)
                role_cap = min(23, 27 - model_calls - 8 * (future_actions + 1))
                if role_cap < 8:
                    return {'arm': arm, 'status': 'unknown', 'reason': 'episode_call_cap',
                            'result': None, 'history': history, 'calls': model_calls}
                out = Engine(call, EngineConfig(max_calls=role_cap, max_depth=2, beam_width=2, max_alternatives=2)).run(_task(visible, choosing=True))
                history.append({'kind': 'model_decision', 'outcome': out})
                if out['status'] not in {'proposal', 'incomplete'} or not isinstance(out.get('result'), dict):
                    return {'arm': arm, 'status': out['status'], 'result': None, 'history': history, 'calls': model_calls}
                choice = _decision_response({'choice': out['result']['answer']}, available)
            else:
                # Save input and response, including each recheck, as private trace.
                raw = call('source_decision', visible)
                history.append({'kind': 'model_decision', 'stage': 'source_decision', 'input': visible, 'output': copy.deepcopy(raw)})
                choice = _decision_response(raw, available)
                if arm == 'B_self':
                    review_input = {'visible': visible, 'previous_decision': raw}
                    check = call('source_decision_recheck', review_input)
                    history.append({'kind': 'model_decision', 'stage': 'source_decision_recheck', 'input': review_input, 'output': copy.deepcopy(check)})
                    choice = _decision_response(check, available)
            if choice == 'STOP':
                history.append({'kind': 'stop', 'origin': 'model'})
                break
            saved = replay.retrieve(choice)
            history.append({'kind': 'replay_retrieval', 'action_id': choice,
                            'response_sha256': saved['response_sha256'], 'simulated_not_provider_cost': True})
        final_task = _task(replay.visible(), choosing=False)
        if arm == 'C':
            remaining = min(23, 27 - model_calls)
            if remaining < 8:
                return {'arm': arm, 'status': 'unknown', 'reason': 'episode_call_cap',
                        'result': None, 'history': history, 'calls': model_calls}
            final = Engine(call, EngineConfig(max_calls=remaining, max_depth=2, beam_width=2, max_alternatives=2)).run(final_task)
            status, result = final['status'], final.get('result')
        else:
            final = _branch(arm, prepare_task(final_task), call, self_check=arm == 'B_self')
            status, result = final['status'], final.get('final_result')
        history.append({'kind': 'final', 'outcome': final})
        return {'arm': arm, 'status': status, 'result': result, 'history': history,
                'calls': model_calls, 'semantic_status': 'unreviewed',
                'simulated_replay_spent_micro_usd': replay.visible()['simulated_spent_micro_usd']}
    except Exception as exc:
        return {'arm': arm, 'status': 'technical_failure', 'reason': type(exc).__name__,
                'result': None, 'history': history, 'calls': model_calls, 'semantic_status': 'unreviewed'}
