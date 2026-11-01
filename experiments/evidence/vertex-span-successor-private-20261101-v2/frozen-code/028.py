"""Offline integration checks for the Vertex role adapter and durable journal.

The transports below are scripted callbacks. Nothing in this module opens a
network connection or invokes a model.
"""
from __future__ import annotations

import json
import os
import sqlite3

import pytest

from reasoning_engine.executor import EffectExecutor, HttpResponse
from reasoning_engine.journal_callback import JournaledCallError
import reasoning_engine.vertex_journal as vertex_journal_module
from reasoning_engine.vertex_journal import VertexJournal, VertexJournalError


IDENTITY = {"run": "offline-vertex-fixture", "model": "gemini-3.8-flash"}
INPUT = {"selected_texts": [{"id": "premise-1", "text": "Saved premise A"}]}
COUNT_OK = b'{"totalTokens":32}'
RATE_LIMIT = b'{"error":{"code":429,"status":"RESOURCE_EXHAUSTED"}}'
FORBIDDEN_WIRE_HASHES = (
    "17a148b5aeade7252bf07660e16d3c6ffbb4da639aaf31d2332cd88b2a7e10e4",
    "cbc14ce21dfdabfb14657e14823f19db22e31a6a63bc9136ec949dd868c6094e",
    "fd2e5bcb4de52dce98b476e54fc8538f291058ecfbb9f832ab4d2e5113690581",
)


def generation_body(*, content=None, finish="STOP", model="gemini-3.8-flash",
                    usage=None):
    if content is None:
        content = {"conclusion": "Cautious fixture inference"}
    if usage is None:
        usage = {"promptTokenCount": 32, "candidatesTokenCount": 18,
                 "thoughtsTokenCount": 7, "totalTokenCount": 50}
    return json.dumps({
        "modelVersion": model,
        "usageMetadata": usage,
        "candidates": [{"finishReason": finish,
                        "content": {"parts": [{"text": json.dumps(content)}]}}],
    }, sort_keys=True).encode()


class ScriptedTransport:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.requests = []

    def __call__(self, request):
        self.requests.append(request)
        if not self.responses:
            raise AssertionError("unexpected provider dispatch")
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        return response


def ok(body):
    return HttpResponse(200, body)


def journal(db, count, generate, *, session="session_a", identity=IDENTITY,
            call_cap=29, exposure_cap=2_500_000, sleep=lambda _: None,
            rng=lambda: 0.5):
    executor = EffectExecutor(str(db), call_cap=call_cap,
                              exposure_cap=exposure_cap, sleep=lambda _: None)
    bridge = VertexJournal(
        executor, count, generate, session_id=session, identity=identity,
        endpoint_count="countTokens",
        endpoint_generate="gemini-3.8-flash@global",
        sleep=sleep, rng=rng,
    )
    return executor, bridge


def records(db):
    with sqlite3.connect(db) as conn:
        return conn.execute(
            "SELECT operation_id, branch, request, state, attempts, response_status, "
            "raw_response, parse_status FROM operations ORDER BY rowid"
        ).fetchall()


def call(bridge):
    return bridge("inference", INPUT)


def test_count_and_generation_are_separate_durable_raw_200_effects(tmp_path):
    db = tmp_path / "effects.sqlite3"
    count = ScriptedTransport(ok(COUNT_OK))
    raw_generation = generation_body()
    generate = ScriptedTransport(ok(raw_generation))
    executor, bridge = journal(db, count, generate)
    try:
        assert call(bridge) == {"conclusion": "Cautious fixture inference"}
        assert len(count.requests) == len(generate.requests) == 1
        assert count.requests[0] == generate.requests[0]
        assert len(records(db)) == 2
        assert [row[6] for row in records(db)] == [COUNT_OK, raw_generation]
        assert [row[4] for row in records(db)] == [1, 1]
        assert all(row[3] == "succeeded" and row[5] == 200 for row in records(db))
        assert executor.accounting()["calls"] == 2
    finally:
        executor.close()


