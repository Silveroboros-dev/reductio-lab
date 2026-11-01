"""Offline selection and display tests; sources and model outputs are fixtures."""
import copy
import hashlib
import json
import unittest

from faithful_v3.action_case import run_case
from faithful_v3.excerpts import resolve_selection, source_registry
from faithful_v3.prompts import bind_model
from reasoning_engine.engine import EngineConfig, InvalidOutput, InvalidTask, prepare_task
from faithful_v3.engine import StrictEngine
from reasoning_engine.renderer import render_outcome
from reasoning_engine.replay_sources import digest
from test_strict_v3 import checkpoint_fixture


class UnstructuredSelectionTests(unittest.TestCase):
    def test_source_loop_selects_unicode_slice_for_raw_and_json_payloads(self):
        raw = 'α café😊 e\u0301 SECRET-rest'
        for payload in (raw, {'text': raw}, [raw], '{"passages":"a raw string, not a bundle"} café😊 SECRET-rest'):
            with self.subTest(payload_type=type(payload).__name__):
                checkpoint, catalog = checkpoint_fixture(with_initial=True)
                saved = checkpoint['input']['initial_evidence'][0]['response']
                saved['payload'], saved['response_sha256'] = payload, digest(payload)
                checkpoint['input_version'] = digest(checkpoint['input'])
                requested = []
                def requester(req):
                    stage, x = req['stage'], req['input']
                    if stage == 'source_decision': return {'choice': 'STOP', 'reason': 'fixture', 'expected_result': 'fixture'}
                    if stage == 'selection':
                        source = x['available_statements'][0]
                        text = source['text']; start = text.index('café😊')
                        requested.append((text, source['text_representation'], start))
                        return {'alternatives': [[{'id': source['id'], 'spans': [{'start_char': start, 'end_char': start + 5}]}]]}
                    if stage == 'inference':
                        self.assertEqual(set(x), {'selected_texts'})
                        self.assertEqual(x['selected_texts'][0]['text'], 'café😊')
                        self.assertNotIn('SECRET-rest', json.dumps(req, ensure_ascii=False))
                        return {'conclusion': 'fixture inference'}
                    if stage == 'halter': return {'sufficient': False, 'reason': 'fixture', 'evidence_assessment': 'insufficient'}
                    if stage == 'value': return {'score': .5}
                    raise AssertionError(stage)
                out = run_case(checkpoint, catalog, bind_model(requester), max_depth=1)
                self.assertEqual(out['status'], 'unknown')
                view, representation, start = requested[0]
                self.assertEqual(representation, 'saved_payload_text' if isinstance(payload, str) else 'saved_payload_json')
                self.assertEqual(view, payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False, sort_keys=True))
                ref = out['unknown_explanation']['model_assessments'][0]['selected_source_refs'][0]
                self.assertEqual(ref['scope'], 'saved_response_text_span')
                self.assertEqual(ref['offset_basis'], 'saved_evidence_text_not_original_document')
                self.assertEqual(ref['saved_payload_sha256'], digest(payload))
                self.assertEqual(ref['binding'], 'caller_supplied_hash_consistency')
                rendered = render_outcome(out)
                self.assertIn('saved-text offsets', rendered)
                self.assertIn('not original-document offsets', rendered)
                self.assertNotIn('SECRET-rest', rendered)
                self.assertNotIn(digest(payload), rendered)

    def test_bounds_duplicates_wrong_hash_and_surrogate(self):
        node = {'id': 'source:x', 'text': 'a😊e\u0301 z', 'source': 'fixture', 'kind': 'observation',
                'text_representation': 'saved_payload_text', 'raw_ref': 'sha256:' + digest('a😊e\u0301 z')}
        reg = source_registry([node]); nodes = {'source:x': node}
        def span(a, b): return {'id': 'source:x', 'spans': [{'start_char': a, 'end_char': b}]}
        _, text, refs = resolve_selection([span(1, 4)], nodes, {'source:x'}, reg)
        self.assertEqual(text[0]['text'], '😊e\u0301')
        self.assertEqual(refs[0]['end_char'] - refs[0]['start_char'], 3)
        invalid = [span(True, 2), span(-1, 2), span(2, 2), span(0, 100),
                   {'id': 'source:x', 'spans': [{'start_char': 0, 'end_char': 1}, {'start_char': 0, 'end_char': 1}]},
                   {'id': 'source:x', 'spans': [{'start_char': 0, 'end_char': 1, 'text': 'invented'}]}]
        for choice in invalid:
            with self.subTest(choice=choice), self.assertRaises(InvalidOutput):
                resolve_selection([choice], nodes, {'source:x'}, reg)
        node['raw_ref'] = 'sha256:' + '0'*64
        with self.assertRaisesRegex(InvalidOutput, 'hash mismatch'):
            resolve_selection([span(0, 1)], nodes, {'source:x'}, reg)
        broken = dict(node, text='x\ud800')
        task = {'case_id': 'x', 'question': 'target', 'task_type': 'exploration', 'evidence': [broken]}
        with self.assertRaisesRegex(InvalidTask, 'valid UTF-8'): prepare_task(task)

    def test_unstructured_derived_or_unknown_source_cannot_claim_a_span(self):
        node = {'id': 'node:0001', 'text': 'previous inference', 'source': 'model', 'kind': 'derived_claim'}
        choice = {'id': 'node:0001', 'spans': [{'start_char': 0, 'end_char': 1}]}
        with self.assertRaises(InvalidOutput): resolve_selection([choice], {'node:0001': node}, set(), {})
        with self.assertRaises(InvalidOutput): resolve_selection([dict(choice, id='missing')], {}, set(), {})

    def test_json_looking_explicit_caller_text_stays_unstructured(self):
        text = '{"passages": "plain text, not a saved bundle"}'
        node = {'id': 'x', 'text': text, 'kind': 'observation', 'source': 'fixture',
                'text_representation': 'caller_text'}
        registry = source_registry([node])
        self.assertNotIn('x', registry)
        start = text.index('plain')
        choice = {'id': 'x', 'spans': [{'start_char': start, 'end_char': start + 5}]}
        _, resolved, refs = resolve_selection([choice], {'x': node}, {'x'}, registry)
        self.assertEqual(resolved[0]['text'], 'plain')
        self.assertEqual(refs[0]['binding'], 'caller_supplied_text')

    def test_legacy_whole_source_selection_is_explicitly_labelled(self):
        node = {'id': 'x', 'text': 'abc', 'source': 'fixture', 'kind': 'observation'}
        _, text, refs = resolve_selection(['x'], {'x': node}, {'x'}, {})
        self.assertEqual(text[0]['text'], 'abc')
        self.assertEqual(refs[0]['scope'], 'whole_saved_response')

    def test_empty_saved_strings_use_explicit_json_view(self):
        for payload in ('', '   '):
            checkpoint, catalog = checkpoint_fixture(with_initial=True)
            saved = checkpoint['input']['initial_evidence'][0]['response']
            saved['payload'], saved['response_sha256'] = payload, digest(payload)
            checkpoint['input_version'] = digest(checkpoint['input'])
            def model(stage, data):
                if stage == 'source_decision': return {'choice': 'STOP', 'reason': 'fixture', 'expected_result': 'none'}
                if stage == 'selection':
                    source = data['available_statements'][0]
                    self.assertEqual(source['text_representation'], 'saved_payload_json')
                    return {'alternatives': [[{'id': source['id'], 'spans': [{'start_char': 0, 'end_char': 1}]}]]}
                if stage == 'inference': return {'conclusion': 'fixture'}
                if stage == 'halter': return {'sufficient': False, 'reason': 'fixture'}
                if stage == 'value': return {'score': .5}
                raise AssertionError(stage)
            out = run_case(checkpoint, catalog, model, max_depth=1)
            self.assertEqual(out['status'], 'unknown')

    def test_marked_source_hash_mismatch_rejected_before_any_callback(self):
        for representation, text in [('saved_payload_text', 'plain'), ('saved_payload_json', '{"x":1}')]:
            task = {'case_id': 'x', 'question': 'target', 'task_type': 'exploration',
                    'evidence': [{'id': 's', 'kind': 'observation', 'source': 'fixture', 'text': text,
                                  'text_representation': representation, 'raw_ref': 'sha256:' + '0'*64}],
                    'required_questions': [{'id': 'q', 'question': 'target', 'evidence_ids': []}]}
            out = StrictEngine(lambda *_: self.fail('unexpected callback')).run(task)
            self.assertEqual((out['status'], out['calls']), ('technical_failure', 0))
            self.assertIn('hash mismatch', out['reason'])

    def test_unstructured_span_survives_derived_step(self):
        text = 'prefix café😊 HIDDEN'
        task = {'case_id': 'x', 'question': 'target', 'task_type': 'exploration',
                'evidence': [{'id': 'src', 'text': text, 'source': 'fixture', 'kind': 'observation'}],
                'required_questions': [{'id': 'q', 'question': 'target', 'evidence_ids': []}]}
        counts = {'selection': 0, 'halter': 0}
        def model(stage, payload):
            if stage == 'selection':
                counts['selection'] += 1
                item = {'id': 'src', 'spans': [{'start_char': 7, 'end_char': 12}]} if counts['selection'] == 1 else 'node:0001'
                return {'alternatives': [[item]]}
            if stage == 'inference':
                self.assertNotIn('HIDDEN', json.dumps(payload, ensure_ascii=False))
                return {'conclusion': payload['selected_texts'][0]['text']}
            if stage == 'halter':
                counts['halter'] += 1
                return {'sufficient': counts['halter'] == 2, 'reason': 'fixture'}
            if stage == 'value': return {'score': .5}
            if stage == 'formatter': return {'answer': payload['final_inference'], 'citations': payload['allowed_citation_ids']}
            raise AssertionError(stage)
        out = StrictEngine(model, EngineConfig(max_calls=10, max_depth=2, beam_width=1)).run(task)
        self.assertEqual(out['status'], 'proposal')
        self.assertEqual(out['result']['answer'], 'café😊')
        ref = out['selected_trace'][0]['selected_source_refs'][0]
        self.assertEqual(ref['scope'], 'saved_response_text_span')
        self.assertEqual((ref['start_char'], ref['end_char']), (7, 12))


