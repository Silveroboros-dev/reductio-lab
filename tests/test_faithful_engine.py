"""Offline structural tests: fake callbacks do not measure model quality."""
import copy

import pytest

from reasoning_engine import Engine, EngineConfig, InvalidTask, prepare_task
from reasoning_engine.prompts import bind_model, build_request


def task():
    return {
        "case_id": "cpi-synthetic", "task_type": "forecast",
        "question": "Assess the contract and the effect of the supplied news.",
        "as_of_utc": "2026-10-29T12:35:00Z",
        "evidence": [
            {"id": "rule", "kind": "contract_rule", "text": "Reported CPI over 0.2 resolves YES.",
             "source": "synthetic rule", "captured_at_utc": "2026-10-29T10:00:00Z"},
            {"id": "quote", "kind": "quote", "text": "Bid 0.56; ask 0.58.", "source": "synthetic quote"},
            {"id": "pce", "kind": "news", "text": "A PCE release is available.",
             "source": "synthetic news", "available_at_utc": "2026-10-29T12:30:00Z"},
        ],
        "required_questions": [{"id": "impact", "question": "Assess the news impact.", "evidence_ids": ["pce"]}],
        "thesis": {"text": "Synthetic thesis", "version": "v1", "origin": "caller-provided"},
    }


def two_branches(stage, payload):
    if stage == "selection":
        return {"alternatives": [["rule", "quote"], ["rule", "quote", "pce"]]}
    if stage == "inference":
        return {"conclusion": "This is an unverified local inference."}
    if stage == "halter":
        return {"sufficient": True}
    if stage == "value":
        return {"score": 0.85 if "pce" in payload["trace"][-1]["selected_ids"] else 0.95}
    if stage == "formatter":
        return {"answer": "There were no other economic releases.", "citations": ["rule", "quote"],
                "assessments": [{"id": "impact", "status": "assessed", "reason": "No change."}]}
    raise AssertionError(stage)


def test_cpi_like_omission_is_visible_but_not_semantically_certified():
    out = Engine(two_branches).run(task())
    assert out["status"] == "incomplete"
    assert out["result"]["answer"] == "There were no other economic releases."
    assert out["semantic_status"] == "unreviewed"
    assert out["coverage"][0]["status"] == "not_assessed"
    assert out["coverage"][0]["unselected_ids"] == ["pce"]
    assert {x["id"] for x in out["evidence"]} == {"input:thesis", "rule", "quote", "pce"}
    assert out["calls"] == 8
    assert [x["stage"] for x in out["events"] if x["event"] == "model_started"] == [
        "selection", "inference", "halter", "value", "inference", "halter", "value", "formatter"]
    assert out["inference_dependency_depth"] == 1


def test_inference_never_receives_question_or_unselected_evidence():
    out = Engine(two_branches).run(task())
    first = next(x for x in out["events"] if x["event"] == "model_started" and x["stage"] == "inference")
    assert set(first["payload"]) == {"selected_texts"}
    assert "pce" not in str(first["payload"]).lower()
    assert "Assess the contract" not in str(first["payload"])
    req = build_request("inference", first["payload"])
    assert "unseen question" in req["instruction"]
    with pytest.raises(ValueError):
        build_request("inference", {"selected_texts": [], "question": "hidden"})


def test_all_five_roles_are_actual_callbacks_and_request_bindings():
    requests = []
    def requester(request):
        requests.append(request)
        return two_branches(request["stage"], request["input"])
    out = Engine(bind_model(requester)).run(task())
    assert out["status"] == "incomplete"
    assert {x["stage"] for x in requests} == {"selection", "inference", "halter", "value", "formatter"}
    assert all(x["prompt_version"] == "faithful-engine-prompts-v1" for x in requests)


def test_missing_evidence_is_not_claimed_unavailable_or_false():
    t = task()
    t["evidence"] = [x for x in t["evidence"] if x["id"] != "pce"]
    def one(stage, payload):
        if stage == "selection": return {"alternatives": [["rule"]]}
        if stage == "inference": return {"conclusion": "A limited conclusion."}
        if stage == "halter": return {"sufficient": True}
        if stage == "value": return {"score": 0.5}
        if stage == "formatter": return {"answer": "Unknown.", "citations": ["rule"], "assessments": []}
    out = Engine(one).run(t)
    assert out["coverage"][0]["status"] == "not_assessed"
    assert "availability unknown" in out["coverage"][0]["reason"]
    t["unavailable_evidence_ids"] = ["pce"]
    asserted = Engine(one).run(t)
    assert asserted["coverage"][0]["status"] == "source_unavailable"
    assert "caller reports" in asserted["coverage"][0]["reason"]


