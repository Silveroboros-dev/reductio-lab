"""Offline tests of passage boundaries, provenance and conservative unknowns."""
import copy
import json
import unittest

from faithful_v3.action_case import run_case
from faithful_v3.engine import StrictEngine
from faithful_v3.excerpts import resolve_selection, source_registry
from faithful_v3.prompts import bind_model
from reasoning_engine.engine import EngineConfig, InvalidOutput
from reasoning_engine.renderer import render_outcome
from reasoning_engine.replay_sources import digest
from test_strict_v3 import checkpoint_fixture


def captured_payload():
    text = 'prefix café😊 SECRET_FRAGMENT suffix'
    start = 100
    return {'passages': [{'id': 'p1', 'start_char': start, 'end_char': start + len(text), 'text': text},
                         {'id': 'p2', 'start_char': 200, 'end_char': 211, 'text': 'other data!'}],
            'coverage': {'range_unit': 'unicode_code_points', 'visible_char_ranges': [[start, start + len(text)], [200, 211]],
                         'saved_object_complete': False, 'source_document_complete': False},
            'source_document_char_count': 250}


def evidence(payload=None):
    payload = captured_payload() if payload is None else payload
    return {'id': 'source:a', 'kind': 'observation', 'source': 'saved source',
            'raw_ref': 'sha256:' + digest(payload), 'text': json.dumps(payload, ensure_ascii=False, sort_keys=True)}


def selection(start=107, end=112, passage='p1'):
    return {'id': 'source:a', 'spans': [{'passage_id': passage, 'start_char': start, 'end_char': end}]}


