"""Offline tests of strict role projections and bounded source replay.

All source and role responses below are scripted fixtures; no live model calls.
"""
from __future__ import annotations

import copy
import json
import unittest

from faithful_v3.action_case import run_case
from faithful_v3.engine import StrictEngine
from faithful_v3.prompts import build_request
from reasoning_engine.engine import EngineConfig
from reasoning_engine.replay_sources import digest

def checkpoint_fixture(*, with_initial=False):
    task = {'thesis': 'USER_TARGET_SENTINEL: find X', 'task': 'Use the saved fragments',
            'information_cutoff': '2026-10-29T00:00:00Z', 'replay_max_actions': 2,
            'replay_max_simulated_micro_usd': 20,
            'tool_catalog': [{'action_id': 'a', 'description': 'read A', 'quoted_micro_usd': 1, 'capture_ref': 'ra'},
                             {'action_id': 'b', 'description': 'read B', 'quoted_micro_usd': 1, 'capture_ref': 'rb'}],
            'initial_evidence': [], 'preconsumed_action_ids': []}
    if with_initial:
        payload = {'text': 'initial observed text'}
        task['initial_evidence'] = [{'action_id': 'initial', 'response': {'payload': payload, 'response_sha256': digest(payload)}}]
        task['preconsumed_action_ids'] = ['initial']
    checkpoint = {'case_id': 'fixture', 'input': task, 'input_version': digest(task)}
    catalog = []
    for aid, payload in [('a', {'text': 'DATA_A'}), ('b', {'text': 'SECRET_B'})]:
        catalog.append({'case_id': 'fixture', 'action_id': aid, 'capture_ref': 'r' + aid,
                        'saved_response': {'payload': payload, 'response_sha256': digest(payload)}})
    return checkpoint, catalog


def engine_task(required=True):
    return {'case_id': 'fixture', 'question': 'USER_TARGET_SENTINEL: find X',
            'task_type': 'exploration', 'evidence': [
                {'id': 's1', 'kind': 'observation', 'source': 'saved', 'text': 'premise A'},
                {'id': 's2', 'kind': 'observation', 'source': 'saved', 'text': 'premise B'}],
            'required_questions': ([{'id': 'user-target', 'question': 'USER_TARGET_SENTINEL: find X', 'evidence_ids': []}]
                                   if required else [])}


class ScriptedSI:
    def __init__(self, target='USER_TARGET_SENTINEL', *, sufficient=True, two=False):
        self.target, self.sufficient, self.two = target, sufficient, two
        self.calls = []

    def __call__(self, stage, payload):
        request = build_request(stage, payload)
        self.calls.append((stage, copy.deepcopy(payload), request))
        if stage == 'selection':
            assert self.target in payload['question']
            ids = [x['id'] for x in payload['available_statements']]
            return {'alternatives': [[ids[0]], [ids[1]]]} if self.two and len(ids) > 1 else {'alternatives': [[ids[0]]]}
        if stage == 'inference':
            assert set(payload) == {'selected_texts'}
            assert self.target not in json.dumps(request, ensure_ascii=False)
            return {'conclusion': 'SCRIPTED_FIXTURE_INFERENCE'}
        if stage == 'halter':
            assert self.target in payload['question']
            return {'sufficient': self.sufficient, 'reason': 'scripted answerability judgement, not model evidence'}
        if stage == 'value':
            return {'score': 0.5}
        if stage == 'formatter':
            assert set(payload) == {'final_inference', 'allowed_citation_ids'}
            assert self.target not in json.dumps(request, ensure_ascii=False)
            return {'answer': payload['final_inference'], 'citations': [payload['allowed_citation_ids'][0]]}
        raise AssertionError(stage)