@pytest.mark.parametrize("limited_stage", ["count", "generation"])
def test_captured_429_has_one_exact_retry_with_same_body(tmp_path, limited_stage):
    db = tmp_path / "effects.sqlite3"
    busy = HttpResponse(429, RATE_LIMIT)
    count = ScriptedTransport(*( [busy, ok(COUNT_OK)] if limited_stage == "count" else [ok(COUNT_OK)]))
    generate = ScriptedTransport(*( [busy, ok(generation_body())] if limited_stage == "generation"
                                    else [ok(generation_body())]))
    delays = []
    executor, bridge = journal(db, count, generate, sleep=delays.append)
    try:
        assert call(bridge)["conclusion"] == "Cautious fixture inference"
        retried = count if limited_stage == "count" else generate
        assert retried.requests == [retried.requests[0], retried.requests[0]]
        assert len(records(db)) == 3
        assert [row[4] for row in records(db)] == [1, 1, 1]
        assert [row[5] for row in records(db)].count(429) == 1
        assert delays == [2.5]
        assert executor.accounting()["calls"] == 3
        accounting = bridge.accounting()
        assert accounting["http_429_attempts"] == 1
        assert accounting[f"{limited_stage}_attempts"] == 2
    finally:
        executor.close()


@pytest.mark.parametrize("uncertain_stage", ["count", "generation"])
def test_uncertain_effect_keeps_reservation_and_never_repeats_after_restart(
        tmp_path, uncertain_stage):
    db = tmp_path / "effects.sqlite3"
    count = ScriptedTransport(*( [TimeoutError("offline fixture timeout")] if uncertain_stage == "count"
                                 else [ok(COUNT_OK)]))
    generate = ScriptedTransport(*( [TimeoutError("offline fixture timeout")]
                                    if uncertain_stage == "generation" else []))
    executor, bridge = journal(db, count, generate)
    try:
        with pytest.raises(JournaledCallError) as first:
            call(bridge)
        assert first.value.kind == "uncertain"
        before = executor.accounting()
        assert before["calls"] == (1 if uncertain_stage == "count" else 2)
        assert any(row[3] == "uncertain" for row in records(db))
        assert first.value.receipt["kind"] == uncertain_stage
        assert first.value.receipt["state"] == "uncertain"
        assert first.value.receipt["attempts"][-1]["state"] == "uncertain"
        if uncertain_stage == "generation":
            assert bridge.accounting()["reserved_micro_usd"] == 520_000
    finally:
        executor.close()

    forbidden_count = ScriptedTransport()
    forbidden_generate = ScriptedTransport()
    executor, bridge = journal(db, forbidden_count, forbidden_generate)
    try:
        with pytest.raises(JournaledCallError) as resumed:
            call(bridge)
        assert resumed.value.kind == "uncertain"
        assert not forbidden_count.requests and not forbidden_generate.requests
        assert executor.accounting() == before
    finally:
        executor.close()


@pytest.mark.parametrize("raw", [b"{broken", b'"not an object"'])
def test_malformed_generation_200_is_saved_and_never_retried(tmp_path, raw):
    db = tmp_path / "effects.sqlite3"
    count = ScriptedTransport(ok(COUNT_OK))
    generate = ScriptedTransport(ok(raw))
    executor, bridge = journal(db, count, generate)
    try:
        with pytest.raises(JournaledCallError):
            call(bridge)
        assert len(generate.requests) == 1
        assert records(db)[1][6] == raw
        assert executor.accounting()["calls"] == 2
    finally:
        executor.close()


def test_max_tokens_preserves_raw_response_and_usage(tmp_path):
    db = tmp_path / "effects.sqlite3"
    usage = {"promptTokenCount": 32, "candidatesTokenCount": 18,
             "thoughtsTokenCount": 7, "totalTokenCount": 50}
    raw = generation_body(content={"partial": True}, finish="MAX_TOKENS", usage=usage)
    executor, bridge = journal(db, ScriptedTransport(ok(COUNT_OK)),
                               ScriptedTransport(ok(raw)))
    try:
        with pytest.raises(JournaledCallError) as error:
            call(bridge)
        saved = records(db)[1][6]
        assert saved == raw
        parsed = json.loads(saved)
        assert parsed["candidates"][0]["finishReason"] == "MAX_TOKENS"
        assert parsed["usageMetadata"] == usage
        assert error.value.receipt["attempts"][-1]["finish_reason"] == "MAX_TOKENS"
        assert error.value.receipt["attempts"][-1]["usage_metadata"] == usage
        assert executor.accounting()["calls"] == 2
    finally:
        executor.close()


@pytest.mark.parametrize("raw", [
    generation_body(model="gemini-3.5-flash"),
    generation_body(usage={"promptTokenCount": "32", "totalTokenCount": 50}),
    generation_body(usage={"promptTokenCount": 32, "totalTokenCount": 30}),
])
def test_model_and_usage_mismatches_fail_closed(tmp_path, raw):
    db = tmp_path / "effects.sqlite3"
    generate = ScriptedTransport(ok(raw))
    executor, bridge = journal(db, ScriptedTransport(ok(COUNT_OK)), generate)
    try:
        with pytest.raises(JournaledCallError):
            call(bridge)
        assert len(generate.requests) == 1
        assert records(db)[1][6] == raw
    finally:
        executor.close()