class ExcerptTests(unittest.TestCase):
    def test_precise_unicode_slice_and_bound_provenance(self):
        item = evidence(); reg = source_registry([item])
        ids, texts, refs = resolve_selection([selection()], {'source:a': item}, {'source:a'}, reg)
        self.assertEqual(ids, ['source:a'])
        self.assertEqual(texts[0]['text'], 'café😊')
        self.assertEqual(refs[0]['saved_payload_sha256'], digest(captured_payload()))
        self.assertEqual(refs[0]['binding'], 'caller_supplied_hash_consistency')
        self.assertEqual(refs[0]['document_offsets'], 'source_reported_not_independently_verified')
        self.assertEqual((refs[0]['start_char'], refs[0]['end_char']), (107, 112))
        self.assertNotIn('SECRET_FRAGMENT', json.dumps(texts))

    def test_reject_bad_ids_offsets_and_invented_quote(self):
        item = evidence(); nodes = {'source:a': item, 'node:0001': {'text': 'inference'}}
        reg = source_registry([item])
        invalid = [
            ['source:a'], [selection(99, 102)], [selection(107, 107)], [selection(107, 999)],
            [selection(True, 112)], [selection(107, 112, 'missing')],
            [{'id': 'node:0001', 'spans': [{'passage_id': 'p1', 'start_char': 107, 'end_char': 112}]}],
            [{'id': 'source:invented', 'spans': [{'passage_id': 'p1', 'start_char': 107, 'end_char': 112}]}],
            [{'id': 'source:a', 'spans': [{'passage_id': 'p1', 'start_char': 107, 'end_char': 112, 'text': 'invented'}]}],
            [{'id': 'source:a', 'spans': [selection()['spans'][0], selection()['spans'][0]]}],
        ]
        for value in invalid:
            with self.subTest(value=value), self.assertRaises(InvalidOutput):
                resolve_selection(value, nodes, {'source:a'}, reg)

    def test_tampered_hash_and_malformed_capture_rejected(self):
        item = evidence(); item['raw_ref'] = 'sha256:' + '0' * 64
        with self.assertRaises(InvalidOutput): source_registry([item])
        for transform in ('duplicate', 'bounds', 'coverage', 'unit'):
            payload = captured_payload()
            if transform == 'duplicate': payload['passages'].append(copy.deepcopy(payload['passages'][0]))
            if transform == 'bounds': payload['passages'][0]['end_char'] += 1
            if transform == 'coverage': payload['coverage']['visible_char_ranges'] = [[0, 2]]
            if transform == 'unit': payload['coverage']['range_unit'] = 'bytes'
            with self.subTest(transform=transform), self.assertRaises(InvalidOutput): source_registry([evidence(payload)])

    def test_overlapping_saved_passages_must_agree(self):
        payload = {'passages': [{'id': 'a', 'start_char': 0, 'end_char': 5, 'text': 'alpha'},
                                {'id': 'b', 'start_char': 2, 'end_char': 5, 'text': 'pha'}],
                   'coverage': {'range_unit': 'unicode_code_points', 'visible_char_ranges': [[0, 5]]},
                   'source_document_char_count': 5}
        self.assertIn('source:a', source_registry([evidence(payload)]))
        payload['passages'][1]['text'] = 'XYZ'
        with self.assertRaisesRegex(InvalidOutput, 'overlapping saved passages disagree'):
            source_registry([evidence(payload)])

    def test_multiple_spans_and_unstructured_fallback(self):
        item = evidence(); plain = {'id': 'plain', 'kind': 'observation', 'source': 'saved', 'text': 'whole response'}
        items = [selection()['spans'][0], {'passage_id': 'p2', 'start_char': 200, 'end_char': 205}]
        ids, texts, refs = resolve_selection([{'id': 'source:a', 'spans': items}, 'plain'],
                                            {'source:a': item, 'plain': plain}, {'source:a', 'plain'}, source_registry([item]))
        self.assertEqual(ids, ['source:a', 'plain'])
        self.assertEqual([v['text'] for v in texts], ['café😊', 'other', 'whole response'])
        self.assertEqual(refs[-1]['scope'], 'whole_saved_response')
        self.assertIsNone(refs[-1]['excerpt_offsets'])

    def test_caller_supplied_claim_does_not_become_a_registered_source(self):
        item = evidence()
        item['kind'] = 'derived_claim'
        registry = source_registry([item])
        self.assertNotIn(item['id'], registry)
        with self.assertRaises(InvalidOutput):
            resolve_selection([selection()], {item['id']: item}, set(), registry)
        for items in ([item], [evidence(), item]):
            if len(items) == 2:
                items[1] = dict(items[1], id='fake')
            task = {'case_id': 'test', 'question': 'target', 'task_type': 'exploration',
                    'evidence': items, 'required_questions': [{'id': 'q', 'question': 'target', 'evidence_ids': []}]}
            out = StrictEngine(lambda *_: self.fail('must not call model')).run(task)
            self.assertEqual(out['status'], 'technical_failure')
            self.assertIn('derived claims', out['reason'])
            self.assertEqual(out['calls'], 0)

    def test_default_render_redacts_old_packets_and_proposals(self):
        for packet in (
            {'status': 'unknown', 'evidence': [{'text': 'private source sentinel'}]},
            {'status': 'technical_failure', 'evidence': [{'text': 'private source sentinel'}]},
            {'version': 'faithful-v3-strict-3', 'status': 'proposal',
             'result': {'answer': 'private answer sentinel'}, 'evidence': [{'text': 'private source sentinel'}]},
            {'version': 'faithful-v3-source-loop-3', 'status': 'proposal', 'history': [
                {'kind': 'final', 'outcome': {'evidence': [{'text': 'private source sentinel'}]}}]},
        ):
            with self.subTest(status=packet['status']):
                result = render_outcome(packet)
                self.assertNotIn('private source sentinel', result)
                self.assertNotIn('private answer sentinel', result)

    def test_derived_node_keeps_parent_span_provenance(self):
        item = evidence()
        target = 'target'
        task = {'case_id': 'test', 'question': target, 'task_type': 'exploration',
                'evidence': [item], 'required_questions': [{'id': 'q', 'question': target, 'evidence_ids': []}]}
        calls = []
        def model(stage, payload):
            calls.append(stage)
            if stage == 'selection':
                if calls.count('selection') == 1: return {'alternatives': [[selection()]]}
                return {'alternatives': [['node:0001']]}
            if stage == 'inference': return {'conclusion': payload['selected_texts'][0]['text']}
            if stage == 'halter': return {'sufficient': calls.count('halter') == 2, 'reason': 'fixture'}
            if stage == 'value': return {'score': 0.5}
            if stage == 'formatter': return {'answer': payload['final_inference'], 'citations': payload['allowed_citation_ids']}
            raise AssertionError(stage)
        out = StrictEngine(model, EngineConfig(max_calls=10, max_depth=2, beam_width=1)).run(task)
        self.assertEqual(out['status'], 'proposal')
        self.assertEqual(out['inference_dependency_depth'], 2)
        self.assertEqual(out['selected_trace'][0]['selected_source_refs'][0]['passage_id'], 'p1')
        self.assertEqual(out['result']['answer'], 'café😊')
        self.assertNotIn('café', render_outcome(out))

    def test_same_source_different_spans_remain_distinct_alternatives(self):
        item = evidence()
        task = {'case_id': 'test', 'question': 'target', 'task_type': 'exploration',
                'evidence': [item], 'required_questions': [{'id': 'q', 'question': 'target', 'evidence_ids': []}]}
        calls = []
        def model(stage, payload):
            if stage == 'selection': return {'alternatives': [[selection()], [selection(200, 205, 'p2')]]}
            if stage == 'inference':
                calls.append(payload['selected_texts'][0]['text'])
                return {'conclusion': calls[-1]}
            if stage == 'halter': return {'sufficient': False, 'reason': 'fixture', 'evidence_assessment': 'conflicting'}
            if stage == 'value': return {'score': .5}
            raise AssertionError(stage)
        out = StrictEngine(model, EngineConfig(max_calls=8, max_depth=1)).run(task)
        self.assertEqual(calls, ['café😊', 'other'])
        self.assertEqual(len(out['unknown_explanation']['model_assessments']), 2)
        self.assertIn('conflicting evidence', render_outcome(out))

    def test_invalid_evidence_assessment_is_not_accepted(self):
        item = evidence()
        task = {'case_id': 'test', 'question': 'target', 'task_type': 'exploration',
                'evidence': [item], 'required_questions': [{'id': 'q', 'question': 'target', 'evidence_ids': []}]}
        def model(stage, payload):
            if stage == 'selection': return {'alternatives': [[selection()]]}
            if stage == 'inference': return {'conclusion': 'x'}
            if stage == 'halter': return {'sufficient': False, 'reason': 'x', 'evidence_assessment': ['invented']}
            raise AssertionError(stage)
        out = StrictEngine(model).run(task)
        self.assertEqual(out['status'], 'technical_failure')
        self.assertIn('evidence assessment', out['reason'])

    def test_full_source_loop_and_safe_unknown_view(self):
        checkpoint, catalog = checkpoint_fixture(with_initial=True)
        payload = captured_payload()
        saved = checkpoint['input']['initial_evidence'][0]['response']
        saved['payload'], saved['response_sha256'] = payload, digest(payload)
        checkpoint['input_version'] = digest(checkpoint['input'])
        seen = []
        def requester(req):
            stage, data = req['stage'], req['input']; seen.append(stage)
            if stage == 'source_decision':
                return {'choice': 'STOP', 'reason': 'PRIVATE_MODEL_REASON', 'expected_result': 'none'}
            if stage == 'selection':
                s = selection(); s['id'] = 'source:initial'
                return {'alternatives': [[s]]}
            if stage == 'inference':
                self.assertEqual(set(data), {'selected_texts'})
                self.assertEqual(data['selected_texts'][0]['text'], 'café😊')
                self.assertNotIn('SECRET_FRAGMENT', json.dumps(req, ensure_ascii=False))
                self.assertNotIn('USER_TARGET_SENTINEL', json.dumps(req, ensure_ascii=False))
                return {'conclusion': 'PRIVATE_MODEL_CONCLUSION'}
            if stage == 'halter':
                return {'sufficient': False, 'reason': 'PRIVATE_HALTER_REASON', 'evidence_assessment': 'insufficient'}
            if stage == 'value': return {'score': .5}
            raise AssertionError(stage)
        out = run_case(checkpoint, catalog, bind_model(requester), max_depth=1)
        self.assertEqual(out['status'], 'unknown')
        explanation = out['unknown_explanation']
        self.assertEqual(explanation['stop_kind'], 'execution_limit')
        assess = explanation['model_assessments'][0]
        self.assertEqual((assess['origin'], assess['evidence_assessment']), ('model_unverified', 'insufficient'))
        self.assertEqual(assess['selected_source_refs'][0]['passage_id'], 'p1')
        self.assertEqual(assess['selected_source_refs'][0]['saved_payload_sha256'], digest(payload))
        safe = render_outcome(out)
        for secret in ('SECRET_FRAGMENT', 'PRIVATE_MODEL_REASON', 'PRIVATE_MODEL_CONCLUSION', 'PRIVATE_HALTER_REASON', 'USER_TARGET_SENTINEL', 'café'):
            self.assertNotIn(secret, safe)
        self.assertIn('execution limit reached', safe)
        self.assertIn('unverified model assessment of a recorded inference: insufficient evidence', safe)
        self.assertIn('Unresolved question Q1', safe)
        self.assertIn('R1 / P1', safe)
        self.assertIn('SI call #3', safe)
        self.assertNotIn(digest(payload), safe)
        private = render_outcome(out, include_private=True)
        self.assertIn(r'PRIVATE\_HALTER\_REASON', private)

    def test_source_uncertainty_default_view_hides_model_and_source_content(self):
        checkpoint, catalog = checkpoint_fixture(with_initial=True)
        out = run_case(checkpoint, catalog, lambda stage, payload: {
            'choice': 'UNKNOWN', 'reason': 'PRIVATE_REASON initial observed text', 'expected_result': 'none'})
        safe = render_outcome(out)
        self.assertIn('model declined a source decision', safe)
        self.assertNotIn('PRIVATE_REASON', safe)
        self.assertNotIn('initial observed text', safe)
        self.assertEqual(out['unknown_explanation']['stop_kind'], 'model_decision')


if __name__ == '__main__': unittest.main()
