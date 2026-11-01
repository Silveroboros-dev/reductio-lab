"""Offline demonstration. Fake responses are illustrative, not model evidence.

Run: python -m reasoning_engine.demo [--json]
"""
from __future__ import annotations

import argparse
import json

from .engine import Engine
from .prompts import bind_model
from .renderer import render_outcome


def demo_packet() -> dict:
    task = {
        "case_id": "synthetic-cpi-coverage", "task_type": "evidence_impact",
        "question": "Assess the supplied news against this synthetic contract.",
        "as_of_utc": "2026-10-29T12:35:00Z",
        "thesis": {"text": "A synthetic inflation thesis", "version": "v1", "origin": "demo only"},
        "evidence": [
            {"id": "rule", "kind": "contract_rule", "text": "A published monthly CPI figure above 0.2% resolves YES.", "source": "synthetic contract"},
            {"id": "pce", "kind": "news", "text": "A hypothetical PCE report was released.", "source": "synthetic news"},
        ],
        "required_questions": [{"id": "pce-impact", "question": "Assess the PCE report's impact on YES.", "evidence_ids": ["pce"]}],
    }
    requests = []
    def scripted(request):
        requests.append(request)
        stage = request["stage"]
        if stage == "selection":
            return {"alternatives": [["rule"], ["rule", "pce"]]}
        if stage == "inference":
            return {"conclusion": "An illustrative and unverified inference."}
        if stage == "halter":
            return {"sufficient": True}
        if stage == "value":
            ids = request["input"]["trace"][-1]["selected_ids"]
            return {"score": 0.8 if "pce" in ids else 0.9}
        if stage == "formatter":
            return {"answer": "No further release needs assessment.", "citations": ["rule"],
                    "assessments": [{"id": "pce-impact", "status": "assessed", "reason": "No impact."}]}
        raise ValueError(stage)
    outcome = Engine(bind_model(scripted)).run(task)
    return {"kind": "scripted_offline_demo_not_model_evidence", "task": task,
            "model_requests": requests, "outcome": outcome,
            "accounting": {"real_model_calls": 0, "source_calls": 0, "provider_cost_usd": 0,
                           "scripted_stage_callbacks": outcome["calls"]}}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="show complete task, requests, trace and synthetic outputs")
    args = parser.parse_args()
    packet = demo_packet()
    if args.json:
        print(json.dumps(packet, indent=2, ensure_ascii=False))
    else:
        print("OFFLINE SCRIPTED DEMONSTRATION: no real model or source calls; not experimental results.\n")
        print(render_outcome(packet["outcome"]))
        print("Costs: $0; scripted callbacks:", packet["outcome"]["calls"])
        print("For the complete synthetic packet run: python -m reasoning_engine.demo --json")


if __name__ == "__main__":
    main()
