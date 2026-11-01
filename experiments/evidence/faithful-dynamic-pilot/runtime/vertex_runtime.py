"""Offline-only, injected-transport Vertex accounting prototype; NOT a live executor."""
from __future__ import annotations

import hashlib
import json
import os
import threading
import uuid
from pathlib import Path

PRIOR_MICRO = 721_593
INPUT_LIMIT = 16_384
OUTPUT_RESERVE = 8_192
RESERVE_MICRO = 86_016  # 16384 * $1.50/M + 8192 * $7.50/M

class RuntimeStop(Exception):
    pass

class UncertainEffect(RuntimeStop):
    pass

class OutputError(RuntimeStop):
    pass


def _json_bytes(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'), sort_keys=True).encode('utf-8')


def _fsync_dir(path):
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


class VertexRuntime:
    """Single-process, non-resumable demonstration; transport must be injected.

    transport(operation, model, request_body) returns (HTTP status, raw bytes).
    Effects other than this transport are NOT budgeted or journaled. Never use live.
    """
    def __init__(self, directory, transport, model, *, prior_micro=PRIOR_MICRO,
                 external_reserve_micro=5_000_000, cap_micro=40_000_000,
                 previous_generations=79, max_generations=835,
                 previous_counts=11, max_counts=767):
        if not callable(transport) or not isinstance(model, str) or not model:
            raise ValueError('transport and pinned model required')
        values = (prior_micro, external_reserve_micro, cap_micro, previous_generations,
                  max_generations, previous_counts, max_counts)
        if any(not isinstance(x, int) or isinstance(x, bool) or x < 0 for x in values):
            raise ValueError('limits must be nonnegative integers')
        self.directory = Path(directory)
        if self.directory.parent.resolve() != self.directory.parent.absolute():
            raise ValueError('symlink parent rejected')
        os.mkdir(self.directory, 0o700)  # existing ledger is never resumed or replaced
        _fsync_dir(self.directory.parent)
        self.journal_path = self.directory / 'events.jsonl'
        self.fd = os.open(self.journal_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        _fsync_dir(self.directory)
        self.transport, self.model = transport, model
        self.prior_micro, self.external_reserve_micro, self.cap_micro = prior_micro, external_reserve_micro, cap_micro
        self.exposure_micro = prior_micro + external_reserve_micro
        self.generations, self.max_generations = previous_generations, max_generations
        self.counts, self.max_counts = previous_counts, max_counts
        self.stopped = False
        self.lock = threading.Lock()
        self._event({'state':'initialized', 'prior_micro':prior_micro, 'external_reserve_micro':external_reserve_micro,
                     'cap_micro':cap_micro, 'previous_generations':previous_generations,
                     'max_generations':max_generations, 'previous_counts':previous_counts,
                     'max_counts':max_counts, 'model':model})

    def _event(self, event):
        try:
            data = _json_bytes(event) + b'\n'
            offset = 0
            while offset < len(data):
                n = os.write(self.fd, data[offset:])
                if n <= 0:
                    raise OSError('journal short write')
                offset += n
            os.fsync(self.fd)
        except BaseException:
            self.stopped = True
            raise

    def _capture(self, opid, raw):
        name = opid + '.response.json'
        fd = os.open(self.directory / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            offset = 0
            while offset < len(raw):
                n = os.write(fd, raw[offset:])
                if n <= 0:
                    raise OSError('response short write')
                offset += n
            os.fsync(fd)
        finally:
            os.close(fd)
        _fsync_dir(self.directory)
        return name

    def close(self):
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None

    def _request(self, operation, body, *, case_id, stage):
        if self.stopped:
            raise RuntimeStop('runtime stopped; no resume or retry')
        if not isinstance(case_id, str) or not case_id or not isinstance(stage, str) or not stage:
            raise ValueError('case_id and stage required')
        body_bytes = _json_bytes(body)
        generation = operation == 'generateContent'
        if generation:
            if self.generations >= self.max_generations or self.exposure_micro + RESERVE_MICRO > self.cap_micro:
                raise RuntimeStop('generation or conservative budget cap')
        elif operation == 'countTokens':
            if self.counts >= self.max_counts:
                raise RuntimeStop('countTokens cap')
        else:
            raise ValueError('unsupported operation')
        opid = uuid.uuid4().hex
        common = {'id':opid, 'operation':operation, 'case_id':case_id, 'stage':stage,
                  'model':self.model, 'request_sha256':hashlib.sha256(body_bytes).hexdigest()}
        self._event({**common, 'state':'prepared'})
        if generation:
            self.generations += 1
            self.exposure_micro += RESERVE_MICRO
        else:
            self.counts += 1
        self._event({**common, 'state':'started', 'exposure_micro':self.exposure_micro})
        try:
            status, raw = self.transport(operation, self.model, json.loads(body_bytes))
            if not isinstance(status, int) or isinstance(status, bool) or not isinstance(raw, bytes):
                raise TypeError('transport must return (int, bytes)')
        except BaseException as exc:
            self.stopped = True
            self._event({**common, 'state':'uncertain', 'error_type':type(exc).__name__,
                         'exposure_micro':self.exposure_micro})
            raise UncertainEffect('transport failed after started; no retry') from exc
        try:
            path = self._capture(opid, raw)
        except BaseException as exc:
            self.stopped = True
            self._event({**common, 'state':'succeeded', 'http_status':status, 'capture':'failed',
                         'error_type':type(exc).__name__, 'exposure_micro':self.exposure_micro})
            raise RuntimeStop('response received but evidence capture failed; reserve retained') from exc
        self._event({**common, 'state':'succeeded', 'http_status':status, 'capture':path,
                     'response_sha256':hashlib.sha256(raw).hexdigest(), 'exposure_micro':self.exposure_micro})
        if status != 200:
            self.stopped = True
            raise RuntimeStop('non-200 response; reserve retained; run stopped')
        try:
            response = json.loads(raw)
            if not isinstance(response, dict):
                raise ValueError('response must be object')
        except (ValueError, UnicodeDecodeError) as exc:
            self.stopped = True
            raise OutputError('response invalid JSON; reserve retained') from exc
        return common, response

    def count_tokens(self, body, *, case_id, stage):
        with self.lock:
            common, response = self._request('countTokens', body, case_id=case_id, stage=stage)
            total = response.get('totalTokens')
            if not isinstance(total, int) or isinstance(total, bool) or total < 0:
                self.stopped = True
                raise OutputError('invalid countTokens result')
            self._event({**common, 'state':'accounted', 'counted_tokens':total})
            return total

    def generate(self, body, *, case_id, stage):
        with self.lock:
            # Copy once so the counted request cannot be mutated between operations.
            body = json.loads(_json_bytes(body))
            if 'model' in body:
                raise ValueError('body.model is forbidden; pinned model is supplied separately')
            config = body.get('generationConfig', {})
            if config.get('maxOutputTokens') != 4096:
                raise ValueError('generationConfig.maxOutputTokens must be 4096')
            if self.stopped:
                raise RuntimeStop('runtime stopped; no resume or retry')
            if self.generations >= self.max_generations or self.exposure_micro + RESERVE_MICRO > self.cap_micro:
                raise RuntimeStop('generation or conservative budget cap')
            count_body = {'generateContentRequest': {'model': self.model, **body}}
            counted, result = self._request('countTokens', count_body, case_id=case_id, stage=stage)
            total_count = result.get('totalTokens')
            if not isinstance(total_count, int) or isinstance(total_count, bool) or total_count < 0:
                self.stopped = True
                raise OutputError('invalid countTokens result')
            self._event({**counted, 'state':'accounted', 'counted_tokens':total_count})
            if total_count > INPUT_LIMIT:
                opid = uuid.uuid4().hex
                self._event({'id':opid, 'state':'failed_before_effect', 'operation':'generateContent',
                             'case_id':case_id, 'stage':stage, 'reason':'countTokens cap',
                             'counted_tokens':total_count})
                raise RuntimeStop('input exceeds token cap; generation not started')
            common, response = self._request('generateContent', body, case_id=case_id, stage=stage)
            usage = response.get('usageMetadata')
            try:
                prompt, total = usage['promptTokenCount'], usage['totalTokenCount']
                thought = usage.get('thoughtsTokenCount')
                thought_for_validation = 0 if thought is None else thought
                output = total - prompt
                if any(not isinstance(v, int) or isinstance(v, bool) or v < 0 for v in (prompt, total, output, thought_for_validation)) or thought_for_validation > output:
                    raise ValueError('invalid usage')
            except (TypeError, KeyError, ValueError):
                self.stopped = True
                self._event({**common, 'state':'usage_unknown', 'exposure_micro':self.exposure_micro})
                raise OutputError('usage unavailable; reserve retained')
            cost = (3 * prompt + 15 * output + 1) // 2
            self.exposure_micro += cost - RESERVE_MICRO
            self._event({**common, 'state':'accounted', 'prompt_tokens':prompt, 'total_tokens':total,
                         'output_including_thought_tokens':output, 'thought_tokens':thought,
                         'cost_micro':cost, 'exposure_micro':self.exposure_micro})
            if prompt > INPUT_LIMIT or output > OUTPUT_RESERVE or self.exposure_micro > self.cap_micro:
                self.stopped = True
                raise RuntimeStop('actual usage exceeded reserve; stop')
            return response
