"""Durable, single-runner Vertex bridge for a caller-authorized run.

The two supplied transports each accept one frozen wire body and return one
HttpResponse. They must disable SDK/HTTP retries. This module has no network
client, credentials, or authority to start a provider run by itself. The caller owns
the run identity and the endpoint-bound transports.

EffectExecutor records every raw HTTP response before this module parses it.
Its built-in 429 retry is deliberately disabled: it checks only the status,
whereas this bridge requires a captured 429/RESOURCE_EXHAUSTED body. A retry
is a separate registered operation with exactly the predecessor's request.

The caller supplies every budget, price and forbidden-request binding. A
per-generation reservation is a local risk bound, not a provider-enforced
maximum bill. Usage-derived costs are estimates, not an invoice. One
process/worker must own the SQLite journal at a time.
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
from dataclasses import dataclass
from typing import Any, Callable

from faithful_v3.prompts import build_request
from reasoning_engine.executor import (
    EffectExecutor, EffectResult, HttpResponse, OperationConflict, RetryPolicy,
)
from reasoning_engine.journal_callback import JournaledCallback, JournaledCallError
from reasoning_engine.vertex_adapter import (
    MODEL, MAX_OUTPUT_TOKENS, AdapterError, build_generation_request,
    canonical_json,
)

SQLITE_MAX_INT = (1 << 63) - 1
COUNT_ENDPOINT = "countTokens"
GENERATION_ENDPOINT = "gemini-3.8-flash@global"


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


@dataclass(frozen=True)
class VertexBudget:
    """Caller-authorized local limits and pricing for one immutable run.

    All money values are integer micro-USD. Rates are integer micro-USD per
    million tokens. Prior exposure is a caller-supplied estimate or reserve;
    it is not an invoice or an independently verified provider balance.
    """

    prior_exposure_micro_usd: int
    incremental_cap_micro_usd: int
    generation_reserve_micro_usd: int
    count_attempt_cap: int
    generation_attempt_cap: int
    max_input_tokens: int
    input_rate_micro_usd_per_million: int
    output_rate_micro_usd_per_million: int
    count_tokens_are_free: bool
    forbidden_request_sha256: frozenset[str]

    def __post_init__(self) -> None:
        nonnegative = (
            "prior_exposure_micro_usd", "incremental_cap_micro_usd",
            "count_attempt_cap", "generation_attempt_cap",
        )
        positive = (
            "generation_reserve_micro_usd", "max_input_tokens",
            "input_rate_micro_usd_per_million",
            "output_rate_micro_usd_per_million",
        )
        for name in nonnegative + positive:
            value = getattr(self, name)
            if type(value) is not int or value < (1 if name in positive else 0) or value > SQLITE_MAX_INT:
                raise ValueError(f"{name} must be a finite SQLite-sized integer")
        if self.prior_exposure_micro_usd > SQLITE_MAX_INT - self.incremental_cap_micro_usd:
            raise ValueError("prior exposure plus incremental cap exceeds SQLite integer range")
        if self.count_tokens_are_free is not True:
            raise ValueError("countTokens requires an explicit current free-pricing assertion")
        if type(self.forbidden_request_sha256) is not frozenset or any(
                type(value) is not str or re.fullmatch(r"[0-9a-f]{64}", value) is None
                for value in self.forbidden_request_sha256):
            raise ValueError("forbidden_request_sha256 must be a frozenset of lowercase SHA-256 hashes")

    def as_contract(self) -> dict[str, Any]:
        """Return JSON-safe, validated immutable run settings."""
        return {
            "prior_exposure_micro_usd": self.prior_exposure_micro_usd,
            "incremental_cap_micro_usd": self.incremental_cap_micro_usd,
            "generation_reserve_micro_usd": self.generation_reserve_micro_usd,
            "count_attempt_cap": self.count_attempt_cap,
            "generation_attempt_cap": self.generation_attempt_cap,
            "max_input_tokens": self.max_input_tokens,
            "input_rate_micro_usd_per_million": self.input_rate_micro_usd_per_million,
            "output_rate_micro_usd_per_million": self.output_rate_micro_usd_per_million,
            "count_tokens_are_free": self.count_tokens_are_free,
            "forbidden_request_sha256": sorted(self.forbidden_request_sha256),
        }

    def snapshot(self) -> dict[str, Any]:
        return self.as_contract()


def _pinned_model_version(version: Any) -> bool:
    """Only the exact configured model is admissible to this run."""
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


def _usage_cost(raw: bytes, budget: VertexBudget) -> tuple[int, dict[str, Any], str | None]:
    """Price captured usage before attempting to parse candidate role content.

    Output is totalTokenCount - promptTokenCount and includes thinking.
    Round caller-priced usage up to one micro-USD. This is an estimate.
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
    if usage.get("candidatesTokenCount", 0) + usage.get("thoughtsTokenCount", 0) > output:
        raise ValueError("candidate and thinking tokens exceed output tokens")
    if usage.get("cachedContentTokenCount", 0) > prompt:
        raise ValueError("cached tokens exceed prompt tokens")
    if usage.get("toolUsePromptTokenCount", 0) != 0:
        raise ValueError("unexpected tool use in tool-free request")
    numerator = (prompt * budget.input_rate_micro_usd_per_million
                 + output * budget.output_rate_micro_usd_per_million)
    cost = (numerator + 999_999) // 1_000_000
    if cost > SQLITE_MAX_INT:
        raise ValueError("usage cost exceeds SQLite integer range")
    return cost, usage, envelope.get("modelVersion")


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
                 budget: VertexBudget | None = None,
                 retry_confirmed_429: bool = False,
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
            raise ValueError("endpoint/model differs from pinned Vertex contract")
        try:
            identity_raw = canonical_json(identity)
        except (TypeError, ValueError, UnicodeError) as exc:
            raise ValueError("identity must be finite JSON") from exc
        if _contains_credential_key(identity):
            raise ValueError("identity must not contain credential fields")
        if type(budget) is not VertexBudget:
            raise ValueError("explicit budget (VertexBudget) required")
        if type(retry_confirmed_429) is not bool:
            raise ValueError("retry_confirmed_429 must be a boolean")
        super().__init__(executor, count_transport, session_id=session_id,
                         exposure_per_attempt=0)
        self._count_transport = count_transport
        self._generate_transport = generate_transport
        self._sleep = sleep
        self._rng = rng
        self._db = executor._db
        self._budget = budget
        self._budget_values = budget.as_contract()
        self._retry_confirmed_429 = retry_confirmed_429
        contract = {
            "schema": 1, "session_id": session_id, "identity_sha256": _sha(identity_raw),
            "identity_bytes": len(identity_raw), "model": MODEL,
            "observed_model_policy": "exact",
            "endpoint_count": endpoint_count, "endpoint_generate": endpoint_generate,
            "budget": self._budget_values,
            "retry_confirmed_429": retry_confirmed_429,
            "retry_policy": ("one exact separate attempt after captured 429/RESOURCE_EXHAUSTED; delay=2+jitter[0,1] seconds"
                             if retry_confirmed_429 else "none"),
        }
        self._contract = canonical_json(contract)
        self._protect_journal_file()
        self._init_bridge()

    def _protect_journal_file(self) -> None:
        path = self._executor.db_path
        if path == ":memory:":
            raise VertexJournalError("provider journal must be durable")
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
                raise VertexJournalError("run identity, endpoint, model or configuration changed")
        except sqlite3.Error as exc:
            raise VertexJournalError("bridge journal initialization failed") from exc

    def _halt(self, reason: str) -> None:
        self._db.execute("UPDATE vertex_run SET halted=COALESCE(halted,?) WHERE singleton=1", (reason,))

    def _check_budget(self) -> None:
        if self._budget.as_contract() != self._budget_values:
            raise VertexJournalError("run budget configuration changed")

    def _check_live(self) -> None:
        self._check_budget()
        row = self._db.execute("SELECT halted FROM vertex_run WHERE singleton=1").fetchone()
        if row is None or row["halted"] is not None:
            raise VertexJournalError("run halted or contract missing")

    def accounting(self) -> dict[str, Any]:
        """Observed attempt counts and conservative unsettled reservations."""
        try:
            row = self._db.execute("""SELECT
                COALESCE(SUM(kind='count'),0) AS counts,
                COALESCE(SUM(kind='generation'),0) AS generations,
                COALESCE(SUM(CASE WHEN settled_micro_usd IS NULL THEN reserved_micro_usd ELSE 0 END),0) AS reserved,
                COALESCE(SUM(COALESCE(settled_micro_usd,0)),0) AS settled,
                COALESCE(SUM(http_status=429),0) AS http_429,
                COALESCE(SUM(state='uncertain'),0) AS uncertain
                FROM vertex_attempts""").fetchone()
        except sqlite3.Error as exc:
            self._halt("accounting overflow or corruption")
            raise VertexJournalError("attempt accounting cannot be represented") from exc
        halted = self._db.execute("SELECT halted FROM vertex_run WHERE singleton=1").fetchone()[0]
        committed = row["reserved"] + row["settled"]
        if (row["counts"] > self._budget_values["count_attempt_cap"]
                or row["generations"] > self._budget_values["generation_attempt_cap"]):
            raise VertexJournalError("attempt accounting exceeds hard cap")
        if committed > SQLITE_MAX_INT:
            self._halt("accounting overflow")
            raise VertexJournalError("attempt accounting exceeds SQLite integer range")
        cap_exceeded = committed > self._budget_values["incremental_cap_micro_usd"]
        result = {"count_attempts": row["counts"], "generation_attempts": row["generations"],
                "count_attempt_cap": self._budget_values["count_attempt_cap"],
                "generation_attempt_cap": self._budget_values["generation_attempt_cap"],
                "settled_micro_usd": row["settled"],
                "reserved_micro_usd": row["reserved"],
                "committed_micro_usd": committed,
                "cap_exceeded": cap_exceeded,
                "incremental_cap_micro_usd": self._budget_values["incremental_cap_micro_usd"],
                "remaining_micro_usd": max(0, self._budget_values["incremental_cap_micro_usd"] - committed),
                "prior_exposure_micro_usd": self._budget_values["prior_exposure_micro_usd"],
                "total_configured_exposure_micro_usd":
                    self._budget_values["prior_exposure_micro_usd"] + committed,
                "invoice_status": "not_reconciled",
                "http_429_attempts": row["http_429"],
                "uncertain_attempts": row["uncertain"], "halted": halted}
        return result

    def close(self) -> None:
        """Close the owned EffectExecutor's SQLite connection."""
        self._executor.close()

    def _register_call(self, logical_id: str, ordinal: int, stage: str,
                       role_sha: str, request: bytes) -> None:
        self._check_budget()
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
        self._check_budget()
        operation_id = f"{logical_id}:{kind}" + (":retry1" if attempt_no else "")
        endpoint = COUNT_ENDPOINT if kind == "count" else GENERATION_ENDPOINT
        reserved = 0 if kind == "count" else self._budget_values["generation_reserve_micro_usd"]
        try:
            self._db.execute("BEGIN IMMEDIATE")
            current = self._db.execute("SELECT * FROM vertex_attempts WHERE operation_id=?",
                                       (operation_id,)).fetchone()
            if current is None:
                self._check_live()
                if attempt_no:
                    if not self._retry_confirmed_429:
                        raise VertexJournalError("retry is not authorized by the run contract")
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
                cap = (self._budget_values["count_attempt_cap"] if kind == "count"
                       else self._budget_values["generation_attempt_cap"])
                if used >= cap:
                    raise VertexJournalError("kind attempt cap exhausted")
                committed = self._db.execute("""SELECT COALESCE(SUM(COALESCE(settled_micro_usd,reserved_micro_usd)),0)
                    FROM vertex_attempts""").fetchone()[0]
                if committed + reserved > self._budget_values["incremental_cap_micro_usd"]:
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
        branch = kind + ":" + (COUNT_ENDPOINT if kind == "count" else GENERATION_ENDPOINT)
        halted = self._db.execute("SELECT halted FROM vertex_run WHERE singleton=1").fetchone()
        if halted is None:
            raise VertexJournalError("run contract missing")
        if halted["halted"] is not None:
            # A bridge row may have been prepared before registration failed.
            # A halted run may only read a durable effect or finish recovery of
            # an already-started effect; it must never enter a fresh callback.
            operation = self._executor._get_operation(operation_id)
            if operation is None or operation["state"] == "ready":
                raise VertexJournalError("halted run cannot dispatch an effect")
            self._executor.register(operation_id, branch=branch, request=request,
                                    exposure_per_attempt=0)
            if operation["state"] == "started":
                def no_dispatch(_request: bytes) -> HttpResponse:
                    raise VertexJournalError("halted run cannot dispatch an effect")

                result = self._executor.execute(operation_id, callback=no_dispatch,
                                                retry=RetryPolicy(allow_429=False))
            else:
                result = self._executor.get_result(operation_id)
            self._record_result(operation_id, result)
            return result
        transport = self._count_transport if kind == "count" else self._generate_transport
        self._executor.register(operation_id, branch=branch,
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
            if _confirmed_429(result) and attempt_no == 0 and self._retry_confirmed_429:
                try:
                    jitter = float(self._rng())
                    if not 0.0 <= jitter <= 1.0:
                        raise ValueError("retry jitter outside [0,1]")
                    self._sleep(2.0 + jitter)
                except Exception as exc:
                    self._halt("retry delay failed; no retry dispatched")
                    raise VertexJournalError("retry delay failed") from exc
                continue
            self._halt("confirmed 429 retry unavailable or exhausted" if _confirmed_429(result)
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
            if (cost > self._budget_values["generation_reserve_micro_usd"]
                    or committed > self._budget_values["incremental_cap_micro_usd"]):
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
            if _sha(request) in self._budget.forbidden_request_sha256:
                self._halt("forbidden request hash")
                raise ValueError("wire request matches caller-forbidden hash")
            if json.loads(request)["generationConfig"]["maxOutputTokens"] != MAX_OUTPUT_TOKENS:
                raise ValueError("generation configuration changed")
        except (AdapterError, TypeError, ValueError, UnicodeError) as exc:
            raise JournaledCallError("request_error") from exc
        self._ordinal += 1
        ordinal = self._ordinal
        logical_id = f"{self._session_id}:call:{ordinal}"
        try:
            self._register_call(logical_id, ordinal, stage, _sha(role_raw), request)
            call_row = self._db.execute("SELECT status FROM vertex_calls WHERE logical_id=?",
                                        (logical_id,)).fetchone()
            completed_before = call_row is not None and call_row["status"] == "completed"
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
            if tokens > self._budget.max_input_tokens:
                raise ValueError("countTokens exceeds configured input cap")
            generation = self._one_kind(logical_id, "generation", request)
            self._last_receipt = self._receipt(logical_id, stage, ordinal,
                                              "generation", generation)
            if generation.raw_response is None:
                raise ValueError("missing generation response bytes")
            self._capture_metadata(generation.operation_id, generation.raw_response)
            self._last_receipt = self._receipt(logical_id, stage, ordinal,
                                              "generation", generation)
            cost, usage, observed_model = _usage_cost(generation.raw_response, self._budget)
            if not _pinned_model_version(observed_model):
                # Pricing for another or ambiguous model is unknown. Keep the
                # full reservation even though the HTTP effect succeeded.
                raise ValueError("observed model is not pinned Gemini 3.8")
            self._settle_generation(generation.operation_id, cost)
            self._last_receipt = self._receipt(logical_id, stage, ordinal,
                                              "generation", generation)
            if usage["promptTokenCount"] > self._budget.max_input_tokens:
                raise ValueError("observed generation input exceeded configured cap")
            if self.accounting()["halted"] is not None and not completed_before:
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
            if isinstance(exc, (VertexJournalError, OperationConflict)):
                # An immutable binding failure cannot yield a trustworthy
                # receipt for this invocation, even if bridge rows exist.
                self._last_receipt = None
            else:
                try:
                    kind = "generation" if self._db.execute(
                        "SELECT 1 FROM vertex_attempts WHERE logical_id=? AND kind='generation'",
                        (logical_id,)).fetchone() else "count"
                    self._last_receipt = self._receipt(logical_id, stage, ordinal, kind)
                except Exception:
                    pass
            try:
                self._db.execute("UPDATE vertex_calls SET status='journal_error' WHERE logical_id=? AND status!='completed'",
                                 (logical_id,))
            except Exception:
                pass
            raise JournaledCallError("journal_error", self._last_receipt) from exc
