"""Create an attributable review candidate without changing saved outcomes."""
from __future__ import annotations

from typing import Any

from .engine import _text


def propose_annotation(outcome: dict[str, Any], *, target_type: str, target_id: str,
                       comment: str, origin: str) -> dict[str, Any]:
    """The caller persists the candidate separately; no human authority is inferred."""
    if target_type not in {"node", "requirement", "evidence", "thesis"}:
        raise ValueError("unsupported annotation target")
    target_id = _text(target_id, "target_id")
    if target_type == "node":
        allowed = {step.get("conclusion_id") for branch in outcome.get("branches", [])
                   for step in branch.get("steps", [])}
    elif target_type == "requirement":
        allowed = {item.get("id") for item in outcome.get("required_questions", [])}
    elif target_type == "evidence":
        allowed = {item.get("id") for item in outcome.get("evidence", [])}
    else:
        allowed = {"input:thesis"} if any(x.get("id") == "input:thesis" for x in outcome.get("evidence", [])) else set()
    if target_id not in allowed:
        raise ValueError("target does not exist in saved outcome")
    return {"case_id": outcome["case_id"], "input_sha256": outcome["input_sha256"],
            "target_type": target_type, "target_id": target_id,
            "comment": _text(comment, "comment"), "origin": _text(origin, "origin"),
            "status": "candidate_not_activated", "authority_verified": False}
