"""Offline, pinned roll-forward checks for the third authorized Vertex phase run."""
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


def _first_binding():
    return {
        "prior_micro_usd": 56_926_158,
        "incremental_cap_micro_usd": 2_496_012,
        "generation_reserve_micro_usd": 520_000,
        "count_attempt_cap": 8,
        "generation_attempt_cap": 8,
        "predecessor_checkpoint_sha256": vertex.SUCCESSOR_CHECKPOINT_SHA256,
        "predecessor_ledger_sha256": vertex.FIRST_SUCCESSOR_LEDGER_SHA256,
        "original_prior_micro_usd": 56_922_170,
        "original_incremental_cap_micro_usd": 2_500_000,
        "original_count_attempt_cap": 14,
        "original_generation_attempt_cap": 14,
        "carried_committed_micro_usd": 3988,
        "carried_count_attempts": 6,
        "carried_generation_attempts": 6,
    }


def _repin(checkpoint, monkeypatch):
    data = json.loads(checkpoint.read_bytes())
    data["ledger_sha256"] = _sha((checkpoint.parent / "effects.sqlite3").read_bytes())
    for key, name in (("contract_sha256", "contract.json"),
                      ("challenge_sha256", "challenge_packet_v0001.json"),
                      ("outcome_sha256", "outcome.json"),
                      ("summary_sha256", "summary.json")):
        data[key] = _sha((checkpoint.parent / name).read_bytes())
    checkpoint.write_bytes(_json(data))
    monkeypatch.setattr(vertex, "SECOND_SUCCESSOR_CHECKPOINT_SHA256",
                        _sha(checkpoint.read_bytes()))
    monkeypatch.setattr(vertex, "SECOND_SUCCESSOR_LEDGER_SHA256", data["ledger_sha256"])


def _second_predecessor(tmp_path, monkeypatch):
    old = tmp_path / "second"
    old.mkdir()
    contract = {
        "schema": "vertex-halter-successor-v1",
        "original_incremental_cap_micro_usd": 2_500_000,
        "original_phase_count_cap": 14,
        "original_phase_generation_cap": 14,
        "prior_total_exposure_micro_usd": 56_926_158,
        "prior_count_attempts": 1554,
        "prior_generation_attempts": 1632,
        "new_incremental_cap_micro_usd": 2_496_012,
        "count_attempt_cap": 8,
        "generation_attempt_cap": 8,
        "generation_reserve_micro_usd": 520_000,
        "previous_accounting_sha256": vertex.SUCCESSOR_CHECKPOINT_SHA256,
        "previous_ledger_sha256": vertex.FIRST_SUCCESSOR_LEDGER_SHA256,
        "uncertain_retry": False,
        "predecessor_budget_binding": _first_binding(),
    }
    summary = {"accounting": {
        "committed_micro_usd": 1732, "settled_micro_usd": 1732,
        "reserved_micro_usd": 0, "generation_attempts": 2,
        "count_attempts": 2, "uncertain_attempts": 0,
        "http_429_attempts": 0, "halted": None,
        "cumulative_phase_committed_micro_usd": 5720,
        "cumulative_phase_generation_attempts": 8,
        "cumulative_phase_count_attempts": 8,
        "total_estimated_or_reserved_micro_usd": 56_927_890,
        "remaining_micro_usd": 2_494_280,
    }}
    for name, raw in (("contract.json", _json(contract)),
                      ("summary.json", _json(summary)),
                      ("challenge_packet_v0001.json", b"{}"),
                      ("outcome.json", b"{}")):
        (old / name).write_bytes(raw)
    db_path = old / "effects.sqlite3"
    db = sqlite3.connect(db_path)
    db.execute("CREATE TABLE vertex_run (singleton INTEGER PRIMARY KEY, halted TEXT, contract BLOB)")
    journal_contract = {
        "prior_micro_usd": 56_926_158,
        "incremental_cap_micro_usd": 2_496_012,
        "generation_reserve_micro_usd": 520_000,
        "count_attempt_cap": 8,
        "generation_attempt_cap": 8,
        "successor_budget": {key: value for key, value in _first_binding().items()
                             if key not in ("prior_micro_usd", "incremental_cap_micro_usd",
                                            "generation_reserve_micro_usd", "count_attempt_cap",
                                            "generation_attempt_cap")},
    }
    db.execute("INSERT INTO vertex_run VALUES(1,NULL,?)", (_json(journal_contract),))
    db.execute("""CREATE TABLE vertex_attempts
        (kind TEXT,attempt_no INTEGER,state TEXT,http_status INTEGER,
         reserved_micro_usd INTEGER,settled_micro_usd INTEGER)""")
    db.executemany("INSERT INTO vertex_attempts VALUES(?,?,?,?,?,?)", [
        ("count", 0, "http_200", 200, 0, 0),
        ("generation", 0, "http_200", 200, 520_000, 694),
        ("count", 0, "http_200", 200, 0, 0),
        ("generation", 0, "http_200", 200, 520_000, 1038),
    ])
    db.commit()
    db.close()
    checkpoint = {
        "schema": "vertex_halter_successor_accounting_checkpoint_v1",
        "prior_exposure_micro_usd": 56_926_158,
        "prior_generation_attempts": 1632, "prior_count_attempts": 1554,
        "new_estimated_micro_usd": 1732,
        "new_unsettled_reservation_micro_usd": 0,
        "new_generation_attempts": 2, "new_count_attempts": 2,
        "cumulative_phase_committed_micro_usd": 5720,
        "cumulative_phase_generation_attempts": 8,
        "cumulative_phase_count_attempts": 8,
        "total_exposure_micro_usd": 56_927_890,
        "total_generation_attempts": 1634,
        "total_count_attempts": 1556,
        "invoice_status": "not_reconciled",
    }
    path = old / "accounting-checkpoint.json"
    path.write_bytes(_json(checkpoint))
    _repin(path, monkeypatch)
    return path


