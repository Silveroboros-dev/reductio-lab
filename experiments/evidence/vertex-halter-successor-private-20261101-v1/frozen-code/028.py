"""Offline checks that a successor carries the predecessor's consumed authority."""
from __future__ import annotations

import hashlib
import json
import sqlite3

import pytest

from reasoning_engine.executor import EffectExecutor, HttpResponse
from reasoning_engine.journal_callback import JournaledCallError
import reasoning_engine.vertex_journal as vertex


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _predecessor(tmp_path, monkeypatch):
    old = tmp_path / "old"
    old.mkdir()
    contract = {
        "incremental_cap_micro_usd": 2_500_000,
        "prior_exposure_micro_usd": 56_922_170,
        "generation_attempt_cap": 14,
        "count_attempt_cap": 14,
        "generation_reserve_micro_usd": 520_000,
    }
    summary = {"accounting": {
        "committed_micro_usd": 3988, "generation_attempts": 6,
        "count_attempts": 6, "reserved_micro_usd": 0,
        "halted": None, "uncertain_attempts": 0,
    }}
    artifacts = {"contract.json": _json(contract), "summary.json": _json(summary),
                 "challenge_packet_v0001.json": b"{}", "outcome.json": b"{}"}
    for name, raw in artifacts.items():
        (old / name).write_bytes(raw)
    db_path = old / "effects.sqlite3"
    db = sqlite3.connect(db_path)
    db.execute("CREATE TABLE vertex_run (singleton INTEGER PRIMARY KEY, halted TEXT)")
    db.execute("INSERT INTO vertex_run VALUES(1,NULL)")
    db.execute("""CREATE TABLE vertex_attempts
        (kind TEXT,state TEXT,http_status INTEGER,reserved_micro_usd INTEGER,
         settled_micro_usd INTEGER)""")
    db.executemany("INSERT INTO vertex_attempts VALUES(?,?,?,?,?)",
                   [("count", "http_200", 200, 0, 0)] * 6 +
                   [("generation", "http_200", 200, 520_000, cost)
                    for cost in (740, 694, 870, 417, 403, 864)])
    db.commit()
    db.close()
    checkpoint = {
        "schema": "vertex_compatibility_accounting_checkpoint_v1",
        "prior_exposure_micro_usd": 56_922_170,
        "prior_generation_attempts": 1626, "prior_count_attempts": 1548,
        "new_estimated_micro_usd": 3988, "new_unsettled_reservation_micro_usd": 0,
        "new_generation_attempts": 6, "new_count_attempts": 6,
        "total_exposure_micro_usd": 56_926_158,
        "total_generation_attempts": 1632, "total_count_attempts": 1554,
        "invoice_status": "not_reconciled",
        "contract_sha256": _sha(artifacts["contract.json"]),
        "challenge_sha256": _sha(artifacts["challenge_packet_v0001.json"]),
        "outcome_sha256": _sha(artifacts["outcome.json"]),
        "summary_sha256": _sha(artifacts["summary.json"]),
        "ledger_sha256": _sha(db_path.read_bytes()),
    }
    checkpoint_path = old / "accounting-checkpoint.json"
    checkpoint_path.write_bytes(_json(checkpoint))
    monkeypatch.setattr(vertex, "SUCCESSOR_CHECKPOINT_SHA256", _sha(checkpoint_path.read_bytes()))
    return checkpoint_path


def _journal(tmp_path, budget, count, generation):
    path = tmp_path / "successor" / "effects.sqlite3"
    path.parent.mkdir()
    executor = EffectExecutor(str(path), exposure_cap=0, call_cap=16)
    callback = vertex.VertexJournal(
        executor, count, generation, session_id="successor",
        identity={"checkpoint_sha256": budget.as_contract()["predecessor_checkpoint_sha256"]},
        budget=budget, sleep=lambda _: None,
    )
    return executor, callback


def _count(_raw):
    return HttpResponse(200, b'{"totalTokens":32}')


def _generation(_raw):
    body = {"modelVersion": "gemini-3.8-flash",
            "usageMetadata": {"promptTokenCount": 32, "totalTokenCount": 50},
            "candidates": [{"finishReason": "STOP", "content": {
                "parts": [{"text": '{"conclusion":"ok"}'}]}}]}
    return HttpResponse(200, _json(body))


def test_successor_carries_budget_and_attempt_caps(tmp_path, monkeypatch):
    checkpoint = _predecessor(tmp_path, monkeypatch)
    budget = vertex.VertexBudget.successor(checkpoint)
    assert budget.as_contract()["prior_micro_usd"] == 56_926_158
    assert budget.as_contract()["incremental_cap_micro_usd"] == 2_496_012
    assert budget.as_contract()["count_attempt_cap"] == 8
    assert budget.as_contract()["generation_attempt_cap"] == 8
    executor, callback = _journal(tmp_path, budget, _count, _generation)
    try:
        for _ in range(8):
            assert callback("inference", {"selected_texts": [{"id": "p", "text": "saved"}]}) == {"conclusion": "ok"}
        accounting = callback.accounting()
        assert accounting["count_attempts"] == accounting["generation_attempts"] == 8
        assert accounting["cumulative_phase_count_attempts"] == 14
        assert accounting["cumulative_phase_generation_attempts"] == 14
        assert accounting["total_estimated_or_reserved_micro_usd"] <= 59_422_170
        assert budget.as_contract()["predecessor_checkpoint_sha256"] in callback._contract.decode()
        with pytest.raises(JournaledCallError):
            callback("inference", {"selected_texts": [{"id": "p", "text": "saved"}]})
        assert callback.accounting()["count_attempts"] == 8
    finally:
        executor.close()


def test_predecessor_tamper_blocks_successor_before_dispatch(tmp_path, monkeypatch):
    checkpoint = _predecessor(tmp_path, monkeypatch)
    budget = vertex.VertexBudget.successor(checkpoint)
    calls = []
    executor, callback = _journal(tmp_path, budget,
                                  lambda raw: calls.append(raw) or _count(raw), _generation)
    try:
        (checkpoint.parent / "summary.json").write_bytes(b"{}")
        with pytest.raises(JournaledCallError):
            callback("inference", {"selected_texts": [{"id": "p", "text": "saved"}]})
        assert calls == []
    finally:
        executor.close()


def test_successor_rejects_changed_checkpoint(tmp_path, monkeypatch):
    checkpoint = _predecessor(tmp_path, monkeypatch)
    checkpoint.write_bytes(checkpoint.read_bytes() + b" ")
    with pytest.raises(vertex.VertexJournalError, match="checkpoint bytes changed"):
        vertex.VertexBudget.successor(checkpoint)
