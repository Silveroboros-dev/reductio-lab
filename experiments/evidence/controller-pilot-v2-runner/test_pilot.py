import json
import hashlib
import tempfile
import unittest
from pathlib import Path

from pilot import CostGuard, Pilot, StopRun, TechnicalFailure, MAX_PROMPT_BYTES, run, validate_cases, load_carry


def decision(action="stop", action_id=None, answer="unknown"):
    return {"action": action, "action_id": action_id, "rationale": "rationale",
            "expected_result": "expected", "answer": answer, "stop_reason": "reason", "uncertainty": "gap",
            "observed_vs_expected": "matches expectation"}


def envelope(value, *, usage=None, version="stable"):
    return json.dumps({"modelVersion": version,
        "usageMetadata": usage if usage is not None else {"promptTokenCount": 40, "totalTokenCount": 65},
        "candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": json.dumps(value)}]}}]}).encode()


class FakeProvider:
    def __init__(self, values, *, count=100):
        self.values = list(values)
        self.prompts = []
        self.count = count
        self.kinds = []

    def request(self, prompt, *, count=False):
        self.prompts.append(prompt)
        self.kinds.append("count" if count else "generate")
        if count:
            return (200, json.dumps({"totalTokens": self.count}).encode(), 0.01)
        item = self.values.pop(0)
        if isinstance(item, Exception):
            raise item
        return 200, item if isinstance(item, bytes) else envelope(item), 0.01


def case():
    return {"id": "case", "question": "Find the number", "initial_evidence": [],
        "actions": [{"id": "a", "description": "fetch a"}, {"id": "b", "description": "fetch b"}],
        "saved_replay": {"a": {"text": "selected result"}, "b": {"text": "UNSEEN_SECRET_RESULT"}}}


class PilotTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)

    def pilot(self, values, **kwargs):
        provider = FakeProvider(values, **kwargs)
        return Pilot(provider, self.path, CostGuard("1.50", "9")), provider

    def events(self):
        return [json.loads(s) for s in (self.path / "events.jsonl").read_text().splitlines()]

    def test_c_verifier_before_action_reconsideration_and_no_leak(self):
        p, provider = self.pilot([decision(), {"issue": True, "critique": "query first"},
                                  decision("query", "a"), decision(answer="selected")])
        out = p.episode(case(), "C")
        self.assertEqual(out["generations"], 4)
        self.assertEqual(out["source_reads"], 1)
        for index in (0, 2, 3):
            prompt = provider.prompts[index]
            self.assertIn('The only allowed action values are the literal strings "query" and "stop"', prompt)
            self.assertIn('Every field except', prompt)
            self.assertIn('never null', prompt)
        events = self.events()
        self.assertEqual([e["role"] for e in events if e["event"] == "started"],
                         ["proposal", "verifier", "reconsider", "after_retrieval"])
        self.assertGreater(next(i for i,e in enumerate(events) if e["event"] == "local_replay"),
                           next(i for i,e in enumerate(events) if e.get("role") == "reconsider"))
        self.assertTrue(all("UNSEEN_SECRET_RESULT" not in prompt for prompt in provider.prompts))
        self.assertTrue(all("selected result" not in prompt for prompt in provider.prompts[:3]))
        self.assertIn("selected result", provider.prompts[3])

    def test_no_critique_means_no_reconsideration(self):
        p, _ = self.pilot([decision(), {"issue": False, "critique": ""}])
        p.episode(case(), "C")
        self.assertEqual([e["role"] for e in self.events() if e["event"] == "started"], ["proposal", "verifier"])

    def test_flag_requires_explanation(self):
        p, _ = self.pilot([decision(), {"issue": True, "critique": "  "}])
        with self.assertRaises(TechnicalFailure):
            p.episode(case(), "C")

    def test_no_expectation_is_not_reconstructed(self):
        query = decision("query", "a")
        query["expected_result"] = ""
        followup = decision(answer="selected")
        followup["observed_vs_expected"] = "not recorded"
        p, provider = self.pilot([query, followup])
        out = p.episode(case(), "B")
        self.assertEqual(out["chosen_final"]["observed_vs_expected"], "not recorded")
        self.assertIn("never invent an earlier expectation", provider.prompts[1])

    def test_self_check_before_query(self):
        p, provider = self.pilot([decision("query", "a"), decision("query", "a"), decision(answer="selected")])
        p.episode(case(), "B_self_check")
        events = self.events()
        self.assertEqual([e["role"] for e in events if e["event"] == "started"], ["proposal", "self_check", "after_retrieval"])
        self.assertGreater(next(i for i,e in enumerate(events) if e["event"] == "local_replay"),
                           next(i for i,e in enumerate(events) if e.get("role") == "self_check"))
        self.assertIn('The only allowed action values are the literal strings "query" and "stop"', provider.prompts[1])

    def test_unknown_usage_halts_with_reserved_cost(self):
        p, _ = self.pilot([envelope(decision(), usage={})])
        with self.assertRaises(StopRun):
            p.episode(case(), "B")
        self.assertEqual(p.guard.used, 98304)
        self.assertTrue((self.path / "response-001.bin").exists())
        self.assertEqual([e["event"] for e in self.events()][:3], ["episode_started", "started", "received"])

    def test_uncertain_effect_does_not_retry(self):
        p, provider = self.pilot([TimeoutError()])
        with self.assertRaises(StopRun):
            p.episode(case(), "B")
        self.assertEqual(provider.kinds, ["generate"])
        self.assertEqual(p.guard.attempts, 1)
        self.assertEqual([e["effect"] for e in self.events() if e["event"] == "terminal"], ["uncertain"])

    def test_response_terminal_before_parsing(self):
        p, _ = self.pilot([decision()])
        p.episode(case(), "B")
        events = self.events()
        terminal = next(i for i, e in enumerate(events) if e["event"] == "terminal")
        parsed = next(i for i, e in enumerate(events) if e["event"] == "parsed")
        self.assertLess(terminal, parsed)
        self.assertEqual(events[terminal]["effect"], "succeeded")
        self.assertTrue((self.path / "response-001.bin").exists())

    def test_version_drift_stops(self):
        p, _ = self.pilot([envelope(decision(), version="a"), envelope({"issue": False, "critique": ""}, version="b")])
        with self.assertRaises(StopRun):
            p.episode(case(), "C")

    def test_count_only_long_and_no_truncation(self):
        long_case = case()
        long_case["initial_evidence"] = [{"text": "x" * (MAX_PROMPT_BYTES + 1)}]
        p, provider = self.pilot([decision()], count=5000)
        p.episode(long_case, "B")
        self.assertEqual(provider.kinds, ["count", "generate"])
        self.assertIn("x" * (MAX_PROMPT_BYTES + 1), provider.prompts[1])
        self.assertEqual(p.token_count_attempts, 1)

    def test_excessive_count_fails_closed_before_generation(self):
        long_case = case()
        long_case["initial_evidence"] = [{"text": "x" * (MAX_PROMPT_BYTES + 1)}]
        p, provider = self.pilot([], count=16385)
        with self.assertRaises(TechnicalFailure):
            p.episode(long_case, "B")
        self.assertEqual(provider.kinds, ["count"])
        self.assertEqual(p.guard.attempts, 0)

    def test_output_above_reservation_stops(self):
        p, _ = self.pilot([envelope(decision(), usage={"promptTokenCount": 10, "totalTokenCount": 9000})])
        with self.assertRaises(StopRun):
            p.episode(case(), "B")
        self.assertGreaterEqual(p.guard.used, 98304)

    def test_budget_attempt_cap(self):
        g = CostGuard("1.5", "9")
        for _ in range(80):
            g.begin()
        with self.assertRaises(StopRun):
            g.begin()

    def test_actual_predecessor_carry_and_digest_rejection(self):
        root = Path("/Users/rk/.codex/visualizations/2026/10/29/01a1865f-6bd2-75a2-abb1-eb14b071bbe0/controller-pilot-v2-live-run")
        summary, events = root / "summary.json", root / "events.jsonl"
        summary_sha = hashlib.sha256(summary.read_bytes()).hexdigest()
        events_sha = hashlib.sha256(events.read_bytes()).hexdigest()
        carry = load_carry(summary, summary_sha, events, events_sha)
        guard = CostGuard("1.50", "9")
        guard.apply_carry(carry)
        self.assertEqual((guard.attempts, guard.used, carry["count_attempts"]), (3, 12845, 0))
        with self.assertRaises(ValueError):
            load_carry(summary, "0" * 64, events, events_sha)
        guard.begin()
        self.assertEqual((guard.attempts, guard.used), (4, 12845 + 98304))

    def test_preexisting_input_schema_valid(self):
        input_file = Path("/Users/rk/.codex/visualizations/2026/10/29/01a1865f-6bd2-75a2-abb1-eb14b071bbe0/controller-pilot-v2-inputs/cases.json")
        self.assertEqual(len(validate_cases(json.loads(input_file.read_bytes()))), 6)

    def test_two_consecutive_failures_stop(self):
        canary = [decision(), {"issue": True, "critique": "query"}, decision("query", "synthetic-report"), decision(answer="27")]
        # Every following invalid decision is a technical episode failure.
        p, provider = self.pilot(canary + [{"bad": True}, {"bad": True}, decision()])
        cases = [dict(case(), id="case" + str(i)) for i in range(6)]
        result = run(p, cases)
        self.assertEqual(result["status"], "stopped_consecutive_failures")
        self.assertEqual(len(result["results"]), 2)
        self.assertEqual(len(provider.values), 1)


if __name__ == "__main__":
    unittest.main()
