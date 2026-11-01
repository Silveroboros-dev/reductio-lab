"""Offline regressions for source gaps, conflicting observations and effect truth."""
import copy
import unittest
from unittest.mock import patch

from faithful_v3.action_case import run_case
from faithful_v3.engine import StrictEngine
from reasoning_engine.engine import EngineConfig
from reasoning_engine.renderer import render_outcome
from reasoning_engine.replay_sources import MissingReplayCapture, ReplayCase, digest
from test_strict_v3 import checkpoint_fixture, engine_task


class MissingSourceTests(unittest.TestCase):
    def test_missing_capture_returns_scoped_unknown_without_callback(self):
        checkpoint, catalog = checkpoint_fixture(with_initial=True)
        checkpoint['input']['initial_evidence'][0]['response']['payload']['text'] = 'INITIAL_PRIVATE_SENTINEL'
        initial = checkpoint['input']['initial_evidence'][0]['response']
        initial['response_sha256'] = digest(initial['payload'])
        checkpoint['input_version'] = digest(checkpoint['input'])
        catalog[0]['saved_response']['payload']['text'] = 'RETAINED_PRIVATE_SENTINEL'
        catalog[0]['saved_response']['response_sha256'] = digest(catalog[0]['saved_response']['payload'])
        calls = []
        result = run_case(checkpoint, catalog[:-1], lambda *args: calls.append(args))
        self.assertEqual((result['status'], result['reason'], result['calls']),
                         ('unknown', 'replay_capture_missing', 0))
        self.assertIsNone(result['result'])
        self.assertEqual(calls, [])
        self.assertEqual(result['missing_action_ids'], ['b'])
        self.assertFalse(result['case_catalog_complete'])
        explanation = result['unknown_explanation']
        self.assertEqual(explanation['stop_kind'], 'input_or_process')
        self.assertEqual(explanation['model_assessments'], [])
        self.assertNotIn('available_saved_sources', explanation)
        self.assertIn('external source availability is unknown', explanation['scope_note'])
        rendered = render_outcome(result)
        self.assertIn('saved capture missing from supplied replay catalog', rendered)
        self.assertNotIn('SECRET_B', rendered)
        for sentinel in ('INITIAL_PRIVATE_SENTINEL', 'RETAINED_PRIVATE_SENTINEL'):
            self.assertNotIn(sentinel, rendered)
            self.assertNotIn(sentinel, str(result))
        self.assertNotIn('source:b', rendered)
        with self.assertRaises(MissingReplayCapture):
            ReplayCase(checkpoint, catalog[:-1])

    def test_bad_bindings_and_tampering_do_not_become_missing_capture(self):
        checkpoint, catalog = checkpoint_fixture()
        bad = copy.deepcopy(catalog)
        bad[0]['saved_response']['response_sha256'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'saved response hash mismatch'):
            run_case(checkpoint, bad, lambda *_: self.fail('callback must not run'))
        bad = copy.deepcopy(catalog)
        bad[0]['capture_ref'] = 'wrong'
        with self.assertRaisesRegex(ValueError, 'action source binding mismatch'):
            run_case(checkpoint, bad, lambda *_: self.fail('callback must not run'))
        with self.assertRaisesRegex(ValueError, 'action source binding mismatch'):
            run_case(checkpoint, catalog + catalog[:1], lambda *_: self.fail('callback must not run'))
        stale = copy.deepcopy(checkpoint)
        stale['input_version'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'input version mismatch'):
            run_case(stale, catalog[:-1], lambda *_: self.fail('callback must not run'))

    def test_no_supplied_evidence_is_unknown_not_absence_from_world(self):
        task = {'case_id': 'missing', 'question': 'target', 'task_type': 'exploration', 'evidence': [],
                'required_questions': [{'id': 'q', 'question': 'target', 'evidence_ids': []}]}
        result = StrictEngine(lambda *_: self.fail('callback must not run')).run(task)
        self.assertEqual((result['status'], result['reason'], result['calls']), ('unknown', 'no_source_evidence', 0))
        self.assertIn('no source evidence supplied', render_outcome(result))