@pytest.mark.parametrize("observed_model", [
    "gemini-3.8-flash-cyber",
    "gemini-3.8-flash-exp",
    "gemini-3.8-flash-001",
    "gemini-3.5-flash",
])
def test_foreign_model_200_keeps_full_reserve_and_halts_without_retry(
        tmp_path, observed_model):
    db = tmp_path / "effects.sqlite3"
    raw = generation_body(model=observed_model)
    count = ScriptedTransport(ok(COUNT_OK))
    generate = ScriptedTransport(ok(raw))
    executor, bridge = journal(db, count, generate)
    try:
        with pytest.raises(JournaledCallError) as error:
            call(bridge)
        assert error.value.kind == "parse_error"
        receipt = error.value.receipt
        assert receipt["kind"] == "generation"
        assert receipt["attempts"][-1]["observed_model"] == observed_model
        assert receipt["attempts"][-1]["usage_metadata"] == {
            "promptTokenCount": 32, "candidatesTokenCount": 18,
            "thoughtsTokenCount": 7, "totalTokenCount": 50,
        }
        assert records(db)[1][6] == raw
        assert len(count.requests) == len(generate.requests) == 1
        summary = bridge.accounting()
        assert summary["generation_attempts"] == 1
        assert summary["settled_micro_usd"] == 0
        assert summary["reserved_micro_usd"] == 520_000
        assert summary["committed_micro_usd"] == 520_000
        assert summary["halted"] is not None
    finally:
        executor.close()
    forbidden_count = ScriptedTransport()
    forbidden_generate = ScriptedTransport()
    executor, bridge = journal(db, forbidden_count, forbidden_generate)
    try:
        with pytest.raises(JournaledCallError):
            call(bridge)
        assert not forbidden_count.requests and not forbidden_generate.requests
        assert bridge.accounting()["reserved_micro_usd"] == 520_000
    finally:
        executor.close()


def test_reused_session_cannot_rebind_same_role_to_different_identity_or_input(tmp_path):
    db = tmp_path / "effects.sqlite3"
    executor, bridge = journal(db, ScriptedTransport(ok(COUNT_OK)),
                               ScriptedTransport(ok(generation_body())))
    try:
        assert call(bridge)["conclusion"]
        before = executor.accounting()
    finally:
        executor.close()
    forbidden_count = ScriptedTransport()
    forbidden_generate = ScriptedTransport()
    with pytest.raises(VertexJournalError, match="identity|contract|model"):
        executor, changed = journal(db, forbidden_count, forbidden_generate,
                                    identity={**IDENTITY, "run": "other-run"})
    executor, changed = journal(db, forbidden_count, forbidden_generate)
    try:
        with pytest.raises((JournaledCallError, ValueError)):
            changed("inference", {"selected_texts": [{"id": "other", "text": "Different"}]})
        assert executor.accounting() == before
        assert not forbidden_count.requests and not forbidden_generate.requests
    finally:
        executor.close()


def test_count_request_binding_corruption_blocks_generation_on_restart(tmp_path):
    db = tmp_path / "effects.sqlite3"
    executor, bridge = journal(db, ScriptedTransport(ok(COUNT_OK)),
                               ScriptedTransport(ok(generation_body())))
    try:
        assert call(bridge)["conclusion"]
        before = executor.accounting()
    finally:
        executor.close()
    with sqlite3.connect(db) as conn:
        conn.execute("UPDATE vertex_attempts SET request_sha256=? WHERE kind='count'",
                     ("0" * 64,))
    forbidden_count = ScriptedTransport()
    forbidden_generate = ScriptedTransport()
    executor, bridge = journal(db, forbidden_count, forbidden_generate)
    try:
        with pytest.raises(JournaledCallError) as error:
            call(bridge)
        assert error.value.kind == "journal_error"
        assert not forbidden_count.requests and not forbidden_generate.requests
        assert executor.accounting() == before
    finally:
        executor.close()


