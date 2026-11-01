"""Versioned source-acquisition loop around the strict SI-style engine.

The caller supplies every model callback and provider controls. ReplayCase only
reads already captured local data. Model decisions remain proposals, not policy.
"""
from __future__ import annotations

import copy
import datetime as dt
import json
from typing import Callable, Any

from reasoning_engine.engine import EngineConfig, prepare_task
from reasoning_engine.replay_sources import ReplayCase, digest
from faithful_v3.engine import StrictEngine, _stop_kind

VERSION = 'faithful-v3-source-loop-2'


def _utc_timestamp(value: Any) -> str | None:
    """Recognize only complete UTC timestamps; free-text cutoffs stay unknown."""
    if not isinstance(value, str):
        return None
    try:
        parsed = dt.datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() != dt.timedelta(0):
        return None
    return value


def _factual_task(visible: dict, *, case_id: str) -> dict:
    target = visible['thesis']
    instructions = visible['question']
    question = target + '\n\nTask instructions: ' + instructions
    if visible.get('information_cutoff'):
        question += '\nInformation boundary: ' + visible['information_cutoff']
    evidence = []
    for item in visible['observed']:
        payload = item['response']['payload']
        entry = {'id': 'source:' + item['action_id'], 'kind': 'observation',
                 'source': 'saved response for ' + item['action_id'],
                 'raw_ref': 'sha256:' + item['response']['response_sha256'],
                 'text': json.dumps(payload, ensure_ascii=False, sort_keys=True)}
        provenance = payload.get('provenance', {}) if isinstance(payload, dict) else {}
        if not isinstance(provenance, dict):
            raise ValueError('source provenance must be an object')
        if isinstance(provenance, dict):
            for source_key, target_key in (('captured_at', 'captured_at_utc'),
                                           ('available_at', 'available_at_utc'),
                                           ('published_at', 'published_at_utc')):
                if source_key in provenance:
                    stamp = _utc_timestamp(provenance[source_key])
                    if stamp is None:
                        raise ValueError('source timestamp is not a complete UTC timestamp')
                    entry[target_key] = stamp
        evidence.append(entry)
    return {'case_id': case_id, 'task_type': 'exploration', 'question': question,
            'as_of_utc': _utc_timestamp(visible.get('information_cutoff')),
            'thesis': {'text': target, 'version': 'retained-input', 'origin': 'research case; no new approval'},
            'evidence': evidence,
            'required_questions': [{'id': 'user-target', 'question': target, 'evidence_ids': []}]}


def _decision(raw: Any, allowed: set[str]) -> str:
    if not isinstance(raw, dict) or not isinstance(raw.get('choice'), str):
        raise ValueError('source decision must be an object with a choice')
    if not isinstance(raw.get('reason'), str) or not raw['reason'].strip():
        raise ValueError('source decision requires a model-authored reason')
    if not isinstance(raw.get('expected_result'), str) or not raw['expected_result'].strip():
        raise ValueError('source decision requires a model-authored expected result')
    if raw['choice'] not in allowed | {'STOP', 'UNKNOWN'}:
        raise ValueError('source decision is not available')
    return raw['choice']