class RoleAndControlTests(unittest.TestCase):
    def test_exact_role_inputs_and_unverified_status(self):
        fake = ScriptedSI()
        out = StrictEngine(fake, EngineConfig(max_calls=5)).run(engine_task())
        self.assertEqual(out['status'], 'proposal')
        self.assertEqual(out['semantic_status'], 'unreviewed')
        self.assertEqual(out['coverage'][0]['assessment_origin'], 'model_unverified')
        self.assertEqual([x[0] for x in fake.calls], ['selection', 'inference', 'halter', 'value', 'formatter'])

    def test_user_target_not_a_selectable_source_premise(self):
        task = engine_task(); task['thesis'] = {'text': 'USER_TARGET_SENTINEL: find X', 'version': '1', 'origin': 'human'}
        fake = ScriptedSI(); out = StrictEngine(fake, EngineConfig(max_calls=5)).run(task)
        self.assertEqual(out['status'], 'proposal')
        selection = next(p for s, p, _ in fake.calls if s == 'selection')
        self.assertNotIn('input:thesis', {x['id'] for x in selection['available_statements']})
        self.assertEqual(out['user_target']['text'], task['thesis']['text'])

    def test_budget_preserves_first_completed_branch_and_formatter(self):
        fake = ScriptedSI(two=True)
        out = StrictEngine(fake, EngineConfig(max_calls=5, max_alternatives=2)).run(engine_task())
        self.assertEqual(out['status'], 'proposal')
        self.assertEqual(out['calls'], 5)
        self.assertEqual(len(out['branches']), 1)
        self.assertTrue(any(x['event'] == 'budget_pruned' for x in out['events']))
        self.assertEqual(out['selected_trace'][0]['selected_ids'], ['s1'])

    def test_budget_retains_answerable_branch_pruned_from_active_beam(self):
        selection_count = [0]
        def model(stage, payload):
            if stage == 'selection':
                selection_count[0] += 1
                return {'alternatives': [['s1'], ['s2']]}
            if stage == 'inference': return {'conclusion': payload['selected_texts'][0]['text']}
            if stage == 'halter':
                ready = payload['current_inference'] == 'premise A'
                return {'sufficient': ready, 'reason': 'scripted answerability'}
            if stage == 'value':
                return {'score': 0.2 if payload['trace'][-1]['conclusion'] == 'premise A' else 0.9}
            if stage == 'formatter':
                return {'answer': payload['final_inference'], 'citations': ['s1']}
            raise AssertionError(stage)
        out = StrictEngine(model, EngineConfig(max_calls=8, max_depth=2, beam_width=1, max_alternatives=2)).run(engine_task())
        self.assertEqual((out['status'], out['calls']), ('proposal', 8))
        self.assertEqual(out['selected_trace'][0]['selected_ids'], ['s1'])
        self.assertEqual(len(out['branches']), 2)
        self.assertEqual(selection_count[0], 1)

    def test_formatter_failure_preserves_selected_partial_trace(self):
        fake = ScriptedSI()
        def model(stage, payload):
            if stage == 'formatter': raise RuntimeError('fixture failure')
            return fake(stage, payload)
        out = StrictEngine(model, EngineConfig(max_calls=5)).run(engine_task())
        self.assertEqual((out['status'], out['reason']), ('technical_failure', 'callback_failed:RuntimeError'))
        self.assertEqual(out['partial_trace'][0]['selected_ids'], ['s1'])
        self.assertIsNone(out['result'])
        self.assertEqual(out['coverage'][0]['status'], 'not_assessed')

    def test_later_callback_failure_preserves_completed_branch(self):
        def model(stage, payload):
            if stage == 'selection': return {'alternatives': [['s1'], ['s2']]}
            if stage == 'inference':
                if payload['selected_texts'][0]['text'] == 'premise B': raise RuntimeError('fixture failure')
                return {'conclusion': 'first inference'}
            if stage == 'halter': return {'sufficient': True, 'reason': 'fixture'}
            if stage == 'value': return {'score': 0.7}
            raise AssertionError(stage)
        out = StrictEngine(model, EngineConfig(max_calls=8, max_alternatives=2)).run(engine_task())
        self.assertEqual(out['status'], 'technical_failure')
        self.assertEqual(out['partial_trace'][0]['selected_ids'], ['s1'])
        self.assertIsNone(out['result'])

    def test_missing_target_and_model_false_are_unknown_not_success(self):
        fake = ScriptedSI(); out = StrictEngine(fake).run(engine_task(required=False))
        self.assertEqual((out['status'], out['reason'], out['calls']), ('unknown', 'required_target_missing', 0))
        fake = ScriptedSI(sufficient=False)
        out = StrictEngine(fake, EngineConfig(max_calls=5, max_depth=1)).run(engine_task())
        self.assertEqual(out['status'], 'unknown')
        self.assertIsNone(out['result'])
        self.assertNotIn('formatter', [x[0] for x in fake.calls])
        self.assertEqual(out['coverage'][0]['status'], 'not_assessed')

    def test_multiple_or_unbound_targets_do_not_create_false_coverage(self):
        task = engine_task(); task['required_questions'].append({'id': 'other', 'question': 'Another target', 'evidence_ids': []})
        out = StrictEngine(ScriptedSI()).run(task)
        self.assertEqual((out['status'], out['reason'], out['calls']), ('unknown', 'multiple_targets_not_supported', 0))
        task = engine_task(); task['required_questions'][0]['question'] = 'DIFFERENT TARGET'
        out = StrictEngine(ScriptedSI()).run(task)
        self.assertEqual((out['status'], out['reason'], out['calls']), ('unknown', 'user_target_not_bound_to_question', 0))

    def test_invalid_or_unselected_citation_is_not_accepted(self):
        fake = ScriptedSI()
        def invalid(stage, payload):
            if stage == 'formatter': return {'answer': 'test', 'citations': ['s2']}
            return fake(stage, payload)
        out = StrictEngine(invalid, EngineConfig(max_calls=5)).run(engine_task())
        self.assertEqual(out['status'], 'technical_failure')
        self.assertIn('citations', out['reason'])

    def test_source_actions_are_separate_from_observed_facts(self):
        checkpoint, catalog = checkpoint_fixture(); fake = ScriptedSI()
        def model(stage, payload):
            self.assertNotIn('SECRET_B', json.dumps(payload, ensure_ascii=False))
            if stage == 'source_decision':
                return {'choice': 'a' if payload['remaining_actions'] == 2 else 'STOP',
                        'reason': 'scripted selection or stop', 'expected_result': 'test only'}
            if stage == 'selection':
                ids = [x['id'] for x in payload['available_statements']]
                self.assertEqual(ids, ['source:a'])
                self.assertTrue(all(not x.startswith('action:') for x in ids))
                self.assertEqual(payload['candidate_findings'][0]['semantic_status'], 'unverified')
                self.assertEqual(payload['candidate_findings'][0]['context_evidence_ids'], ['source:a'])
            return fake(stage, payload)
        out = run_case(checkpoint, catalog, model)
        self.assertEqual(out['status'], 'proposal')
        self.assertEqual([e['action_id'] for e in out['history'] if e['kind'] == 'replay_retrieval'], ['a'])
        self.assertIn('SECRET_B', json.dumps(catalog))

    def test_unknown_or_invalid_action_never_retrieves(self):
        checkpoint, catalog = checkpoint_fixture()
        for choice, status in [('UNKNOWN', 'unknown'), ('made-up', 'technical_failure')]:
            out = run_case(checkpoint, catalog, lambda stage, p: {'choice': choice, 'reason': 'fixture', 'expected_result': 'fixture'})
            self.assertEqual(out['status'], status)
            self.assertFalse(any(e['kind'] == 'replay_retrieval' for e in out['history']))

    def test_future_timestamp_is_rejected_when_cutoff_is_structured(self):
        checkpoint, catalog = checkpoint_fixture(with_initial=True)
        saved = checkpoint['input']['initial_evidence'][0]['response']
        saved['payload']['provenance'] = {'captured_at': '2026-10-30T00:00:00Z'}
        saved['response_sha256'] = digest(saved['payload'])
        checkpoint['input_version'] = digest(checkpoint['input'])
        out = run_case(checkpoint, catalog, lambda stage, p: {'choice': 'STOP', 'reason': 'fixture', 'expected_result': 'fixture'})
        self.assertEqual((out['status'], out['reason']), ('technical_failure', 'InvalidTask'))
        self.assertEqual(out['calls'], 0)
        self.assertEqual(out['cutoff_mode'], 'structured_utc')
        self.assertEqual(out['captured_timestamp_presence']['source:initial'], 'known_utc')
        self.assertEqual(out['case_id'], 'fixture')

    def test_real_prompt_binding_and_retained_case_identity(self):
        from faithful_v3.prompts import bind_model
        checkpoint, catalog = checkpoint_fixture()
        seen = []
        def requester(request):
            stage = request['stage']; payload = request['input']; seen.append(stage)
            if stage == 'source_decision':
                return {'choice': 'a' if payload['remaining_actions'] == 2 else 'STOP',
                        'reason': 'fixture', 'expected_result': 'fixture'}
            if stage == 'selection': return {'alternatives': [['source:a']]}
            if stage == 'inference':
                self.assertNotIn('USER_TARGET_SENTINEL', json.dumps(request))
                return {'conclusion': 'DATA_A'}
            if stage == 'halter': return {'sufficient': True, 'reason': 'fixture'}
            if stage == 'value': return {'score': 0.5}
            if stage == 'formatter':
                self.assertNotIn('USER_TARGET_SENTINEL', json.dumps(request))
                return {'answer': 'DATA_A', 'citations': ['source:a']}
            raise AssertionError(stage)
        out = run_case(checkpoint, catalog, bind_model(requester))
        self.assertEqual(out['status'], 'proposal')
        self.assertEqual(out['history'][-1]['outcome']['case_id'], 'fixture')
        self.assertEqual(seen, ['source_decision', 'source_decision', 'selection', 'inference', 'halter', 'value', 'formatter'])

    def test_source_callback_failure_is_visible_without_retry(self):
        checkpoint, catalog = checkpoint_fixture(); called = []
        def model(stage, payload):
            called.append(stage)
            raise TimeoutError('fixture only')
        out = run_case(checkpoint, catalog, model)
        self.assertEqual((out['status'], out['reason']), ('unknown', 'source_callback_interrupted:TimeoutError'))
        self.assertEqual(called, ['source_decision'])
        self.assertEqual(out['history'][0]['kind'], 'model_decision_failed')
        self.assertEqual(out['history'][0]['exception_type'], 'TimeoutError')
