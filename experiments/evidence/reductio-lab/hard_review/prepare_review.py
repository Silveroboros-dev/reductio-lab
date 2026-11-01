"""Build blinded, per-assignment review packets from a completed or partial run.

This utility is intentionally read-only on the run directory and makes no
provider/model calls. Reviewer packets never contain arm labels or other-arm
outcomes. The separate custodian directory contains the unblinding map/key.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
from pathlib import Path
from typing import Any


RUBRIC = """# Independent review rubric

Review each packet on its own. A proposal is not automatically correct because
its answer matches the synthetic answer key. Do not treat unknowns or technical
failures as incorrect answers.

For a substantive proposal, record:

1. **Conclusion correctness** — Does the answer follow from the supplied task
   and evidence? Check polarity, entity, and requested condition.
2. **Premise sufficiency** — Do the cited/selected premises support every
   inference step needed for the conclusion? For these logical tasks, check the
   stated rule antecedents and whether the initial fact reaches them. This is
   logical sufficiency, not a claim about real-world causation.
3. **Unsupported inference** — Mark any invented premise, skipped condition,
   invalid substitution, polarity flip, contradiction, or outside knowledge.
4. **Evidence use** — Are explanations and citations faithful to the supplied
   statements? A citation ID alone does not establish entailment.

Use `supported`, `partly_supported`, `unsupported`, or `unclear` for the first
two criteria. For unsupported inference, record `none_observed`, `present`, or
`unclear`, with a short explanation.

For `unknown_no_answer`, judge whether UNKNOWN is warranted because neither
answer follows, or whether the supplied evidence supports YES/NO. Keep this
separate from answer correctness. For `technical_failure_no_answer` or
`no_final_proposal`, do not assign semantic correctness; record the item in the
failure denominator and note the visible failure category only.

The C trace can reveal the method through its role names and branch structure.
Blinding is therefore limited. Do not infer that traceability proves truth,
causal influence, or semantic validity. An automated synthetic key may be
provided separately by the custodian after blinded review; it is not a human
gold standard.

