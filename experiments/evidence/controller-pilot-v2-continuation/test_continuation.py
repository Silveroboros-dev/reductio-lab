import json
import tempfile
import unittest
from pathlib import Path

import continuation as c


class FakeRunner:
    def __init__(self, pilot, actions):
        self.pilot = pilot
        self.actions = list(actions)
        self.seen = []
        self.logs = []
        self.guard = pilot.CostGuard('1.50', '9')
        self.guard.attempts = 31
        self.guard.used = 359587
        self.version = c.MODEL_VERSION

    def episode(self, case, arm):
        slot = case['id'] + ':' + arm
        self.seen.append(slot)
        action = self.actions.pop(0) if self.actions else 'ok'
        if action == 'technical':
            raise self.pilot.TechnicalFailure('synthetic failure')
        if action == 'global':
            raise self.pilot.StopRun('synthetic uncertainty')
        return {'slot': slot, 'status': 'completed'}

    def log(self, **event):
        self.logs.append(event)


class ContinuationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pilot = c.load_pilot()
        cls.slots = c.verify_predecessor(cls.pilot)

    def test_carry_and_only_seven_unstarted_slots(self):
        self.assertEqual(tuple(x['id'] + ':' + a for x, a in self.slots), c.EXPECTED_REMAINING)
        self.assertNotIn('usgs_withdrawal:B_self_check', c.EXPECTED_REMAINING)
        self.assertEqual(len(set(c.EXPECTED_REMAINING)), 7)
        self.assertFalse(set(c.EXPECTED_STARTED) & set(c.EXPECTED_REMAINING))
        runner = FakeRunner(self.pilot, [])
        result = c.run_continuation(self.pilot, runner, self.slots)
        self.assertEqual(result['status'], 'completed')
        self.assertEqual(tuple(runner.seen), c.EXPECTED_REMAINING)
        self.assertEqual((result['attempts'], result['estimated_or_reserved_micro_usd']), (31, 359587))

    def test_predecessor_consecutive_failure_counts(self):
        runner = FakeRunner(self.pilot, ['technical', 'ok'])
        result = c.run_continuation(self.pilot, runner, self.slots)
        self.assertEqual(result['status'], 'stopped_consecutive_failures')
        self.assertEqual(runner.seen, [c.EXPECTED_REMAINING[0]])
        self.assertEqual(runner.logs[-1]['reason'], 'two consecutive technical episode failures')

    def test_success_resets_failure_counter(self):
        runner = FakeRunner(self.pilot, ['ok', 'technical', 'ok'])
        result = c.run_continuation(self.pilot, runner, self.slots)
        self.assertEqual(result['status'], 'completed')
        self.assertEqual(len(runner.seen), 7)
        self.assertEqual(result['results'][1]['status'], 'technical_failure')

    def test_global_uncertainty_stops_without_retry(self):
        runner = FakeRunner(self.pilot, ['global', 'ok'])
        result = c.run_continuation(self.pilot, runner, self.slots)
        self.assertEqual(result['status'], 'stopped_boundary')
        self.assertEqual(runner.seen, [c.EXPECTED_REMAINING[0]])

    def test_predecessor_digest_mismatch_fails_closed(self):
        with self.assertRaises(ValueError):
            c.read_bound(c.PREDECESSOR / 'summary.json', '0' * 64)

    def test_create_only_fence_blocks_second_process(self):
        with tempfile.TemporaryDirectory() as temp:
            fence = Path(temp) / 'fence.json'
            c.claim_dispatch(self.pilot, fence, Path(temp))
            original = fence.read_bytes()
            with self.assertRaises(FileExistsError):
                c.claim_dispatch(self.pilot, fence, Path(temp))
            self.assertEqual(fence.read_bytes(), original)

    def test_model_version_pinned_before_first_call(self):
        p = self.pilot
        class FakeProvider:
            def request(self, prompt, *, count=False):
                data = {'modelVersion': 'different-version', 'usageMetadata': {'promptTokenCount': 10, 'totalTokenCount': 20},
                        'candidates': [{'finishReason': 'STOP', 'content': {'parts': [{'text': '{}'}]}}]}
                return 200, json.dumps(data).encode(), 0.0
        with tempfile.TemporaryDirectory() as temp:
            runner = p.Pilot(FakeProvider(), Path(temp), p.CostGuard('1.5', '9'), carried_count_attempts=6)
            runner.version = c.MODEL_VERSION
            with self.assertRaises(p.StopRun):
                runner.call('proposal', 'prompt', {'question': 'x'})
            events = [json.loads(line) for line in (Path(temp) / 'events.jsonl').read_text().splitlines()]
            self.assertEqual([e['event'] for e in events if e['event'] == 'parsed'], [])
            self.assertEqual(runner.guard.attempts, 1)

    def test_inherited_generation_ceiling(self):
        guard = self.pilot.CostGuard('1.5', '9')
        guard.attempts, guard.used = 31, 359587
        for _ in range(49):
            guard.begin()
        with self.assertRaises(self.pilot.StopRun):
            guard.begin()

    def test_inherited_count_ceiling_and_count_numbering(self):
        p = self.pilot
        class FakeProvider:
            def __init__(self): self.calls = []
            def request(self, prompt, *, count=False):
                self.calls.append(count)
                return 200, json.dumps({'totalTokens': 9000}).encode(), 0.0
        with tempfile.TemporaryDirectory() as temp:
            provider = FakeProvider()
            runner = p.Pilot(provider, Path(temp), p.CostGuard('1.5', '9'), carried_count_attempts=80)
            with self.assertRaises(p.TechnicalFailure):
                runner.call('proposal', 'x' * (p.MAX_PROMPT_BYTES + 1), {})
            self.assertEqual(provider.calls, [])


if __name__ == '__main__': unittest.main()
