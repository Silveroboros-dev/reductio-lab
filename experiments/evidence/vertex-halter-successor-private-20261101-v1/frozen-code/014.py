"""Small offline comparison and reporting helpers for Faithful Engine runs.

This module deliberately does not judge semantics, ethics, or human-gold
quality. It checks declared inputs and summarizes recorded outcomes/operations.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
from typing import Any, Iterable, Mapping, Sequence


RUNTIME_STATUSES = (
    "assigned",
    "completed",
    "unknown",
    "incomplete",
    "technical_failure",
)
REVIEW_STATUSES = (
    "unreviewed",
    "adjudicated",
    "not_applicable",
)
METRICS = ("cost", "calls", "tokens", "latency_ms")
RUBRIC_DIMENSIONS = {"thesis", "fit", "evidence", "local_inference", "forecast", "action_stop", "human_value", "resources"}
COMPARE_FIELDS = (
    "human_task",
    "evidence_snapshot",
    "as_of",
    "quote",
    "prior",
    "p0",
    "model_settings",
    "limits",
)
INTENTIONAL_DIFFERENCE_FIELDS = ("role_prompt", "strategy_prompt", "projection")


def canonical_json(value: Any) -> str:
    """Return stable JSON for JSON-like data; mapping order is insignificant."""
    def convert(item: Any) -> Any:
        if isinstance(item, datetime):
            if item.tzinfo is None:
                return item.isoformat()
            return item.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
        if isinstance(item, date):
            return item.isoformat()
        if isinstance(item, Mapping):
            if not all(isinstance(k, str) for k in item):
                raise TypeError("mapping keys must be strings")
            return {k: convert(item[k]) for k in sorted(item)}
        if isinstance(item, (list, tuple)):
            return [convert(v) for v in item]
        if item is None or isinstance(item, (str, bool, int)):
            return item
        if isinstance(item, float):
            if not math.isfinite(item):
                raise ValueError("non-finite numbers are not supported")
            return item
        raise TypeError(f"unsupported value type: {type(item).__name__}")

    return json.dumps(convert(value), sort_keys=True, ensure_ascii=False,
                      separators=(",", ":"), allow_nan=False)


def stable_hash(value: Any) -> str:
    """SHA-256 of canonical JSON, prefixed with the algorithm name."""
    payload = canonical_json(value).encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def compare_inputs(left: Mapping[str, Any], right: Mapping[str, Any],
                   fields: Sequence[str] = COMPARE_FIELDS) -> dict[str, Any]:
    """Check required comparable inputs pairwise; intentional prompt fields are excluded.

    Every requested field must exist on both sides and have identical canonical
    content. Hashes are reported instead of copying potentially sensitive input.
    """
    if not fields or any(not isinstance(field, str) or not field for field in fields):
        raise ValueError("fields must contain at least one non-empty field name")

    field_results: dict[str, Any] = {}
    for field in fields:
        has_left, has_right = field in left, field in right
        if not has_left or not has_right:
            field_results[field] = {
                "equal": False,
                "left_present": has_left,
                "right_present": has_right,
                "reason": "missing_input",
            }
            continue
        if field in {"human_task", "evidence_snapshot", "as_of", "model_settings", "limits"} and (left[field] is None or right[field] is None):
            field_results[field] = {"equal": False, "reason": "unknown_input"}
            continue
        if field == "p0":
            p0_left, p0_right = left[field], right[field]
            required = ("value", "content", "justification")
            if p0_left is None and p0_right is None:
                field_results[field] = {"equal": True, "reason": "both_declared_no_p0"}
                continue
            if (not isinstance(p0_left, Mapping) or not isinstance(p0_right, Mapping)
                    or any(key not in p0_left or key not in p0_right for key in required)
                    or any(p0_left[key] is None or p0_right[key] is None for key in ("content", "justification"))
                    or not _numeric(p0_left.get("value"))
                    or not 0 <= p0_left["value"] <= 1
                    or not _numeric(p0_right.get("value"))
                    or not 0 <= p0_right["value"] <= 1):
                field_results[field] = {"equal": False, "reason": "invalid_p0_shape"}
                continue
            components = {}
            for key in required:
                components[key] = {
                    "equal": stable_hash(p0_left[key]) == stable_hash(p0_right[key]),
                    "left_hash": stable_hash(p0_left[key]),
                    "right_hash": stable_hash(p0_right[key]),
                }
            field_results[field] = {
                "equal": all(v["equal"] for v in components.values()),
                "components": components,
            }
            continue
        left_hash, right_hash = stable_hash(left[field]), stable_hash(right[field])
        field_results[field] = {
            "equal": left_hash == right_hash,
            "left_hash": left_hash,
            "right_hash": right_hash,
        }
    return {
        "equal": all(v["equal"] for v in field_results.values()),
        "fields": field_results,
        "excluded_intentional_difference_fields": list(INTENTIONAL_DIFFERENCE_FIELDS),
    }


def _numeric(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _metric_summary(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    for metric in METRICS:
        known = [r.get("metrics", {}).get(metric) for r in records
                 if isinstance(r.get("metrics", {}), Mapping)]
        valid = [v for v in known if _numeric(v) and v >= 0]
        summary[metric] = {
            "known_count": len(valid),
            "unknown_count": len(records) - len(valid),
            "total": sum(valid) if valid else None,
            "mean": (sum(valid) / len(valid)) if valid else None,
        }
    return summary


def _branch_report(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    runtime_counts = Counter()
    review_counts = Counter()
    by_runtime: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    exposures = Counter()
    posthoc = []
    rubric_reviews = []
    assignment_ids = set()
    case_ids = set()
    for index, record in enumerate(records):
        runtime_status = record.get("runtime_status")
        review_status = record.get("review_status")
        if runtime_status not in RUNTIME_STATUSES:
            raise ValueError(f"record {index} has invalid runtime_status: {runtime_status!r}")
        if review_status not in REVIEW_STATUSES:
            raise ValueError(f"record {index} has invalid review_status: {review_status!r}")
        assignment_id, case_id = record.get("assignment_id"), record.get("case_id")
        if not isinstance(assignment_id, str) or not assignment_id:
            raise ValueError(f"record {index} requires a non-empty assignment_id")
        if not isinstance(case_id, str) or not case_id:
            raise ValueError(f"record {index} requires a non-empty case_id")
        if assignment_id in assignment_ids:
            raise ValueError(f"duplicate assignment_id: {assignment_id!r}")
        if case_id in case_ids:
            raise ValueError(f"duplicate case_id in branch: {case_id!r}")
        assignment_ids.add(assignment_id)
        case_ids.add(case_id)
        runtime_counts[runtime_status] += 1
        review_counts[review_status] += 1
        by_runtime[runtime_status].append(record)
        exposure = record.get("exposure", "unknown")
        if exposure not in ("exposed", "claimed_blind", "confirmation_unexposed", "unknown"):
            raise ValueError(f"record {index} has invalid exposure: {exposure!r}")
        if exposure == "confirmation_unexposed" and not record.get("exposure_attestation"):
            raise ValueError(f"record {index} requires external exposure_attestation")
        exposures[exposure] += 1
        reviews = record.get("rubric_reviews", [])
        if not isinstance(reviews, list):
            raise ValueError(f"record {index} has invalid rubric_reviews")
        for review in reviews:
            if (not isinstance(review, Mapping) or not isinstance(review.get("dimension"), str)
                    or review.get("dimension") not in RUBRIC_DIMENSIONS
                    or review.get("verdict") not in ("pass", "fail", "unknown")
                    or not isinstance(review.get("reviewer"), str) or not review["reviewer"].strip()
                    or not isinstance(review.get("origin"), str) or not review["origin"].strip()):
                raise ValueError(f"record {index} has invalid attributed rubric review")
            rubric_reviews.append({"assignment_id": assignment_id, "case_id": case_id,
                                   "dimension": review["dimension"], "verdict": review["verdict"],
                                   "reviewer": review["reviewer"], "origin": review["origin"],
                                   "note": review.get("note"), "identity_verified": False})
        if "posthoc_outputs" in record:
            posthoc.append({"record_index": index, "outputs": record["posthoc_outputs"]})

    denominator = len(records)
    runtime_status_counts = {s: runtime_counts[s] for s in RUNTIME_STATUSES}
    review_status_counts = {s: review_counts[s] for s in REVIEW_STATUSES}
    return {
        "denominator": denominator,
        "assignment_count": denominator,
        "runtime_status_counts": runtime_status_counts,
        "runtime_status_rates": {
            s: (runtime_counts[s] / denominator if denominator else None) for s in RUNTIME_STATUSES
        },
        "review_status_counts": review_status_counts,
        "review_status_rates": {
            s: (review_counts[s] / denominator if denominator else None) for s in REVIEW_STATUSES
        },
        "metrics_by_runtime_status": {
            s: _metric_summary(by_runtime[s]) for s in RUNTIME_STATUSES
        },
        "exposure_counts": {
            s: exposures[s] for s in ("exposed", "claimed_blind", "confirmation_unexposed", "unknown")
        },
        "exposure_use": {
            "exposed": "development_or_regression_only",
            "claimed_blind": "caller_claim_unverified; holdout status not established",
            "confirmation_unexposed": "external attestation supplied; not authenticated here",
            "unknown": "use not established",
        },
        "rubric_reviews_as_supplied": rubric_reviews,
        "posthoc_outputs": posthoc,
        "posthoc_is_separate_from_primary_metrics": True,
        "semantic_review": {
            "model_score_used": False,
            "adjudication_is_reported_as_supplied": True,
            "human_gold_quality_assessed": False,
        },
    }


def build_report(branches: Mapping[str, Iterable[Mapping[str, Any]]],
                 input_comparisons: Mapping[str, Mapping[str, Any]] | None = None,
                 outcomes: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Summarize branches without hiding failures, unknowns, or missing telemetry.

    ``input_comparisons`` may map a pair name to ``compare_inputs`` output.
    ``outcomes`` is optional explicit outcome data. This evaluator never derives
    a forecast score; scoring requires a separately specified protocol.
    """
    branch_reports = {name: _branch_report(list(records)) for name, records in branches.items()}
    return {
        "input_comparisons": dict(input_comparisons or {}),
        "branches": branch_reports,
        "forecast_scoring": {
            "computed": False,
            "outcomes_supplied": outcomes is not None,
            "reason": ("explicit_outcomes_present_but_scoring_protocol_not_defined"
                       if outcomes is not None else "no_outcome_data"),
        },
        "value_or_evidence_accuracy_from_model_numbers": "not_computed",
    }
