"""Offline evidence-version comparison; never rewrites old decisions or runs a model."""
from __future__ import annotations

from typing import Any

from .engine import _all_evidence, prepare_task


def reassessment(previous: dict[str, Any], new_task: dict[str, Any]) -> dict[str, Any]:
    """Report changed inputs and possible impact, not correctness or stability.

    New evidence can be relevant even when it was absent from a prior proof, so
    any input change leaves overall relevance for review. The function returns
    only a proposal; it does not mutate the previous result or contact providers.
    """
    task = prepare_task(new_task)
    old_items = previous.get("evidence")
    if not isinstance(old_items, list) or any(not isinstance(x, dict) or not isinstance(x.get("id"), str) for x in old_items):
        raise ValueError("previous evidence required")
    old = {item["id"]: item for item in old_items}
    if len(old) != len(old_items):
        raise ValueError("duplicate previous evidence ID")
    new = {item["id"]: item for item in _all_evidence(task)}
    changed = sorted(x for x in set(old) & set(new) if old[x] != new[x])
    added, removed = sorted(set(new) - set(old)), sorted(set(old) - set(new))
    selected = {p for step in previous.get("selected_trace", []) for p in step.get("selected_ids", [])}
    impacted = sorted((set(changed) | set(removed)) & selected)
    input_changed = previous.get("input_sha256") != task["input_sha256"]
    return {"previous_input_sha256": previous.get("input_sha256"), "new_input_sha256": task["input_sha256"],
            "previous_evidence_sha256": previous.get("evidence_sha256"), "new_evidence_sha256": task["evidence_sha256"],
            "changed_ids": changed, "added_ids": added, "removed_ids": removed,
            "selected_evidence_changed": impacted, "input_changed": input_changed,
            "reassessment_required": input_changed, "answer_stability_established": False,
            "status": "candidate_not_activated"}
