import os
import tempfile
import unittest

from reasoning_engine.executor import (
    BudgetExceeded,
    JournalError,
    OperationConflict,
    EffectExecutor,
    HttpResponse,
    RetryPolicy,
)


class EffectExecutorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.temp.name, "journal.sqlite3")
        self.sleeps = []
        self.executor = EffectExecutor(
            self.db, exposure_cap=100, call_cap=20,
            sleep=self.sleeps.append, rng=lambda: 0.5,
        )

    def tearDown(self):
        self.executor.close()
        self.temp.cleanup()

    def register(self, op_id, *, exposure=2, branch="branch-a"):
        self.executor.register(op_id, branch=branch, request=b"payload",
                               exposure_per_attempt=exposure)

    def test_explicit_429_recovers_only_with_pre_authorized_policy(self):
        self.register("recover")
        responses = iter([HttpResponse(429, b"busy"), HttpResponse(200, b'{"ok":true}')])
        calls = []

        def callback(request):
            calls.append(request)
            return next(responses)

        result = self.executor.execute(
            "recover", callback=callback,
            retry=RetryPolicy(allow_429=True, max_attempts=3,
                              base_backoff_seconds=2, max_backoff_seconds=5),
        )
        self.assertEqual(result.state, "succeeded")
        self.assertEqual(result.attempts, 2)
        self.assertEqual(result.parse_status, "valid_json")
        self.assertEqual(calls, [b"payload", b"payload"])
        self.assertEqual(self.sleeps, [1.0])
        self.assertEqual(self.executor.accounting()["calls"], 2)
        self.assertEqual(self.executor.accounting()["exposure_units"], 4)

    def test_429_without_pre_authorization_is_not_retried(self):
        self.register("no-retry")
        calls = []

        def callback(_request):
            calls.append(1)
            return HttpResponse(429, b"busy")

        result = self.executor.execute("no-retry", callback=callback)
        self.assertEqual(result.state, "failed")
        self.assertEqual(result.attempts, 1)
        self.assertEqual(len(calls), 1)

    def test_retry_authorization_is_durable_across_resume(self):
        self.register("resume-429")
        self.executor.close()
        sleep_fails = EffectExecutor(self.db, exposure_cap=100, call_cap=20,
                                     sleep=lambda _delay: (_ for _ in ()).throw(RuntimeError("stop")),
                                     rng=lambda: 0.5)
        policy = RetryPolicy(allow_429=True, max_attempts=3)
        with self.assertRaises(RuntimeError):
            sleep_fails.execute("resume-429", callback=lambda _r: HttpResponse(429, b"busy"), retry=policy)
        self.assertEqual(sleep_fails.get_result("resume-429").state, "ready")
        sleep_fails.close()
        self.executor = EffectExecutor(self.db, exposure_cap=100, call_cap=20,
                                       sleep=self.sleeps.append, rng=lambda: 0.5)
        with self.assertRaises(OperationConflict):
            self.executor.execute("resume-429", callback=lambda _r: self.fail("policy mismatch must block"))
        resumed = self.executor.execute("resume-429", callback=lambda _r: HttpResponse(200, b"{}"), retry=policy)
        self.assertEqual(resumed.state, "succeeded")
        self.assertEqual(resumed.attempts, 2)

    def test_429_retries_exhausted(self):
        self.register("exhaust")
        calls = []

        def callback(_request):
            calls.append(1)
            return HttpResponse(429, b"slow down")

        result = self.executor.execute("exhaust", callback=callback,
                                       retry=RetryPolicy(allow_429=True, max_attempts=2))
        self.assertEqual(result.state, "failed")
        self.assertEqual(result.attempts, 2)
        self.assertEqual(len(calls), 2)
        self.assertIn("429", result.error)

    def test_timeout_is_uncertain_never_repeated_and_other_branch_runs(self):
        self.register("ambiguous", branch="branch-a")
        self.register("independent", branch="branch-b")
        calls = []

        def timeout(_request):
            calls.append("timeout")
            raise TimeoutError("no response")

        result = self.executor.execute("ambiguous", callback=timeout,
                                       retry=RetryPolicy(allow_429=True, max_attempts=4))
        self.assertEqual(result.state, "uncertain")
        self.assertEqual(result.attempts, 1)
        again = self.executor.execute("ambiguous", callback=timeout,
                                      retry=RetryPolicy(allow_429=True, max_attempts=4))
        self.assertEqual(again.state, "uncertain")
        self.assertEqual(calls, ["timeout"])

        other = self.executor.execute("independent", callback=lambda _r: HttpResponse(200, b"{}"))
        self.assertEqual(other.state, "succeeded")
        self.assertEqual(self.executor.accounting()["calls"], 2)
        # Timeout exposure is held, not released, and remains counted.
        self.assertEqual(self.executor.accounting()["exposure_units"], 4)

    def test_connection_error_is_durably_uncertain_and_not_retried(self):
        self.register('disconnect')
        calls = []
        def disconnected(_request):
            calls.append('attempt')
            raise ConnectionResetError('fixture only')
        policy = RetryPolicy(allow_429=True, max_attempts=4)
        first = self.executor.execute('disconnect', callback=disconnected, retry=policy)
        self.assertEqual((first.state, first.attempts), ('uncertain', 1))
        self.executor.close()
        self.executor = EffectExecutor(self.db, exposure_cap=100, call_cap=20,
                                       sleep=self.sleeps.append, rng=lambda: 0.5)
        resumed = self.executor.execute('disconnect', callback=disconnected, retry=policy)
        self.assertEqual((resumed.state, resumed.attempts), ('uncertain', 1))
        self.assertEqual(calls, ['attempt'])
        self.assertEqual(self.executor.accounting()['exposure_units'], 2)

    def test_200_invalid_json_is_successful_effect_without_retry(self):
        self.register("bad-json")
        calls = []

        def callback(_request):
            calls.append(1)
            return HttpResponse(200, b"\xffnot-json")

        result = self.executor.execute("bad-json", callback=callback,
                                       retry=RetryPolicy(allow_429=True, max_attempts=4))
        self.assertEqual(result.state, "succeeded")
        self.assertEqual(result.raw_response, b"\xffnot-json")
        self.assertEqual(result.response_status, 200)
        self.assertEqual(result.parse_status, "invalid_json")
        self.assertIsNotNone(result.parse_error)
        self.assertEqual(len(calls), 1)

    def test_accounting_caps_and_persistent_resume(self):
        self.register("persist", exposure=3)
        result = self.executor.execute("persist", callback=lambda _r: HttpResponse(200, b'{"n":7}'))
        self.assertEqual(result.state, "succeeded")
        self.executor.close()

        # Same journal cannot increase caps; completed operations resume from
        # durable state without invoking the callback.
        self.executor = EffectExecutor(self.db, exposure_cap=100, call_cap=20,
                                       sleep=self.sleeps.append, rng=lambda: 0.5)
        self.assertEqual(self.executor.accounting(), {
            "calls": 1, "exposure_units": 3, "call_cap": 20, "exposure_cap": 100
        })
        resumed = self.executor.execute(
            "persist", callback=lambda _r: self.fail("callback must not run on resume"))
        self.assertEqual(resumed.parsed_json, {"n": 7})
        self.assertEqual(self.executor.accounting()["calls"], 1)

        self.register("over-cap", exposure=98)
        with self.assertRaises(BudgetExceeded):
            self.executor.execute("over-cap", callback=lambda _r: self.fail("cap must stop dispatch"))
        self.assertEqual(self.executor.get_result("over-cap").state, "failed")
        self.assertEqual(self.executor.accounting()["calls"], 1)

    def test_call_cap_stops_next_operation_without_stopping_prior_result(self):
        self.executor.close()
        self.executor = EffectExecutor(self.db, exposure_cap=100, call_cap=1)
        self.register("first")
        self.register("second")
        calls = []
        first = self.executor.execute("first", callback=lambda _r: (calls.append(1) or HttpResponse(200, b"{}")))
        self.assertEqual(first.state, "succeeded")
        with self.assertRaises(BudgetExceeded):
            self.executor.execute("second", callback=lambda _r: self.fail("call cap must stop dispatch"))
        self.assertEqual(self.executor.get_result("second").state, "failed")
        self.assertEqual(len(calls), 1)
        self.assertEqual(self.executor.accounting()["calls"], 1)

    def test_reopening_cannot_raise_persistent_caps(self):
        self.executor.close()
        with self.assertRaises(JournalError):
            EffectExecutor(self.db, exposure_cap=101, call_cap=20)
        self.executor = EffectExecutor(self.db, exposure_cap=100, call_cap=20)


if __name__ == "__main__":
    unittest.main()
