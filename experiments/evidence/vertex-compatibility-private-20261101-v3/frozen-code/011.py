"""Offline B1 and bounded B_self baselines for the Faithful Engine task contract.

No provider is bound here. The caller injects ``generate(stage, payload)``.
Responses that pass formatter-shape validation are still semantic proposals,
marked unreviewed. A failed self-check is recorded as failure; earlier answers
remain in history and are not silently promoted as the final result.
"""

from __future__ import annotations

import copy
from typing import Any, Callable, Mapping

from reasoning_engine.engine import Engine, prepare_task


SELF_CHECK_LIMIT = 1
BASELINE_STAGES = ("baseline_initial", "baseline_recheck")
ASSESSMENT_STATUSES = {"assessed", "insufficient_evidence"}


def _format_problem(response: Any, allowed_evidence: set[str], allowed_questions: set[str]) -> str | None:
    """Mirror the engine formatter's structural checks for a full-answer object."""
    if not isinstance(response, dict):
        return "formatter response must be an object"
    answer = response.get("answer")
    citations = response.get("citations")
    assessments = response.get("assessments", [])
    if not isinstance(answer, str) or not answer.strip():
        return "formatter answer must be nonempty"
    if (not isinstance(citations, list) or any(not isinstance(x, str) for x in citations)
            or len(set(citations)) != len(citations)
            or any(x not in allowed_evidence for x in citations)):
        return "formatter citations must be unique supplied evidence IDs"
    if not isinstance(assessments, list):
        return "formatter assessments must be an array"
    claims = set()
    for item in assessments:
        if (not isinstance(item, dict) or not isinstance(item.get("id"), str)
                or item.get("id") not in allowed_questions or item.get("id") in claims
                or not isinstance(item.get("status"), str)
                or item.get("status") not in ASSESSMENT_STATUSES
                or not isinstance(item.get("reason"), str) or not item["reason"].strip()):
            return "invalid model assessment"
        claims.add(item["id"])
    return None


def _coverage(prepared: dict[str, Any], response: dict[str, Any]) -> list[dict[str, Any]]:
    """Use the engine's structural coverage helper over the full supplied bundle."""
    evidence = {item["id"] for item in prepared["evidence"]}
    if "thesis" in prepared:
        evidence.add("input:thesis")
    claims = {
        item["id"]: {"status": item["status"], "reason": item["reason"]}
        for item in response.get("assessments", [])
    }
    # _coverage has no callback effects; it only applies shared structural rules.
    return Engine(lambda _stage, _payload: {})._coverage(prepared, evidence, claims)


def _branch(name: str, prepared: dict[str, Any], generate: Callable[[str, dict[str, Any]], Any],
            self_check: bool) -> dict[str, Any]:
    allowed_evidence = {item["id"] for item in prepared["evidence"]}
    if "thesis" in prepared:
        allowed_evidence.add("input:thesis")
    allowed_questions = {item["id"] for item in prepared["required_questions"]}
    history: list[dict[str, Any]] = []

    def invoke(stage: str, payload: dict[str, Any]) -> Any:
        saved_payload = copy.deepcopy(payload)
        try:
            raw = generate(stage, copy.deepcopy(saved_payload))
        except Exception as exc:
            history.append({"stage": stage, "payload": saved_payload,
                            "error": type(exc).__name__})
            return None, f"callback_failed:{type(exc).__name__}"
        try:
            saved = copy.deepcopy(raw)
        except Exception:
            # Non-copyable outputs still have an explicit failure record.
            history.append({"stage": stage, "payload": saved_payload,
                            "error": "UncopyableResponse"})
            return None, "callback_returned_uncopyable_response"
        history.append({"stage": stage, "payload": saved_payload, "response": saved})
        return saved, _format_problem(saved, allowed_evidence, allowed_questions)

    # Both branches receive this exact same prepared task package. Rechecks get
    # that package plus only their own immediately preceding successful answer.
    response, problem = invoke("baseline_initial", prepared)
    if problem:
        return {
            "branch": name, "status": "technical_failure", "reason": problem,
            "semantic_status": "unreviewed", "calls": len(history),
            "responses": history, "final_result": None, "coverage": [],
        }

    if self_check:
        for _ in range(SELF_CHECK_LIMIT):
            previous = response
            response, problem = invoke("baseline_recheck", {
                "prepared_task": prepared,
                "previous_response": previous,
            })
            if problem:
                return {
                    "branch": name, "status": "technical_failure", "reason": problem,
                    "semantic_status": "unreviewed", "calls": len(history),
                    "responses": history, "last_valid_response": copy.deepcopy(previous),
                    "final_result": None, "coverage": [],
                }

    coverage = _coverage(prepared, response)
    return {
        "branch": name,
        "status": "completed" if all(row["status"] == "assessed" for row in coverage) else "incomplete",
        "reason": "model_proposal_requires_semantic_review",
        "semantic_status": "unreviewed",
        "calls": len(history),
        "responses": history,
        "final_result": copy.deepcopy(response),
        "coverage": coverage,
        "coverage_counts": {
            status: sum(row["status"] == status for row in coverage)
            for status in ("assessed", "insufficient_evidence", "source_unavailable", "not_assessed")
        },
    }


def run_baselines(task: Mapping[str, Any], generate: Callable[[str, dict[str, Any]], Any]) -> dict[str, Any]:
    """Run B1 and B_self from the same ``prepare_task`` result, without network I/O."""
    if not callable(generate):
        raise ValueError("generate callback required")
    prepared = prepare_task(dict(task))
    return {
        "case_id": prepared["case_id"],
        "input_sha256": prepared["input_sha256"],
        "self_check_limit": SELF_CHECK_LIMIT,
        "branches": {
            "B1": _branch("B1", prepared, generate, self_check=False),
            "B_self": _branch("B_self", prepared, generate, self_check=True),
        },
    }
