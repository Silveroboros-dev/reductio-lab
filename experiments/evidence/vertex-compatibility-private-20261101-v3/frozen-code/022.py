"""Offline adapter from versioned role requests to Vertex Gemini wire bodies.

This module has no credentials, HTTP client, retry loop, or provider authority.
Callers supply a ledger implementing ``count`` and ``generate`` plus its
single-shot transport. Operation IDs are supplied by the caller and must be
stable and unique for one role call.
"""
from __future__ import annotations

import copy
import json
from dataclasses import dataclass
from typing import Any, Callable

MODEL = "gemini-3.8-flash"
MAX_OUTPUT_TOKENS = 4096
THINKING_LEVEL = "LOW"


def model_matches(version: Any, model: str = MODEL) -> bool:
    return isinstance(version, str) and (version == model or version.startswith(model + '-'))


class AdapterError(ValueError):
    """The provider returned a response that cannot be used as a role result."""


class IncompleteGeneration(AdapterError):
    """The provider stopped before completing the role response."""

    def __init__(self, finish_reason: str, receipt: "VertexResult"):
        super().__init__(f"generation was incomplete: {finish_reason}")
        self.finish_reason = finish_reason
        self.receipt = receipt


def canonical_json(value: Any) -> bytes:
    """Canonical UTF-8 JSON used to freeze and compare request bodies."""
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def build_generation_request(role_request: dict[str, Any]) -> dict[str, Any]:
    """Convert one prompts.build_request result into a Gemini generate body.

    The version, stage, instruction and input are retained together as one
    user message. The separately supplied system text is sent as
    ``systemInstruction``. Count and generate callers must use this exact body.
    """
    required = {"prompt_version", "system", "stage", "instruction", "input"}
    if not isinstance(role_request, dict) or set(role_request) != required:
        raise AdapterError("role request has an unexpected shape")
    for key in ("prompt_version", "system", "stage", "instruction"):
        if not isinstance(role_request[key], str) or not role_request[key].strip():
            raise AdapterError(f"role request {key} must be nonempty text")
    if not isinstance(role_request["input"], dict):
        raise AdapterError("role request input must be an object")

    role_envelope = {
        "prompt_version": role_request["prompt_version"],
        "stage": role_request["stage"],
        "instruction": role_request["instruction"],
        "input": copy.deepcopy(role_request["input"]),
    }
    return {
        "systemInstruction": {"parts": [{"text": role_request["system"]}]},
        "contents": [{"role": "user", "parts": [{"text": canonical_json(role_envelope).decode("utf-8")}]}],
        "generationConfig": {
            "maxOutputTokens": MAX_OUTPUT_TOKENS,
            "responseMimeType": "application/json",
            "thinkingConfig": {"thinkingLevel": THINKING_LEVEL},
        },
    }


def build_count_request(generation_request: dict[str, Any]) -> dict[str, Any]:
    """Return an independent copy with byte-identical canonical JSON."""
    encoded = canonical_json(generation_request)
    result = json.loads(encoded)
    if canonical_json(result) != encoded:
        raise AdapterError("count request serialization changed the generation body")
    return result


@dataclass(frozen=True)
class VertexResult:
    content: dict[str, Any]
    usage_metadata: dict[str, Any]
    finish_reason: str
    model_version: str


def _object_no_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise AdapterError("duplicate JSON object key")
        result[key] = value
    return result


def _nonnegative_int(value: Any, field: str) -> int:
    if type(value) is not int or value < 0:
        raise AdapterError(f"invalid usageMetadata.{field}")
    return value


