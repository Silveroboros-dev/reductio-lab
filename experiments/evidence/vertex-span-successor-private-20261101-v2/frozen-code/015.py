"""Offline, journaled effect executor for Faithful Engine experiments.

All semantic/SI roles remain caller-supplied model callbacks. This module only
records and dispatches an already-formed effect through a supplied callback;
it contains no HTTP client and makes no semantic decisions.

API sketch::

    executor = EffectExecutor("effects.sqlite3", exposure_cap=100, call_cap=20)
    executor.register("op-1", branch="a", request=b"payload",
                      exposure_per_attempt=3)
    result = executor.execute(
        "op-1", callback=lambda request: HttpResponse(200, b'{"ok":true}'),
        retry=RetryPolicy(allow_429=True, max_attempts=3),
    )

The durable `started` attempt and its conservative exposure reservation are
committed before calling the callback. A 200 response's exact raw bytes are
committed before JSON parsing; effect success and parse status are independent.
Only an explicit 429 can be retried, and only with an explicitly enabled
RetryPolicy. Unknown callback exceptions (including timeouts) become
`uncertain`, keep their reservation, and are never automatically repeated.
Exposure units are caller-defined conservative upper bounds, not provider
usage or price estimates. Since those values are unknown, every attempt
consumes its full declared exposure allowance, including 429 attempts and
uncertain calls. Configure hard caps before dispatch and do not pass credentials.
The journal assumes one active executor/worker at a time; it is not certified
for concurrent or live provider use.
"""
from __future__ import annotations

import json
import os
import random
import sqlite3
import time
from dataclasses import dataclass
from typing import Callable, Optional


class ExecutorError(RuntimeError):
    """Base executor error."""


class BudgetExceeded(ExecutorError):
    """A call or exposure hard cap would be exceeded."""


class OperationConflict(ExecutorError):
    """An operation id was reused with different immutable inputs."""


class JournalError(ExecutorError):
    """A journal read/write failed or violated an invariant."""


@dataclass(frozen=True)
class HttpResponse:
    """Response supplied by an offline/test callback; no network is performed."""

    status_code: int
    body: bytes


@dataclass(frozen=True)
class RetryPolicy:
    """Pre-authorized retry policy for explicit HTTP 429 responses only."""

    allow_429: bool = False
    max_attempts: int = 1
    base_backoff_seconds: float = 0.25
    max_backoff_seconds: float = 8.0


@dataclass(frozen=True)
class EffectResult:
    operation_id: str
    state: str
    attempts: int
    response_status: Optional[int]
    raw_response: Optional[bytes]
    parse_status: Optional[str]
    parsed_json: object = None
    parse_error: Optional[str] = None
    error: Optional[str] = None


