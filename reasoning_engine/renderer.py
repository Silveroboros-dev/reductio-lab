"""A safe, readable view of a saved Faithful Engine outcome.

This summarizes the engine's public outcome contract. It does not execute the
engine or independently assess the meaning of its claims.
"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlsplit, urlunsplit


_STATUSES = {
    "proposal": "Proposal",
    "incomplete": "Incomplete",
    "unknown": "Unknown",
    "technical_failure": "Technical failure",
}
_COVERAGE = {
    "assessed": "assessed (model assessment; unverified)",
    "insufficient_evidence": "insufficient evidence",
    "not_assessed": "not assessed",
    "source_unavailable": "source unavailable",
}
_EVENT_NAMES = {
    "step_proposed": "Step proposed",
    "beam_selected": "Beam selected",
    "model_started": "Model call started",
    "model_returned": "Model call returned",
    "callback_failed": "Callback failed",
}
_STAGES = {
    "selection": "Selection", "inference": "Inference", "halter": "Halter",
    "value": "Value", "formatter": "Formatter",
}
_SECRET_PATTERNS = (
    re.compile(r"(?i)\b(api[_ -]?key|access[_ -]?token|secret|password)\s*[:=]\s*[^\s,;]+"),
    re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{12,}\b"),
)
_MD = re.compile(r"([\\`*_{}\[\]<>|])")


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _items(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _safe_text(value: Any) -> str:
    if value is None or isinstance(value, (dict, list, tuple, set)):
        return ""
    text = str(value).replace("\r", " ").replace("\n", " ").strip()
    for pattern in _SECRET_PATTERNS:
        text = pattern.sub("[REDACTED]", text)
    return _MD.sub(r"\\\1", text)


def _ids(value: Any) -> list[str]:
    return [str(item) for item in _items(value) if isinstance(item, (str, int))]


def _url(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    try:
        parts = urlsplit(value.strip())
        if parts.scheme.lower() not in {"http", "https"} or not parts.hostname:
            return ""
        host = parts.hostname + (f":{parts.port}" if parts.port else "")
        return urlunsplit((parts.scheme.lower(), host, parts.path, "", ""))
    except ValueError:
        return ""


def _stage(value: Any) -> str:
    if isinstance(value, str):
        return _STAGES.get(value.lower(), "Other")
    return "Other"


def _answer(result: Any) -> str:
    # Formatter output is retained as a dict by the engine. Expose only answer;
    # citations/assessments are rendered from their separate outcome fields.
    if isinstance(result, dict):
        return _safe_text(result.get("answer"))
    return ""


def render_outcome(outcome: dict[str, Any]) -> str:
    """Render one engine outcome using an explicit field allowlist.

    Unknown keys and model call payload/result objects are never serialized.
    """
    data = _mapping(outcome)
    lines: list[str] = [f"# Faithful Engine outcome — {_safe_text(data.get('case_id')) or 'Unknown'}", ""]

    answer = _answer(data.get("result"))
    lines.extend(["## Proposed answer", answer or "No result was saved.", ""])
    status_value = data.get("status")
    status = _STATUSES.get(status_value, "Unknown") if isinstance(status_value, str) else "Unknown"
    lines.append(f"**Status:** {status}")
    reason = _safe_text(data.get("reason"))
    if reason:
        lines.append(f"**Outcome reason:** {reason}")
    semantic_status = data.get("semantic_status")
    if semantic_status == "unreviewed":
        lines.append("**Semantic status:** unreviewed")
    lines.append("")

    coverage = _items(data.get("coverage"))
    lines.append("## Required-question coverage")
    if not coverage:
        lines.append("No coverage records were saved; coverage is unknown.")
    for raw_item in coverage:
        item = _mapping(raw_item)
        question_id = _safe_text(item.get("question_id")) or "Unknown question"
        question = _safe_text(item.get("question"))
        state_value = item.get("status")
        state = _COVERAGE.get(state_value, "unknown") if isinstance(state_value, str) else "unknown"
        detail = _safe_text(item.get("reason"))
        missing = _ids(item.get("missing_ids"))
        unselected = _ids(item.get("unselected_ids"))
        required_ids = _ids(item.get("evidence_ids"))
        text = f"- **{question_id}:** {state}"
        if question:
            text += f" — {question}"
        if detail:
            text += f"; {detail}"
        if missing:
            text += f"; missing from bundle IDs: {', '.join(_safe_text(x) for x in missing)}"
        if unselected:
            text += f"; not supplied to selected formatter context: {', '.join(_safe_text(x) for x in unselected)}"
        elif required_ids and state_value == "source_unavailable":
            text += f"; required IDs: {', '.join(_safe_text(x) for x in required_ids)}"
        lines.append(text)
    lines.append("")

    evidence_rows: list[tuple[str, dict[str, Any]]] = []
    for raw_item in _items(data.get("evidence")):
        item = _mapping(raw_item)
        ident = _safe_text(item.get("id"))
        if ident:
            evidence_rows.append((ident, item))
    evidence_by_id = {ident: item for ident, item in evidence_rows}
    selected_ids: set[str] = set()
    trace = _items(data.get("selected_trace"))
    for raw_step in trace:
        step = _mapping(raw_step)
        selected_ids.update(_ids(step.get("selected_ids")))
        conclusion_id = step.get("conclusion_id")
        if isinstance(conclusion_id, (str, int)):
            selected_ids.add(str(conclusion_id))

    lines.append("## Sources used by the selected path")
    visible = [(ident, item) for ident, item in evidence_rows if ident in selected_ids]
    if visible:
        for ident, item in visible:
            text = _safe_text(item.get("text")) or "No source text saved."
            source = _safe_text(item.get("source"))
            kind = _safe_text(item.get("kind"))
            extra = f" — {source}" if source else ""
            if kind:
                extra += f" ({kind})"
            raw_ref = _safe_text(item.get("raw_ref"))
            if raw_ref:
                extra += f"; raw reference: {raw_ref}"
            url = _url(item.get("source"))
            if url:
                extra += f"; source URL: {_safe_text(url)}"
            lines.append(f"- **{ident}:** {text}{extra}")
    else:
        lines.append("No supplied source was linked to the selected trace.")

    sidecar_ids = [ident for ident, _ in evidence_rows if ident not in selected_ids]
    lines.extend(["", "## Evidence outside the selected path"])
    if sidecar_ids:
        for ident in sidecar_ids:
            item = evidence_by_id[ident]
            text = _safe_text(item.get("text")) or "No source text saved."
            source = _safe_text(item.get("source"))
            extra = f" — {source}" if source else ""
            lines.append(f"- **{ident}:** {text}{extra}")
    else:
        lines.append("No other supplied evidence items.")

    lines.extend([
        "", "## Semantic verification",
        "The engine records semantic status as unreviewed. This view cannot establish whether "
        "the selected claims are semantically consistent; possible contradiction or its absence "
        "remains unknown.",
        "Model value scores are ranking signals, not probabilities of truth or measures of human value.",
        "",
    ])

    lines.append("## Selected trace (allowlisted summary)")
    if trace:
        for index, raw_step in enumerate(trace, 1):
            step = _mapping(raw_step)
            selected_step_ids = _ids(step.get("selected_ids"))
            conclusion_id = _safe_text(step.get("conclusion_id"))
            conclusion = _safe_text(step.get("conclusion"))
            depth = step.get("depth")
            depth_text = str(depth) if type(depth) in (int, float) else "unknown"
            verification = _safe_text(step.get("verification")) or "unknown"
            fields = [f"depth {depth_text}", f"verification: {verification}"]
            fields.append(f"selected IDs: {', '.join(_safe_text(x) for x in selected_step_ids) or 'none saved'}")
            if conclusion_id:
                fields.append(f"conclusion ID: {conclusion_id}")
            if conclusion:
                fields.append(f"conclusion: {conclusion}")
            lines.append(f"- Step {index}: " + "; ".join(fields))
    else:
        lines.append("No selected trace steps were saved.")
    lines.append("")

    # Engine events preserve model payloads/results. Aggregate call lifecycle
    # events without disclosing those task-content objects.
    events = [_mapping(item) for item in _items(data.get("events"))]
    call_counts: dict[str, dict[str, int]] = {}
    for event in events:
        name = event.get("event")
        if name in {"model_started", "model_returned"}:
            stage = _stage(event.get("stage"))
            bucket = call_counts.setdefault(stage, {"model_started": 0, "model_returned": 0})
            bucket[name] += 1

    lines.append("## Saved event summary")
    if not events:
        lines.append("No events were saved.")
    else:
        if call_counts:
            for stage, counts in call_counts.items():
                lines.append(f"- {stage} calls: {counts['model_started']} started, {counts['model_returned']} returned.")
        for event in events:
            name = event.get("event")
            if name == "step_proposed":
                branch_id = _safe_text(event.get("branch_id")) or "unknown"
                chosen = _ids(event.get("selected_ids"))
                conclusion_id = _safe_text(event.get("conclusion_id"))
                sufficient = event.get("sufficient")
                sufficient_text = "yes" if sufficient is True else "no" if sufficient is False else "unknown"
                score = event.get("value_score")
                score_text = f"{score:g}" if type(score) in (int, float) else "unknown"
                bits = [f"branch {branch_id}", f"selected: {', '.join(_safe_text(x) for x in chosen) or 'unknown'}"]
                if conclusion_id:
                    bits.append(f"conclusion ID: {conclusion_id}")
                bits.extend([f"halter sufficient: {sufficient_text}", f"value score: {score_text}"])
                for key, label in (("selection_reason", "Selection reason"),
                                   ("halter_reason", "Halter reason"),
                                   ("value_reason", "Value reason")):
                    saved = _safe_text(event.get(key))
                    bits.append(f"{label}: {saved or 'reason not recorded'}")
                lines.append("- Step proposed: " + "; ".join(bits))
            elif name == "beam_selected":
                branch_ids = _ids(event.get("branch_ids"))
                lines.append("- Beam selected: " + (", ".join(_safe_text(x) for x in branch_ids) or "no branch IDs saved"))
            elif name == "callback_failed":
                lines.append(f"- Callback failed during {_stage(event.get('stage'))}; failure details beyond the recorded type are unknown.")
            # model_started/model_returned were represented in aggregate counts.
            # All unrecognized event shapes are deliberately ignored.

    lines.extend([
        "", "## Saved trace artifact",
        "This page is an allowlisted summary, not the complete trace. The full recorded trace "
        "and model-call evidence remain in the saved outcome artifact; arbitrary call payloads "
        "and model results are not reproduced here.",
    ])

    selected_branch = data.get("selected_branch")
    selected_branch = selected_branch if isinstance(selected_branch, str) else ""
    selected_parts = selected_branch.split(".") if selected_branch else []
    selected_lineage = {".".join(selected_parts[:i]) for i in range(2, len(selected_parts) + 1)}
    selected_lineage.add(selected_branch)
    branch_rows = [_mapping(item) for item in _items(data.get("branches"))]
    if branch_rows:
        lines.extend(["", "## Other recorded branches"])
        shown = False
        beams_by_depth: dict[Any, set[str]] = {}
        for event in events:
            if event.get("event") == "beam_selected":
                depth = event.get("depth")
                beams_by_depth[depth] = set(_ids(event.get("branch_ids")))
        for branch in branch_rows:
            branch_id_raw = branch.get("branch_id")
            branch_id = branch_id_raw if isinstance(branch_id_raw, str) else ""
            if not branch_id or branch_id in selected_lineage:
                continue
            shown = True
            steps = _items(branch.get("steps"))
            last = _mapping(steps[-1]) if steps else {}
            conclusion = _safe_text(last.get("conclusion")) or "No conclusion saved."
            score = branch.get("score")
            score_text = f"{score:g}" if type(score) in (int, float) else "unknown"
            halted = branch.get("halted")
            halted_text = "yes" if halted is True else "no" if halted is False else "unknown"
            depth = last.get("depth")
            beam = beams_by_depth.get(depth)
            disposition = "not identified as selected" if beam is None else (
                "included in recorded beam" if branch_id in beam else "not retained in recorded beam")
            lines.append(f"- **{_safe_text(branch_id)}** ({disposition}): last conclusion: {conclusion}; score {score_text}; halted: {halted_text}.")
        if not shown:
            lines.append("No distinct alternative branch was recorded.")

    return "\n".join(lines).rstrip() + "\n"


render = render_outcome
