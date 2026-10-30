import copy
import unittest

from reasoning_engine.baseline import SELF_CHECK_LIMIT, run_baselines


def task():
    return {
        "case_id": "case-1",
        "question": "What does the evidence support?",
        "task_type": "exploration",
        "as_of_utc": "2026-10-05T00:00:00Z",
        "thesis": {"text": "A test thesis", "version": "v1", "origin": "human"},
        "evidence": [{
            "id": "e1", "text": "A source excerpt", "kind": "quote", "source": "source-1",
            "captured_at_utc": "2026-10-04T00:00:00Z",
            "available_at_utc": "2026-10-03T00:00:00Z",
            "published_at_utc": "2026-10-02T00:00:00Z",
        }],
        "unavailable_evidence_ids": ["e2"],
        "required_questions": [
            {"id": "q1", "question": "What supports the claim?", "evidence_ids": ["e1"]},
            {"id": "q2", "question": "What about missing evidence?", "evidence_ids": ["e2"]},
        ],
    }


def answer(text):
    return {
        "answer": text,
        "citations": ["e1", "input:thesis"],
        "assessments": [{"id": "q1", "status": "assessed", "reason": "The provided quote is relevant."}],
    }


class BaselineTests(unittest.TestCase):
    def test_same_prepared_package_and_recheck_receives_only_prior_result(self):
        calls = []
        first = answer("B1 initial")
        bself_initial = answer("B_self initial")
        second = answer("rechecked")

        def generate(stage, payload):
            calls.append((stage, copy.deepcopy(payload)))
            if stage == "baseline_recheck":
                return second
            return first if len(calls) == 1 else bself_initial

        report = run_baselines(task(), generate)
        self.assertEqual([s for s, _ in calls], ["baseline_initial", "baseline_initial", "baseline_recheck"])
        b1_payload, bself_payload, recheck_payload = [p for _, p in calls]
        self.assertEqual(b1_payload, bself_payload)
        self.assertIn("thesis", b1_payload)
        self.assertEqual(b1_payload["evidence"][0]["id"], "e1")
        self.assertEqual(b1_payload["required_questions"][0]["id"], "q1")
        self.assertEqual(set(recheck_payload), {"prepared_task", "previous_response"})
        self.assertEqual(recheck_payload["prepared_task"], bself_payload)
        self.assertEqual(recheck_payload["previous_response"], bself_initial)
        self.assertEqual(report["self_check_limit"], SELF_CHECK_LIMIT)
        self.assertEqual(set(report["branches"]), {"B1", "B_self"})
        self.assertEqual(report["branches"]["B1"]["calls"], 1)
        self.assertEqual(report["branches"]["B_self"]["calls"], 2)
        self.assertEqual(len(report["branches"]["B_self"]["responses"]), 2)
        self.assertEqual(report["branches"]["B_self"]["responses"][0]["response"], bself_initial)
        self.assertEqual(report["branches"]["B_self"]["responses"][1]["response"], second)
        self.assertEqual(report["branches"]["B_self"]["final_result"], second)
        self.assertEqual(report["branches"]["B_self"]["responses"][1]["payload"], recheck_payload)

    def test_success_is_unreviewed_and_reports_coverage(self):
        report = run_baselines(task(), lambda _stage, _payload: answer("supported"))
        b1 = report["branches"]["B1"]
        self.assertEqual(b1["semantic_status"], "unreviewed")
        self.assertEqual(b1["status"], "incomplete")
        self.assertEqual(b1["coverage_counts"]["assessed"], 1)
        self.assertEqual(b1["coverage_counts"]["source_unavailable"], 1)
        self.assertEqual(b1["coverage"][0]["assessment_origin"], "model_unverified")

    def test_failed_self_check_preserves_history_but_does_not_fallback_final(self):
        def generate(stage, _payload):
            if stage == "baseline_recheck":
                raise RuntimeError("offline failure")
            return answer("initial survives in history")

        report = run_baselines(task(), generate)
        bself = report["branches"]["B_self"]
        self.assertEqual(bself["status"], "technical_failure")
        self.assertIsNone(bself["final_result"])
        self.assertEqual(bself["last_valid_response"], answer("initial survives in history"))
        self.assertEqual(bself["responses"][0]["response"], answer("initial survives in history"))
        self.assertEqual(bself["responses"][1]["error"], "RuntimeError")
        self.assertEqual(bself["responses"][1]["payload"]["previous_response"], answer("initial survives in history"))
        self.assertIn("prepared_task", bself["responses"][1]["payload"])

    def test_formatter_shape_is_validated_and_bad_answer_is_not_selected(self):
        bad = answer("bad citation")
        bad["citations"] = ["not-in-bundle"]
        report = run_baselines(task(), lambda _stage, _payload: bad)
        b1 = report["branches"]["B1"]
        self.assertEqual(b1["status"], "technical_failure")
        self.assertIsNone(b1["final_result"])
        self.assertIn("citations", b1["reason"])
        self.assertEqual(b1["responses"][0]["response"], bad)
        self.assertIn("case_id", b1["responses"][0]["payload"])


if __name__ == "__main__":
    unittest.main()
