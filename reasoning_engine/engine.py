"""Faithful-style research engine: model roles, Python projections and trace.

One injected callback ``generate(stage, payload)`` supplies each model result.
Selection, inference, halter, value and formatter remain separate model calls;
this module does not verify natural-language entailment. Events contain task
content and must be handled as private evidence, not general telemetry.
"""
from __future__ import annotations

import copy
import datetime as dt
import hashlib
import json
import math
from dataclasses import dataclass, field
from typing import Any, Callable

VERSION = "faithful-engine-v1"
STAGES = ("selection", "inference", "halter", "value", "formatter")
EVIDENCE_KINDS = {"contract_rule", "news", "observation", "quote", "prior", "derived_claim"}
TASK_TYPES = {"exploration", "fit", "evidence_impact", "forecast"}
EVIDENCE_FIELDS = {"id", "text", "kind", "source", "captured_at_utc", "available_at_utc",
                   "published_at_utc", "raw_ref", "content_sha256"}


class InvalidTask(ValueError):
    pass


class InvalidOutput(ValueError):
    pass


class BudgetExhausted(Exception):
    pass


def _text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise InvalidTask(f"{name} must be nonempty text")
    return value


def _instant(value: Any, name: str) -> dt.datetime:
    try:
        parsed = dt.datetime.fromisoformat(_text(value, name).replace("Z", "+00:00"))
    except ValueError as exc:
        raise InvalidTask(f"{name} must be an ISO timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != dt.timedelta(0):
        raise InvalidTask(f"{name} must be UTC")
    return parsed


def _identity(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest()


def prepare_task(task: Any) -> dict[str, Any]:
    """Allowlist task and evidence, rejecting future recorded availability.

    Missing timestamps are unknown; source metadata and human authority are
    caller-provided evidence, not independently validated or granted here.
    Unavailable required evidence IDs are allowed and yield scoped coverage.
    """
    if not isinstance(task, dict):
        raise InvalidTask("task must be an object")
    case_id = _text(task.get("case_id"), "case_id")
    question = _text(task.get("question"), "question")
    task_type = task.get("task_type")
    if task_type not in TASK_TYPES:
        raise InvalidTask("unsupported task_type")
    as_of = task.get("as_of_utc")
    cutoff = _instant(as_of, "as_of_utc") if as_of is not None else None
    if not isinstance(task.get("evidence"), list) or not isinstance(task.get("required_questions", []), list):
        raise InvalidTask("evidence and required_questions must be arrays")
    evidence, seen = [], set()
    for item in task["evidence"]:
        if not isinstance(item, dict):
            raise InvalidTask("evidence must be an object")
        ident = _text(item.get("id"), "evidence.id")
        if ident in seen or ident.startswith("node:") or ident == "input:thesis":
            raise InvalidTask("duplicate or reserved evidence id")
        seen.add(ident)
        if item.get("kind") not in EVIDENCE_KINDS:
            raise InvalidTask("unsupported evidence kind")
        _text(item.get("text"), "evidence.text")
        _text(item.get("source"), "evidence.source")
        entry = {k: copy.deepcopy(v) for k, v in item.items() if k in EVIDENCE_FIELDS and v is not None}
        times = {}
        for key in ("captured_at_utc", "available_at_utc", "published_at_utc"):
            if key in entry:
                times[key] = _instant(entry[key], key)
                if cutoff is not None and times[key] > cutoff:
                    raise InvalidTask(f"{key} after information cutoff")
        if "published_at_utc" in times and "available_at_utc" in times and times["published_at_utc"] > times["available_at_utc"]:
            raise InvalidTask("publication after availability")
        if "available_at_utc" in times and "captured_at_utc" in times and times["available_at_utc"] > times["captured_at_utc"]:
            raise InvalidTask("availability after capture")
        evidence.append(entry)
    unavailable = task.get("unavailable_evidence_ids", [])
    if (not isinstance(unavailable, list) or any(not isinstance(x, str) or not x.strip() for x in unavailable)
            or len(unavailable) != len(set(unavailable)) or set(unavailable) & seen):
        raise InvalidTask("unavailable evidence IDs must be unique and not present")
    obligations, obligation_ids = [], set()
    for item in task.get("required_questions", []):
        if not isinstance(item, dict):
            raise InvalidTask("required question must be an object")
        ident = _text(item.get("id"), "required_questions.id")
        if ident in obligation_ids:
            raise InvalidTask("duplicate required question id")
        obligation_ids.add(ident)
        ids = item.get("evidence_ids", [])
        if not isinstance(ids, list) or any(not isinstance(x, str) or not x.strip() for x in ids) or len(ids) != len(set(ids)):
            raise InvalidTask("required evidence IDs must be unique strings")
        obligations.append({"id": ident, "question": _text(item.get("question"), "required_questions.question"),
                            "evidence_ids": list(ids)})
    result = {"case_id": case_id, "question": question, "task_type": task_type,
              "as_of_utc": as_of, "evidence": evidence, "required_questions": obligations,
              "unavailable_evidence_ids": list(unavailable), "evidence_sha256": _identity(evidence)}
    # Optional user-confirmed thesis stays a caller-provided record, never an
    # authority grant or an automatically adopted model output.
    if task.get("thesis") is not None:
        thesis = task["thesis"]
        if not isinstance(thesis, dict):
            raise InvalidTask("thesis must be an object")
        result["thesis"] = {"text": _text(thesis.get("text"), "thesis.text"),
                            "version": _text(thesis.get("version"), "thesis.version"),
                            "origin": _text(thesis.get("origin"), "thesis.origin")}
    supplied_evidence = task.get("evidence_sha256")
    if supplied_evidence is not None and supplied_evidence != result["evidence_sha256"]:
        raise InvalidTask("evidence version mismatch")
    result["input_sha256"] = _identity(result)
    supplied_input = task.get("input_sha256")
    if supplied_input is not None and supplied_input != result["input_sha256"]:
        raise InvalidTask("task version mismatch")
    return result


def _all_evidence(task: dict) -> list[dict]:
    items = copy.deepcopy(task["evidence"])
    if "thesis" in task:
        items.insert(0, {"id": "input:thesis", "text": task["thesis"]["text"],
                         "kind": "human_thesis", "source": task["thesis"]["origin"],
                         "version": task["thesis"]["version"]})
    return items


@dataclass(frozen=True)
class EngineConfig:
    max_calls: int = 23
    max_depth: int = 2
    beam_width: int = 2
    max_alternatives: int = 2

    def __post_init__(self):
        for name in ("max_calls", "max_depth", "beam_width", "max_alternatives"):
            value = getattr(self, name)
            if type(value) is not int or value < 1:
                raise ValueError(f"{name} must be a positive integer")


@dataclass
class _Branch:
    ident: str
    nodes: dict[str, dict[str, Any]]
    steps: list[dict[str, Any]] = field(default_factory=list)
    score: float = 0.0
    halted: bool = False
    latest: str | None = None


def _ancestry(steps: list[dict], latest: str) -> tuple[list[dict], set[str], int]:
    """Return declared inference dependencies, not proof of model causality."""
    by_id = {step["conclusion_id"]: step for step in steps}
    wanted, leaves = set(), set()

    def visit(ident: str) -> int:
        if ident not in by_id:
            leaves.add(ident)
            return 0
        wanted.add(ident)
        return 1 + max((visit(parent) for parent in by_id[ident]["selected_ids"]), default=0)

    depth = visit(latest)
    return [copy.deepcopy(step) for step in steps if step["conclusion_id"] in wanted], leaves, depth


class Engine:
    """One research case; the callback supplies model results, never human approval."""

    def __init__(self, generate: Callable[[str, dict], dict], config: EngineConfig | None = None):
        if not callable(generate):
            raise ValueError("generate callback required")
        self.generate = generate
        self.config = config or EngineConfig()
        self.events: list[dict] = []
        self.calls = 0
        self._next_node = 0
        self._used = False
        self._branches: list[dict] = []

    def _call(self, stage: str, payload: dict, branch_id: str | None = None) -> dict:
        if self.calls >= self.config.max_calls:
            raise BudgetExhausted()
        self.calls += 1
        self.events.append({"event": "model_started", "stage": stage, "ordinal": self.calls,
                            "branch_id": branch_id, "payload": copy.deepcopy(payload)})
        try:
            output = self.generate(stage, copy.deepcopy(payload))
        except Exception as exc:
            self.events.append({"event": "callback_failed", "stage": stage, "ordinal": self.calls,
                                "branch_id": branch_id, "exception_type": type(exc).__name__})
            raise
        if not isinstance(output, dict):
            raise InvalidOutput("model response must be an object")
        self.events.append({"event": "model_returned", "stage": stage, "ordinal": self.calls,
                            "branch_id": branch_id, "result": copy.deepcopy(output)})
        return copy.deepcopy(output)

    def _outcome(self, task: dict, status: str, reason: str, **extra: Any) -> dict:
        return {"version": VERSION, "case_id": task["case_id"], "input_sha256": task["input_sha256"],
                "status": status, "reason": reason, "calls": self.calls,
                "evidence_sha256": task["evidence_sha256"], "semantic_status": "unreviewed", "evidence": _all_evidence(task),
                "required_questions": copy.deepcopy(task["required_questions"]),
                "events": copy.deepcopy(self.events), **copy.deepcopy(extra)}

    def run(self, task: dict) -> dict:
        if self._used:
            raise ValueError("engine instances are single use")
        self._used = True
        task = prepare_task(task)
        try:
            return self._run(task)
        except BudgetExhausted:
            return self._outcome(task, "unknown", "generation_cap_exhausted", result=None,
                                 coverage=self._coverage(task, set(), {}), selected_trace=[], branches=self._branches)
        except InvalidOutput as exc:
            return self._outcome(task, "technical_failure", str(exc), result=None,
                                 coverage=self._coverage(task, set(), {}), selected_trace=[], branches=self._branches)
        except Exception as exc:
            # Effect truth and retry decisions remain owned by the executor.
            # A failed callback is not evidence that a source or fact is absent.
            return self._outcome(task, "technical_failure", "callback_failed:" + type(exc).__name__,
                                 result=None, coverage=self._coverage(task, set(), {}),
                                 selected_trace=[], branches=self._branches)

    def _coverage(self, task: dict, leaves: set[str], claims: dict[str, dict]) -> list[dict]:
        present = {x["id"] for x in _all_evidence(task)}
        output = []
        for item in task["required_questions"]:
            ids = item["evidence_ids"]
            missing = [x for x in ids if x not in present]
            unselected = [x for x in ids if x in present and x not in leaves]
            if missing and all(x in task["unavailable_evidence_ids"] for x in missing):
                status, reason = "source_unavailable", "caller reports required evidence unavailable for this case"
            elif missing:
                status, reason = "not_assessed", "required evidence absent from the bundle; availability unknown"
            elif unselected:
                status, reason = "not_assessed", "required evidence not supplied to selected formatter context"
            elif item["id"] not in claims:
                status, reason = "not_assessed", "no recorded model assessment"
            else:
                status, reason = claims[item["id"]]["status"], claims[item["id"]]["reason"]
            output.append({"question_id": item["id"], "question": item["question"], "status": status,
                           "reason": reason, "evidence_ids": list(ids), "missing_ids": missing,
                           "unselected_ids": unselected,
                           "assessment_origin": "model_unverified" if status in {"assessed", "insufficient_evidence"} else "structural"})
        return output

    def _run(self, task: dict) -> dict:
        common = {item["id"]: copy.deepcopy(item) for item in _all_evidence(task)}
        beam = [_Branch("root", copy.deepcopy(common))]
        all_branches = self._branches
        for depth in range(1, self.config.max_depth + 1):
            candidates = []
            for branch in beam:
                if branch.halted:
                    candidates.append(branch)
                    continue
                selected = self._call("selection", {"question": task["question"], "task_type": task["task_type"],
                    "as_of_utc": task["as_of_utc"], "required_questions": copy.deepcopy(task["required_questions"]),
                    "available_statements": list(branch.nodes.values())}, branch.ident)
                selection_call = self.calls
                alternatives = selected.get("alternatives")
                if not isinstance(alternatives, list) or len(alternatives) > self.config.max_alternatives:
                    raise InvalidOutput("invalid selection alternatives")
                signatures = set()
                for position, ids in enumerate(alternatives, 1):
                    if (not isinstance(ids, list) or not ids or any(not isinstance(x, str) or not x for x in ids)
                            or len(ids) != len(set(ids)) or any(x not in branch.nodes for x in ids)):
                        raise InvalidOutput("selection has unknown, duplicate or empty IDs")
                    signature = tuple(sorted(ids))
                    if signature in signatures:
                        continue
                    signatures.add(signature)
                    texts = [{"text": branch.nodes[x]["text"],
                              "source": branch.nodes[x].get("source", "model inference, not source fact"),
                              "kind": branch.nodes[x].get("kind", "derived_claim")} for x in ids]
                    inference = self._call("inference", {"selected_texts": texts}, branch.ident)
                    inference_call = self.calls
                    conclusion = inference.get("conclusion")
                    if not isinstance(conclusion, str) or not conclusion.strip():
                        raise InvalidOutput("inference conclusion must be nonempty")
                    self._next_node += 1
                    node_id = f"node:{self._next_node:04d}"
                    ident = f"{branch.ident}.{depth}.{position}"
                    steps = copy.deepcopy(branch.steps) + [{"selected_ids": list(ids), "conclusion_id": node_id,
                        "conclusion": conclusion, "depth": depth, "verification": "unreviewed",
                        "selection_call_ordinal": selection_call, "inference_call_ordinal": inference_call}]
                    nodes = copy.deepcopy(branch.nodes)
                    nodes[node_id] = {"id": node_id, "text": conclusion, "kind": "derived_claim",
                                      "source": "model inference, not source fact"}
                    halt = self._call("halter", {"question": task["question"], "task_type": task["task_type"],
                                                   "as_of_utc": task["as_of_utc"], "current_inference": conclusion,
                                                   "selected_texts": texts}, ident)
                    halter_call = self.calls
                    if type(halt.get("sufficient")) is not bool:
                        raise InvalidOutput("halter sufficient must be boolean")
                    value = self._call("value", {"question": task["question"], "task_type": task["task_type"],
                        "as_of_utc": task["as_of_utc"], "visible_evidence": list(common.values()), "trace": steps}, ident)
                    value_call = self.calls
                    score = value.get("score")
                    if type(score) not in (int, float) or not math.isfinite(score) or not 0 <= score <= 1:
                        raise InvalidOutput("value score must be finite in [0,1]")
                    candidate = _Branch(ident, nodes, steps, float(score), halt["sufficient"], node_id)
                    candidates.append(candidate)
                    event = {"event": "step_proposed", "branch_id": ident, "depth": depth,
                             "selected_ids": list(ids), "conclusion_id": node_id,
                             "sufficient": halt["sufficient"], "value_score": float(score),
                             "selection_call_ordinal": selection_call, "inference_call_ordinal": inference_call,
                             "halter_call_ordinal": halter_call, "value_call_ordinal": value_call}
                    # Only explicitly returned reasons are recorded; never invent one.
                    for name, source in (("selection_reason", selected), ("halter_reason", halt), ("value_reason", value)):
                        if isinstance(source.get("reason"), str) and source["reason"].strip():
                            event[name] = source["reason"]
                    self.events.append(event)
                    all_branches.append({"branch_id": ident, "steps": copy.deepcopy(steps),
                                         "score": float(score), "halted": halt["sufficient"]})
            if not candidates:
                return self._outcome(task, "unknown", "no_valid_candidate", result=None,
                                     coverage=self._coverage(task, set(), {}), selected_trace=[], branches=all_branches)
            candidates.sort(key=lambda b: (-b.score, b.ident))
            beam = candidates[:self.config.beam_width]
            self.events.append({"event": "beam_selected", "depth": depth, "branch_ids": [b.ident for b in beam]})
            if all(b.halted for b in beam):
                break
        ready = [b for b in beam if b.halted and b.latest is not None]
        if not ready:
            return self._outcome(task, "unknown", "reasoning_depth_exhausted", result=None,
                                 coverage=self._coverage(task, set(), {}), selected_trace=[], branches=all_branches)
        best = ready[0]
        trace, leaves, effective_depth = _ancestry(best.steps, best.latest)
        selected_evidence = [copy.deepcopy(item) for item in _all_evidence(task) if item["id"] in leaves]
        # Obligations are the user's task, not hidden source text. The formatter
        # may address only the selected evidence and selected inference ancestry.
        raw = self._call("formatter", {"question": task["question"], "task_type": task["task_type"],
            "as_of_utc": task["as_of_utc"], "selected_trace": trace,
            "selected_evidence": selected_evidence, "required_questions": copy.deepcopy(task["required_questions"])}, best.ident)
        answer = raw.get("answer")
        citations = raw.get("citations")
        assessments = raw.get("assessments", [])
        if not isinstance(answer, str) or not answer.strip():
            raise InvalidOutput("formatter answer must be nonempty")
        if (not isinstance(citations, list) or any(not isinstance(x, str) for x in citations)
                or len(set(citations)) != len(citations) or any(x not in leaves for x in citations)):
            raise InvalidOutput("formatter citations must be unique selected evidence IDs")
        if not isinstance(assessments, list):
            raise InvalidOutput("formatter assessments must be an array")
        allowed = {item["id"] for item in task["required_questions"]}
        claims = {}
        for item in assessments:
            if (not isinstance(item, dict) or not isinstance(item.get("id"), str)
                    or item.get("id") not in allowed or item.get("id") in claims
                    or not isinstance(item.get("status"), str)
                    or item.get("status") not in {"assessed", "insufficient_evidence"}
                    or not isinstance(item.get("reason"), str) or not item["reason"].strip()):
                raise InvalidOutput("invalid model assessment")
            claims[item["id"]] = {"status": item["status"], "reason": item["reason"]}
        coverage = self._coverage(task, leaves, claims)
        status = "proposal" if all(item["status"] == "assessed" for item in coverage) else "incomplete"
        return self._outcome(task, status, "model_proposal_requires_semantic_review", result=raw,
                             coverage=coverage, selected_trace=trace, selected_branch=best.ident,
                             inference_dependency_depth=effective_depth, branches=all_branches)
