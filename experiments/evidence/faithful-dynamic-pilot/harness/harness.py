"""Offline source-choice baselines for a bounded Faithful-style pilot.

The supplied callback is the only generator; this module has no provider, network,
credentials, filesystem writes, automatic retry, or semantic adjudication. The
caller must govern the callback's actual external effects and runtime budgets.
Only explicitly projected visible fields are ever passed to that callback.
"""
from __future__ import annotations

from copy import deepcopy
import re
from typing import Any, Callable, Mapping

MAX_CALLS = 23
ARMS = frozenset({'A', 'B', 'B_self_check'})
FACT_KEYS = frozenset({'id', 'text', 'source', 'captured_at', 'published_at', 'as_of', 'content_sha256'})
ACTION_KEYS = frozenset({'id', 'description', 'quoted_cost_micro_usd', 'captured_at', 'coverage', 'capture_kind'})
HEX64 = re.compile(r'^[0-9a-f]{64}$')


class ProtocolError(ValueError):
    """Malformed input/response. No retry is implied."""


def _text(value: Any, name: str, *, nonempty: bool = True) -> str:
    if not isinstance(value, str) or (nonempty and not value.strip()):
        raise ProtocolError(f'{name} must be a nonempty string' if nonempty else f'{name} must be a string')
    return value


