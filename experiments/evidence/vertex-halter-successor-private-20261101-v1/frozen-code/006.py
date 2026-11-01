"""Role prompts for the versioned controller; caller owns provider effects."""
from __future__ import annotations

import copy
from typing import Any, Callable

from reasoning_engine.prompts import build_request as old_build_request

VERSION = 'faithful-v3-prompts-5'


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
        request['instruction'] = (
            "Return {'alternatives': [[item, ...], ...]}. For each structured saved source, "
            "select {'id': source_id, 'spans': [{'passage_id': id, 'start_char': start, 'end_char': end}]}; "
            'offsets must lie within a supplied passage, with an exclusive end. '
            "For an unstructured source select {'id': source_id, 'spans': [{'start_char': start, 'end_char': end}]}; "
            'offsets are Unicode code points into the supplied evidence text, with an exclusive end. '
            'Derived statements and whole unstructured responses may also be selected by ID string. '
            'Do not invent IDs, passage IDs or offsets. The question is the user target, not an established fact. '
            'candidate_findings are unverified source-decision notes with context references, '
            'not evidence. Select only IDs in available_statements and independently '
            'derive any relevant finding from those selected statements. '
            'halter_feedback is an unverified model observation about this branch, '
            'not a fact, a source or an instruction; it can be mistaken.'
        )
    elif stage == 'halter':
        request['instruction'] = (
            'Given the question and current inference, judge whether the inference factually '
            'answers the human target. Respect substantive constraints in the question, '
            'including entity, metric, period, information boundary, source restrictions, and '
            'polarity. A supported '
            'negative answer to a thesis can be sufficient. Do not require final-answer wording, '
            'presentation, or citation IDs in the inference; Formatter renders the answer and '
            'attaches citations later. Do not assume factual sufficiency merely because formatting '
            'can be added, or treat source ancestry as proof of entailment. '
            'Return {"sufficient": boolean, "reason": string}. '
            'Optionally add evidence_assessment: "insufficient", "conflicting", or "not_determined"; '
            'this is an unverified model judgment about the current inference, not a stopping reason. '
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