def _count(_raw):
    return HttpResponse(200, b'{"totalTokens":32}')


def _generation(_raw):
    body = {"modelVersion": "gemini-3.8-flash",
            "usageMetadata": {"promptTokenCount": 32, "totalTokenCount": 50},
            "candidates": [{"finishReason": "STOP", "content": {
                "parts": [{"text": '{"conclusion":"ok"}'}]}}]}
    return HttpResponse(200, _json(body))


def _journal(tmp_path, budget, count=_count):
    path = tmp_path / "third" / "effects.sqlite3"
    path.parent.mkdir()
    executor = EffectExecutor(str(path), exposure_cap=0, call_cap=16)
    callback = vertex.VertexJournal(
        executor, count, _generation, session_id="third",
        identity={"checkpoint_sha256": budget.as_contract()["predecessor_checkpoint_sha256"]},
        budget=budget, sleep=lambda _: None)
    return executor, callback


def test_second_successor_carries_exact_remaining_authority(tmp_path, monkeypatch):
    checkpoint = _second_predecessor(tmp_path, monkeypatch)
    budget = vertex.VertexBudget.second_successor(checkpoint)
    values = budget.as_contract()
    assert values["prior_micro_usd"] == 56_927_890
    assert values["incremental_cap_micro_usd"] == 2_494_280
    assert values["count_attempt_cap"] == values["generation_attempt_cap"] == 6
    assert values["generation_reserve_micro_usd"] == 520_000
    assert values["carried_committed_micro_usd"] == 5720
    assert values["carried_count_attempts"] == values["carried_generation_attempts"] == 8
    executor, callback = _journal(tmp_path, budget)
    try:
        for _ in range(6):
            assert callback("inference", {"selected_texts": [{"id": "p", "text": "saved"}]}) == {"conclusion": "ok"}
        accounting = callback.accounting()
        assert accounting["cumulative_phase_count_attempts"] == 14
        assert accounting["cumulative_phase_generation_attempts"] == 14
        assert accounting["cumulative_phase_committed_micro_usd"] == 5720 + accounting["committed_micro_usd"]
        assert accounting["total_estimated_or_reserved_micro_usd"] <= 59_422_170
        with pytest.raises(JournaledCallError):
            callback("inference", {"selected_texts": [{"id": "p", "text": "saved"}]})
        assert callback.accounting()["count_attempts"] == 6
    finally:
        executor.close()


def test_second_successor_revalidates_before_dispatch(tmp_path, monkeypatch):
    checkpoint = _second_predecessor(tmp_path, monkeypatch)
    budget = vertex.VertexBudget.second_successor(checkpoint)
    calls = []
    executor, callback = _journal(tmp_path, budget,
                                  lambda raw: calls.append(raw) or _count(raw))
    try:
        (checkpoint.parent / "summary.json").write_bytes(b"{}")
        with pytest.raises(JournaledCallError):
            callback("inference", {"selected_texts": [{"id": "p", "text": "saved"}]})
        assert calls == []
    finally:
        executor.close()


def test_second_successor_rejects_raw_checkpoint_and_ledger_tamper(tmp_path, monkeypatch):
    checkpoint = _second_predecessor(tmp_path, monkeypatch)
    checkpoint.write_bytes(checkpoint.read_bytes() + b" ")
    with pytest.raises(vertex.VertexJournalError, match="checkpoint bytes changed"):
        vertex.VertexBudget.second_successor(checkpoint)
    _repin(checkpoint, monkeypatch)
    ledger = checkpoint.parent / "effects.sqlite3"
    ledger.write_bytes(ledger.read_bytes() + b" ")
    with pytest.raises(vertex.VertexJournalError, match="artifact binding changed"):
        vertex.VertexBudget.second_successor(checkpoint)


def test_second_successor_rejects_rebound_first_link_and_retry(tmp_path, monkeypatch):
    checkpoint = _second_predecessor(tmp_path, monkeypatch)
    contract_path = checkpoint.parent / "contract.json"
    contract = json.loads(contract_path.read_bytes())
    contract["predecessor_budget_binding"]["carried_count_attempts"] = 5
    contract_path.write_bytes(_json(contract))
    _repin(checkpoint, monkeypatch)
    with pytest.raises(vertex.VertexJournalError, match="first predecessor linkage changed"):
        vertex.VertexBudget.second_successor(checkpoint)
    contract["predecessor_budget_binding"]["carried_count_attempts"] = 6
    contract_path.write_bytes(_json(contract))
    db_path = checkpoint.parent / "effects.sqlite3"
    db = sqlite3.connect(db_path)
    db.execute("UPDATE vertex_attempts SET attempt_no=1 WHERE rowid=1")
    db.commit()
    db.close()
    _repin(checkpoint, monkeypatch)
    with pytest.raises(vertex.VertexJournalError, match="journal accounting changed"):
        vertex.VertexBudget.second_successor(checkpoint)