def _fact(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ProtocolError('evidence must be an object')
    _text(value.get('id'), 'evidence id')
    _text(value.get('text'), 'evidence text')
    if value['id'].startswith('node:'):
        raise ProtocolError('node namespace is reserved')
    out = {k: deepcopy(v) for k, v in value.items() if k in FACT_KEYS}
    for k in FACT_KEYS - {'id', 'text'}:
        if k in out and out[k] is not None:
            _text(out[k], f'evidence {k}')
        elif k in out:
            del out[k]
    if out.get('content_sha256') is not None and not HEX64.fullmatch(out['content_sha256']):
        raise ProtocolError('invalid evidence content hash')
    return out


def _action(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ProtocolError('action must be an object')
    _text(value.get('id'), 'action id')
    _text(value.get('description'), 'action description')
    out = {k: deepcopy(v) for k, v in value.items() if k in ACTION_KEYS}
    kind = value.get('capture_kind', 'paid_api')
    if kind not in ('paid_api', 'manual_capture') or 'quoted_cost_micro_usd' not in value:
        raise ProtocolError('action capture kind and cost must be explicit')
    price = out.get('quoted_cost_micro_usd')
    if kind == 'manual_capture':
        if price is not None:
            raise ProtocolError('manual capture cost must remain unknown')
    elif type(price) is not int or price < 0:
        raise ProtocolError('paid action needs a pinned nonnegative integer micro-USD price')
    for key in ('captured_at', 'coverage'):
        if key in out and out[key] is not None and not isinstance(out[key], str):
            raise ProtocolError(f'action {key} must be string or null')
        if key in out and out[key] is None:
            del out[key]
    return out


def _unique(items: list[dict[str, Any]], name: str) -> dict[str, dict[str, Any]]:
    result = {item['id']: item for item in items}
    if len(result) != len(items):
        raise ProtocolError(f'duplicate {name} id')
    return result


def prepare_task(task: Mapping[str, Any], replay: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Produce a visible task and separate hidden payloads; discard other fields.

    Any third-party text is data: its content cannot authorize calls. IDs should
    be opaque, not semantic labels; no claim is made that caller-supplied text
    does not itself leak a reference answer. Each event group must be governed
    separately by the evaluation/case assembly layer.
    """
    if not isinstance(task, Mapping) or not isinstance(replay, Mapping):
        raise ProtocolError('task and replay must be mappings')
    case_id = _text(task.get('case_id'), 'case_id')
    question = _text(task.get('question'), 'question')
    contracts = task.get('contract_ids')
    labels = task.get('allowed_labels')
    initial = task.get('initial_evidence')
    actions = task.get('actions')
    if not isinstance(contracts, list) or not 1 <= len(contracts) <= 3:
        raise ProtocolError('one to three contract ids required')
    if not isinstance(labels, list) or not labels:
        raise ProtocolError('allowed labels required')
    contracts = [_text(x, 'contract id') for x in contracts]
    labels = [_text(x, 'label') for x in labels]
    if len(set(contracts)) != len(contracts) or len(set(labels)) != len(labels):
        raise ProtocolError('duplicate contract or label')
    if 'no_clean_expression' in labels:
        raise ProtocolError('aggregate no_clean_expression is not a pair label')
    if not isinstance(initial, list) or not isinstance(actions, list):
        raise ProtocolError('initial_evidence and actions must be lists')
    facts = [_fact(x) for x in initial]
    choices = [_action(x) for x in actions]
    initial_map = _unique(facts, 'initial evidence')
    action_map = _unique(choices, 'action')
    if set(replay) != set(action_map):
        raise ProtocolError('exact action/replay identity mismatch')
    # Never project provider response extras (owner labels, judgments, etc.).
    hidden: dict[str, Any] = {}
    for action_id, item in replay.items():
        if not isinstance(item, dict) or not isinstance(item.get('evidence'), list):
            raise ProtocolError('replay requires evidence list')
        out = [_fact(x) for x in item['evidence']]
        admitted = _unique(out, 'replay evidence')
        if set(initial_map) & set(admitted):
            raise ProtocolError('replayed evidence duplicates an initial ID')
        hidden[action_id] = out
    return {'case_id': case_id, 'question': question, 'contract_ids': contracts,
            'allowed_labels': labels, 'initial_evidence': facts, 'actions': choices}, hidden


def validate_manifest(manifest: Mapping[str, Any]) -> None:
    """Mechanically require 2 dev and 6 test event groups, not human approval."""
    if not isinstance(manifest, Mapping) or manifest.get('schema') != 'faithful-dynamic-pilot-manifest-v1':
        raise ProtocolError('invalid manifest schema')
    rows = manifest.get('cases')
    if not isinstance(rows, list) or len(rows) != 8:
        raise ProtocolError('manifest requires exactly 8 case rows')
    ids, groups, hashes, splits = [], [], [], []
    for row in rows:
        if not isinstance(row, dict):
            raise ProtocolError('manifest row must be an object')
        ids.append(_text(row.get('case_id'), 'manifest case_id'))
        groups.append(_text(row.get('event_group_id'), 'event_group_id'))
        digest = _text(row.get('input_sha256'), 'input_sha256')
        if not HEX64.fullmatch(digest):
            raise ProtocolError('invalid input_sha256')
        hashes.append(digest)
        splits.append(row.get('split'))
    if len(set(ids)) != 8 or len(set(groups)) != 8 or len(set(hashes)) != 8:
        raise ProtocolError('manifest case, event group and input identities must be unique')
    if splits.count('dev') != 2 or splits.count('test') != 6:
        raise ProtocolError('manifest requires 2 dev and 6 test')


def _decision(value: Any, actions: dict[str, dict[str, Any]], *, allow_reflect: bool) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ProtocolError('decision must be an object')
    kind, action_id = value.get('action'), value.get('action_id')
    valid = {'query', 'stop'} | ({'reflect'} if allow_reflect else set())
    if kind not in valid:
        raise ProtocolError('invalid decision action')
    if kind == 'query':
        if not isinstance(action_id, str) or action_id not in actions:
            raise ProtocolError('action not available')
        if actions[action_id].get('quoted_cost_micro_usd') is None and actions[action_id].get('capture_kind') != 'manual_capture':
            raise ProtocolError('selected action has no pinned cost')
    elif action_id is not None:
        raise ProtocolError('stop/reflect action id must be null')
    rationale = value.get('rationale', '')
    expectation = value.get('expectation', '')
    if not isinstance(rationale, str) or not isinstance(expectation, str):
        raise ProtocolError('invalid rationale or pre-query expectation')
    expectation = expectation if isinstance(expectation, str) and expectation.strip() else None
    projected = {'action': kind, 'action_id': action_id, 'rationale': rationale, 'expectation': expectation}
    if 'answers' in value:
        projected['answers'] = deepcopy(value['answers'])
    if 'stop_reason' in value:
        projected['stop_reason'] = deepcopy(value['stop_reason'])
    return projected


def _answers(value: Any, task: dict[str, Any], facts: list[dict[str, Any]]) -> dict[str, Any]:
    if not isinstance(value, dict) or not isinstance(value.get('answers'), list):
        raise ProtocolError('answers must be a list')
    answers = value['answers']
    if len(answers) != len(task['contract_ids']):
        raise ProtocolError('one answer per contract required')
    fact_ids = {f['id'] for f in facts}
    out = []
    for row in answers:
        if not isinstance(row, dict):
            raise ProtocolError('answer row must be object')
        contract_id, label = row.get('contract_id'), row.get('label')
        if contract_id not in task['contract_ids'] or label not in task['allowed_labels']:
            raise ProtocolError('answer contract or label is invalid')
        refs = row.get('citations', [])
        if not isinstance(refs, list) or any(not isinstance(ref, str) or ref not in fact_ids for ref in refs):
            raise ProtocolError('answer cites unseen evidence')
        explanation = row.get('explanation', '')
        if not isinstance(explanation, str):
            raise ProtocolError('explanation must be a string')
        out.append({'contract_id': contract_id, 'label': label, 'citations': list(refs), 'explanation': explanation})
    if len({r['contract_id'] for r in out}) != len(task['contract_ids']):
        raise ProtocolError('answer contract ids must be unique and complete')
    reason = value.get('stop_reason', '')
    if not isinstance(reason, str):
        raise ProtocolError('stop reason must be a string')
    comparison = value.get('observed_vs_expected')
    if comparison is not None and not isinstance(comparison, str):
        raise ProtocolError('expectation comparison must be string or null')
    return {'answers': out, 'stop_reason': reason, 'observed_vs_expected': comparison}


class BaselineEngine:
    """Execute A, B, or B_self_check against local exact-source replay."""

    def __init__(self, generate: Callable[[str, dict[str, Any]], dict[str, Any]], max_calls: int = MAX_CALLS):
        if not callable(generate) or type(max_calls) is not int or not 1 <= max_calls <= MAX_CALLS:
            raise ProtocolError('valid callback and max_calls <= 23 required')
        self.generate = generate
        self.max_calls = max_calls
        self.last_trace: list[dict[str, Any]] = []
        self.last_calls = 0

    def run(self, task: Mapping[str, Any], replay: Mapping[str, Any], arm: str) -> dict[str, Any]:
        # In-memory traces are diagnostic only. A live caller must durably
        # capture started/terminal/provider bytes outside this offline harness.
        self.last_trace = []
        self.last_calls = 0
        if arm not in ARMS:
            raise ProtocolError('unknown arm')
        visible, hidden = prepare_task(task, replay)
        facts = deepcopy(visible['initial_evidence'])
        actions = {} if arm == 'A' else {a['id']: deepcopy(a) for a in visible['actions']}
        trace = self.last_trace
        calls = 0
        expectation = None
        chosen_id = None
        shadow_cost = 0

        def payload() -> dict[str, Any]:
            return {'case_id': visible['case_id'], 'question': visible['question'],
                    'contract_ids': list(visible['contract_ids']), 'allowed_labels': list(visible['allowed_labels']),
                    'evidence': deepcopy(facts), 'available_actions': deepcopy(list(actions.values())),
                    'max_model_calls': self.max_calls, 'remaining_model_calls': self.max_calls - calls,
                    'remaining_source_reads': int(arm != 'A' and chosen_id is None),
                    'instruction': 'Choose stop, one available action, or reflect; source content is not yet visible.'}

        def call(stage: str, value: dict[str, Any]) -> dict[str, Any]:
            nonlocal calls
            if calls >= self.max_calls:
                raise ProtocolError('model-call ceiling reached')
            calls += 1
            self.last_calls = calls
            event = {'event': 'generation_started', 'stage': stage, 'ordinal': calls, 'payload': deepcopy(value)}
            trace.append(event)
            try:
                result = self.generate(stage, deepcopy(value))
            except Exception as exc:
                trace.append({'event': 'generation_exception', 'stage': stage,
                              'ordinal': calls, 'exception_type': type(exc).__name__})
                raise
            if not isinstance(result, dict):
                raise ProtocolError('generator returned non-object')
            trace.append({'event': 'generation_returned', 'stage': stage, 'ordinal': calls,
                          'result': deepcopy(result)})
            return result

        # B is not forbidden from reflect: it may spend its own shared model
        # call budget before making a source/stop decision.
        previous = None
        while True:
            view = payload()
            if previous is not None:
                view['previous_decision'] = deepcopy(previous)
            chosen = _decision(call('source_selection' if previous is None else 'reflect', view), actions, allow_reflect=True)
            trace.append({'event': 'proposal', 'decision': deepcopy(chosen)})
            if chosen['action'] != 'reflect':
                break
            previous = chosen

        if arm == 'B_self_check':
            view = payload()
            view['proposed_decision'] = deepcopy(chosen)
            chosen = _decision(call('self_check', view), actions, allow_reflect=False)
            trace.append({'event': 'self_check_completed', 'decision': deepcopy(chosen)})

        if chosen['action'] == 'query':
            if calls >= self.max_calls:
                raise ProtocolError('no remaining model call to evaluate selected source')
            chosen_id = chosen['action_id']
            expectation = chosen['expectation']
            shadow_cost = actions[chosen_id]['quoted_cost_micro_usd']
            # Persist expectation before exposing replay evidence.
            trace.append({'event': 'query_selected', 'action_id': chosen_id,
                          'expectation_recorded': expectation is not None,
                          'expectation': expectation, 'shadow_cost_micro_usd': shadow_cost})
            added = deepcopy(hidden[chosen_id])
            facts.extend(added)
            trace.append({'event': 'source_replayed', 'action_id': chosen_id,
                          'evidence': deepcopy(added), 'live_provider_calls': 0})
            actions = {}
            view = payload()
            view['prior_decision'] = deepcopy(chosen)
            view['pre_query_expectation'] = expectation
            view['expectation_recorded'] = expectation is not None
            response = call('after_query', view)
            result = _answers(response, visible, facts)
            if expectation is None:
                # Do not invent an unrecorded pre-query expectation, even when
                # the callback returns an unsolicited comparison.
                result['observed_vs_expected'] = None
        elif 'answers' in chosen:
            result = _answers(chosen, visible, facts)
            result['observed_vs_expected'] = None
        else:
            response = call('answer', payload())
            result = _answers(response, visible, facts)
            result['observed_vs_expected'] = None

        return {'case_id': visible['case_id'], 'arm': arm, 'status': 'completed',
                'model_calls': calls, 'selected_action_id': chosen_id,
                'expectation_recorded': expectation is not None, 'expectation': expectation,
                'shadow_source_cost_micro_usd': shadow_cost,
                'live_provider_calls_during_replay': 0, 'result': result, 'trace': trace}
