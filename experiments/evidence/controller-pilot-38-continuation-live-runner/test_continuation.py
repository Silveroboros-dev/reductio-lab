import contextlib
import io
import json
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

import continuation as c


class Technical(Exception):
    pass


class Stop(Technical):
    pass


class Unavailable(Technical):
    pass


class StubRunner:
    def __init__(self, outputs):
        self.outputs = list(outputs)
        self.seen = []
        self.events = []
        self.guard = types.SimpleNamespace(attempts=43, used=423627)
        self.version = c.MODEL
        self.token_count_attempts = 8

    def episode(self, case, arm):
        self.seen.append(case['id'] + ':' + arm)
        value = self.outputs.pop(0)
        if isinstance(value, Exception):
            raise value
        return {'slot': self.seen[-1], 'status': 'completed'}

    def log(self, **event):
        self.events.append(event)


PILOT = types.SimpleNamespace(TechnicalFailure=Technical, StopRun=Stop, ModelUnavailable=Unavailable)
SLOTS = [({'id': 'a'}, 'B'), ({'id': 'b'}, 'C'), ({'id': 'c'}, 'B')]


class ContinuationTest(unittest.TestCase):
    def test_bound_evidence_and_exact_never_started_order(self):
        original, draft, pilot, slots, evidence, config, versions, digest = c.prepare()
        self.assertEqual(len(slots), 14)
        self.assertEqual(tuple(case['id'] + ':' + arm for case, arm in slots), draft.REMAINING)
        self.assertEqual((evidence['attempts'], evidence['counts'], evidence['estimated_plus_reserved_micro_usd']), (43, 8, 423627))
        self.assertEqual(evidence['prior_012'], 'uncertain')
        self.assertEqual(config['adapted_pilot_sha256'], digest)
        self.assertTrue(set(draft.STARTED).isdisjoint(draft.REMAINING))

    def test_first_failure_is_second_consecutive_and_stops(self):
        runner = StubRunner([Technical('invalid output'), None])
        result = c.run_remaining(PILOT, runner, SLOTS)
        self.assertEqual(result['status'], 'stopped_consecutive_failures')
        self.assertEqual(runner.seen, ['a:B'])

    def test_success_resets_streak_429_delays_next_different_slot(self):
        runner = StubRunner([None, Technical('HTTP 429; complete response; cost reserved'), None])
        with patch.object(c.time, 'sleep') as sleep:
            result = c.run_remaining(PILOT, runner, SLOTS)
        self.assertEqual(result['status'], 'completed')
        self.assertEqual(runner.seen, ['a:B', 'b:C', 'c:B'])
        sleep.assert_called_once_with(5)
        self.assertEqual(result['results'][1]['status'], 'technical_failure')

    def test_ambiguous_effect_stops_without_retry(self):
        runner = StubRunner([Stop('provider effect uncertain'), None])
        result = c.run_remaining(PILOT, runner, SLOTS)
        self.assertEqual(result['status'], 'stopped_boundary')
        self.assertEqual(runner.seen, ['a:B'])

    def test_unavailable_does_not_switch_model(self):
        runner = StubRunner([Unavailable('unavailable'), None])
        result = c.run_remaining(PILOT, runner, SLOTS)
        self.assertEqual(result['status'], 'stopped_boundary')
        self.assertEqual(runner.seen, ['a:B'])
        self.assertEqual(result['selected_model'], c.MODEL)

    def test_420_seconds_applies_to_all_httpx_phases(self):
        seen = []
        class FakeCredentials:
            def before_request(self, request, method, url, headers):
                request('POST', 'https://identity.invalid')
        class FakeTransport:
            def __init__(self, pilot, model):
                self.model = model
                self.client = types.SimpleNamespace(timeout=None)
                self.credentials = FakeCredentials()
        transport = c.transport_420(types.SimpleNamespace(Transport=FakeTransport), object())
        self.assertEqual(transport.model, c.MODEL)
        self.assertEqual((transport.client.timeout.connect, transport.client.timeout.read,
                          transport.client.timeout.write, transport.client.timeout.pool), (420, 420, 420, 420))
        transport.credentials.before_request(lambda *a, **kw: seen.append(kw['timeout']), 'POST', 'x', {})
        self.assertEqual(seen, [420])

    def test_one_dispatch_fence_and_no_network_mock_run(self):
        class FakeProvider:
            def __init__(self):
                self.calls = 0
            def request(self, prompt, *, count=False):
                if count:
                    return 200, b'{"totalTokens":1000}', 0.01
                self.calls += 1
                if prompt.startswith('Independently critique'):
                    result = {'issue': False, 'critique': ''}
                else:
                    result = {'action': 'stop', 'action_id': None, 'rationale': 'r', 'expected_result': '',
                              'answer': 'unknown', 'stop_reason': 'r', 'uncertainty': 'gap'}
                envelope = {'modelVersion': c.MODEL,
                    'usageMetadata': {'promptTokenCount': 10, 'totalTokenCount': 20},
                    'candidates': [{'finishReason': 'STOP', 'content': {'parts': [{'text': json.dumps(result)}]}}]}
                return 200, json.dumps(envelope).encode(), 0.01
        provider = FakeProvider()
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)
            with patch.object(c, 'LOCK', p / 'dispatch.lock'), patch.object(c, 'transport_420', return_value=provider), \
                 patch('sys.argv', ['continuation.py', '--output', str(p / 'run1'), '--execute-live']), \
                 contextlib.redirect_stdout(io.StringIO()):
                c.main()
            summary = json.loads((p / 'run1/summary.json').read_bytes())
            self.assertEqual(summary['status'], 'completed')
            self.assertEqual(len(summary['results']), 14)
            self.assertGreater(provider.calls, 14)
            self.assertEqual(summary['attempts'], 43 + provider.calls)
            with patch.object(c, 'LOCK', p / 'dispatch.lock'), patch.object(c, 'transport_420', return_value=provider), \
                 patch('sys.argv', ['continuation.py', '--output', str(p / 'run2'), '--execute-live']):
                with self.assertRaises(FileExistsError):
                    c.main()
            self.assertFalse((p / 'run2').exists())


if __name__ == '__main__':
    unittest.main()
