import unittest

from reasoning_engine.renderer import render_outcome


class RendererTests(unittest.TestCase):
    def engine_outcome(self):
        return {
            "version": "faithful-engine-v1",
            "case_id": "case-1",
            "status": "incomplete",
            "reason": "model_proposal_requires_semantic_review",
            "semantic_status": "unreviewed",
            "selected_branch": "root.1.1",
            "result": {"answer": "no other news", "citations": ["wire"], "assessments": []},
            "coverage": [
                {"question_id": "q1", "question": "Was PCE assessed?", "status": "not_assessed",
                 "reason": "required evidence not supplied to selected formatter context",
                 "evidence_ids": ["pce"], "unselected_ids": ["pce"], "missing_ids": []},
                {"question_id": "q2", "question": "Was the source available?", "status": "source_unavailable",
                 "reason": "required evidence absent from the supplied bundle", "evidence_ids": ["absent"],
                 "missing_ids": ["absent"], "unselected_ids": []},
                {"question_id": "q3", "question": "What was assessed?", "status": "assessed",
                 "reason": "recorded claim", "evidence_ids": ["wire"], "missing_ids": [], "unselected_ids": []},
                {"question_id": "q4", "status": "insufficient_evidence", "reason": "thin record"},
            ],
            "evidence": [
                {"id": "wire", "text": "A selected source", "source": "Wire", "kind": "news"},
                {"id": "pce", "text": "PCE remains a candidate", "source": "Archive", "kind": "observation"},
            ],
            "selected_trace": [{"selected_ids": ["wire"], "conclusion_id": "node:0001",
                                 "conclusion": "No other news", "depth": 1, "verification": "unreviewed"}],
            "events": [
                {"event": "model_started", "stage": "formatter", "ordinal": 4,
                 "payload": {"secret": "PAYLOAD_SECRET"}},
                {"event": "model_returned", "stage": "formatter", "ordinal": 4,
                 "result": {"answer": "MODEL_RAW_SECRET"}},
                {"event": "step_proposed", "branch_id": "root.1.1", "depth": 1,
                 "selected_ids": ["wire"], "conclusion_id": "node:0001", "sufficient": True,
                 "value_score": 0.7, "selection_reason": "best matching source"},
                {"event": "beam_selected", "depth": 1, "branch_ids": ["root.1.1"]},
            ],
            "branches": [
                {"branch_id": "root.1.1", "steps": [{"conclusion": "No other news", "depth": 1}],
                 "score": 0.7, "halted": True},
                {"branch_id": "root.1.2", "steps": [{"conclusion": "Alternate conclusion", "depth": 1}],
                 "score": 0.2, "halted": False, "private_payload": "BRANCH_SECRET"},
            ],
            "private_top_level": "TOP_LEVEL_SECRET",
        }

    def test_actual_statuses_and_coverage_map_without_losing_answer(self):
        rendered = render_outcome(self.engine_outcome())
        self.assertIn("no other news", rendered)
        self.assertIn("**Status:** Incomplete", rendered)
        self.assertIn("**q1:** not assessed", rendered)
        self.assertIn("**q2:** source unavailable", rendered)
        self.assertIn("**q3:** assessed (model assessment; unverified)", rendered)
        self.assertIn("**q4:** insufficient evidence", rendered)
        self.assertNotIn("**q1:** unknown", rendered)
        self.assertIn("PCE remains a candidate", rendered)
        self.assertIn("Selected trace (allowlisted summary)", rendered)
        self.assertIn("conclusion: No other news", rendered)
        self.assertIn("Semantic verification", rendered)
        self.assertIn("possible contradiction or its absence remains unknown", rendered)

    def test_branch_summary_uses_steps_and_does_not_invent_why_pruned(self):
        rendered = render_outcome(self.engine_outcome())
        self.assertIn("Other recorded branches", rendered)
        self.assertIn("root.1.2", rendered)
        self.assertIn("Alternate conclusion", rendered)
        self.assertIn("score 0.2", rendered)
        self.assertIn("halted: no", rendered)
        self.assertIn("not retained in recorded beam", rendered)
        self.assertNotIn("because it was lower quality", rendered)

    def test_step_event_has_individual_missing_reasons(self):
        rendered = render_outcome(self.engine_outcome())
        self.assertIn("Selection reason: best matching source", rendered)
        self.assertIn("Halter reason: reason not recorded", rendered)
        self.assertIn("Value reason: reason not recorded", rendered)

    def test_model_events_aggregate_and_arbitrary_payloads_are_ignored(self):
        rendered = render_outcome(self.engine_outcome())
        self.assertIn("Formatter calls: 1 started, 1 returned", rendered)
        self.assertNotIn("Unknown event", rendered)
        for secret in ("PAYLOAD_SECRET", "MODEL_RAW_SECRET", "BRANCH_SECRET", "TOP_LEVEL_SECRET"):
            self.assertNotIn(secret, rendered)
        self.assertIn("full recorded trace", rendered)
        self.assertIn("not the complete trace", rendered)

    def test_actual_outcome_statuses_and_failure_details(self):
        for status, displayed in (
            ("proposal", "Proposal"), ("incomplete", "Incomplete"),
            ("unknown", "Unknown"), ("technical_failure", "Technical failure"),
        ):
            self.assertIn(f"**Status:** {displayed}", render_outcome({"status": status}))
        rendered = render_outcome({"events": [{"event": "callback_failed", "stage": "selection",
                                                "exception_type": "RuntimeError",
                                                "message": "secret payload"}]})
        self.assertIn("Callback failed during Selection", rendered)
        self.assertIn("failure details beyond the recorded type are unknown", rendered)
        self.assertNotIn("secret payload", rendered)


if __name__ == "__main__":
    unittest.main()


def test_real_scripted_engine_result_renders_without_erasing_omitted_pce():
    from reasoning_engine.demo import demo_packet
    packet = demo_packet()
    view = render_outcome(packet['outcome'])
    assert 'not assessed' in view
    assert 'pce' in view
    assert 'unreviewed' in view
    assert packet['accounting']['real_model_calls'] == 0
    assert len(packet['model_requests']) == packet['outcome']['calls']
