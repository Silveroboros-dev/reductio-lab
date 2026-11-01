"""Offline, injected-model Faithful-style controller for a bounded research pilot.

This module has no provider, credential or network client. Callback outputs are
model proposals; ID and schema checks do not establish semantic correctness.
"""
from __future__ import annotations

import copy
import math
import re
from dataclasses import dataclass, field
from typing import Any, Callable

MAX_CALLS = 23
BEAM_WIDTH = 2
PROPOSALS_PER_BRANCH = 2
MAX_DEPTH = 2


class InvalidOutput(ValueError):
    pass


class BudgetExhausted(Exception):
    pass


def _text(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise InvalidOutput(f"{field_name} must be a non-empty string")
    return value


def _evidence(item: Any) -> dict[str, Any]:
    """Project an admitted source item; arbitrary hidden metadata never passes."""
    if not isinstance(item, dict):
        raise InvalidOutput('evidence must be an object')
    identity = _text(item.get('id'), 'evidence.id')
    if identity.startswith('node:'):
        raise InvalidOutput('node namespace is reserved')
    result = {'id': identity, 'text': _text(item.get('text'), 'evidence.text')}
    # Known provenance is data, not a truth or completeness assertion.
    for key in ('source', 'captured_at', 'published_at', 'as_of', 'content_sha256'):
        value = item.get(key)
        if value is not None:
            result[key] = _text(value, f'evidence.{key}')
    if 'content_sha256' in result and not re.fullmatch(r'[0-9a-f]{64}', result['content_sha256']):
        raise InvalidOutput('content_sha256 must be a lowercase SHA-256-shaped string')
    return result


def _action(item: Any) -> dict[str, Any]:
    if not isinstance(item, dict):
        raise InvalidOutput('action must be an object')
    result = {'id': _text(item.get('id'), 'action.id'),
              'description': _text(item.get('description'), 'action.description')}
    kind = item.get('capture_kind', 'paid_api')
    if kind not in ('paid_api', 'manual_capture') or 'quoted_cost_micro_usd' not in item:
        raise InvalidOutput('action capture kind and quoted cost must be explicit')
    if kind == 'manual_capture':
        if item['quoted_cost_micro_usd'] is not None:
            raise InvalidOutput('manual capture cost is unknown, not zero or a quote')
        result['capture_kind'] = kind
    elif type(item['quoted_cost_micro_usd']) is not int or item['quoted_cost_micro_usd'] < 0:
        raise InvalidOutput('each paid action needs an explicit non-negative quoted cost')
    elif 'capture_kind' in item:
        result['capture_kind'] = kind
    result['quoted_cost_micro_usd'] = item['quoted_cost_micro_usd']
    for key in ('captured_at', 'coverage'):
        if key in item and item[key] is not None:
            val = item[key]
            if not isinstance(val, str):
                raise InvalidOutput(f'action.{key} must be a string')
            result[key] = val
    return result


def _unique(items: list[dict[str, Any]], kind: str) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for item in items:
        if item['id'] in result:
            raise InvalidOutput(f'duplicate {kind} id')
        result[item['id']] = item
    return result


@dataclass
class Branch:
    branch_id: str
    # A branch sees common visible evidence and only its own derived nodes.
    nodes: dict[str, dict[str, Any]] = field(default_factory=dict)
    trace: list[dict[str, Any]] = field(default_factory=list)
    score: float = 0.0
    halted: bool = False
    latest: str | None = None


class Engine:
    """One bounded case; callers manage provider access and durable effect logs.

    `generate(stage, projection)` is invoked once per requested generation.
    The callback must supply valid JSON-like objects under the stage schemas.
    `replay` is separate from model-visible case fields and never projected before
    the corresponding source action is selected. No labels/reviewer references
    are passed to the callback. This engine alone does not authorize any API call.
    """
    def __init__(self, generate: Callable[[str, dict[str, Any]], dict[str, Any]], *, max_calls: int = MAX_CALLS):
        if not callable(generate) or type(max_calls) is not int or not 1 <= max_calls <= MAX_CALLS:
            raise ValueError('a callback and 1..23 generation cap are required')
        self.generate = generate
        self.max_calls = max_calls
        self.calls = 0
        self.events: list[dict[str, Any]] = []
        self._node_counter = 0

    def _call(self, stage: str, payload: dict[str, Any]) -> dict[str, Any]:
        if self.calls >= self.max_calls:
            raise BudgetExhausted()
        self.calls += 1
        # Copy before and after so callbacks cannot mutate the controller state.
        projection = copy.deepcopy(payload)
        self.events.append({'event': 'model_started', 'stage': stage, 'ordinal': self.calls,
                            'projection': copy.deepcopy(projection)})
        try:
            answer = self.generate(stage, projection)
        except Exception as exc:
            # Never convert a provider timeout or ambiguous effect into an
            # ordinary per-case result. The injected wrapper owns the effect
            # journal and must decide whether the entire run must stop.
            self.events.append({'event': 'callback_raised', 'stage': stage,
                                'ordinal': self.calls, 'error_type': type(exc).__name__})
            raise
        if not isinstance(answer, dict):
            raise InvalidOutput(f'{stage} output must be an object')
        result = copy.deepcopy(answer)
        self.events.append({'event': 'model_returned', 'stage': stage, 'ordinal': self.calls,
                            'output': result})
        return result

    def run(self, task: dict[str, Any], replay: dict[str, Any]) -> dict[str, Any]:
        if self.calls or self.events:
            raise ValueError('an Engine instance handles exactly one case')
        try:
            return self._run(task, replay)
        except BudgetExhausted:
            return self._outcome('unknown', 'generation_cap_exhausted')
        except InvalidOutput as exc:
            return self._outcome('technical_failure', f'{type(exc).__name__}: {exc}')

    def _outcome(self, status: str, reason: str, **extra: Any) -> dict[str, Any]:
        self.events.append({'event': 'stopped', 'status': status, 'reason': reason})
        return {'status': status, 'reason': reason, 'calls': self.calls,
                'events': copy.deepcopy(self.events), **copy.deepcopy(extra)}

    def _run(self, task: dict[str, Any], replay: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(task, dict) or not isinstance(replay, dict):
            raise InvalidOutput('task and replay must be objects')
        case_id = _text(task.get('case_id'), 'case_id')
        question = _text(task.get('question'), 'question')
        contracts = task.get('contract_ids')
        labels = task.get('allowed_labels')
        if (not isinstance(contracts, list) or not 1 <= len(contracts) <= 3 or
                any(not isinstance(x, str) or not x.strip() for x in contracts) or len(set(contracts)) != len(contracts)):
            raise InvalidOutput('one to three unique contract IDs are required')
        if (not isinstance(labels, list) or not labels or
                any(not isinstance(x, str) or not x.strip() for x in labels) or
                len(set(labels)) != len(labels) or 'no_clean_expression' in labels):
            raise InvalidOutput('pair labels must be non-empty unique values; aggregate no_clean is not a pair label')
        raw_initial, raw_actions = task.get('initial_evidence'), task.get('actions')
        if not isinstance(raw_initial, list) or not isinstance(raw_actions, list):
            raise InvalidOutput('initial evidence and action catalog must be arrays')
        visible = _unique([_evidence(x) for x in raw_initial], 'evidence')
        actions = _unique([_action(x) for x in raw_actions], 'action')
        if set(replay) != set(actions):
            raise InvalidOutput('replay must bind exactly the declared action catalog')
        # Validate each hidden replay structurally before any model call. Its
        # bytes are not projected, and matching IDs in different alternatives
        # are permitted because only one alternative can be selected.
        for hidden in replay.values():
            if not isinstance(hidden, dict) or not isinstance(hidden.get('evidence'), list):
                raise InvalidOutput('every replay must provide an evidence array')
            projected = _unique([_evidence(x) for x in hidden['evidence']], 'replayed evidence')
            if set(visible) & set(projected):
                raise InvalidOutput('replayed evidence duplicates a visible ID')
        self.events.append({'event': 'case_started', 'case_id': case_id,
                            'contract_ids': copy.deepcopy(contracts)})

        source = self._call('source_selection', {
            'case_id': case_id, 'question': question, 'contract_ids': contracts,
            'allowed_labels': labels, 'evidence': list(visible.values()),
            'available_actions': list(actions.values()),
            'max_model_calls': self.max_calls,
            'remaining_model_calls': self.max_calls - self.calls,
            'remaining_source_reads': 1,
            'instruction': 'Choose stop or one available action; source content is not yet visible. Return action, action_id, rationale, expectation; use empty strings when no rationale or expectation is recorded.'})
        choice = source.get('action')
        if choice not in ('query', 'stop'):
            raise InvalidOutput('source selection action must be query or stop')
        action_id = source.get('action_id')
        rationale = source.get('rationale', '')
        expectation = source.get('expectation', '')
        if not isinstance(rationale, str) or not isinstance(expectation, str):
            raise InvalidOutput('source rationale and expectation must be strings when present')
        # This is logged before reading replay: a missing expectation remains
        # missing and can never be reconstructed from the returned evidence.
        self.events.append({'event': 'source_decision', 'action': choice, 'action_id': action_id,
                            'rationale': rationale, 'expectation': expectation})
        if choice == 'stop':
            if action_id is not None:
                raise InvalidOutput('stop must not name an action')
            self.events.append({'event': 'source_stopped'})
        else:
            if not isinstance(action_id, str) or action_id not in actions:
                raise InvalidOutput('selected source action is not available')
            selected = replay[action_id]
            if not isinstance(selected, dict) or not isinstance(selected.get('evidence'), list):
                raise InvalidOutput('selected replay must provide an evidence array')
            admitted = _unique([_evidence(x) for x in selected['evidence']], 'replayed evidence')
            if set(visible) & set(admitted):
                raise InvalidOutput('replayed evidence duplicates a visible ID')
            visible.update(admitted)
            self.events.append({'event': 'source_replayed', 'action_id': action_id,
                                'evidence_ids': list(admitted),
                                'capture_kind': actions[action_id].get('capture_kind', 'paid_api'),
                                'quoted_cost_micro_usd': actions[action_id].get('quoted_cost_micro_usd'),
                                'evidence': list(admitted.values())})

        common = copy.deepcopy(visible)
        beam = [Branch(branch_id='root', nodes=copy.deepcopy(common))]
        for depth in range(1, MAX_DEPTH + 1):
            candidates: list[Branch] = []
            for branch in beam:
                if branch.halted:
                    candidates.append(branch)
                    continue
                selected = self._call('selection', {
                    'question': question, 'available_statements': list(branch.nodes.values()),
                    'instruction': 'Return up to two distinct nonempty lists of visible statement IDs.'})
                alternatives = selected.get('alternatives')
                if not isinstance(alternatives, list) or len(alternatives) > PROPOSALS_PER_BRANCH:
                    raise InvalidOutput('selection must contain at most two alternatives')
                seen: set[tuple[str, ...]] = set()
                for alternative_index, ids in enumerate(alternatives):
                    if (not isinstance(ids, list) or not ids or
                            any(not isinstance(x, str) or not x for x in ids) or len(ids) != len(set(ids))):
                        raise InvalidOutput('each selection must contain distinct IDs')
                    if any(x not in branch.nodes for x in ids):
                        raise InvalidOutput('selection refers to unseen or another branch ID')
                    signature = tuple(sorted(ids))
                    if signature in seen:
                        self.events.append({'event': 'duplicate_selection_skipped', 'branch_id': branch.branch_id,
                                            'depth': depth, 'selected_ids': ids})
                        continue
                    seen.add(signature)
                    inference = self._call('inference', {
                        'selected_texts': [branch.nodes[x]['text'] for x in ids]})
                    conclusion = _text(inference.get('conclusion'), 'inference.conclusion')
                    self._node_counter += 1
                    node_id = f'node:{self._node_counter:04d}'
                    path_id = f'{branch.branch_id}.{depth}.{alternative_index + 1}'
                    trace = copy.deepcopy(branch.trace) + [{'selected_ids': ids,
                        'conclusion_id': node_id, 'conclusion': conclusion}]
                    new_nodes = copy.deepcopy(branch.nodes)
                    new_nodes[node_id] = {'id': node_id, 'text': conclusion}
                    halt = self._call('halter', {'question': question, 'current_inference': conclusion,
                        'instruction': 'Is this inference sufficient to answer? Return sufficient: boolean.'})
                    if type(halt.get('sufficient')) is not bool:
                        raise InvalidOutput('halter sufficient must be boolean')
                    value = self._call('value', {'question': question,
                        'visible_evidence': list(common.values()), 'trace': trace,
                        'instruction': 'Return a comparable value score between 0 and 1 for this partial trace.'})
                    score = value.get('score')
                    if type(score) not in (int, float) or not math.isfinite(score) or not 0 <= score <= 1:
                        raise InvalidOutput('value score must be a finite number in 0..1')
                    candidates.append(Branch(branch_id=path_id, nodes=new_nodes, trace=trace,
                                             score=float(score), halted=halt['sufficient'], latest=node_id))
                    self.events.append({'event': 'step_proposed', 'branch_id': path_id, 'depth': depth,
                        'selected_ids': ids, 'conclusion_id': node_id, 'halted': halt['sufficient'],
                        'value_score': float(score)})
            if not candidates:
                return self._outcome('unknown', 'no_valid_candidate')
            # Stable tie-break makes bookkeeping reproducible, not semantic truth.
            candidates.sort(key=lambda b: (-b.score, b.branch_id))
            beam = candidates[:BEAM_WIDTH]
            self.events.append({'event': 'beam_selected', 'depth': depth,
                                'branch_ids': [b.branch_id for b in beam]})
            if all(b.halted for b in beam):
                break
        ready = [b for b in beam if b.halted and b.latest is not None]
        if not ready:
            return self._outcome('unknown', 'reasoning_depth_exhausted')
        best = ready[0]
        # Formatter is deliberately denied the question, raw source context,
        # source catalog, discarded branches and reviewer references.
        formatted = self._call('formatter', {
            'current_inference': best.nodes[best.latest]['text'],
            'contract_ids': contracts, 'allowed_labels': labels,
            'instruction': 'Format only from the inference; return answers as [{contract_id, label}].'})
        answers = formatted.get('answers')
        if not isinstance(answers, list):
            raise InvalidOutput('formatter answers must be an array')
        if any(not isinstance(a, dict) or not isinstance(a.get('contract_id'), str) or
               not isinstance(a.get('label'), str) for a in answers):
            raise InvalidOutput('formatter answer must have contract_id and label strings')
        answer_ids = [a['contract_id'] for a in answers]
        if len(answer_ids) != len(set(answer_ids)) or any(x not in contracts for x in answer_ids):
            raise InvalidOutput('formatter emitted duplicate or unavailable contract IDs')
        if any(a['label'] not in labels for a in answers):
            raise InvalidOutput('formatter emitted an unavailable pair label')
        if set(answer_ids) != set(contracts):
            return self._outcome('unknown', 'incomplete_contract_vector',
                                 selected_trace=best.trace, proposed_answers=answers)
        return self._outcome('proposal', 'model_proposal_requires_semantic_review',
                             selected_trace=best.trace, proposed_answers=answers)
