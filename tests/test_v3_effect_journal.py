"""Controller/effect-journal integration using only scripted offline responses."""
from __future__ import annotations

import json
import os
import tempfile
import unittest
from unittest.mock import patch

from faithful_v3.action_case import run_case
from faithful_v3.engine import StrictEngine
from faithful_v3.prompts import VERSION as PROMPT_VERSION, build_request
from reasoning_engine.engine import EngineConfig
from reasoning_engine.executor import EffectExecutor, HttpResponse
from reasoning_engine.journal_callback import JournaledCallback
from reasoning_engine.renderer import render_outcome
from test_strict_v3 import checkpoint_fixture, engine_task


class JournalIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.temp.name, 'effects.sqlite3')
        self.executor = EffectExecutor(self.db, exposure_cap=50, call_cap=20)

    def tearDown(self):
        self.executor.close()
        self.temp.cleanup()

    def restart(self):
        self.executor.close()
        self.executor = EffectExecutor(self.db, exposure_cap=50, call_cap=20)

    def callback(self, transport, session='fixture'):
        return JournaledCallback(self.executor, transport, session_id=session, exposure_per_attempt=2)

    def test_successful_si_records_distinct_receipts_and_isolates_inference(self):
        seen = []
        def transport(request):
            envelope = json.loads(request)
            stage, payload = envelope['stage'], envelope['input']
            self.assertEqual(envelope, build_request(stage, payload))
            self.assertEqual(envelope['prompt_version'], PROMPT_VERSION)
            seen.append((stage, payload))
            if stage == 'selection': response = {'alternatives': [['s1']]}
            elif stage == 'inference':
                self.assertEqual(set(payload), {'selected_texts'})
                self.assertNotIn('USER_TARGET_SENTINEL', json.dumps(envelope))
                self.assertEqual(envelope['instruction'], build_request('inference', payload)['instruction'])
                response = {'conclusion': 'fixture conclusion'}
            elif stage == 'halter': response = {'sufficient': True, 'reason': 'scripted'}
            elif stage == 'value': response = {'score': .5}
            elif stage == 'formatter': response = {'answer': 'fixture conclusion', 'citations': ['s1']}
            else: self.fail('unexpected stage: ' + stage)
            return HttpResponse(200, json.dumps(response).encode())
        out = StrictEngine(self.callback(transport), EngineConfig(max_calls=5)).run(engine_task())
        self.assertEqual(out['status'], 'proposal')
        self.assertEqual([stage for stage, _ in seen], ['selection', 'inference', 'halter', 'value', 'formatter'])
        receipts = [event['operation_receipt'] for event in out['events'] if event['event'] == 'model_returned']
        self.assertEqual(len(receipts), 5)
        self.assertEqual([r['stage'] for r in receipts], [stage for stage, _ in seen])
        self.assertEqual(len({r['operation_id'] for r in receipts}), 5)
        for receipt in receipts:
            self.assertEqual((receipt['state'], receipt['response_status'], receipt['attempts']), ('succeeded', 200, 1))
            self.assertEqual(self.executor.get_result(receipt['operation_id']).state, 'succeeded')

    def test_timeout_stays_uncertain_through_restart_without_a_repeat(self):
        transport_calls = []
        def interrupted(_request):
            transport_calls.append(1)
            raise TimeoutError('PRIVATE_TRANSPORT_ERROR')
        out = StrictEngine(self.callback(interrupted)).run(engine_task())
        self.assertEqual(out['status'], 'unknown')
        receipt = out['unknown_explanation']['effect_receipt']
        self.assertEqual((receipt['stage'], receipt['state'], receipt['attempts']), ('selection', 'uncertain', 1))
        self.assertEqual(self.executor.accounting()['exposure_units'], 2)
        self.restart()
        resumed = StrictEngine(self.callback(interrupted)).run(engine_task())
        again = resumed['unknown_explanation']['effect_receipt']
        self.assertEqual((again['operation_id'], again['state'], again['attempts']),
                         (receipt['operation_id'], 'uncertain', 1))
        self.assertEqual(transport_calls, [1])
        self.assertEqual(self.executor.accounting()['exposure_units'], 2)
        rendered = render_outcome(out)
        self.assertNotIn('PRIVATE_TRANSPORT_ERROR', rendered)
        self.assertNotIn('USER_TARGET_SENTINEL', rendered)

    def test_429_is_known_failed_effect_without_retry(self):
        calls = []
        def transport(_request):
            calls.append(1)
            return HttpResponse(429, b'PRIVATE_RATE_LIMIT_BODY')
        out = StrictEngine(self.callback(transport)).run(engine_task())
        receipt = out['unknown_explanation']['effect_receipt']
        self.assertEqual((receipt['state'], receipt['response_status'], receipt['attempts']), ('failed', 429, 1))
        self.assertEqual(calls, [1])
        self.assertNotIn('PRIVATE_RATE_LIMIT_BODY', render_outcome(out))

    def test_invalid_json_after_200_is_known_successful_effect_not_uncertain(self):
        calls = []
        def transport(_request):
            calls.append(1)
            return HttpResponse(200, b'PRIVATE_INVALID_JSON')
        out = StrictEngine(self.callback(transport)).run(engine_task())
        receipt = out['unknown_explanation']['effect_receipt']
        self.assertEqual((receipt['state'], receipt['response_status'], receipt['parse_status']),
                         ('succeeded', 200, 'invalid_json'))
        self.assertEqual(calls, [1])
        self.assertNotIn('PRIVATE_INVALID_JSON', render_outcome(out))

    def test_source_decision_failure_keeps_its_receipt_in_outer_outcome(self):
        checkpoint, catalog = checkpoint_fixture()
        calls = []
        def transport(request):
            calls.append(json.loads(request)['stage'])
            raise ConnectionResetError('PRIVATE_SOURCE_FAILURE')
        out = run_case(checkpoint, catalog, self.callback(transport))
        receipt = out['unknown_explanation']['effect_receipt']
        self.assertEqual((out['status'], receipt['stage'], receipt['state']), ('unknown', 'source_decision', 'uncertain'))
        self.assertEqual(calls, ['source_decision'])
        self.assertEqual(out['history'][-1]['operation_receipt']['operation_id'], receipt['operation_id'])
        self.assertNotIn('PRIVATE_SOURCE_FAILURE', render_outcome(out))

    def test_later_failure_binds_later_role_not_previous_receipt(self):
        def transport(request):
            stage = json.loads(request)['stage']
            if stage == 'selection': return HttpResponse(200, b'{"alternatives":[["s1"]]}')
            self.assertEqual(stage, 'inference')
            raise ConnectionResetError('fixture')
        out = StrictEngine(self.callback(transport)).run(engine_task())
        receipt = out['unknown_explanation']['effect_receipt']
        self.assertEqual((receipt['stage'], receipt['ordinal'], receipt['state']), ('inference', 2, 'uncertain'))
        self.assertEqual(self.executor.accounting()['calls'], 2)

    def test_reused_session_with_changed_request_never_binds_prior_receipt(self):
        calls = []
        def transport(_request):
            calls.append(1)
            return HttpResponse(200, b'{"alternatives":[["s1"]]}')
        first = self.callback(transport)
        first('selection', {'request': 'first'})
        second = self.callback(transport)
        out = StrictEngine(second).run(engine_task())
        self.assertEqual((out['status'], out['reason']), ('unknown', 'journal_call_journal_error'))
        self.assertNotIn('effect_receipt', out['unknown_explanation'])
        self.assertEqual(out['unknown_explanation']['callback_effect_state'], 'not_established')
        self.assertEqual(calls, [1])

    def test_schema_failure_retains_known_200_receipt(self):
        out = StrictEngine(self.callback(lambda _r: HttpResponse(200, b'{"wrong":"shape"}'))).run(engine_task())
        self.assertEqual(out['status'], 'technical_failure')
        receipt = out['unknown_explanation']['effect_receipt']
        self.assertEqual((receipt['stage'], receipt['state'], receipt['response_status']),
                         ('selection', 'succeeded', 200))

    def test_bad_second_selection_alternative_keeps_original_selection_receipt(self):
        calls = []
        def transport(request):
            stage = json.loads(request)['stage']
            calls.append(stage)
            if stage == 'selection': response = {'alternatives': [['s1'], ['missing-source']]}
            elif stage == 'inference': response = {'conclusion': 'fixture conclusion'}
            elif stage == 'halter': response = {'sufficient': True, 'reason': 'fixture'}
            elif stage == 'value': response = {'score': .5}
            else: self.fail('unexpected call: ' + stage)
            return HttpResponse(200, json.dumps(response).encode())
        out = StrictEngine(self.callback(transport),
                           EngineConfig(max_calls=8, max_alternatives=2)).run(engine_task())
        self.assertEqual(out['status'], 'technical_failure')
        receipt = out['unknown_explanation']['effect_receipt']
        self.assertEqual((receipt['stage'], receipt['ordinal'], receipt['state'], receipt['response_status']),
                         ('selection', 1, 'succeeded', 200))
        self.assertEqual(calls, ['selection', 'inference', 'halter', 'value'])
        self.assertEqual(self.executor.accounting()['calls'], 4)

    def test_source_loop_passes_journal_through_si_wrapper(self):
        checkpoint, catalog = checkpoint_fixture()
        def transport(request):
            envelope = json.loads(request)
            stage = envelope['stage']
            if stage == 'source_decision':
                choice = 'a' if envelope['input']['remaining_actions'] == 2 else 'STOP'
                response = {'choice': choice, 'reason': 'fixture', 'expected_result': 'fixture'}
            elif stage == 'selection':
                raise TimeoutError('fixture')
            else:
                self.fail('unexpected stage: ' + stage)
            return HttpResponse(200, json.dumps(response).encode())
        out = run_case(checkpoint, catalog, self.callback(transport))
        receipt = out['unknown_explanation']['effect_receipt']
        self.assertEqual((receipt['stage'], receipt['state']), ('selection', 'uncertain'))
        self.assertEqual(out['history'][-1]['outcome']['events'][-1]['operation_receipt']['operation_id'],
                         receipt['operation_id'])

    def test_saved_200_survives_parse_write_failure_and_restart_without_repeat(self):
        calls = []
        def transport(_request):
            calls.append(1)
            return HttpResponse(200, b'{"alternatives":[["s1"]]}')
        with patch.object(self.executor, '_parse_after_success', side_effect=RuntimeError('fixture')):
            out = StrictEngine(self.callback(transport)).run(engine_task())
        receipt = out['unknown_explanation']['effect_receipt']
        self.assertEqual((out['status'], out['reason']), ('unknown', 'journal_call_journal_error'))
        self.assertEqual((receipt['state'], receipt['response_status'], receipt['attempts']), ('started', 200, 1))
        self.restart()
        replay = self.callback(transport)
        # Repeat the identical first selection: executor finishes parsing saved
        # bytes and does not invoke the single-shot transport again.
        selection_payload = next(event['payload'] for event in out['events'] if event['event'] == 'model_started')
        self.assertEqual(replay('selection', selection_payload), {'alternatives': [['s1']]})
        self.assertEqual((replay.last_receipt['state'], replay.last_receipt['response_status']), ('succeeded', 200))
        self.assertEqual(calls, [1])
        self.assertEqual(self.executor.accounting()['calls'], 1)

    def test_unreadable_journal_before_registration_is_not_proven_dispatch(self):
        calls = []
        def transport(_request):
            calls.append(1)
            return HttpResponse(200, b'{}')
        with patch.object(self.executor, 'register', side_effect=RuntimeError('journal inaccessible')):
            out = StrictEngine(self.callback(transport)).run(engine_task())
        self.assertEqual((out['status'], out['reason']), ('unknown', 'journal_call_journal_error'))
        self.assertNotIn('effect_receipt', out['unknown_explanation'])
        self.assertEqual(out['unknown_explanation']['callback_effect_state'], 'not_established')
        self.assertEqual(calls, [])
        self.assertEqual(self.executor.accounting()['calls'], 0)

    def test_unreadable_journal_after_callback_never_fabricates_receipt(self):
        calls = []
        def transport(_request):
            calls.append(1)
            return HttpResponse(200, b'{}')
        with patch.object(self.executor, '_save_response', side_effect=RuntimeError('write failed')):
            with patch.object(self.executor, 'get_result', side_effect=RuntimeError('read failed')):
                out = StrictEngine(self.callback(transport)).run(engine_task())
        self.assertEqual((out['status'], out['reason']), ('unknown', 'journal_call_journal_error'))
        self.assertNotIn('effect_receipt', out['unknown_explanation'])
        self.assertEqual(out['unknown_explanation']['callback_effect_state'], 'not_established')
        self.assertEqual(calls, [1])
        self.assertEqual(self.executor.accounting()['calls'], 1)
        # Restoring access and retrying the same operation turns the durable
        # started record into uncertain, without invoking transport a second time.
        self.restart()
        resumed = StrictEngine(self.callback(transport)).run(engine_task())
        receipt = resumed['unknown_explanation']['effect_receipt']
        self.assertEqual((receipt['state'], receipt['attempts']), ('uncertain', 1))
        self.assertEqual(calls, [1])

    def test_invalid_source_decision_preserves_its_known_200_receipt(self):
        checkpoint, catalog = checkpoint_fixture()
        calls = []
        def transport(request):
            calls.append(json.loads(request)['stage'])
            return HttpResponse(200, b'{"choice":"not-an-action", "reason":"fixture"}')
        out = run_case(checkpoint, catalog, self.callback(transport))
        receipt = out['unknown_explanation']['effect_receipt']
        self.assertEqual(out['status'], 'technical_failure')
        self.assertEqual((receipt['stage'], receipt['state'], receipt['response_status']),
                         ('source_decision', 'succeeded', 200))
        self.assertEqual(calls, ['source_decision'])


if __name__ == '__main__':
    unittest.main()