def test_evidence_versions_fail_closed_and_unknown_metadata_not_projected():
    t = task()
    t["evidence"][0]["private_review_answer"] = "hidden"
    t["private_reference"] = "hidden"
    prepared = prepare_task(t)
    assert "private_reference" not in prepared
    assert "private_review_answer" not in prepared["evidence"][0]
    assert prepare_task(prepared)["input_sha256"] == prepared["input_sha256"]
    prepared["evidence"][0]["text"] = "changed"
    with pytest.raises(InvalidTask, match="evidence version"):
        prepare_task(prepared)


def test_future_timestamp_rejected_and_unspecified_time_stays_unknown():
    t = task()
    del t["evidence"][2]["available_at_utc"]
    assert "available_at_utc" not in prepare_task(t)["evidence"][2]
    t["evidence"][2]["available_at_utc"] = "2026-10-29T13:00:00Z"
    with pytest.raises(InvalidTask, match="after information cutoff"):
        prepare_task(t)


def test_unseen_or_cross_branch_id_is_not_passed_to_inference():
    seen = []
    def fake(stage, payload):
        seen.append(stage)
        if stage == "selection": return {"alternatives": [["secret-unseen"]]}
        raise AssertionError("inference must not run")
    out = Engine(fake).run(task())
    assert out["status"] == "technical_failure"
    assert seen == ["selection"]


def test_real_dependency_depth_not_number_of_generated_steps():
    state = {"selection": 0, "halt": 0}
    def fake(stage, payload):
        if stage == "selection":
            state["selection"] += 1
            return {"alternatives": [["rule"]]}
        if stage == "inference": return {"conclusion": "Independent inference."}
        if stage == "halter":
            state["halt"] += 1
            return {"sufficient": state["halt"] == 2}
        if stage == "value": return {"score": 0.5}
        if stage == "formatter": return {"answer": "An answer.", "citations": ["rule"], "assessments": []}
    out = Engine(fake).run(task())
    assert len(out["branches"][-1]["steps"]) == 2
    assert len(out["selected_trace"]) == 1
    assert out["inference_dependency_depth"] == 1


def test_linked_inference_is_two_deep_and_no_semantic_truth_is_claimed():
    state = {"selection": 0, "halt": 0}
    def fake(stage, payload):
        if stage == "selection":
            state["selection"] += 1
            return {"alternatives": [["rule"]] if state["selection"] == 1 else [["node:0001"]]}
        if stage == "inference": return {"conclusion": "Unverified conclusion."}
        if stage == "halter":
            state["halt"] += 1
            return {"sufficient": state["halt"] == 2}
        if stage == "value": return {"score": 1.0}
        if stage == "formatter": return {"answer": "direct", "citations": ["rule"], "assessments": []}
    out = Engine(fake).run(task())
    assert out["inference_dependency_depth"] == 2
    assert len(out["selected_trace"]) == 2
    assert out["semantic_status"] == "unreviewed"
    assert all(step["verification"] == "unreviewed" for step in out["selected_trace"])


def test_callback_mutation_cannot_change_task_or_recorded_inputs():
    t = task(); original = copy.deepcopy(t)
    def fake(stage, payload):
        result = two_branches(stage, payload)
        if stage == "selection": payload["available_statements"][0]["text"] = "mutated"
        return result
    out = Engine(fake).run(t)
    assert t == original
    selection = next(x for x in out["events"] if x["event"] == "model_started")
    assert selection["payload"]["available_statements"][0]["text"] == original["thesis"]["text"]


def test_generation_cap_returns_unknown_and_one_instance_is_single_use():
    e = Engine(two_branches, EngineConfig(max_calls=1))
    out = e.run(task())
    assert (out["status"], out["reason"], out["calls"]) == ("unknown", "generation_cap_exhausted", 1)
    with pytest.raises(ValueError): e.run(task())


def test_callback_failure_is_isolated_without_claiming_provider_truth():
    def broken(stage, payload): raise TimeoutError("raw private detail")
    out = Engine(broken).run(task())
    assert out["status"] == "technical_failure"
    assert out["reason"] == "callback_failed:TimeoutError"
    assert "raw private detail" not in str(out)
    assert out["coverage"][0]["status"] == "not_assessed"


def test_invalid_formatter_is_technical_failure_not_fabricated_answer():
    def fake(stage, payload):
        if stage == "formatter": return {"answer": "missing citations"}
        return two_branches(stage, payload)
    out = Engine(fake).run(task())
    assert out["status"] == "technical_failure"
    assert out["result"] is None
    assert any(x.get("stage") == "formatter" and x["event"] == "model_returned" for x in out["events"])


def test_thesis_is_visible_and_can_be_selected_without_assigning_human_authority():
    def fake(stage, payload):
        if stage == "selection":
            assert any(x["id"] == "input:thesis" and x["text"] == "Synthetic thesis" for x in payload["available_statements"])
            return {"alternatives": [["input:thesis"]]}
        if stage == "inference": return {"conclusion": "A proposed thesis interpretation."}
        if stage == "halter": return {"sufficient": True}
        if stage == "value": return {"score": 0.5}
        if stage == "formatter":
            assert payload["selected_evidence"][0]["id"] == "input:thesis"
            return {"answer": "A proposal.", "citations": ["input:thesis"], "assessments": []}
    out = Engine(fake).run(task())
    assert out["status"] == "incomplete"
    assert out["semantic_status"] == "unreviewed"
    assert out["selected_trace"][0]["selected_ids"] == ["input:thesis"]