class ConflictingSourcesTests(unittest.TestCase):
    def test_distinct_conflicting_observations_are_both_selected_without_merging(self):
        checkpoint, _ = checkpoint_fixture()
        inp = checkpoint['input']
        inp['tool_catalog'] = []
        inp['initial_evidence'] = []
        for aid, value in [('first', '354'), ('second', '355')]:
            payload = {'metric': 'water withdrawal', 'year': 2010, 'unit': 'billion gallons per day', 'value': value}
            inp['initial_evidence'].append({'action_id': aid, 'response': {'payload': payload, 'response_sha256': digest(payload)}})
        inp['preconsumed_action_ids'] = ['first', 'second']
        checkpoint['input_version'] = digest(inp)
        def model(stage, data):
            if stage == 'selection':
                selected = []
                for item in data['available_statements']:
                    value = '354' if item['id'] == 'source:first' else '355'
                    self.assertIn(value, item['text'])
                    selected.append({'id': item['id'], 'spans': [{'start_char': 0, 'end_char': len(item['text'])}]})
                return {'alternatives': [selected]}
            if stage == 'inference':
                import json
                payloads = [json.loads(x['text']) for x in data['selected_texts']]
                self.assertEqual([x['value'] for x in payloads], ['354', '355'])
                self.assertEqual({(x['metric'], x['year'], x['unit']) for x in payloads},
                                 {('water withdrawal', 2010, 'billion gallons per day')})
                return {'conclusion': 'Scripted fixture: values differ, 354 and 355.'}
            if stage == 'halter':
                return {'sufficient': False, 'reason': 'Scripted conflict', 'evidence_assessment': 'conflicting'}
            if stage == 'value': return {'score': .5}
            self.fail('unexpected stage: ' + stage)
        out = run_case(checkpoint, [], model, max_depth=1)
        self.assertEqual(out['status'], 'unknown')
        self.assertIsNone(out['result'])
        assessment = out['unknown_explanation']['model_assessments'][0]
        self.assertEqual((assessment['evidence_assessment'], assessment['origin']), ('conflicting', 'model_unverified'))
        self.assertEqual({r['id'] for r in assessment['selected_source_refs']}, {'source:first', 'source:second'})
        self.assertIn('conflicting evidence', render_outcome(out))


class EffectTruthTests(unittest.TestCase):
    def test_source_callback_failures_never_claim_a_known_effect_or_retry(self):
        for exc in (TimeoutError, ConnectionError, ConnectionResetError, RuntimeError):
            with self.subTest(exc=exc.__name__):
                checkpoint, catalog = checkpoint_fixture()
                calls = []
                def fail(stage, payload):
                    calls.append(stage)
                    raise exc('scripted')
                out = run_case(checkpoint, catalog, fail)
                self.assertEqual(calls, ['source_decision'])
                self.assertEqual(out['unknown_explanation']['callback_effect_state'], 'not_established')
                self.assertIn('dispatch is not proven', render_outcome(out))
                if issubclass(exc, (TimeoutError, ConnectionError)):
                    self.assertEqual(out['status'], 'unknown')
                    self.assertEqual(out['unknown_explanation']['stop_kind'], 'callback_interrupted')
                else:
                    self.assertEqual(out['status'], 'technical_failure')
                    self.assertEqual(out['unknown_explanation']['stop_kind'], 'technical_failure')

    def test_si_connection_failure_and_local_error_are_distinguished(self):
        calls = []
        def disconnected(stage, payload):
            calls.append(stage)
            raise ConnectionResetError('scripted')
        out = StrictEngine(disconnected).run(engine_task())
        self.assertEqual((out['status'], out['reason']), ('unknown', 'callback_interrupted:ConnectionResetError'))
        self.assertEqual(out['unknown_explanation']['callback_effect_state'], 'not_established')
        self.assertEqual(calls, ['selection'])
        with patch('faithful_v3.engine.source_registry', side_effect=ConnectionError('local failure')):
            out = StrictEngine(lambda *_: self.fail('callback must not run')).run(engine_task())
        self.assertEqual((out['status'], out['reason'], out['calls']), ('technical_failure', 'local_error:ConnectionError', 0))
        self.assertNotIn('callback_effect_state', out['unknown_explanation'])

    def test_saved_stop_reason_is_visible_without_source_text(self):
        def model(stage, payload):
            if stage == 'selection': return {'alternatives': [['s1']]}
            if stage == 'inference': return {'conclusion': 'secret inference'}
            if stage == 'halter': return {'sufficient': False, 'reason': 'secret reason'}
            if stage == 'value': return {'score': .5}
            raise AssertionError(stage)
        for config, expected in [(EngineConfig(max_calls=5, max_depth=1), 'reasoning-depth limit reached'),
                                 (EngineConfig(max_calls=5, max_depth=2), 'generation-call limit reached')]:
            out = StrictEngine(model, config).run(engine_task())
            rendered = render_outcome(out)
            self.assertIn(expected, rendered)
            self.assertNotIn('secret', rendered)


if __name__ == '__main__': unittest.main()