class EffectExecutor:
    """SQLite-backed, at-most-once-on-ambiguity effect dispatcher.

    `exposure_cap` and `call_cap` are hard lifetime caps for this journal.
    Calls and declared exposure are durably reserved per attempt before the
    callback runs. Callback code must issue at most one external request and
    must have SDK/network retries disabled; the executor itself has no HTTP.
    This implementation assumes a single active executor/worker and is not
    certified for concurrent or live provider use.
    """

    def __init__(self, db_path: str, *, exposure_cap: int, call_cap: int,
                 sleep: Callable[[float], None] = time.sleep,
                 rng: Callable[[], float] = random.random,
                 hard_max_attempts: int = 5):
        if exposure_cap < 0 or call_cap < 0 or hard_max_attempts < 1:
            raise ValueError("caps must be nonnegative and hard_max_attempts positive")
        self.db_path = os.fspath(db_path)
        self.sleep = sleep
        self.rng = rng
        self.hard_max_attempts = hard_max_attempts
        self._db = sqlite3.connect(self.db_path, timeout=30, isolation_level=None)
        self._db.row_factory = sqlite3.Row
        self._db.execute("PRAGMA foreign_keys = ON")
        self._db.execute("PRAGMA journal_mode = WAL")
        self._db.execute("PRAGMA synchronous = FULL")
        self._init_journal(exposure_cap, call_cap)

    def close(self) -> None:
        self._db.close()

    def __enter__(self) -> "EffectExecutor":
        return self

    def __exit__(self, *_exc) -> None:
        self.close()

    def _init_journal(self, exposure_cap: int, call_cap: int) -> None:
        try:
            self._db.executescript("""
                CREATE TABLE IF NOT EXISTS config (
                    singleton INTEGER PRIMARY KEY CHECK(singleton=1),
                    exposure_cap INTEGER NOT NULL CHECK(exposure_cap >= 0),
                    call_cap INTEGER NOT NULL CHECK(call_cap >= 0)
                );
                CREATE TABLE IF NOT EXISTS operations (
                    operation_id TEXT PRIMARY KEY,
                    branch TEXT NOT NULL,
                    request BLOB NOT NULL,
                    exposure_per_attempt INTEGER NOT NULL CHECK(exposure_per_attempt >= 0),
                    retry_bound INTEGER NOT NULL DEFAULT 0 CHECK(retry_bound IN (0,1)),
                    retry_429_authorized INTEGER NOT NULL DEFAULT 0 CHECK(retry_429_authorized IN (0,1)),
                    retry_max_attempts INTEGER NOT NULL DEFAULT 1,
                    retry_base_backoff REAL NOT NULL DEFAULT 0.25,
                    retry_max_backoff REAL NOT NULL DEFAULT 8.0,
                    state TEXT NOT NULL CHECK(state IN ('ready','started','succeeded','failed','uncertain')),
                    attempts INTEGER NOT NULL DEFAULT 0 CHECK(attempts >= 0),
                    response_status INTEGER,
                    raw_response BLOB,
                    parse_status TEXT,
                    parsed_json TEXT,
                    parse_error TEXT,
                    error TEXT
                );
                CREATE TABLE IF NOT EXISTS attempts (
                    operation_id TEXT NOT NULL REFERENCES operations(operation_id),
                    attempt_no INTEGER NOT NULL CHECK(attempt_no > 0),
                    state TEXT NOT NULL CHECK(state IN ('started','response','uncertain')),
                    exposure_units INTEGER NOT NULL CHECK(exposure_units >= 0),
                    response_status INTEGER,
                    raw_response BLOB,
                    started_at REAL NOT NULL,
                    completed_at REAL,
                    error TEXT,
                    PRIMARY KEY(operation_id, attempt_no)
                );
            """)
            row = self._db.execute("SELECT exposure_cap, call_cap FROM config WHERE singleton=1").fetchone()
            if row is None:
                self._db.execute("INSERT INTO config VALUES(1, ?, ?)", (exposure_cap, call_cap))
            elif exposure_cap > row["exposure_cap"] or call_cap > row["call_cap"]:
                raise JournalError("reopening a journal cannot increase its hard caps")
            # A lower supplied cap intentionally tightens the persistent cap.
            elif exposure_cap < row["exposure_cap"] or call_cap < row["call_cap"]:
                self._db.execute("UPDATE config SET exposure_cap=?, call_cap=? WHERE singleton=1",
                                  (exposure_cap, call_cap))
        except sqlite3.Error as exc:
            raise JournalError(f"journal initialization failed: {exc}") from exc

    def register(self, operation_id: str, *, branch: str, request: bytes,
                 exposure_per_attempt: int) -> None:
        """Register immutable work. Re-registering identical inputs is idempotent."""
        if not operation_id or not branch or not isinstance(request, (bytes, bytearray)):
            raise ValueError("operation_id, branch, and bytes request are required")
        if exposure_per_attempt < 0:
            raise ValueError("exposure_per_attempt must be nonnegative")
        try:
            self._db.execute("BEGIN IMMEDIATE")
            existing = self._db.execute("SELECT * FROM operations WHERE operation_id=?",
                                        (operation_id,)).fetchone()
            if existing:
                if (existing["branch"] != branch or bytes(existing["request"]) != bytes(request)
                        or existing["exposure_per_attempt"] != exposure_per_attempt):
                    raise OperationConflict(f"operation {operation_id!r} has different immutable inputs")
            else:
                self._db.execute("""INSERT INTO operations
                    (operation_id, branch, request, exposure_per_attempt, state)
                    VALUES(?,?,?,?, 'ready')""",
                    (operation_id, branch, bytes(request), exposure_per_attempt))
            self._db.execute("COMMIT")
        except (sqlite3.Error, OperationConflict) as exc:
            self._rollback()
            if isinstance(exc, OperationConflict):
                raise
            raise JournalError(f"operation registration failed: {exc}") from exc

    def execute(self, operation_id: str, *, callback: Callable[[bytes], HttpResponse],
                retry: RetryPolicy = RetryPolicy()) -> EffectResult:
        """Run a registered effect, resuming only a definitive 429 retry chain.

        The callback takes raw request bytes and returns HttpResponse. Any
        exception is treated as an unknown outcome; it must not hide retries.
        A `started` row found after restart is likewise converted to uncertain.
        """
        self._validate_policy(retry)
        op = self._get_operation(operation_id)
        if op is None:
            raise KeyError(operation_id)
        if op["state"] in ("succeeded", "failed", "uncertain"):
            return self.get_result(operation_id)
        self._bind_or_validate_policy(op, retry)
        op = self._get_operation(operation_id)
        if op["state"] == "started":
            latest = self._db.execute(
                "SELECT state, response_status, raw_response FROM attempts WHERE operation_id=? ORDER BY attempt_no DESC LIMIT 1",
                (operation_id,)).fetchone()
            if latest is not None and latest["state"] == "response":
                # Recover safely if the process stopped after saving a known
                # response but before finalizing it / scheduling a 429 retry.
                if latest["response_status"] == 200:
                    self._parse_after_success(operation_id, bytes(latest["raw_response"]))
                    return self.get_result(operation_id)
                if latest["response_status"] == 429 and retry.allow_429:
                    if op["attempts"] < min(retry.max_attempts, self.hard_max_attempts):
                        delay = self._backoff(retry, op["attempts"])
                        self._reset_ready_for_retry(operation_id)
                        self.sleep(delay)
                    else:
                        self._mark_failed(operation_id, "explicit HTTP 429 retries exhausted")
                        return self.get_result(operation_id)
                else:
                    self._mark_failed(operation_id, f"HTTP {latest['response_status']}")
                    return self.get_result(operation_id)
            else:
                self._mark_orphan_uncertain(operation_id)
                return self.get_result(operation_id)

        max_attempts = min(retry.max_attempts if retry.allow_429 else 1,
                           self.hard_max_attempts)
        while True:
            op = self._get_operation(operation_id)
            attempt_no = op["attempts"] + 1
            if attempt_no > max_attempts:
                self._mark_failed(operation_id, "explicit HTTP 429 retries exhausted")
                return self.get_result(operation_id)
            self._reserve_and_start(op, attempt_no)
            try:
                response = callback(bytes(op["request"]))
                if not isinstance(response, HttpResponse) or not isinstance(response.body, bytes):
                    raise TypeError("callback must return HttpResponse(status_code, body: bytes)")
                if not (100 <= response.status_code <= 599):
                    raise ValueError("callback returned invalid HTTP status")
            except Exception as exc:
                self._mark_uncertain(operation_id, attempt_no,
                                     type(exc).__name__)
                return self.get_result(operation_id)

            # Persist every response (especially exact 200 bytes) before parsing.
            self._save_response(operation_id, attempt_no, response)
            if response.status_code == 200:
                self._parse_after_success(operation_id, response.body)
                return self.get_result(operation_id)
            if response.status_code == 429:
                if retry.allow_429 and attempt_no < max_attempts:
                    self._reset_ready_for_retry(operation_id)
                    self.sleep(self._backoff(retry, attempt_no))
                    continue
                self._mark_failed(operation_id, "explicit HTTP 429 retries exhausted or unauthorized")
                return self.get_result(operation_id)
            self._mark_failed(operation_id, f"HTTP {response.status_code}")
            return self.get_result(operation_id)

    def get_result(self, operation_id: str) -> EffectResult:
        """Read and validate the durable operation and attempt journal."""
        op = self._get_operation(operation_id)
        if op is None:
            raise KeyError(operation_id)
        try:
            attempts = self._db.execute("SELECT * FROM attempts WHERE operation_id=? ORDER BY attempt_no",
                                        (operation_id,)).fetchall()
            if len(attempts) != op["attempts"]:
                raise JournalError("attempt count does not match operation journal")
            for i, attempt in enumerate(attempts, 1):
                if attempt["attempt_no"] != i:
                    raise JournalError("attempt sequence is not contiguous")
                if attempt["state"] == "response" and attempt["response_status"] is None:
                    raise JournalError("response attempt has no status")
            if op["state"] == "succeeded":
                if op["response_status"] != 200 or op["raw_response"] is None:
                    raise JournalError("successful effect is missing its raw 200 response")
                if op["parse_status"] not in ("valid_json", "invalid_json"):
                    raise JournalError("successful effect is missing parse status")
            return EffectResult(
                operation_id=operation_id, state=op["state"], attempts=op["attempts"],
                response_status=op["response_status"],
                raw_response=bytes(op["raw_response"]) if op["raw_response"] is not None else None,
                parse_status=op["parse_status"],
                parsed_json=json.loads(op["parsed_json"]) if op["parsed_json"] is not None else None,
                parse_error=op["parse_error"], error=op["error"])
        except sqlite3.Error as exc:
            raise JournalError(f"journal read failed: {exc}") from exc

    def accounting(self) -> dict:
        """Return validated lifetime calls/exposure and the configured hard caps."""
        try:
            cfg = self._db.execute("SELECT * FROM config WHERE singleton=1").fetchone()
            rows = self._db.execute("SELECT state, exposure_units FROM attempts").fetchall()
            calls = len(rows)
            exposure = sum(row["exposure_units"] for row in rows)
            if calls > cfg["call_cap"] or exposure > cfg["exposure_cap"]:
                raise JournalError("journal accounting exceeds configured hard cap")
            return {"calls": calls, "exposure_units": exposure,
                    "call_cap": cfg["call_cap"], "exposure_cap": cfg["exposure_cap"]}
        except sqlite3.Error as exc:
            raise JournalError(f"accounting read failed: {exc}") from exc

    def _validate_policy(self, policy: RetryPolicy) -> None:
        if not isinstance(policy, RetryPolicy):
            raise TypeError("retry must be a RetryPolicy")
        if policy.max_attempts < 1 or policy.max_attempts > self.hard_max_attempts:
            raise ValueError("retry max_attempts exceeds the executor hard maximum")
        if policy.base_backoff_seconds < 0 or policy.max_backoff_seconds < 0:
            raise ValueError("backoff values must be nonnegative")

    def _bind_or_validate_policy(self, op, policy: RetryPolicy) -> None:
        """Persist retry authority before the first callback is entered."""
        try:
            self._db.execute("BEGIN IMMEDIATE")
            current = self._db.execute("SELECT * FROM operations WHERE operation_id=?",
                                       (op["operation_id"],)).fetchone()
            if current is None:
                raise JournalError("operation disappeared before policy binding")
            if not current["retry_bound"]:
                if current["state"] != "ready" or current["attempts"] != 0:
                    raise JournalError("unbound retry policy found after dispatch started")
                self._checked_update("UPDATE operations SET retry_bound=1, retry_429_authorized=?, retry_max_attempts=?, retry_base_backoff=?, retry_max_backoff=? WHERE operation_id=? AND retry_bound=0 AND state='ready' AND attempts=0",
                                     (1 if policy.allow_429 else 0, policy.max_attempts,
                                      policy.base_backoff_seconds, policy.max_backoff_seconds,
                                      op["operation_id"]))
            elif (bool(current["retry_429_authorized"]) != policy.allow_429
                  or current["retry_max_attempts"] != policy.max_attempts
                  or current["retry_base_backoff"] != policy.base_backoff_seconds
                  or current["retry_max_backoff"] != policy.max_backoff_seconds):
                raise OperationConflict("retry policy differs from policy durably authorized before dispatch")
            self._db.execute("COMMIT")
        except (sqlite3.Error, JournalError, OperationConflict) as exc:
            self._rollback()
            if isinstance(exc, (JournalError, OperationConflict)):
                raise
            raise JournalError(f"retry policy binding failed: {exc}") from exc

    def _backoff(self, policy: RetryPolicy, attempt_no: int) -> float:
        ceiling = min(policy.max_backoff_seconds,
                     policy.base_backoff_seconds * (2 ** (attempt_no - 1)))
        value = float(self.rng())
        if not 0.0 <= value <= 1.0:
            raise ValueError("rng must return a number between 0 and 1")
        return ceiling * value

    def _get_operation(self, operation_id: str):
        try:
            return self._db.execute("SELECT * FROM operations WHERE operation_id=?",
                                    (operation_id,)).fetchone()
        except sqlite3.Error as exc:
            raise JournalError(f"operation read failed: {exc}") from exc

    def _reserve_and_start(self, op, attempt_no: int) -> None:
        try:
            self._db.execute("BEGIN IMMEDIATE")
            current = self._db.execute("SELECT * FROM operations WHERE operation_id=?",
                                       (op["operation_id"],)).fetchone()
            if current is None or current["state"] != "ready" or current["attempts"] + 1 != attempt_no:
                raise JournalError("operation state changed before dispatch")
            cfg = self._db.execute("SELECT * FROM config WHERE singleton=1").fetchone()
            agg = self._db.execute("SELECT COUNT(*) AS calls, COALESCE(SUM(exposure_units),0) AS exposure FROM attempts").fetchone()
            units = current["exposure_per_attempt"]
            if agg["calls"] + 1 > cfg["call_cap"] or agg["exposure"] + units > cfg["exposure_cap"]:
                self._db.execute("ROLLBACK")
                self._mark_failed(op["operation_id"], "hard cap prevents dispatch")
                raise BudgetExceeded("hard call or exposure cap prevents dispatch")
            self._db.execute("INSERT INTO attempts VALUES(?,?, 'started', ?, NULL, NULL, ?, NULL, NULL)",
                             (op["operation_id"], attempt_no, units, time.time()))
            self._checked_update("UPDATE operations SET state='started', attempts=? WHERE operation_id=? AND state='ready'",
                                 (attempt_no, op["operation_id"]))
            self._db.execute("COMMIT")
        except (sqlite3.Error, JournalError, BudgetExceeded) as exc:
            self._rollback()
            if isinstance(exc, (JournalError, BudgetExceeded)):
                raise
            raise JournalError(f"attempt reservation failed: {exc}") from exc

    def _save_response(self, operation_id: str, attempt_no: int, response: HttpResponse) -> None:
        try:
            self._db.execute("BEGIN IMMEDIATE")
            self._checked_update("UPDATE attempts SET state='response', response_status=?, raw_response=?, completed_at=? WHERE operation_id=? AND attempt_no=? AND state='started'",
                                 (response.status_code, sqlite3.Binary(response.body), time.time(), operation_id, attempt_no))
            self._checked_update("UPDATE operations SET response_status=?, raw_response=? WHERE operation_id=? AND state='started'",
                                 (response.status_code, sqlite3.Binary(response.body), operation_id))
            self._db.execute("COMMIT")
        except (sqlite3.Error, JournalError) as exc:
            self._rollback()
            if isinstance(exc, JournalError):
                raise
            raise JournalError(f"response write failed: {exc}") from exc

    def _parse_after_success(self, operation_id: str, body: bytes) -> None:
        try:
            parsed = json.loads(body.decode("utf-8"))
            parse_status, encoded, parse_error = "valid_json", json.dumps(parsed, separators=(",", ":")), None
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            parse_status, encoded, parse_error = "invalid_json", None, f"{type(exc).__name__}: {exc}"
        try:
            self._db.execute("BEGIN IMMEDIATE")
            self._checked_update("UPDATE operations SET state='succeeded', parse_status=?, parsed_json=?, parse_error=?, error=NULL WHERE operation_id=? AND state='started' AND response_status=200 AND raw_response=?",
                                 (parse_status, encoded, parse_error, operation_id, sqlite3.Binary(body)))
            self._db.execute("COMMIT")
        except (sqlite3.Error, JournalError) as exc:
            self._rollback()
            if isinstance(exc, JournalError):
                raise
            raise JournalError(f"parse status write failed: {exc}") from exc

    def _mark_uncertain(self, operation_id: str, attempt_no: int, error: str) -> None:
        try:
            self._db.execute("BEGIN IMMEDIATE")
            self._checked_update("UPDATE attempts SET state='uncertain', error=?, completed_at=? WHERE operation_id=? AND attempt_no=? AND state='started'",
                                 (error, time.time(), operation_id, attempt_no))
            self._checked_update("UPDATE operations SET state='uncertain', error=? WHERE operation_id=? AND state='started'",
                                 (error, operation_id))
            self._db.execute("COMMIT")
        except (sqlite3.Error, JournalError) as exc:
            self._rollback()
            if isinstance(exc, JournalError):
                raise
            raise JournalError(f"uncertain status write failed: {exc}") from exc

    def _mark_orphan_uncertain(self, operation_id: str) -> None:
        row = self._db.execute("SELECT attempt_no FROM attempts WHERE operation_id=? AND state='started' ORDER BY attempt_no DESC LIMIT 1",
                               (operation_id,)).fetchone()
        if row is None:
            raise JournalError("started operation has no started attempt")
        self._mark_uncertain(operation_id, row["attempt_no"], "process resumed after durable start; outcome unknown")

    def _reset_ready_for_retry(self, operation_id: str) -> None:
        try:
            self._db.execute("BEGIN IMMEDIATE")
            self._checked_update("UPDATE operations SET state='ready' WHERE operation_id=? AND state='started' AND response_status=429",
                                 (operation_id,))
            self._db.execute("COMMIT")
        except (sqlite3.Error, JournalError) as exc:
            self._rollback()
            if isinstance(exc, JournalError):
                raise
            raise JournalError(f"retry transition failed: {exc}") from exc

    def _mark_failed(self, operation_id: str, error: str) -> None:
        try:
            self._db.execute("BEGIN IMMEDIATE")
            self._checked_update("UPDATE operations SET state='failed', error=? WHERE operation_id=? AND state IN ('ready','started')",
                                 (error, operation_id))
            self._db.execute("COMMIT")
        except (sqlite3.Error, JournalError) as exc:
            self._rollback()
            if isinstance(exc, JournalError):
                raise
            raise JournalError(f"failure status write failed: {exc}") from exc

    def _checked_update(self, sql: str, params: tuple) -> None:
        cur = self._db.execute(sql, params)
        if cur.rowcount != 1:
            raise JournalError("journal update did not affect exactly one row")

    def _rollback(self) -> None:
        try:
            if self._db.in_transaction:
                self._db.execute("ROLLBACK")
        except sqlite3.Error:
            pass