def parse_vertex_response(raw: bytes) -> VertexResult:
    """Parse a captured 200 response without discarding usage or finish data."""
    if not isinstance(raw, bytes):
        raise AdapterError("provider response must be bytes")
    try:
        envelope = json.loads(raw.decode("utf-8"), object_pairs_hook=_object_no_duplicate_keys)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AdapterError(f"provider response is not valid JSON: {type(exc).__name__}") from None
    if not isinstance(envelope, dict):
        raise AdapterError("provider response must be a JSON object")

    version = envelope.get("modelVersion")
    usage = envelope.get("usageMetadata")
    candidates = envelope.get("candidates")
    if not isinstance(version, str) or not version:
        raise AdapterError("provider response is missing modelVersion")
    if not isinstance(usage, dict):
        raise AdapterError("provider response is missing usageMetadata")
    prompt_tokens = _nonnegative_int(usage.get("promptTokenCount"), "promptTokenCount")
    total_tokens = _nonnegative_int(usage.get("totalTokenCount"), "totalTokenCount")
    if total_tokens < prompt_tokens:
        raise AdapterError("usageMetadata.totalTokenCount is below promptTokenCount")
    for optional in ("candidatesTokenCount", "thoughtsTokenCount", "cachedContentTokenCount", "toolUsePromptTokenCount"):
        if optional in usage:
            _nonnegative_int(usage[optional], optional)
    if usage.get("thoughtsTokenCount", 0) > total_tokens - prompt_tokens:
        raise AdapterError("usageMetadata.thoughtsTokenCount exceeds output tokens")
    if not isinstance(candidates, list) or len(candidates) != 1 or not isinstance(candidates[0], dict):
        raise AdapterError("provider response must contain exactly one candidate")
    candidate = candidates[0]
    finish = candidate.get("finishReason")
    if not isinstance(finish, str) or not finish:
        raise AdapterError("candidate is missing finishReason")
    content = candidate.get("content")
    if not isinstance(content, dict) or not isinstance(content.get("parts"), list):
        raise AdapterError("candidate is missing content parts")
    text_parts = [part.get("text") for part in content["parts"]
                  if isinstance(part, dict) and isinstance(part.get("text"), str)]
    if not text_parts:
        raise AdapterError("candidate has no text content")
    try:
        role_content = json.loads("".join(text_parts), object_pairs_hook=_object_no_duplicate_keys)
    except (json.JSONDecodeError, AdapterError) as exc:
        if isinstance(exc, AdapterError):
            raise
        raise AdapterError("candidate content is not valid JSON") from None
    if not isinstance(role_content, dict):
        raise AdapterError("candidate content must be a JSON object")
    return VertexResult(content=role_content, usage_metadata=copy.deepcopy(usage),
                        finish_reason=finish, model_version=version)


class VertexAdapter:
    """Run a role request through caller-owned count/generate ledger methods.

    ``ledger`` must expose ``count(count_id, generation_request, transport)``
    and ``generate(generation_id, generation_request, count_id, transport)``.
    The provided transport is passed through unchanged. Exceptions (including
    timeout, HTTP 429 and uncertain-effect errors) propagate to the caller.
    """

    def __init__(self, ledger: Any, transport: Callable[..., tuple[int, bytes]]):
        if ledger is None or not callable(getattr(ledger, "count", None)) or not callable(getattr(ledger, "generate", None)):
            raise ValueError("ledger must provide count and generate")
        if not callable(transport):
            raise ValueError("transport callback required")
        self._ledger = ledger
        self._transport = transport

    def complete(self, role_request: dict[str, Any], *, operation_id: str) -> VertexResult:
        if not isinstance(operation_id, str) or not operation_id.strip():
            raise ValueError("stable operation_id required")
        generation_request = build_generation_request(role_request)
        frozen = canonical_json(generation_request)
        count_id = "count:" + operation_id
        generation_id = "generation:" + operation_id
        count_request = build_count_request(generation_request)
        self._ledger.count(count_id, count_request, self._transport)
        # Recreate from the frozen bytes so a ledger implementation cannot
        # mutate the count dictionary and silently change the generation body.
        generation_request = json.loads(frozen)
        if canonical_json(generation_request) != frozen:
            raise AdapterError("generation request changed after counting")
        raw = self._ledger.generate(generation_id, generation_request, count_id, self._transport)
        result = parse_vertex_response(raw)
        if not model_matches(result.model_version):
            raise AdapterError("observed model version does not match pinned model")
        if result.finish_reason != "STOP":
            raise IncompleteGeneration(result.finish_reason, result)
        return result
