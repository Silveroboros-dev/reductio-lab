import unittest

from reasoning_engine.evaluator import build_report, compare_inputs


def inputs():
    return {
        "human_task": "Assess claim",
        "evidence_snapshot": {
            "items": [{"type": "article", "source": "example", "timestamp": "2026-10-01T00:00:00Z"}]
        },
        "as_of": "2026-10-02T00:00:00Z",
        "quote": "The quoted claim",
        "prior": {"probability": 0.4},
        "p0": {"value": 0.57, "content": "P0 estimate", "justification": "Prior evidence"},
        "model_settings": {"model": "fixed", "temperature": 0},
        "limits": {"max_tokens": 1000},
        "role_prompt": "Selection role",
        "strategy_prompt": "strategy one",
        "projection": {"selection": ["a", "b"]},
    }


class EvaluatorTests(unittest.TestCase):
    def test_p0_compares_score_content_and_justification(self):
        left, right = inputs(), inputs()
        right["p0"]["content"] = "Different P0 estimate"
        result = compare_inputs(left, right)
        self.assertFalse(result["equal"])
        self.assertTrue(result["fields"]["p0"]["components"]["value"]["equal"])
        self.assertFalse(result["fields"]["p0"]["components"]["content"]["equal"])
        right = inputs()
        right["p0"]["justification"] = "Different justification"
        self.assertFalse(compare_inputs(left, right)["fields"]["p0"]["equal"])

    def test_compare_inputs_rejects_empty_fields_and_missing_values(self):
        left, right = inputs(), inputs()
        with self.assertRaises(ValueError):
            compare_inputs(left, right, fields=())
        del right["quote"]
        result = compare_inputs(left, right)
        self.assertFalse(result["equal"])
        self.assertEqual(result["fields"]["quote"]["reason"], "missing_input")

    def test_comparable_package_passes_with_intentional_prompt_differences(self):
        left, right = inputs(), inputs()
        right["role_prompt"] = "Halter role"
        right["strategy_prompt"] = "different strategy"
        right["projection"] = {"halter": {"threshold": 0.7}}
        result = compare_inputs(left, right)
        self.assertTrue(result["equal"])
        self.assertEqual(
            result["excluded_intentional_difference_fields"],
            ["role_prompt", "strategy_prompt", "projection"],
        )

    def test_unknown_and_failures_remain_in_branch_denominator(self):
        report = build_report({"B": [
            {"assignment_id": "a1", "case_id": "c1", "runtime_status": "completed", "review_status": "unreviewed"},
            {"assignment_id": "a2", "case_id": "c2", "runtime_status": "unknown", "review_status": "not_applicable"},
            {"assignment_id": "a3", "case_id": "c3", "runtime_status": "technical_failure", "review_status": "unreviewed"},
            {"assignment_id": "a4", "case_id": "c4", "runtime_status": "incomplete", "review_status": "adjudicated"},
            {"assignment_id": "a5", "case_id": "c5", "runtime_status": "completed", "review_status": "adjudicated"},
            {"assignment_id": "a6", "case_id": "c6", "runtime_status": "assigned", "review_status": "not_applicable"},
        ]})
        branch = report["branches"]["B"]
        self.assertEqual(branch["denominator"], 6)
        self.assertEqual(sum(branch["runtime_status_counts"].values()), 6)
        self.assertEqual(sum(branch["review_status_counts"].values()), 6)
        self.assertEqual(branch["runtime_status_counts"]["unknown"], 1)
        self.assertEqual(branch["runtime_status_counts"]["technical_failure"], 1)
        self.assertEqual(branch["runtime_status_rates"]["technical_failure"], 1 / 6)
        self.assertEqual(branch["review_status_counts"]["unreviewed"], 2)
        self.assertEqual(branch["runtime_status_counts"]["completed"], 2)

    def test_missing_costs_are_unknown_not_zero(self):
        report = build_report({"C": [
            {"assignment_id": "a1", "case_id": "c1", "runtime_status": "completed", "review_status": "unreviewed", "metrics": {"cost": 0.12}},
            {"assignment_id": "a2", "case_id": "c2", "runtime_status": "unknown", "review_status": "not_applicable", "metrics": {}},
        ]})
        metric = report["branches"]["C"]["metrics_by_runtime_status"]["completed"]["cost"]
        self.assertEqual(metric["known_count"], 1)
        self.assertEqual(metric["unknown_count"], 0)
        self.assertEqual(metric["total"], 0.12)
        unknown_metric = report["branches"]["C"]["metrics_by_runtime_status"]["unknown"]["cost"]
        self.assertEqual(unknown_metric["known_count"], 0)
        self.assertEqual(unknown_metric["unknown_count"], 1)
        self.assertIsNone(unknown_metric["total"])
        self.assertIsNone(unknown_metric["mean"])

    def test_no_outcomes_means_no_forecast_scoring(self):
        report = build_report({"B": [
            {"assignment_id": "a1", "case_id": "c1", "runtime_status": "completed", "review_status": "unreviewed", "metrics": {"tokens": 100}, "output": 0.57}
        ]})
        self.assertFalse(report["forecast_scoring"]["computed"])
        self.assertEqual(report["forecast_scoring"]["reason"], "no_outcome_data")
        self.assertEqual(report["value_or_evidence_accuracy_from_model_numbers"], "not_computed")

    def test_posthoc_outputs_are_kept_out_of_primary_metrics(self):
        report = build_report({"B": [{
            "assignment_id": "a1", "case_id": "c1",
            "runtime_status": "completed", "review_status": "unreviewed",
            "metrics": {"calls": 1},
            "posthoc_outputs": {"explanation": "later annotation"},
        }]})
        branch = report["branches"]["B"]
        self.assertTrue(branch["posthoc_is_separate_from_primary_metrics"])
        self.assertEqual(len(branch["posthoc_outputs"]), 1)
        self.assertEqual(branch["metrics_by_runtime_status"]["completed"]["calls"]["total"], 1)

    def test_exposed_records_are_marked_development_regression(self):
        report = build_report({"C": [
            {"assignment_id": "a1", "case_id": "c1", "runtime_status": "completed", "review_status": "adjudicated", "exposure": "exposed"},
            {"assignment_id": "a2", "case_id": "c2", "runtime_status": "completed", "review_status": "unreviewed", "exposure": "claimed_blind"},
        ]})
        branch = report["branches"]["C"]
        self.assertEqual(branch["exposure_counts"]["exposed"], 1)
        self.assertEqual(branch["exposure_use"]["exposed"], "development_or_regression_only")
        self.assertEqual(branch["exposure_counts"]["claimed_blind"], 1)
        self.assertIn("unverified", branch["exposure_use"]["claimed_blind"])

    def test_duplicate_assignment_or_case_ids_are_rejected(self):
        duplicate_assignment = [
            {"assignment_id": "a", "case_id": "c1", "runtime_status": "completed", "review_status": "unreviewed"},
            {"assignment_id": "a", "case_id": "c2", "runtime_status": "completed", "review_status": "unreviewed"},
        ]
        with self.assertRaisesRegex(ValueError, "duplicate assignment_id"):
            build_report({"B": duplicate_assignment})
        duplicate_case = [
            {"assignment_id": "a1", "case_id": "c", "runtime_status": "completed", "review_status": "unreviewed"},
            {"assignment_id": "a2", "case_id": "c", "runtime_status": "completed", "review_status": "unreviewed"},
        ]
        with self.assertRaisesRegex(ValueError, "duplicate case_id"):
            build_report({"B": duplicate_case})

    def test_confirmation_unexposed_requires_attestation(self):
        record = {"assignment_id": "a", "case_id": "c", "runtime_status": "completed",
                  "review_status": "unreviewed", "exposure": "confirmation_unexposed"}
        with self.assertRaisesRegex(ValueError, "external exposure_attestation"):
            build_report({"B": [record]})
        record["exposure_attestation"] = {"source": "external registry", "reference": "att-1"}
        report = build_report({"B": [record]})
        self.assertEqual(report["branches"]["B"]["exposure_counts"]["confirmation_unexposed"], 1)