class RedactedAttributionTests(unittest.TestCase):
    def test_aliases_keep_attribution_without_arbitrary_strings(self):
        s = 'PRIVATE SENTINEL <script>\n'
        ref = {'id': s + 'source', 'passage_id': s + 'passage', 'scope': 'saved_passage_span',
               'start_char': 10, 'end_char': 15, 'offset_unit': 'unicode_code_points',
               'saved_payload_sha256': 'a'*64, 'excerpt_sha256': 'b'*64, 'source': s}
        explanation = {'stop_kind': 'execution_limit', 'unresolved_questions': [{'id': s, 'question': s}],
            'available_saved_sources': [{'id': s + 'source'}],
            'model_assessments': [{'branch_id': s + 'branch', 'halter_call_ordinal': 3,
                'reason': s, 'origin': 'model_unverified', 'evidence_assessment': 'insufficient', 'selected_source_refs': [ref]}]}
        out = {'version': 'faithful-v3-strict-4', 'status': 'unknown', 'unknown_explanation': explanation,
               'evidence': [{'text': s}], 'result': {'answer': s}}
        view = render_outcome(out)
        for secret in ('PRIVATE SENTINEL', '<script>', 'a'*64, 'b'*64): self.assertNotIn(secret, view)
        for expected in ('question Q1', 'response R1', 'B1, SI call #3', 'R1 / P1', '10–15'):
            self.assertIn(expected, view)
        self.assertIn('insufficient evidence', view)
        self.assertIn('unverified', view)
        detailed = render_outcome(out, include_private=True)
        self.assertIn('Alias key (private)', detailed)
        self.assertIn('Q1:', detailed)
        self.assertIn('R1 / P1:', detailed)

    def test_private_alias_key_maps_original_ids(self):
        explanation = {'stop_kind': 'execution_limit', 'unresolved_questions': [{'id': 'my-question', 'question': 'private question'}],
            'available_saved_sources': [{'id': 'source:actual'}], 'model_assessments': [{'branch_id': 'root.1.1',
            'halter_call_ordinal': 3, 'origin': 'model_unverified', 'evidence_assessment': 'not_determined', 'reason': 'private reason',
            'selected_source_refs': [{'id': 'source:actual', 'passage_id': 'actual-passage', 'scope': 'saved_passage_span',
                                      'start_char': 1, 'end_char': 2, 'offset_unit': 'unicode_code_points'}]}]}
        out = {'version': 'faithful-v3-strict-4', 'status': 'unknown', 'unknown_explanation': explanation}
        safe = render_outcome(out)
        for text in ('my-question', 'source:actual', 'actual-passage', 'root.1.1'):
            self.assertNotIn(text, safe)
        private = render_outcome(out, include_private=True)
        for mapping in ('Q1: my-question', 'R1: source:actual', 'R1 / P1: actual-passage', 'B1: root.1.1'):
            self.assertIn(mapping, private)

    def test_malformed_attribution_is_not_echoed(self):
        data = {'version': 'faithful-v3-strict-4', 'status': 'unknown', 'unknown_explanation': {
            'stop_kind': 'execution_limit', 'model_assessments': [{'branch_id': {'bad': 'SECRET'}, 'halter_call_ordinal': True, 'origin': 'model_unverified',
                'evidence_assessment': ['bad'], 'selected_source_refs': [{'id': ['SECRET'], 'passage_id': ['SECRET'],
                    'scope': 'saved_passage_span', 'offset_unit': 'unicode_code_points', 'start_char': False, 'end_char': 999999999999}]}]}}
        view = render_outcome(data)
        self.assertNotIn('SECRET', view)
        self.assertNotIn('call #', view)
        self.assertNotIn('999999999999', view)
        self.assertIn('not determined', view)

    def test_stale_wrong_origin_and_mismatched_stop_do_not_claim_assessments(self):
        for status, kind in [('technical_failure', 'technical_failure'), ('unknown', 'effect_uncertain'), ('proposal', 'model_decision')]:
            out = {'version': 'faithful-v3-strict-4', 'status': status, 'unknown_explanation': {
                'stop_kind': kind, 'model_assessments': [{'origin': 'model_unverified', 'evidence_assessment': 'insufficient'}],
                'source_decision': {'origin': 'model_unverified', 'call_ordinal': 7}}}
            view = render_outcome(out)
            self.assertNotIn('insufficient evidence', view)
            self.assertNotIn('source decision was uncertain', view)
        out = {'status': 'unknown', 'unknown_explanation': {'stop_kind': 'execution_limit',
               'model_assessments': [{'origin': 'human', 'evidence_assessment': 'insufficient'}]}}
        self.assertNotIn('insufficient evidence', render_outcome(out))

    def test_aliases_are_stable_across_branches_and_distinct_sources(self):
        def ref(source):
            return {'id': source, 'passage_id': 'same-id', 'scope': 'saved_passage_span',
                    'start_char': 1, 'end_char': 2, 'offset_unit': 'unicode_code_points'}
        def assessment(branch, refs):
            return {'branch_id': branch, 'origin': 'model_unverified', 'halter_call_ordinal': 2,
                    'evidence_assessment': 'not_determined', 'selected_source_refs': refs}
        explanation = {'stop_kind': 'execution_limit', 'unresolved_questions': [{'id': 'q1'}],
                       'available_saved_sources': [{'id': 'src1'}, {'id': 'src1'}, {'id': 'src2'}],
                       'model_assessments': [assessment('branch1', [ref('src1'), ref('src2')]),
                                             assessment('branch2', [ref('src1')])]}
        out = {'version': 'faithful-v3-strict-4', 'status': 'unknown', 'unknown_explanation': explanation}
        view = render_outcome(out)
        self.assertEqual(view.count('Available saved response R1'), 1)
        self.assertIn('B1, SI call #2', view)
        self.assertIn('B2, SI call #2', view)
        self.assertEqual(view.count('R1 / P1'), 2)
        self.assertIn('R2 / P2', view)

    def test_private_alias_key_distinguishes_sanitized_identifier_collisions(self):
        ids = ['a\nb', 'a b', 'api_key=one', 'api_key=two']
        out = {'version': 'faithful-v3-strict-4', 'status': 'unknown',
               'unknown_explanation': {'stop_kind': 'execution_limit',
                   'unresolved_questions': [{'id': ident, 'question': 'private'} for ident in ids]}}
        private = render_outcome(out, include_private=True)
        for ident in ids:
            self.assertIn(hashlib.sha256(ident.encode('utf-8')).hexdigest(), private)
        self.assertNotIn('api_key=one', private)
        self.assertNotIn('api_key=two', private)
        safe = render_outcome(out)
        for ident in ids:
            self.assertNotIn(hashlib.sha256(ident.encode('utf-8')).hexdigest(), safe)

    def test_bounded_view_discloses_truncation(self):
        out = {'status': 'unknown', 'unknown_explanation': {'stop_kind': 'execution_limit',
            'unresolved_questions': [{'id': str(i)} for i in range(101)],
            'available_saved_sources': [{'id': str(i)} for i in range(101)],
            'model_assessments': [{'origin': 'model_unverified'} for _ in range(101)]}}
        view = render_outcome(out)
        self.assertIn('Additional unresolved questions omitted', view)
        self.assertIn('Additional saved responses omitted', view)
        self.assertIn('Additional model assessments omitted', view)
        self.assertNotIn('question Q101', view)


if __name__ == '__main__': unittest.main()