Suggested review fields: conclusion_correctness, premise_sufficiency,
unsupported_inference, evidence_use, unknown_warranted (when applicable), and
reviewer_explanation.
"""


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _read_json(path: Path) -> Any:
    return json.loads(path.read_bytes())


def _write_new(path: Path, value: Any) -> None:
    raw = _canonical(value)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                 getattr(os, "O_NOFOLLOW", 0), 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())


def _proposal(outcome: dict[str, Any], arm: str) -> dict[str, Any]:
    result = outcome.get("result") if arm == "C" else outcome.get("final_result")
    if isinstance(result, dict) and isinstance(result.get("answer"), str) and result["answer"].strip():
        category = "proposal"
        public_result = result
    elif outcome.get("status") == "unknown":
        category, public_result = "unknown_no_answer", None
    elif outcome.get("status") == "technical_failure":
        category, public_result = "technical_failure_no_answer", None
    else:
        category, public_result = "no_final_proposal", None
    reason = outcome.get("reason")
    return {"category": category, "reason": reason if isinstance(reason, str) else None,
            "final_response": public_result}


def _reviewer_packet(case_alias: str, packet_id: str, task: dict[str, Any],
                     outcome_packet: dict[str, Any], arm: str) -> dict[str, Any]:
    outcome = outcome_packet["outcome"]
    packet = {
        "schema": "hard-si-independent-review-v1",
        "packet_id": packet_id,
        "case_alias": case_alias,
        "task": {key: value for key, value in task.items() if key != "case_id"},
        "submission": _proposal(outcome, arm),
        "review": {
            "conclusion_correctness": None,
            "premise_sufficiency": None,
            "unsupported_inference": None,
            "evidence_use": None,
            "unknown_warranted": None,
            "reviewer_explanation": None,
        },
    }
    if arm == "C":
        # Preserve the recorded C reasoning and branch evidence. These details
        # can make the method recognizable, which the rubric discloses.
        packet["recorded_trace"] = {
            key: outcome.get(key)
            for key in ("events", "branches", "selected_trace", "selected_branch",
                        "inference_dependency_depth", "partial_trace")
            if key in outcome
        }
    return packet


def build_packets(run_dir: Path, output_dir: Path, *, seed: int = 20261029) -> dict[str, Any]:
    """Create reviewer and custodian folders from summary/tasks/key/outcomes.

    Supports partial summaries. The source directory is read only. The output
    directory must not already exist, preventing accidental packet replacement.
    """
    run_dir, output_dir = Path(run_dir), Path(output_dir)
    summary = _read_json(run_dir / "summary.json")
    tasks_raw = _read_json(run_dir / "tasks.json")
    keys_raw = _read_json(run_dir / "answer-key.json")
    tasks = {task["case_id"]: task for task in tasks_raw}
    keys = {key["case_id"]: key for key in keys_raw}
    records = summary.get("records")
    if not isinstance(records, list):
        raise ValueError("summary must contain a records array")

    work = []
    seen = set()
    for record in records:
        case_id, arm, slot = record.get("case_id"), record.get("arm"), record.get("slot")
        if not all(isinstance(value, str) and value for value in (case_id, arm, slot)):
            raise ValueError("each record requires case_id, arm, and slot")
        identity = (case_id, arm)
        if identity in seen:
            raise ValueError("duplicate case/arm record")
        seen.add(identity)
        if case_id not in tasks or case_id not in keys:
            raise ValueError("record is missing its task or synthetic key")
        artifact = _read_json(run_dir / f"{slot}.outcome.json")
        if (artifact.get("case_id"), artifact.get("arm")) != identity:
            raise ValueError("outcome identity does not match summary record")
        case_alias = "case-" + _sha(f"{seed}:case:{case_id}")[:12]
        packet_id = "packet-" + _sha(f"{seed}:assignment:{case_id}:{arm}")[:16]
        work.append((case_alias, packet_id, case_id, arm, slot, artifact))

    random.Random(seed).shuffle(work)
    if output_dir.exists() or output_dir.is_symlink():
        raise ValueError("output directory already exists")
    reviewer_dir = output_dir / "reviewer"
    custodian_dir = output_dir / "custodian"
    reviewer_dir.mkdir(parents=True, mode=0o700)
    custodian_dir.mkdir(mode=0o700)

    mapping = []
    manifest = []
    for case_alias, packet_id, case_id, arm, slot, artifact in work:
        packet = _reviewer_packet(case_alias, packet_id, tasks[case_id], artifact, arm)
        _write_new(reviewer_dir / f"{packet_id}.json", packet)
        manifest.append({"packet_id": packet_id, "case_alias": case_alias})
        mapping.append({"packet_id": packet_id, "case_alias": case_alias,
                        "case_id": case_id, "arm": arm, "slot": slot})

    _write_new(reviewer_dir / "manifest.json", {
        "schema": "hard-si-review-manifest-v1",
        "packet_order": [item["packet_id"] for item in manifest],
        "packet_count": len(manifest),
        "limitations": [
            "Case and assignment identifiers are pseudonymized.",
            "Each packet contains only one assignment outcome.",
            "C traces can reveal the method; blinding is limited.",
        ],
    })
    rubric_fd = os.open(reviewer_dir / "RUBRIC.md", os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                        getattr(os, "O_NOFOLLOW", 0), 0o600)
    with os.fdopen(rubric_fd, "w", encoding="utf-8") as stream:
        stream.write(RUBRIC)
        stream.flush()
        os.fsync(stream.fileno())
    _write_new(custodian_dir / "unblinding-key.json", {
        "schema": "hard-si-unblinding-key-v1",
        "shuffle_seed": seed,
        "synthetic_key_notice": "Generated corpus key; not a human golden.",
        "assignments": mapping,
        "answer_keys": [keys[case_id] for case_id in sorted({item[2] for item in work})],
    })
    return {"packet_count": len(work), "reviewer_dir": str(reviewer_dir),
            "custodian_dir": str(custodian_dir)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_dir", type=Path, help="private run artifact directory")
    parser.add_argument("output_dir", type=Path, help="new output directory")
    parser.add_argument("--seed", type=int, default=20261029)
    args = parser.parse_args()
    print(json.dumps(build_packets(args.run_dir, args.output_dir, seed=args.seed), indent=2))


if __name__ == "__main__":
    main()