@pytest.mark.parametrize("forbidden_hash", FORBIDDEN_WIRE_HASHES)
def test_historical_uncertain_wire_hash_blocks_before_any_registration_or_dispatch(
        tmp_path, monkeypatch, forbidden_hash):
    db = tmp_path / "effects.sqlite3"
    count = ScriptedTransport()
    generate = ScriptedTransport()
    executor, bridge = journal(db, count, generate)
    original_sha = vertex_journal_module._sha

    def historical_wire_sha(raw):
        if raw.startswith(b'{"contents"'):
            return forbidden_hash
        return original_sha(raw)

    monkeypatch.setattr(vertex_journal_module, "_sha", historical_wire_sha)
    try:
        contract = json.loads(bridge._contract)
        assert contract["predecessor"]["forbidden_request_hashes"] == sorted(
            FORBIDDEN_WIRE_HASHES)
        with pytest.raises(JournaledCallError):
            call(bridge)
        assert not count.requests and not generate.requests
        assert executor.accounting()["calls"] == 0
        assert bridge.accounting()["count_attempts"] == 0
        assert bridge.accounting()["generation_attempts"] == 0
        assert bridge.accounting()["halted"] is not None
        with sqlite3.connect(db) as conn:
            for table in ("vertex_calls", "vertex_attempts", "operations", "attempts"):
                assert conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0
    finally:
        executor.close()


@pytest.mark.parametrize("raw", [b"{bad", b"{}", b'{"totalTokens":true}',
                                  b'{"totalTokens":32,"totalTokens":33}'])
def test_bad_count_schema_saves_raw_200_and_blocks_generation(tmp_path, raw):
    db = tmp_path / "effects.sqlite3"
    count = ScriptedTransport(ok(raw))
    generate = ScriptedTransport()
    executor, bridge = journal(db, count, generate)
    try:
        with pytest.raises(JournaledCallError) as error:
            call(bridge)
        assert error.value.kind == "parse_error"
        assert error.value.receipt["kind"] == "count"
        assert not generate.requests
        assert records(db)[0][6] == raw
        assert bridge.accounting()["count_attempts"] == 1
        assert bridge.accounting()["generation_attempts"] == 0
    finally:
        executor.close()


def test_input_count_above_8192_blocks_generation(tmp_path):
    db = tmp_path / "effects.sqlite3"
    generate = ScriptedTransport()
    executor, bridge = journal(db, ScriptedTransport(ok(b'{"totalTokens":8193}')),
                               generate)
    try:
        with pytest.raises(JournaledCallError) as error:
            call(bridge)
        assert error.value.kind == "parse_error"
        assert error.value.receipt["attempts"][-1]["count_tokens"] == 8193
        assert not generate.requests
        assert bridge.accounting()["generation_attempts"] == 0
    finally:
        executor.close()


def test_accounting_sums_settled_usage_and_uncertain_reservation(tmp_path):
    db = tmp_path / "effects.sqlite3"
    count = ScriptedTransport(ok(COUNT_OK), ok(COUNT_OK))
    generate = ScriptedTransport(ok(generation_body()), TimeoutError("offline timeout"))
    executor, bridge = journal(db, count, generate)
    try:
        assert call(bridge)["conclusion"]
        with pytest.raises(JournaledCallError) as error:
            call(bridge)
        assert error.value.kind == "uncertain"
        summary = bridge.accounting()
        expected_settlement = (32 * 3 + 18 * 15 + 3) // 4
        assert summary["count_attempts"] == 2
        assert summary["generation_attempts"] == 2
        assert summary["count_attempt_cap"] == 14
        assert summary["generation_attempt_cap"] == 14
        assert summary["settled_micro_usd"] == expected_settlement
        assert summary["reserved_micro_usd"] == 520_000
        assert summary["committed_micro_usd"] == expected_settlement + 520_000
        assert summary["incremental_cap_micro_usd"] == 2_500_000
        assert summary["remaining_micro_usd"] == 2_500_000 - summary["committed_micro_usd"]
        assert summary["prior_micro_usd"] == 56_922_170
        assert summary["total_estimated_or_reserved_micro_usd"] == (
            summary["prior_micro_usd"] + summary["committed_micro_usd"])
    finally:
        executor.close()


def test_completed_429_chain_replays_after_restart_without_dispatch(tmp_path):
    db = tmp_path / "effects.sqlite3"
    count = ScriptedTransport(HttpResponse(429, RATE_LIMIT), ok(COUNT_OK))
    generate = ScriptedTransport(ok(generation_body()))
    executor, bridge = journal(db, count, generate)
    try:
        first = call(bridge)
        before = bridge.accounting()
    finally:
        executor.close()
    forbidden_count = ScriptedTransport()
    forbidden_generate = ScriptedTransport()
    executor, bridge = journal(db, forbidden_count, forbidden_generate)
    try:
        assert call(bridge) == first
        assert not forbidden_count.requests and not forbidden_generate.requests
        assert bridge.accounting() == before
    finally:
        executor.close()