if __name__ == "__main__":
    unittest.main()


def test_explicitly_absent_p0_is_comparable_but_missing_is_not():
    from reasoning_engine.evaluator import compare_inputs
    assert compare_inputs({'p0': None}, {'p0': None}, fields=['p0'])['equal']
    assert not compare_inputs({}, {'p0': None}, fields=['p0'])['equal']


def test_rubric_review_keeps_attribution_without_granting_authority():
    import pytest
    from reasoning_engine.evaluator import build_report
    record = {'assignment_id': 'a1', 'case_id': 'case1', 'runtime_status': 'completed',
              'review_status': 'unreviewed', 'rubric_reviews': [{'dimension': 'human_value',
              'verdict': 'unknown', 'reviewer': 'reviewer1', 'origin': 'caller-supplied', 'note': 'needs assessment'}]}
    report = build_report({'C': [record]})['branches']['C']
    assert report['rubric_reviews_as_supplied'][0]['identity_verified'] is False
    assert report['review_status_counts']['unreviewed'] == 1
    record['rubric_reviews'][0]['reviewer'] = ''
    with pytest.raises(ValueError): build_report({'C': [record]})


def test_missing_critical_metadata_is_not_comparable_even_when_both_none():
    from reasoning_engine.evaluator import compare_inputs
    for name in ('human_task', 'evidence_snapshot', 'as_of', 'model_settings', 'limits'):
        result = compare_inputs({name: None}, {name: None}, fields=[name])
        assert not result['equal'] and result['fields'][name]['reason'] == 'unknown_input'


def test_unknown_p0_justification_is_not_a_comparable_prior():
    from reasoning_engine.evaluator import compare_inputs
    p0 = {'value': .57, 'content': 'prior', 'justification': None}
    result = compare_inputs({'p0': p0}, {'p0': p0}, fields=['p0'])
    assert not result['equal'] and result['fields']['p0']['reason'] == 'invalid_p0_shape'
