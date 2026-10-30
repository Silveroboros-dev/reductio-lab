"""Role prompts for the versioned controller; caller owns provider effects."""
from __future__ import annotations

import copy
from typing import Any, Callable

from reasoning_engine.prompts import build_request as old_build_request

VERSION = 'faithful-v3-prompts-1'


def build_request(stage: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Project one stateless role request; the task cannot leak into Inference/Formatter."""
    if stage == 'inference' and set(payload) != {'selected_texts'}:
        raise ValueError('inference may only receive selected premises')
    if stage == 'formatter' and set(payload) != {'final_inference', 'allowed_citation_ids'}:
        raise ValueError('formatter may only receive the final inference and citation IDs')
    request = old_build_request(stage, copy.deepcopy(payload))
    request['prompt_version'] = VERSION
    if stage == 'source_decision':
        request['instruction'] = (
            'Choose one available action ID, STOP, or UNKNOWN based only on the task, '
            'observed source results and available action descriptions. STOP means stop '
            'acquiring sources, not that the factual question has been answered. '
            'UNKNOWN means you cannot responsibly choose an action. Return a JSON object '
            "{'choice': string, 'reason': string, 'expected_result': string}. "
            'Descriptions say what an action may retrieve; they are not retrieved facts.'
        )
    elif stage == 'selection':
        request['instruction'] += (
            ' The question is the user target, not an established fact. '
            'candidate_findings are unverified source-decision notes with context references, '
            'not evidence. Select only IDs in available_statements and independently '
            'derive any relevant finding from those selected statements.'
        )
    elif stage == 'halter':
        request['instruction'] = (
            'Given the exact question and the current inference, determine whether the '
            'inference answers that question. Return {"sufficient": boolean, "reason": string}. '
            'Do not treat a nearby metric, entity, period, or a proxy as the requested answer. '
            'If the inference is insufficient, say so; this judgment is unverified.'
        )
    elif stage == 'formatter':
        request['instruction'] = (
            'Render only the supplied final inference. Do not introduce new factual claims. '
            'Return {"answer": string, "citations": [IDs]} using only allowed_citation_ids. '
            'The citation IDs identify declared evidence ancestry, not verified entailment.'
        )
    return request


def bind_model(requester: Callable[[dict[str, Any]], dict[str, Any]]) -> Callable[[str, dict[str, Any]], dict[str, Any]]:
    if not callable(requester):
        raise ValueError('requester callback required')
    def generate(stage: str, payload: dict[str, Any]) -> dict[str, Any]:
        return requester(build_request(stage, payload))
    return generate
