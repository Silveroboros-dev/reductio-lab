"""Durable, single-runner Vertex bridge for a bounded live canary.

The two supplied transports each accept one frozen wire body and return one
HttpResponse. They must disable SDK/HTTP retries. This module has no network
client, credentials, or authority to start a canary by itself. The caller owns
the run identity and the endpoint-bound transports.

EffectExecutor records every raw HTTP response before this module parses it.
Its built-in 429 retry is deliberately disabled: it checks only the status,
whereas this canary requires a captured 429/RESOURCE_EXHAUSTED body. A retry
is a separate registered operation with exactly the predecessor's request.

The $0.52 per-generation reservation is an accepted local risk bound, not a
provider-enforced maximum bill. Usage-derived dollars are estimates, not a
billing statement. One process/worker must own the SQLite journal at a time.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
import random
import re
import sqlite3
import time
from typing import Any, Callable

from faithful_v3.prompts import build_request
from reasoning_engine.executor import EffectExecutor, EffectResult, HttpResponse, RetryPolicy
from reasoning_engine.journal_callback import JournaledCallback, JournaledCallError
from reasoning_engine.vertex_adapter import (
    MODEL, MAX_OUTPUT_TOKENS, AdapterError, build_generation_request,
    canonical_json,
)

PRIOR_MICRO_USD = 56_922_170
INCREMENTAL_CAP_MICRO_USD = 2_500_000
GENERATION_RESERVE_MICRO_USD = 520_000
MAX_COUNT_ATTEMPTS = 14
MAX_GENERATION_ATTEMPTS = 14
MAX_INPUT_TOKENS = 8192
COUNT_ENDPOINT = "countTokens"
GENERATION_ENDPOINT = "gemini-3.8-flash@global"
FORBIDDEN_REQUEST_SHA256 = frozenset({
    "17a148b5aeade7252bf07660e16d3c6ffbb4da639aaf31d2332cd88b2a7e10e4",
    "cbc14ce21dfdabfb14657e14823f19db22e31a6a63bc9136ec949dd868c6094e",
    "fd2e5bcb4de52dce98b476e54fc8538f291058ecfbb9f832ab4d2e5113690581",
})


class VertexJournalError(RuntimeError):
    """A bridge binding or durable accounting invariant failed."""


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _constant(_value: str) -> None:
    raise ValueError("non-finite JSON number")


def _json_object(raw: bytes) -> dict[str, Any]:
    value = json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs,
                       parse_constant=_constant)
    if not isinstance(value, dict):
        raise ValueError("JSON object required")
    return value


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _pinned_model_version(version: Any) -> bool:
    """Only the exact priced model is admissible to this canary."""
    return type(version) is str and version == MODEL


def _contains_credential_key(value: Any) -> bool:
    if isinstance(value, dict):
        for key, child in value.items():
            if isinstance(key, str) and re.search(
                    r"password|secret|credential|authorization|api.?key|access.?token|refresh.?token",
                    key, re.I):
                return True
            if _contains_credential_key(child):
                return True
    elif isinstance(value, list):
        return any(_contains_credential_key(child) for child in value)
    return False


def _confirmed_429(result: EffectResult) -> bool:
    if result.response_status != 429 or result.raw_response is None:
        return False
    try:
        error = _json_object(result.raw_response).get("error")
    except (ValueError, UnicodeError):
        return False
    return (isinstance(error, dict) and type(error.get("code")) is int
            and error["code"] == 429 and error.get("status") == "RESOURCE_EXHAUSTED")


def _usage_cost(raw: bytes) -> tuple[int, dict[str, Any], str | None]:
    """Price captured usage before attempting to parse candidate role content.

    Global standard rates: $0.75/M input and $3.75/M output, where output is
    totalTokenCount - promptTokenCount and therefore includes thinking.
    Round up to one micro-USD; this is an estimate from observed usage.
    """
    envelope = _json_object(raw)
    usage = envelope.get("usageMetadata")
    if not isinstance(usage, dict):
        raise ValueError("missing usageMetadata")
    prompt = usage.get("promptTokenCount")
    total = usage.get("totalTokenCount")
    if type(prompt) is not int or type(total) is not int or prompt <= 0 or total < prompt:
        raise ValueError("invalid prompt or total token count")
    output = total - prompt
    for key in ("candidatesTokenCount", "thoughtsTokenCount",
                "cachedContentTokenCount", "toolUsePromptTokenCount"):
        if key in usage and (type(usage[key]) is not int or usage[key] < 0):
            raise ValueError("invalid usage token count")
    if usage.get("thoughtsTokenCount", 0) > output:
        raise ValueError("thinking exceeds output tokens")
    # Multiplying by four keeps the decimal rates exact through rounding.
    return (prompt * 3 + output * 15 + 3) // 4, usage, envelope.get("modelVersion")


def _role_content(raw: bytes) -> dict[str, Any]:
    """Check finish before reading only the non-thought candidate text."""
    envelope = _json_object(raw)
    candidates = envelope.get("candidates")
    if not isinstance(candidates, list) or len(candidates) != 1 or not isinstance(candidates[0], dict):
        raise ValueError("exactly one candidate required")
    candidate = candidates[0]
    if candidate.get("finishReason") != "STOP":
        raise ValueError("generation did not finish with STOP")
    content = candidate.get("content")
    parts = content.get("parts") if isinstance(content, dict) else None
    if not isinstance(parts, list):
        raise ValueError("candidate parts missing")
    texts = []
    for part in parts:
        if not isinstance(part, dict):
            raise ValueError("invalid candidate part")
        if part.get("thought") is True:
            continue
        if part.get("thought") not in (None, False) or not isinstance(part.get("text"), str):
            raise ValueError("invalid non-thought candidate part")
        texts.append(part["text"])
    if not texts:
        raise ValueError("non-thought role content missing")
    return _json_object("".join(texts).encode("utf-8"))


class VertexJournal(JournaledCallback):
    """StrictEngine/run_case-compatible role callback with durable per-call effects.

    ``identity`` is a non-sensitive JSON object identifying the frozen run,
    source/case cohort, code/runtime envelope, and pricing evidence. Reopening
    the same SQLite journal with any changed identity, model or endpoint fails.
    The EffectExecutor must use the same SQLite file, FULL synchronous mode,
    and a call cap no smaller than the intended number of dispatched attempts.
    """

    def __init__(self, executor: EffectExecutor,
                 count_transport: Callable[[bytes], HttpResponse],
                 generate_transport: Callable[[bytes], HttpResponse], *,
                 session_id: str, identity: dict[str, Any],
                 endpoint_count: str = COUNT_ENDPOINT,
                 endpoint_generate: str = GENERATION_ENDPOINT,
                 sleep: Callable[[float], None] = time.sleep,
                 rng: Callable[[], float] = random.random):
        if not isinstance(executor, EffectExecutor):
            raise ValueError("EffectExecutor required")
        if not callable(count_transport) or not callable(generate_transport):
            raise ValueError("single-request transports required")
        if not callable(sleep) or not callable(rng):
            raise ValueError("retry sleep and jitter functions required")
        if not isinstance(identity, dict) or not identity:
            raise ValueError("nonempty run identity required")
        if endpoint_count != COUNT_ENDPOINT or endpoint_generate != GENERATION_ENDPOINT:
            raise ValueError("canary endpoint/model differs from pinned Vertex 3.8 contract")
        try:
            identity_raw = canonical_json(identity)
        except (TypeError, ValueError, UnicodeError) as exc:
            raise ValueError("identity must be finite JSON") from exc
        if _contains_credential_key(identity):
            raise ValueError("identity must not contain credential fields")
        super().__init__(executor, count_transport, session_id=session_id,
                         exposure_per_attempt=0)
        self._count_transport = count_transport
        self._generate_transport = generate_transport
        self._sleep = sleep
        self._rng = rng
        self._db = executor._db
        self._contract = canonical_json({
            "schema": 1, "session_id": session_id, "identity_sha256": _sha(identity_raw),
            "identity_bytes": len(identity_raw), "model": MODEL,
            "observed_model_policy": "exact",
            "predecessor": {"forbidden_request_hashes": sorted(FORBIDDEN_REQUEST_SHA256)},
            "endpoint_count": endpoint_count, "endpoint_generate": endpoint_generate,
            "count_attempt_cap": MAX_COUNT_ATTEMPTS,
            "generation_attempt_cap": MAX_GENERATION_ATTEMPTS,
            "prior_micro_usd": PRIOR_MICRO_USD,
            "incremental_cap_micro_usd": INCREMENTAL_CAP_MICRO_USD,
            "generation_reserve_micro_usd": GENERATION_RESERVE_MICRO_USD,
            "max_input_tokens": MAX_INPUT_TOKENS,
            "input_rate_usd_per_million": "0.75",
            "output_rate_usd_per_million": "3.75",
            "retry_policy": "one exact separate attempt after captured 429/RESOURCE_EXHAUSTED; delay=2+jitter[0,1] seconds",
        })
        self._protect_journal_file()
        self._init_bridge()

    def _protect_journal_file(self) -> None:
        path = self._executor.db_path
        if path == ":memory:":
            raise VertexJournalError("live-canary journal must be durable")
        if os.path.islink(path):
            raise VertexJournalError("journal file must not be a symlink")
        try:
            os.chmod(path, 0o600)
            for suffix in ("-wal", "-shm"):
                sidecar = path + suffix
                if os.path.exists(sidecar):
                    if os.path.islink(sidecar):
                        raise VertexJournalError("journal sidecar must not be a symlink")
                    os.chmod(sidecar, 0o600)
        except OSError as exc:
            raise VertexJournalError("cannot restrict journal file permissions") from exc

    def _init_bridge(self) -> None:
        try:
            self._db.executescript("""
                CREATE TABLE IF NOT EXISTS vertex_run (
                    singleton INTEGER PRIMARY KEY CHECK(singleton=1),
                    contract BLOB NOT NULL, halted TEXT
                );
                CREATE TABLE IF NOT EXISTS vertex_calls (
                    logical_id TEXT PRIMARY KEY, ordinal INTEGER NOT NULL UNIQUE,
                    stage TEXT NOT NULL, role_sha256 TEXT NOT NULL,
                    request BLOB NOT NULL, request_sha256 TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'prepared', error TEXT
                );
                CREATE TABLE IF NOT EXISTS vertex_attempts (
                    operation_id TEXT PRIMARY KEY,
                    logical_id TEXT NOT NULL REFERENCES vertex_calls(logical_id),
                    kind TEXT NOT NULL CHECK(kind IN ('count','generation')),
                    attempt_no INTEGER NOT NULL CHECK(attempt_no IN (0,1)),
                    endpoint TEXT NOT NULL, request_sha256 TEXT NOT NULL,
                    reserved_micro_usd INTEGER NOT NULL,
                    settled_micro_usd INTEGER,
                    state TEXT NOT NULL DEFAULT 'prepared',
                    http_status INTEGER, response_sha256 TEXT, response_bytes INTEGER,
                    observed_model TEXT, usage_json TEXT, finish_reason TEXT,
                    count_tokens INTEGER,
                    UNIQUE(logical_id,kind,attempt_no)
                );
            """)
            row = self._db.execute("SELECT contract FROM vertex_run WHERE singleton=1").fetchone()
            if row is None:
                self._db.execute("INSERT INTO vertex_run(singleton,contract) VALUES(1,?)",
                                 (sqlite3.Binary(self._contract),))
            elif bytes(row["contract"]) != self._contract:
                raise VertexJournalError("run identity, endpoint, model or caps changed")
        except sqlite3.Error as exc:
            raise VertexJournalError("bridge journal initialization failed") from exc

    def _halt(self, reason: str) -> None:
        self._db.execute("UPDATE vertex_run SET halted=COALESCE(halted,?) WHERE singleton=1", (reason,))

    def _check_live(self) -> None:
        row = self._db.execute("SELECT halted FROM vertex_run WHERE singleton=1").fetchone()
        if row is None or row["halted"] is not None:
            raise VertexJournalError("canary halted or run contract missing")

    def accounting(self) -> dict[str, Any]:
        """Observed attempt counts and conservative unsettled reservations."""
        row = self._db.execute("""SELECT
            COALESCE(SUM(kind='count'),0) AS counts,
            COALESCE(SUM(kind='generation'),0) AS generations,
            COALESCE(SUM(CASE WHEN settled_micro_usd IS NULL THEN reserved_micro_usd ELSE 0 END),0) AS reserved,
            COALESCE(SUM(COALESCE(settled_micro_usd,0)),0) AS settled,
            COALESCE(SUM(http_status=429),0) AS http_429,
            COALESCE(SUM(state='uncertain'),0) AS uncertain
            FROM vertex_attempts""").fetchone()
        halted = self._db.execute("SELECT halted FROM vertex_run WHERE singleton=1").fetchone()[0]
        committed = row["reserved"] + row["settled"]
        if (row["counts"] > MAX_COUNT_ATTEMPTS or row["generations"] > MAX_GENERATION_ATTEMPTS):
            raise VertexJournalError("attempt accounting exceeds hard cap")
        return {"count_attempts": row["counts"], "generation_attempts": row["generations"],
                "count_attempt_cap": MAX_COUNT_ATTEMPTS,
                "generation_attempt_cap": MAX_GENERATION_ATTEMPTS,
                "settled_micro_usd": row["settled"],
                "reserved_micro_usd": row["reserved"],
                "committed_micro_usd": committed,
                "incremental_cap_micro_usd": INCREMENTAL_CAP_MICRO_USD,
                "remaining_micro_usd": max(0, INCREMENTAL_CAP_MICRO_USD - committed),
                "prior_micro_usd": PRIOR_MICRO_USD,
                "total_estimated_or_reserved_micro_usd": PRIOR_MICRO_USD + committed,
                "http_429_attempts": row["http_429"],
                "uncertain_attempts": row["uncertain"], "halted": halted}

    def close(self) -> None:
        """Close the owned EffectExecutor's SQLite connection."""
        self._executor.close()

    def _register_call(self, logical_id: str, ordinal: int, stage: str,
                       role_sha: str, request: bytes) -> None:
        try:
            self._db.execute("BEGIN IMMEDIATE")
            current = self._db.execute("SELECT * FROM vertex_calls WHERE logical_id=?",
                                       (logical_id,)).fetchone()
            if current is None:
                self._check_live()
                self._db.execute("""INSERT INTO vertex_calls
                    (logical_id,ordinal,stage,role_sha256,request,request_sha256)
                    VALUES(?,?,?,?,?,?)""", (logical_id, ordinal, stage, role_sha,
                                             sqlite3.Binary(request), _sha(request)))
            elif (current["ordinal"] != ordinal or current["stage"] != stage
                  or current["role_sha256"] != role_sha
                  or bytes(current["request"]) != request
                  or current["request_sha256"] != _sha(request)):
                raise VertexJournalError("logical call was rebound to changed role or wire bytes")
            self._db.execute("COMMIT")
        except (sqlite3.Error, VertexJournalError) as exc:
            if self._db.in_transaction:
                self._db.execute("ROLLBACK")
            if isinstance(exc, VertexJournalError):
                raise
            raise VertexJournalError("call registration failed") from exc

    def _prepare_attempt(self, logical_id: str, kind: str, attempt_no: int,
                         request: bytes) -> str:
        operation_id = f"{logical_id}:{kind}" + (":retry1" if attempt_no else "")
        endpoint = COUNT_ENDPOINT if kind == "count" else GENERATION_ENDPOINT
        reserved = 0 if kind == "count" else GENERATION_RESERVE_MICRO_USD
        try:
            self._db.execute("BEGIN IMMEDIATE")
            current = self._db.execute("SELECT * FROM vertex_attempts WHERE operation_id=?",
                                       (operation_id,)).fetchone()
            if current is None:
                self._check_live()
                if attempt_no:
                    predecessor_id = f"{logical_id}:{kind}"
                    predecessor = self._db.execute("SELECT * FROM vertex_attempts WHERE operation_id=?",
                                                   (predecessor_id,)).fetchone()
                    if (predecessor is None or predecessor["state"] != "confirmed_429"
                            or predecessor["request_sha256"] != _sha(request)):
                        raise VertexJournalError("retry lacks an identical confirmed 429 predecessor")
                elif self._db.execute("SELECT 1 FROM vertex_attempts WHERE logical_id=? AND kind=?",
                                      (logical_id, kind)).fetchone():
                    raise VertexJournalError("initial attempt already exists under another identity")
                used = self._db.execute("SELECT COUNT(*) FROM vertex_attempts WHERE kind=?", (kind,)).fetchone()[0]
                cap = MAX_COUNT_ATTEMPTS if kind == "count" else MAX_GENERATION_ATTEMPTS
                if used >= cap:
                    raise VertexJournalError("kind attempt cap exhausted")
                committed = self._db.execute("""SELECT COALESCE(SUM(COALESCE(settled_micro_usd,reserved_micro_usd)),0)
                    FROM vertex_attempts""").fetchone()[0]
                if committed + reserved > INCREMENTAL_CAP_MICRO_USD:
                    raise VertexJournalError("incremental cost reservation cap exhausted")
                self._db.execute("""INSERT INTO vertex_attempts
                    (operation_id,logical_id,kind,attempt_no,endpoint,request_sha256,reserved_micro_usd)
                    VALUES(?,?,?,?,?,?,?)""", (operation_id, logical_id, kind,
                          attempt_no, endpoint, _sha(request), reserved))
            elif (current["logical_id"] != logical_id or current["kind"] != kind
                  or current["attempt_no"] != attempt_no or current["endpoint"] != endpoint
                  or current["request_sha256"] != _sha(request)
                  or current["reserved_micro_usd"] != reserved):
                raise VertexJournalError("attempt was rebound to changed request or endpoint")
            self._db.execute("COMMIT")
        except (sqlite3.Error, VertexJournalError) as exc:
            if self._db.in_transaction:
                self._db.execute("ROLLBACK")
            if isinstance(exc, VertexJournalError):
                raise
            raise VertexJournalError("attempt preparation failed") from exc
        return operation_id

    def _record_result(self, operation_id: str, result: EffectResult) -> None:
        raw = result.raw_response
        status = result.response_status
        state = ("uncertain" if result.state == "uncertain" else
                 "confirmed_429" if _confirmed_429(result) else
                 "http_200" if result.state == "succeeded" and status == 200 else
                 "failed")
        try:
            self._db.execute("BEGIN IMMEDIATE")
            row = self._db.execute("SELECT * FROM vertex_attempts WHERE operation_id=?",
                                   (operation_id,)).fetchone()
            if row is None:
                raise VertexJournalError("attempt accounting row missing")
            actual = 0 if state == "confirmed_429" or row["kind"] == "count" else None
            # Preserve an existing usage settlement on idempotent replay.
            settled = row["settled_micro_usd"] if row["settled_micro_usd"] is not None else actual
            self._db.execute("""UPDATE vertex_attempts SET state=?, http_status=?,
                response_sha256=?, response_bytes=?, settled_micro_usd=? WHERE operation_id=?""",
                (state, status, _sha(raw) if raw is not None else None,
                 len(raw) if raw is not None else None, settled, operation_id))
            if state == "uncertain":
                self._halt("uncertain external effect")
            elif state == "failed":
                self._halt("HTTP failure or unconfirmed 429")
            self._db.execute("COMMIT")
        except (sqlite3.Error, VertexJournalError) as exc:
            if self._db.in_transaction:
                self._db.execute("ROLLBACK")
            if isinstance(exc, VertexJournalError):
                raise
            raise VertexJournalError("result accounting failed") from exc

    def _effect(self, logical_id: str, kind: str, attempt_no: int,
                request: bytes) -> EffectResult:
        operation_id = self._prepare_attempt(logical_id, kind, attempt_no, request)
        transport = self._count_transport if kind == "count" else self._generate_transport
        self._executor.register(operation_id, branch=kind + ":" +
                                (COUNT_ENDPOINT if kind == "count" else GENERATION_ENDPOINT),
                                request=request, exposure_per_attempt=0)
        try:
            result = self._executor.execute(operation_id, callback=transport,
                                            retry=RetryPolicy(allow_429=False))
        except Exception:
            # A durable response may already exist if finalization failed.
            result = self._executor.get_result(operation_id)
            self._record_result(operation_id, result)
            raise
        self._record_result(operation_id, result)
        return result

    def _one_kind(self, logical_id: str, kind: str, request: bytes) -> EffectResult:
        for attempt_no in (0, 1):
            result = self._effect(logical_id, kind, attempt_no, request)
            if result.state == "uncertain":
                raise JournaledCallError("uncertain")
            if result.state == "succeeded" and result.response_status == 200:
                return result
            if _confirmed_429(result) and attempt_no == 0:
                try:
                    jitter = float(self._rng())
                    if not 0.0 <= jitter <= 1.0:
                        raise ValueError("retry jitter outside [0,1]")
                    self._sleep(2.0 + jitter)
                except Exception as exc:
                    self._halt("retry delay failed; no successor dispatched")
                    raise VertexJournalError("retry delay failed") from exc
                continue
            self._halt("confirmed 429 retry exhausted" if _confirmed_429(result)
                       else "HTTP operation failed")
            raise JournaledCallError("failed")
        raise AssertionError("unreachable")

    def _capture_metadata(self, operation_id: str, raw: bytes) -> None:
        """Persist available provider metadata before role content validation."""
        try:
            envelope = _json_object(raw)
        except (ValueError, UnicodeError):
            envelope = {}
        model = envelope.get("modelVersion")
        model = model if isinstance(model, str) else None
        usage = envelope.get("usageMetadata")
        public_usage_fields = ("promptTokenCount", "totalTokenCount",
                               "candidatesTokenCount", "thoughtsTokenCount",
                               "cachedContentTokenCount", "toolUsePromptTokenCount")
        usage_json = (canonical_json({key: usage[key] for key in public_usage_fields
                                     if key in usage and type(usage[key]) is int}).decode("utf-8")
                      if isinstance(usage, dict) else None)
        candidates = envelope.get("candidates")
        finish = (candidates[0].get("finishReason")
                  if isinstance(candidates, list) and len(candidates) == 1
                  and isinstance(candidates[0], dict) else None)
        finish = finish if isinstance(finish, str) else None
        try:
            self._db.execute("BEGIN IMMEDIATE")
            row = self._db.execute("SELECT state FROM vertex_attempts WHERE operation_id=?",
                                   (operation_id,)).fetchone()
            if row is None or row["state"] != "http_200":
                raise VertexJournalError("metadata requires captured HTTP 200")
            self._db.execute("""UPDATE vertex_attempts SET observed_model=?, usage_json=?,
                finish_reason=? WHERE operation_id=?""", (model, usage_json, finish, operation_id))
            self._db.execute("COMMIT")
        except (sqlite3.Error, VertexJournalError) as exc:
            if self._db.in_transaction:
                self._db.execute("ROLLBACK")
            if isinstance(exc, VertexJournalError):
                raise
            raise VertexJournalError("provider metadata capture failed") from exc

    def _capture_count(self, operation_id: str, tokens: int) -> None:
        cursor = self._db.execute(
            "UPDATE vertex_attempts SET count_tokens=? WHERE operation_id=? AND state='http_200'",
            (tokens, operation_id))
        if cursor.rowcount != 1:
            raise VertexJournalError("count token capture missing HTTP 200 attempt")

    def _settle_generation(self, operation_id: str, cost: int) -> None:
        try:
            self._db.execute("BEGIN IMMEDIATE")
            row = self._db.execute("SELECT * FROM vertex_attempts WHERE operation_id=?",
                                   (operation_id,)).fetchone()
            if row is None or row["kind"] != "generation" or row["state"] != "http_200":
                raise VertexJournalError("cannot settle a generation without a raw HTTP 200")
            if row["settled_micro_usd"] is not None and row["settled_micro_usd"] != cost:
                raise VertexJournalError("generation cost settlement changed")
            self._db.execute("UPDATE vertex_attempts SET settled_micro_usd=? WHERE operation_id=?",
                             (cost, operation_id))
            committed = self._db.execute("""SELECT COALESCE(SUM(COALESCE(settled_micro_usd,reserved_micro_usd)),0)
                FROM vertex_attempts""").fetchone()[0]
            if cost > GENERATION_RESERVE_MICRO_USD or committed > INCREMENTAL_CAP_MICRO_USD:
                self._halt("observed usage exceeds accepted local reservation or incremental cap")
            self._db.execute("COMMIT")
        except (sqlite3.Error, VertexJournalError) as exc:
            if self._db.in_transaction:
                self._db.execute("ROLLBACK")
            if isinstance(exc, VertexJournalError):
                raise
            raise VertexJournalError("generation settlement failed") from exc

    def _receipt(self, logical_id: str, stage: str, ordinal: int,
                 kind: str, result: EffectResult | None = None) -> dict[str, Any]:
        def attempts(which: str) -> list[dict[str, Any]]:
            rows = self._db.execute("""SELECT operation_id,attempt_no,state,http_status,
                response_sha256,response_bytes,reserved_micro_usd,settled_micro_usd,
                observed_model,usage_json,finish_reason,count_tokens
                FROM vertex_attempts WHERE logical_id=? AND kind=? ORDER BY attempt_no""",
                (logical_id, which)).fetchall()
            output = []
            for row in rows:
                item = dict(row)
                item["usage_metadata"] = (json.loads(item.pop("usage_json"))
                                          if item["usage_json"] else None)
                output.append(item)
            return output

        attempt_rows = attempts(kind)
        call = self._db.execute("SELECT status,request_sha256 FROM vertex_calls WHERE logical_id=?",
                                (logical_id,)).fetchone()
        receipt = {"logical_id": logical_id, "stage": stage, "ordinal": ordinal,
                "kind": kind, "operation_id": result.operation_id if result else
                    (attempt_rows[-1]["operation_id"] if attempt_rows else None),
                "state": result.state if result else (attempt_rows[-1]["state"] if attempt_rows else "prepared"),
                "validation_status": call["status"],
                "attempts": attempt_rows, "request_sha256": call["request_sha256"],
                "run_contract_sha256": _sha(self._contract),
                "model": MODEL, "endpoint": COUNT_ENDPOINT if kind == "count" else GENERATION_ENDPOINT}
        if kind == "generation":
            receipt["count_attempts"] = attempts("count")
        return receipt

    def __call__(self, stage: str, payload: dict) -> dict:
        self._last_receipt = None
        if not isinstance(stage, str) or not stage.strip() or not isinstance(payload, dict):
            raise ValueError("stage and object payload required")
        try:
            role = build_request(stage, copy.deepcopy(payload))
            role_raw = canonical_json(role)
            request = canonical_json(build_generation_request(role))
            if _sha(request) in FORBIDDEN_REQUEST_SHA256:
                self._halt("forbidden uncertain predecessor request")
                raise ValueError("wire request matches forbidden uncertain predecessor")
            if json.loads(request)["generationConfig"]["maxOutputTokens"] != MAX_OUTPUT_TOKENS:
                raise ValueError("generation configuration changed")
        except (AdapterError, TypeError, ValueError, UnicodeError) as exc:
            raise JournaledCallError("request_error") from exc
        self._ordinal += 1
        ordinal = self._ordinal
        logical_id = f"{self._session_id}:call:{ordinal}"
        try:
            self._register_call(logical_id, ordinal, stage, _sha(role_raw), request)
            count = self._one_kind(logical_id, "count", request)
            self._last_receipt = self._receipt(logical_id, stage, ordinal, "count", count)
            if count.raw_response is None:
                raise ValueError("missing count response bytes")
            count_data = _json_object(count.raw_response)
            tokens = count_data.get("totalTokens")
            if type(tokens) is not int or tokens <= 0:
                raise ValueError("invalid countTokens totalTokens")
            self._capture_count(count.operation_id, tokens)
            self._last_receipt = self._receipt(logical_id, stage, ordinal, "count", count)
            if tokens > MAX_INPUT_TOKENS:
                raise ValueError("countTokens exceeds pinned 8192 input cap")
            generation = self._one_kind(logical_id, "generation", request)
            self._last_receipt = self._receipt(logical_id, stage, ordinal,
                                              "generation", generation)
            if generation.raw_response is None:
                raise ValueError("missing generation response bytes")
            self._capture_metadata(generation.operation_id, generation.raw_response)
            self._last_receipt = self._receipt(logical_id, stage, ordinal,
                                              "generation", generation)
            cost, usage, observed_model = _usage_cost(generation.raw_response)
            if not _pinned_model_version(observed_model):
                # Pricing for another or ambiguous model is unknown. Keep the
                # full reservation even though the HTTP effect succeeded.
                raise ValueError("observed model is not pinned Gemini 3.8")
            self._settle_generation(generation.operation_id, cost)
            self._last_receipt = self._receipt(logical_id, stage, ordinal,
                                              "generation", generation)
            if usage["promptTokenCount"] > MAX_INPUT_TOKENS:
                raise ValueError("observed generation input exceeded pinned 8192 cap")
            if self.accounting()["halted"] is not None:
                raise ValueError("observed cost exceeded local reservation or cap")
            content = _role_content(generation.raw_response)
            self._db.execute("UPDATE vertex_calls SET status='completed' WHERE logical_id=?",
                             (logical_id,))
            self._last_receipt = self._receipt(logical_id, stage, ordinal,
                                              "generation", generation)
            return content
        except JournaledCallError as exc:
            kind = "generation" if self._db.execute(
                "SELECT 1 FROM vertex_attempts WHERE logical_id=? AND kind='generation'",
                (logical_id,)).fetchone() else "count"
            self._db.execute("UPDATE vertex_calls SET status=? WHERE logical_id=?",
                             (exc.kind, logical_id))
            self._last_receipt = self._receipt(logical_id, stage, ordinal, kind)
            raise JournaledCallError(exc.kind, self._last_receipt) from exc
        except (ValueError, AdapterError) as exc:
            self._halt(type(exc).__name__ + " after captured HTTP response")
            self._db.execute("UPDATE vertex_calls SET status='invalid' WHERE logical_id=?",
                             (logical_id,))
            if self._last_receipt is not None:
                kind = self._last_receipt["kind"]
                self._last_receipt = self._receipt(logical_id, stage, ordinal, kind)
            raise JournaledCallError("parse_error", self._last_receipt) from exc
        except Exception as exc:
            try:
                self._halt("journal or accounting failure")
            except Exception:
                pass
            try:
                kind = "generation" if self._db.execute(
                    "SELECT 1 FROM vertex_attempts WHERE logical_id=? AND kind='generation'",
                    (logical_id,)).fetchone() else "count"
                self._db.execute("UPDATE vertex_calls SET status='journal_error' WHERE logical_id=?",
                                 (logical_id,))
                self._last_receipt = self._receipt(logical_id, stage, ordinal, kind)
            except Exception:
                pass
            raise JournaledCallError("journal_error", self._last_receipt) from exc
