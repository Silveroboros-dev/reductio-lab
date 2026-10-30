"""Strict-input SI-style engine with bounded, preserved reasoning branches.

Selection and Halter see the user target. Inference receives only selected
premises; Formatter receives only the final inference and allowable source IDs.
None of these structural checks establishes semantic entailment or truth.
"""
from __future__ import annotations

import copy
import math
from typing import Any, Callable

from reasoning_engine.engine import (BudgetExhausted, Engine, EngineConfig, InvalidOutput,
                                     _Branch, _ancestry, prepare_task)

VERSION = 'faithful-v3-strict-1'


class StrictEngine(Engine):
    def __init__(self, generate: Callable[[str, dict], dict], config: EngineConfig | None = None,
                 *, candidate_findings: list[dict] | None = None):
        super().__init__(generate, config)
        self.candidate_findings = copy.deepcopy(candidate_findings or [])
        self._ready: list[_Branch] = []
        self._active_final: _Branch | None = None

    def _outcome(self, task: dict, status: str, reason: str, **extra: Any) -> dict:
        out = super()._outcome(task, status, reason, **extra)
        out['version'] = VERSION
        # The user's target is metadata, not an established source premise.
        out['evidence'] = copy.deepcopy(task['evidence'])
        out['user_target'] = copy.deepcopy(task.get('thesis'))
        out['candidate_findings'] = copy.deepcopy(self.candidate_findings)
        return out

    def _unknown(self, task: dict, reason: str) -> dict:
        return self._outcome(task, 'unknown', reason, result=None,
            coverage=[{'question_id': q['id'], 'status': 'not_assessed',
                       'reason': 'No answerable inference selected; see recorded model halt events',
                       'assessment_origin': 'structural'}
                      for q in task['required_questions']],
            selected_trace=[], branches=copy.deepcopy(self._branches))

    def run(self, task: dict) -> dict:
        """Retain completed branch evidence even if the final callback fails."""
        if self._used:
            raise ValueError('engine instances are single use')
        self._used = True
        prepared = prepare_task(task)
        try:
            return self._run(prepared)
        except BudgetExhausted:
            status, reason = 'unknown', 'generation_cap_exhausted'
        except TimeoutError:
            status, reason = 'unknown', 'callback_effect_uncertain:TimeoutError'
        except InvalidOutput as exc:
            status, reason = 'technical_failure', str(exc)
        except Exception as exc:
            status, reason = 'technical_failure', 'callback_failed:' + type(exc).__name__
        partial = []
        branch_id = None
        preserved = self._active_final
        if preserved is None and self._ready:
            preserved = sorted(self._ready, key=lambda b: (-b.score, b.ident))[0]
        if preserved is not None and preserved.latest is not None:
            partial, _, _ = _ancestry(preserved.steps, preserved.latest)
            branch_id = preserved.ident
        return self._outcome(prepared, status, reason, result=None,
            coverage=[{'question_id': q['id'], 'status': 'not_assessed',
                       'reason': 'Final answer was not produced', 'assessment_origin': 'structural'}
                      for q in prepared['required_questions']],
            selected_trace=[], partial_trace=partial, selected_branch=branch_id,
            branches=copy.deepcopy(self._branches))

    def _run(self, task: dict) -> dict:
        if not task['required_questions']:
            return self._unknown(task, 'required_target_missing')
        # The current small slice handles one literal user target; it never
        # copies a single model judgment across multiple distinct obligations.
        if len(task['required_questions']) != 1:
            return self._unknown(task, 'multiple_targets_not_supported')
        target = task['required_questions'][0]['question']
        if target not in task['question'] or ('thesis' in task and task['thesis']['text'] != target):
            return self._unknown(task, 'user_target_not_bound_to_question')
        # Unlike v1, a user question/thesis never becomes a selectable fact.
        common = {x['id']: copy.deepcopy(x) for x in task['evidence']}
        if not common:
            return self._unknown(task, 'no_source_evidence')
        beam = [_Branch('root', copy.deepcopy(common))]
        budget_pruned = False
        for depth in range(1, self.config.max_depth + 1):
            candidates: list[_Branch] = []
            for branch in beam:
                if branch.halted:
                    candidates.append(branch)
                    continue
                # Selection + inference + halter + value + final formatter.
                if self.config.max_calls - self.calls < 5:
                    budget_pruned = True
                    self.events.append({'event': 'budget_pruned', 'branch_id': branch.ident, 'depth': depth})
                    continue
                selected = self._call('selection', {
                    'question': task['question'], 'task_type': task['task_type'],
                    'as_of_utc': task['as_of_utc'], 'required_questions': copy.deepcopy(task['required_questions']),
                    'available_statements': list(branch.nodes.values()),
                    'candidate_findings': copy.deepcopy(self.candidate_findings),
                }, branch.ident)
                selection_call = self.calls
                alternatives = selected.get('alternatives')
                if not isinstance(alternatives, list) or len(alternatives) > self.config.max_alternatives:
                    raise InvalidOutput('invalid selection alternatives')
                signatures = set()
                for position, ids in enumerate(alternatives, 1):
                    if (not isinstance(ids, list) or not ids or any(not isinstance(x, str) or not x for x in ids)
                            or len(ids) != len(set(ids)) or any(x not in branch.nodes for x in ids)):
                        raise InvalidOutput('selection has unknown, duplicate or empty IDs')
                    signature = tuple(sorted(ids))
                    if signature in signatures:
                        continue
                    signatures.add(signature)
                    # Reserve a formatter call even when exploring alternatives.
                    if self.config.max_calls - self.calls < 4:
                        budget_pruned = True
                        self.events.append({'event': 'budget_pruned', 'branch_id': branch.ident,
                                            'depth': depth, 'alternative': position})
                        break
                    texts = [{'text': branch.nodes[x]['text'],
                              'source': branch.nodes[x].get('source', 'model inference, not source fact'),
                              'kind': branch.nodes[x].get('kind', 'derived_claim')} for x in ids]
                    inference = self._call('inference', {'selected_texts': texts}, branch.ident)
                    inference_call = self.calls
                    conclusion = inference.get('conclusion')
                    if not isinstance(conclusion, str) or not conclusion.strip():
                        raise InvalidOutput('inference conclusion must be nonempty')
                    self._next_node += 1
                    node_id = f'node:{self._next_node:04d}'
                    ident = f'{branch.ident}.{depth}.{position}'
                    steps = copy.deepcopy(branch.steps) + [{
                        'selected_ids': list(ids), 'conclusion_id': node_id, 'conclusion': conclusion,
                        'depth': depth, 'verification': 'unreviewed',
                        'selection_call_ordinal': selection_call, 'inference_call_ordinal': inference_call,
                    }]
                    nodes = copy.deepcopy(branch.nodes)
                    nodes[node_id] = {'id': node_id, 'text': conclusion, 'kind': 'derived_claim',
                                      'source': 'model inference, not source fact'}
                    halt = self._call('halter', {'question': task['question'], 'current_inference': conclusion}, ident)
                    halter_call = self.calls
                    if type(halt.get('sufficient')) is not bool or not isinstance(halt.get('reason'), str) or not halt['reason'].strip():
                        raise InvalidOutput('halter requires boolean sufficient and nonempty reason')
                    value = self._call('value', {'question': task['question'], 'task_type': task['task_type'],
                        'as_of_utc': task['as_of_utc'], 'visible_evidence': list(common.values()), 'trace': steps}, ident)
                    value_call = self.calls
                    score = value.get('score')
                    if type(score) not in (int, float) or not math.isfinite(score) or not 0 <= score <= 1:
                        raise InvalidOutput('value score must be finite in [0,1]')
                    candidate = _Branch(ident, nodes, steps, float(score), halt['sufficient'], node_id)
                    candidates.append(candidate)
                    self.events.append({'event': 'step_proposed', 'branch_id': ident, 'depth': depth,
                        'selected_ids': list(ids), 'conclusion_id': node_id, 'sufficient': halt['sufficient'],
                        'halter_reason': halt['reason'], 'value_score': float(score),
                        'selection_call_ordinal': selection_call, 'inference_call_ordinal': inference_call,
                        'halter_call_ordinal': halter_call, 'value_call_ordinal': value_call})
                    self._branches.append({'branch_id': ident, 'steps': copy.deepcopy(steps),
                                           'score': float(score), 'halted': halt['sufficient']})
                    if candidate.halted:
                        self._ready.append(copy.deepcopy(candidate))
            if not candidates:
                if self._ready:
                    break
                return self._unknown(task, 'generation_cap_exhausted' if budget_pruned else 'no_valid_candidate')
            candidates.sort(key=lambda b: (-b.score, b.ident))
            beam = candidates[:self.config.beam_width]
            self.events.append({'event': 'beam_selected', 'depth': depth, 'branch_ids': [b.ident for b in beam]})
            if all(b.halted for b in beam):
                break
        # Retain fully evaluated halted candidates even if a higher-scoring
        # incomplete branch displaced them from the active beam.
        ready = sorted((b for b in self._ready if b.latest is not None),
                       key=lambda b: (-b.score, b.ident))
        if not ready:
            return self._unknown(task, 'generation_cap_exhausted' if budget_pruned else 'reasoning_depth_exhausted')
        best = ready[0]
        self._active_final = copy.deepcopy(best)
        trace, leaves, effective_depth = _ancestry(best.steps, best.latest)
        selected_evidence = [copy.deepcopy(item) for item in task['evidence'] if item['id'] in leaves]
        if not selected_evidence:
            return self._unknown(task, 'no_selected_source_ancestry')
        # Only the final inference and opaque source IDs enter answer generation.
        raw = self._call('formatter', {'final_inference': best.nodes[best.latest]['text'],
                                      'allowed_citation_ids': sorted(leaves)}, best.ident)
        answer, citations = raw.get('answer'), raw.get('citations')
        if not isinstance(answer, str) or not answer.strip():
            raise InvalidOutput('formatter answer must be nonempty')
        if (not isinstance(citations, list) or not citations or any(not isinstance(x, str) for x in citations)
                or len(set(citations)) != len(citations) or any(x not in leaves for x in citations)):
            raise InvalidOutput('formatter citations must be nonempty unique selected evidence IDs')
        # A Halter decision is model-origin evidence, not a semantic verdict.
        ready_event = next(e for e in reversed(self.events) if e.get('event') == 'step_proposed' and e['branch_id'] == best.ident)
        coverage = [{'question_id': q['id'], 'status': 'model_says_answerable',
                     'reason': ready_event['halter_reason'], 'assessment_origin': 'model_unverified'}
                    for q in task['required_questions']]
        return self._outcome(task, 'proposal', 'model_proposal_requires_semantic_review', result=raw,
            coverage=coverage, selected_trace=trace, selected_branch=best.ident,
            inference_dependency_depth=effective_depth, selected_evidence=selected_evidence,
            branches=copy.deepcopy(self._branches))