def test_revision_marks_changed_selected_evidence_and_preserves_old_answer():
    from reasoning_engine.revision import reassessment
    original = task()
    out = Engine(two_branches).run(original)
    saved = copy.deepcopy(out)
    changed = copy.deepcopy(original)
    changed["evidence"][0]["text"] = "A corrected rule."
    audit = reassessment(out, changed)
    assert audit["selected_evidence_changed"] == ["rule"]
    assert audit["reassessment_required"] and not audit["answer_stability_established"]
    assert audit["status"] == "candidate_not_activated"
    assert out == saved


def test_new_evidence_outside_previous_path_also_requires_relevance_review():
    from reasoning_engine.revision import reassessment
    original = task(); out = Engine(two_branches).run(original)
    changed = copy.deepcopy(original)
    changed["evidence"].append({"id": "later", "kind": "news", "text": "New opposing observation.",
                                "source": "synthetic"})
    audit = reassessment(out, changed)
    assert audit["added_ids"] == ["later"]
    assert audit["selected_evidence_changed"] == []
    assert audit["reassessment_required"] and not audit["answer_stability_established"]


def test_annotation_is_a_separate_candidate_bound_to_existing_result():
    from reasoning_engine.annotations import propose_annotation
    out = Engine(two_branches).run(task())
    original = copy.deepcopy(out)
    item = propose_annotation(out, target_type="evidence", target_id="pce",
                              comment="Please assess this.", origin="caller-supplied")
    assert item["input_sha256"] == out["input_sha256"]
    assert item["status"] == "candidate_not_activated" and not item["authority_verified"]
    assert out == original
    with pytest.raises(ValueError):
        propose_annotation(out, target_type="node", target_id="missing", comment="x", origin="x")


def test_partial_branches_survive_later_formatter_failure():
    def fail_formatter(stage, payload):
        if stage == "formatter": raise TimeoutError()
        return two_branches(stage, payload)
    out = Engine(fail_formatter).run(task())
    assert out["status"] == "technical_failure"
    assert len(out["branches"]) == 2


def test_counterfactual_changes_selected_input_and_observed_scripted_output():
    # A sensitivity fixture, not evidence of semantic truth or causal validity.
    def dependent(stage, payload):
        if stage == 'selection': return {'alternatives': [['rule']]}
        if stage == 'inference': return {'conclusion': payload['selected_texts'][0]['text']}
        if stage == 'halter': return {'sufficient': True}
        if stage == 'value': return {'score': 0.5}
        if stage == 'formatter':
            return {'answer': payload['selected_trace'][-1]['conclusion'], 'citations': ['rule'], 'assessments': []}
    original = task()
    altered = copy.deepcopy(original)
    altered['evidence'][0]['text'] = 'A different synthetic condition.'
    a, b = Engine(dependent).run(original), Engine(dependent).run(altered)
    assert a['input_sha256'] != b['input_sha256']
    assert a['selected_trace'][0]['selected_ids'] == b['selected_trace'][0]['selected_ids'] == ['rule']
    assert a['result']['answer'] != b['result']['answer']


def test_engine_and_journal_connect_with_scripted_responses(tmp_path):
    import json
    from reasoning_engine.executor import EffectExecutor, HttpResponse
    with EffectExecutor(str(tmp_path / 'effects.sqlite3'), exposure_cap=20, call_cap=20) as executor:
        counter = [0]
        def requester(request):
            counter[0] += 1
            operation = f"fake-stage-{counter[0]}"
            body = json.dumps(request, ensure_ascii=False).encode()
            executor.register(operation, branch='C', request=body, exposure_per_attempt=1)
            def fake_provider(request_bytes):
                decoded = json.loads(request_bytes)
                output = two_branches(decoded['stage'], decoded['input'])
                return HttpResponse(200, json.dumps(output).encode())
            receipt = executor.execute(operation, callback=fake_provider)
            assert receipt.state == 'succeeded' and receipt.parse_status == 'valid_json'
            return receipt.parsed_json
        out = Engine(bind_model(requester)).run(task())
        assert out['status'] == 'incomplete'
        assert out['calls'] == executor.accounting()['calls'] == 8
        assert executor.accounting()['exposure_units'] == 8


def test_formatter_malformed_assessment_remains_a_schema_failure():
    def malformed(stage, payload):
        if stage == 'formatter':
            return {'answer': 'x', 'citations': [], 'assessments': [{'id': [], 'status': [], 'reason': 'x'}]}
        return two_branches(stage, payload)
    out = Engine(malformed).run(task())
    assert out['status'] == 'technical_failure'
    assert out['reason'] == 'invalid model assessment'
    assert out['result'] is None