def run_case(checkpoint: dict, catalog: list[dict], generate: Callable[[str, dict], dict],
             *, max_calls: int = 26, max_depth: int = 2, beam_width: int = 2,
             max_alternatives: int = 2) -> dict:
    """Run a new offline replay case; callbacks can be scripted or separately authorized.

    Source decisions and SI are separate model roles. No action description is
    admitted into the factual evidence pool. A STOP rationale remains an
    explicitly unverified candidate for Selection to rederive from sources.
    """
    if not callable(generate) or type(max_calls) is not int or max_calls < 1:
        raise ValueError('valid callback and positive call budget required')
    replay = ReplayCase(checkpoint, catalog)
    case_id = checkpoint['case_id']
    case_catalog = [copy.deepcopy(item) for item in catalog if item.get('case_id') == case_id]
    history: list[dict] = []
    findings: list[dict] = []
    model_calls = 0

    def outcome(status: str, reason: str, result=None, **extra):
        current = replay.visible()
        timestamp_presence = {}
        for item in current['observed']:
            payload = item['response']['payload']
            provenance = payload.get('provenance', {}) if isinstance(payload, dict) else {}
            stamp = provenance.get('captured_at') if isinstance(provenance, dict) else None
            timestamp_presence['source:' + item['action_id']] = 'known_utc' if _utc_timestamp(stamp) else 'unknown'
        result_packet = {'version': VERSION, 'arm': 'C_v3_feedback_v2', 'status': status, 'reason': reason,
                'result': copy.deepcopy(result), 'history': copy.deepcopy(history),
                'calls': model_calls, 'semantic_status': 'unreviewed',
                'case_id': case_id, 'input_version': checkpoint['input_version'],
                'case_catalog_sha256': digest(case_catalog),
                'user_target': current['thesis'], 'captured_timestamp_presence': timestamp_presence,
                'cutoff_mode': ('structured_utc' if _utc_timestamp(current.get('information_cutoff'))
                                else 'unstructured_or_missing_not_enforced'),
                'simulated_replay_spent_micro_usd': current['simulated_spent_micro_usd'], **extra}
        if status in {'unknown', 'technical_failure'}:
            explanation = copy.deepcopy(extra.get('unknown_explanation'))
            if not isinstance(explanation, dict):
                explanation = {'status': status, 'stop_reason': reason, 'stop_kind': _stop_kind(status, reason),
                               'unresolved_questions': [{'id': 'user-target', 'question': current['thesis']}],
                               'model_assessments': [],
                               'scope_note': 'Only saved responses available in this run are recorded.'}
            explanation['available_saved_sources'] = [
                {'id': 'source:' + item['action_id'],
                 'raw_ref': 'sha256:' + item['response']['response_sha256']}
                for item in current['observed']
            ]
            if reason == 'source_decision_uncertain':
                last = next((x for x in reversed(history) if x.get('kind') == 'model_decision'
                             and x.get('output', {}).get('choice') == 'UNKNOWN'), None)
                if last:
                    explanation['source_decision'] = {
                        'reason': last['output']['reason'], 'origin': 'model_unverified',
                        'input_sha256': last['callback_input_sha256'],
                        'output_sha256': last['callback_output_sha256'],
                    }
            result_packet['unknown_explanation'] = explanation
        return result_packet

    def call(stage, payload):
        nonlocal model_calls
        if model_calls >= max_calls:
            raise RuntimeError('episode_call_cap')
        model_calls += 1
        return generate(stage, copy.deepcopy(payload))

    try:
        while True:
            visible = replay.visible()
            # Enforce any structured cutoff before a model can observe data;
            # unstructured cutoff text and absent timestamps remain explicit unknowns.
            prepare_task(_factual_task(visible, case_id=case_id))
            allowed = {x['action_id'] for x in visible['available_actions']}
            if not allowed:
                history.append({'kind': 'source_options_exhausted', 'origin': 'structural'})
                break
            # One decision plus the minimum SI path (selection/inference/halter/value/formatter).
            if max_calls - model_calls < 6:
                return outcome('unknown', 'episode_call_cap')
            try:
                raw = call('source_decision', visible)
            except Exception as exc:
                history.append({'kind': 'model_decision_failed', 'stage': 'source_decision',
                                'input': copy.deepcopy(visible), 'exception_type': type(exc).__name__})
                raise
            history.append({'kind': 'model_decision', 'stage': 'source_decision',
                            'input': copy.deepcopy(visible), 'output': copy.deepcopy(raw),
                            'callback_input_sha256': digest(visible),
                            'callback_output_sha256': digest(raw)})
            choice = _decision(raw, allowed)
            if choice == 'UNKNOWN':
                return outcome('unknown', 'source_decision_uncertain')
            if choice == 'STOP':
                # The context IDs record what the model could see, not proof that
                # each item supports the model's explanation.
                findings.append({'id': f'decision-note:{len(history)}', 'text': raw['reason'],
                    'origin': 'model_source_decision_unverified',
                    'context_evidence_ids': ['source:' + x['action_id'] for x in visible['observed']],
                    'visible_action_ids': sorted(allowed),
                    'decision_input_sha256': digest(visible), 'decision_output_sha256': digest(raw),
                    'semantic_status': 'unverified'})
                history.append({'kind': 'stop', 'origin': 'model', 'meaning': 'stop_source_acquisition',
                                'decision_note_id': findings[-1]['id']})
                break
            saved = replay.retrieve(choice)
            capture_ref = next(x['capture_ref'] for x in checkpoint['input']['tool_catalog'] if x['action_id'] == choice)
            history.append({'kind': 'replay_retrieval', 'action_id': choice,
                            'capture_ref': capture_ref, 'response_sha256': saved['response_sha256'],
                            'simulated_not_provider_cost': True})
        factual = _factual_task(replay.visible(), case_id=case_id)
        remaining = max_calls - model_calls
        if remaining < 5:
            return outcome('unknown', 'episode_call_cap')
        final = StrictEngine(call, EngineConfig(max_calls=remaining, max_depth=max_depth,
                            beam_width=beam_width, max_alternatives=max_alternatives),
                            candidate_findings=findings).run(factual)
        history.append({'kind': 'final', 'outcome': final})
        extra = {'unknown_explanation': final['unknown_explanation']} if 'unknown_explanation' in final else {}
        return outcome(final['status'], final['reason'], final.get('result'), **extra)
    except TimeoutError:
        return outcome('unknown', 'source_callback_effect_uncertain:TimeoutError')
    except Exception as exc:
        return outcome('technical_failure', type(exc).__name__)
