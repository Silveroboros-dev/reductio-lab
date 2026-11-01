"""Optional journal-backed callback for role requests.

The caller supplies an offline or separately authorized single-shot transport.
This adapter has no provider client and makes no network calls of its own. Its
request bytes are the complete versioned logical role request, not necessarily
the final provider wire body. Use one unique session_id per run and reuse it only to
replay the same sequence; EffectExecutor rejects changed requests for an ID.
"""
from __future__ import annotations

import copy
import hashlib
import json
import re
from typing import Callable

from reasoning_engine.executor import EffectExecutor, EffectResult, HttpResponse
from faithful_v3.prompts import build_request


class JournaledCallError(RuntimeError):
    """A role call did not yield a usable object; receipt is local journal evidence."""

    def __init__(self, kind: str, receipt: dict | None = None):
        super().__init__(kind)
        self.kind = kind
        self.receipt = copy.deepcopy(receipt)


def _object_without_duplicates(pairs):
    output = {}
    for key, value in pairs:
        if key in output:
            raise ValueError('duplicate JSON key')
        output[key] = value
    return output


def _reject_constant(_value):
    raise ValueError('non-finite JSON value')


class JournaledCallback:
    """Bind each role callback to a durable, at-most-once-on-ambiguity operation.

    Session IDs must be unique per run and are intentionally non-sensitive.
    Restarting with the same session ID safely replays the same ordered calls;
    changes in stage, payload, or exposure reject the reused operation. The
    executor assumes one active worker. Transport must itself perform no retry.
    A journal record is evidence of the callback's recorded result, not of
    provider billing or an independently authenticated response.
    """

    def __init__(self, executor: EffectExecutor, transport: Callable[[bytes], HttpResponse],
                 *, session_id: str, exposure_per_attempt: int = 1):
        if not isinstance(executor, EffectExecutor):
            raise ValueError('EffectExecutor required')
        if not callable(transport):
            raise ValueError('transport callback required')
        if not isinstance(session_id, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,64}', session_id):
            raise ValueError('session_id must be a non-sensitive opaque identifier')
        if type(exposure_per_attempt) is not int or exposure_per_attempt < 0:
            raise ValueError('exposure_per_attempt must be a nonnegative integer')
        self._executor = executor
        self._transport = transport
        self._session_id = session_id
        self._exposure = exposure_per_attempt
        self._ordinal = 0
        self._last_receipt = None

    @property
    def last_receipt(self) -> dict | None:
        """Return metadata only, without request, response, or exception text."""
        return copy.deepcopy(self._last_receipt)

    def _receipt(self, result: EffectResult, stage: str, ordinal: int,
                 request_hash: str) -> dict:
        return {'operation_id': result.operation_id, 'stage': stage, 'ordinal': ordinal,
                'state': result.state, 'attempts': result.attempts,
                'response_status': result.response_status, 'parse_status': result.parse_status,
                'request_sha256': request_hash}

    def __call__(self, stage: str, payload: dict) -> dict:
        self._last_receipt = None
        if not isinstance(stage, str) or not stage.strip() or not isinstance(payload, dict):
            raise ValueError('stage and object payload required')
        try:
            role_request = build_request(stage, payload)
            request = json.dumps(role_request, ensure_ascii=False,
                                 sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')
        except (TypeError, ValueError, UnicodeError) as exc:
            raise JournaledCallError('request_error') from exc
        self._ordinal += 1
        ordinal = self._ordinal
        operation_id = f'{self._session_id}:call:{ordinal}'
        request_hash = hashlib.sha256(request).hexdigest()
        try:
            # Branch binds the stage separately too. Reusing an ID with altered
            # request, stage or exposure is rejected before any callback.
            self._executor.register(operation_id, branch=stage, request=request,
                                    exposure_per_attempt=self._exposure)
        except Exception as exc:
            # Never attach a prior operation's receipt after a binding failure.
            raise JournaledCallError('journal_error') from exc
        try:
            result = self._executor.execute(operation_id, callback=self._transport)
        except Exception as exc:
            # An exception after registration may occur after the durable 200
            # write. Read, but do not execute or retry, to report what is known.
            try:
                result = self._executor.get_result(operation_id)
                self._last_receipt = self._receipt(result, stage, ordinal, request_hash)
            except Exception:
                self._last_receipt = None
            raise JournaledCallError('journal_error', self._last_receipt) from exc
        self._last_receipt = self._receipt(result, stage, ordinal, request_hash)
        if result.state == 'uncertain':
            raise JournaledCallError('uncertain', self._last_receipt)
        if result.state != 'succeeded':
            raise JournaledCallError('failed', self._last_receipt)
        try:
            if result.raw_response is None:
                raise ValueError('missing raw response')
            output = json.loads(result.raw_response.decode('utf-8'),
                                object_pairs_hook=_object_without_duplicates,
                                parse_constant=_reject_constant)
            if not isinstance(output, dict):
                raise ValueError('role response must be an object')
        except (UnicodeDecodeError, ValueError, TypeError) as exc:
            raise JournaledCallError('parse_error', self._last_receipt) from exc
        return output