def test_unconfirmed_429_and_second_confirmed_429_do_not_dispatch_again(tmp_path):
    for name, count_responses, expected_calls in (
        ("unconfirmed", [HttpResponse(429, b'{"error":{"code":429,"status":"OTHER"}}')], 1),
        ("exhausted", [HttpResponse(429, RATE_LIMIT), HttpResponse(429, RATE_LIMIT)], 2),
    ):
        db = tmp_path / f"{name}.sqlite3"
        count = ScriptedTransport(*count_responses)
        generate = ScriptedTransport()
        executor, bridge = journal(db, count, generate)
        try:
            with pytest.raises(JournaledCallError) as error:
                call(bridge)
            assert error.value.kind == "failed"
            assert len(count.requests) == expected_calls
            assert not generate.requests
            assert bridge.accounting()["count_attempts"] == expected_calls
        finally:
            executor.close()


def test_14_attempt_caps_block_fifteenth_role_before_transport(tmp_path):
    db = tmp_path / "effects.sqlite3"
    count = ScriptedTransport(*[ok(COUNT_OK) for _ in range(14)])
    generate = ScriptedTransport(*[ok(generation_body()) for _ in range(14)])
    executor, bridge = journal(db, count, generate)
    try:
        for _ in range(14):
            assert call(bridge)["conclusion"]
        with pytest.raises(JournaledCallError) as error:
            call(bridge)
        assert error.value.kind == "journal_error"
        assert len(count.requests) == len(generate.requests) == 14
        assert bridge.accounting()["count_attempts"] == 14
        assert bridge.accounting()["generation_attempts"] == 14
        assert executor.accounting()["calls"] == 28
    finally:
        executor.close()


def test_generation_uncertainty_reaches_engine_as_generation_receipt(tmp_path):
    from faithful_v3.engine import StrictEngine
    from reasoning_engine.engine import EngineConfig

    db = tmp_path / "effects.sqlite3"
    executor, bridge = journal(db, ScriptedTransport(ok(COUNT_OK)),
                               ScriptedTransport(TimeoutError("offline timeout")))
    task = {
        "case_id": "fixture", "question": "What follows?", "task_type": "exploration",
        "evidence": [{"id": "s1", "kind": "observation", "source": "saved",
                      "text": "Saved premise A"}],
        "required_questions": [{"id": "q1", "question": "What follows?",
                                "evidence_ids": []}],
    }
    try:
        outcome = StrictEngine(bridge, EngineConfig(max_calls=5)).run(task)
        assert outcome["status"] == "unknown"
        receipt = outcome["unknown_explanation"]["effect_receipt"]
        assert receipt["kind"] == "generation"
        assert receipt["state"] == "uncertain"
        assert receipt["attempts"][-1]["state"] == "uncertain"
        assert bridge.accounting()["count_attempts"] == 1
        assert bridge.accounting()["generation_attempts"] == 1
    finally:
        executor.close()


def test_receipt_omits_payload_and_journal_file_is_private(tmp_path):
    db = tmp_path / "effects.sqlite3"
    executor, bridge = journal(db, ScriptedTransport(ok(COUNT_OK)),
                               ScriptedTransport(ok(generation_body())))
    try:
        assert call(bridge)["conclusion"]
        receipt = bridge.last_receipt
        encoded = json.dumps(receipt)
        assert "Saved premise A" not in encoded
        assert "Cautious fixture inference" not in encoded
        assert "request" not in receipt and "response" not in receipt
        assert os.stat(db).st_mode & 0o077 == 0
    finally:
        executor.close()
    invalid_executor = EffectExecutor(str(tmp_path / "credentials.sqlite3"),
                                      call_cap=29, exposure_cap=2_500_000)
    try:
        with pytest.raises(ValueError, match="credential"):
            VertexJournal(invalid_executor, ScriptedTransport(), ScriptedTransport(),
                          session_id="session_a", identity={"api_key": "fixture-only"})
    finally:
        invalid_executor.close()


def test_inference_wire_request_contains_only_selected_premises(tmp_path):
    db = tmp_path / "effects.sqlite3"
    count = ScriptedTransport(ok(COUNT_OK))
    generate = ScriptedTransport(ok(generation_body()))
    executor, bridge = journal(db, count, generate)
    try:
        assert call(bridge)["conclusion"]
        wire = json.loads(generate.requests[0])
        role = json.loads(wire["contents"][0]["parts"][0]["text"])
        assert role["stage"] == "inference"
        assert role["input"] == INPUT
        assert set(role["input"]) == {"selected_texts"}
        assert b"USER_TARGET_SENTINEL" not in generate.requests[0]
    finally:
        executor.close()
