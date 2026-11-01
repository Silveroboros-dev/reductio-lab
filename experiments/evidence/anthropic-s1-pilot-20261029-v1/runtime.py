"""Isolated Vertex runtime for the Anthropic S-1 pilot.

This module does not dispatch on import or ledger construction. The caller must
freeze and challenge the corpus, schedule, prompts, and run contract before
calling ``generator``. Only the caller controls when a live transport is used.
Raw request/response bytes are stored in the mode-0600 single-writer SQLite
ledger before parsing. Accounting is conservative local exposure, not invoice.
"""
from __future__ import annotations
import hashlib
import importlib
import json
import sqlite3
import sys
import time
import subprocess
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Callable

ROOT = Path('/Users/rk/.codex/visualizations/2026/10/29/01a1865f-6bd2-75a2-abb1-eb14b071bbe0')
RESEARCH = ROOT / 'reasoning-research'
OLD = ROOT / 'faithful-dynamic-pilot'
PREDECESSOR = ROOT / 'reasoning-hard-si-20261029-v1'
PROJECT_SHA256 = '8a6a45a093d29e5424feb93ea2299e13faf1e8eac56604629ec4af4702e3bef0'
PRIOR_EXPOSURE_MICRO = 56_609_714
PRIOR_GENERATIONS = 1578
PRIOR_COUNTS = 1500
MAX_GENERATIONS = PRIOR_GENERATIONS + 130
MAX_COUNTS = PRIOR_COUNTS + 130
CAP_MICRO = 60_000_000
RESERVE_MICRO = 519_996

for path in (RESEARCH, OLD / 'forecast-p1-budget-successor-v1', OLD / 'transport'):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from reasoning_engine.vertex_adapter import canonical_json, build_generation_request
from research.retry_facade import ledger_class, RetryFacade
from hard_si.runtime import Adapter
from el.evals.faithful_engine.prompts import build_request, VERSION_V2


def _sha(path: Path) -> str:
    if not path.is_file() or path.is_symlink():
        raise ValueError('unsafe predecessor file')
    return hashlib.sha256(path.read_bytes()).hexdigest()


def predecessor_snapshot() -> dict[str, Any]:
    """Validate last durable counters and keep prior uncertain hashes forbidden."""
    contract_path = PREDECESSOR / 'contract.json'
    summary_path = PREDECESSOR / 'summary.json'
    db_path = PREDECESSOR / 'ledger' / 'ledger.sqlite3'
    contract = json.loads(contract_path.read_bytes())
    summary = json.loads(summary_path.read_bytes())
    db = sqlite3.connect('file:' + str(db_path) + '?mode=ro&immutable=1', uri=True)
    try:
        state = db.execute('SELECT stopped,exposure_micro,generation_attempts,count_attempts,source_attempts FROM run').fetchone()
        uncertain = db.execute("SELECT request_hash FROM effects WHERE state='uncertain'").fetchall()
    finally:
        db.close()
    if state != (1, PRIOR_EXPOSURE_MICRO, PRIOR_GENERATIONS, PRIOR_COUNTS, 0):
        raise ValueError('previous ledger state changed')
    s = summary['ledger']
    if (s['stopped'], s['exposure_micro'], s['generation_attempts'], s['count_attempts'], s['source_attempts']) != state:
        raise ValueError('previous summary does not match journal')
    if len(uncertain) != 1:
        raise ValueError('unexpected predecessor uncertain effects')
    forbidden = set(contract['lineage']['forbidden_uncertain_request_hashes']) | {row[0] for row in uncertain}
    if len(forbidden) != 3 or any(not isinstance(x, str) or len(x) != 64 for x in forbidden):
        raise ValueError('unexpected predecessor request hashes')
    return {
        'contract_sha256': _sha(contract_path), 'summary_sha256': _sha(summary_path),
        'ledger_sha256': _sha(db_path), 'forbidden_request_hashes': sorted(forbidden),
        'state': list(state),
    }


def config() -> dict[str, Any]:
    """Use the prior conservative output envelope and globally cumulative caps."""
    old = json.loads((PREDECESSOR / 'contract.json').read_bytes())['config']
    cfg = dict(old)
    cfg.update(run_id='anthropic-s1-pilot-20261029-v1', prior_micro=PRIOR_EXPOSURE_MICRO,
               prior_generations=PRIOR_GENERATIONS, prior_counts=PRIOR_COUNTS,
               max_generations=MAX_GENERATIONS, max_counts=MAX_COUNTS,
               cap_micro=CAP_MICRO, max_sources=1, source_cap_micro=10_000)
    if (cfg['model'], cfg['location'], cfg['input_limit'], cfg['output_reserve'],
        cfg['max_output_tokens'], cfg['input_rate_half_micro'], cfg['output_rate_half_micro']) != (
            'gemini-3.8-flash', 'global', 16384, 66056, 4096, 3, 15):
        raise ValueError('provider or token envelope drift')
    return cfg


def _new_ledger_class(retry: Any, cfg: dict):
    inherited = ledger_class(retry, cfg)
    class S1Ledger(inherited):
        @staticmethod
        def _validate_contract(value):
            if value != cfg or (value['prior_micro'], value['prior_generations'], value['prior_counts'],
                                value['max_generations'], value['max_counts'], value['cap_micro']) != (
                    PRIOR_EXPOSURE_MICRO, PRIOR_GENERATIONS, PRIOR_COUNTS,
                    MAX_GENERATIONS, MAX_COUNTS, CAP_MICRO):
                raise ValueError('S-1 provider or budget contract mismatch')
    return S1Ledger


def build_live_transport() -> Callable:
    """Construct credentialed one-shot transport; model calls happen only on use."""
    import google.auth
    from google.auth.transport.requests import Request
    from oneshot import OneShotTransport
    creds, project = google.auth.default(scopes=['https://www.googleapis.com/auth/cloud-platform'])
    if not project or hashlib.sha256(project.encode()).hexdigest() != PROJECT_SHA256:
        raise ValueError('Google project does not match prior project')
    def token(provider):
        if provider != 'vertex':
            raise ValueError('provider denied')
        if not creds.valid:
            creds.refresh(Request())
        if not creds.token:
            raise ValueError('Google credential unavailable')
        return creds.token
    return OneShotTransport(project, token)


def build_source_transport() -> Callable:
    """Construct Orthogonal transport; credential acquisition occurs on use."""
    from oneshot import OneShotTransport
    def token(provider):
        if provider != 'orthogonal':
            raise ValueError('provider denied')
        value = subprocess.run(['/usr/bin/security', 'find-generic-password', '-s',
                                'com.maguire.orthogonal.live', '-a', 'maguire', '-w'],
                               stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                               check=False, timeout=15)
        if value.returncode or not value.stdout.strip():
            raise ValueError('Orthogonal credential unavailable')
        return value.stdout.strip().decode('ascii')
    return OneShotTransport('source-only-123', token)


class Runtime:
    """Serial exact-request runtime. Supply an injected one-shot transport.

    ``generator(case_id, arm)`` returns the engine callback. Arm is A, B, C,
    or probe. Each pair may be registered once; every invocation is a separate
    operation, includes a counted input and settles from captured usage. Use a
    new case ID for independent tasks; no conversation history is carried.
    """
    _tags = {'A': 'B', 'B': 'B_self', 'C': 'C', 'probe': 'C'}
    def __init__(self, ledger_dir: str | Path, *, transport: Callable, sleep: Callable = time.sleep, resume: bool = False, _testing: bool = False):
        allowed = ROOT / 'anthropic-s1-pilot-20261029-v1' / 'ledger'
        if not _testing and Path(ledger_dir).absolute() != allowed:
            raise ValueError('exact single-run ledger path required')
        if not callable(transport) or not callable(sleep):
            raise ValueError('one-shot transport and sleep required')
        self.snapshot = predecessor_snapshot()
        self.cfg = config()
        retry = importlib.import_module('p1_retry')
        # One exact repeat per 429; at most 28 retries within physical caps.
        retry.MAX_EXTRA = 28
        ledger_cls = _new_ledger_class(retry, self.cfg)
        self.ledger = ledger_cls(str(Path(ledger_dir).absolute()), self.cfg, create=not resume)
        if resume:
            try:
                self._verify_source_resume()
            except BaseException:
                self.ledger.close()
                raise
        if self.ledger._model_bound() != RESERVE_MICRO:
            self.ledger.close()
            raise ValueError('unexpected generation reservation')
        self.transport = transport
        self._sleep = sleep
        self.adapter = Adapter(RetryFacade(self.ledger, retry, sleep=sleep), self._guarded_transport)
        self._registered: set[tuple[str,str]] = set()
        self._last_end = 0.0

    def _verify_source_resume(self):
        """Only accept one completely captured and settled source-only effect."""
        if predecessor_snapshot() != self.snapshot:
            raise ValueError('predecessor changed before resume')
        state = self.ledger.summary()
        rows = self.ledger.db.execute("select id,kind,provider,endpoint,request,request_hash,quote_micro,quote_evidence_sha,state,http_status,response,response_hash,actual_micro,quote_metadata from effects order by rowid").fetchall()
        if len(rows) != 1 or (state['stopped'], state['generation_attempts'], state['count_attempts'], state['source_attempts']) != (0, PRIOR_GENERATIONS, PRIOR_COUNTS, 1):
            raise ValueError('resume requires exactly one settled source and no model activity')
        ident,kind,provider,endpoint,request,request_hash,quote,proof,status,http,response,response_hash,actual,metadata=rows[0]
        expected=canonical_json({'api':'serper','path':'/news','body':{'q':'Anthropic IPO S-1 compute obligations governance','num':3},'query':{}})
        if (ident,kind,provider,endpoint,quote,status,http)!=( 'source:s1:serper-news:001','source','orthogonal','/v1/run',10_000,'succeeded',200):
            raise ValueError('invalid source receipt identity or status')
        if not isinstance(actual,int) or actual<0 or actual>10_000 or bytes(request)!=expected or hashlib.sha256(bytes(request)).hexdigest()!=request_hash:
            raise ValueError('source request or actual cost invalid')
        if response is None or hashlib.sha256(bytes(response)).hexdigest()!=response_hash:
            raise ValueError('source response digest invalid')
        try:
            data=json.loads(response);meta=json.loads(metadata)
            quoted=Decimal(str(data['priceCents']))*10000
            charged=Decimal(str(data['billing']['chargedPriceCents']))*10000
            if data.get('success') is not True or not quoted.is_finite() or charged!=quoted or charged!=actual:
                raise ValueError('source billing invalid')
            if meta.get('request_sha256')!=request_hash or meta.get('price_evidence_sha256')!=proof or meta.get('max_micro')!=10000:
                raise ValueError('source provenance metadata invalid')
        except (KeyError,TypeError,ValueError,InvalidOperation,json.JSONDecodeError):
            raise ValueError('source receipt cannot be reconciled') from None
        events=self.ledger.db.execute('select state,detail from events where effect_id=? order by seq',(ident,)).fetchall()
        if events != [('prepared',None),('started',None),('succeeded',None),('accounted',str(actual))]:
            raise ValueError('source receipt transition invalid')
        if state['exposure_micro'] != PRIOR_EXPOSURE_MICRO+actual:
            raise ValueError('source exposure was not carried correctly')

    def _guarded_transport(self, provider: str, endpoint: str, raw: bytes):
        if provider != 'vertex' or endpoint not in ('countTokens', 'gemini-3.8-flash@global'):
            raise ValueError('provider endpoint denied')
        if predecessor_snapshot() != self.snapshot:
            raise ValueError('predecessor changed after run construction')
        if hashlib.sha256(raw).hexdigest() in self.snapshot['forbidden_request_hashes']:
            raise ValueError('prior uncertain request is forbidden')
        # A one-second serial gap is a pacing measure, not a retry.
        delay = 1.0 - (time.monotonic() - self._last_end)
        if delay > 0:
            self._sleep(delay)
        try:
            return self.transport(provider, endpoint, raw)
        finally:
            self._last_end = time.monotonic()

    def fetch_serper_news(self, *, price_evidence_sha256: str, transport: Callable) -> bytes:
        """One source request before models; persist effect and exact provider charge.

        The caller must bind a fresh public/catalog price observation and the
        exact request in the separately frozen scope before dispatch. The local
        reserve is a budget admission rule, not a provider-enforced price cap.
        No automatic retry is permitted for any source outcome.
        """
        if not callable(transport) or not isinstance(price_evidence_sha256, str) or len(price_evidence_sha256) != 64:
            raise ValueError('one-shot transport and price evidence digest required')
        try:
            int(price_evidence_sha256, 16)
        except ValueError:
            raise ValueError('invalid price evidence digest') from None
        if self.ledger.db.execute("select 1 from effects where kind in ('generation','count','source') limit 1").fetchone():
            raise ValueError('source operation must be first and is single-use')
        if predecessor_snapshot() != self.snapshot:
            raise ValueError('predecessor changed before source')
        payload = {'api':'serper','path':'/news','body':{'q':'Anthropic IPO S-1 compute obligations governance','num':3},'query':{}}
        raw_request = canonical_json(payload)
        if hashlib.sha256(raw_request).hexdigest() in self.snapshot['forbidden_request_hashes']:
            raise ValueError('prior uncertain request is forbidden')
        op = 'source:s1:serper-news:001'
        metadata = canonical_json({'purpose':'Anthropic S-1 evidence discovery','max_micro':10_000,
                                   'request_sha256':hashlib.sha256(raw_request).hexdigest(),
                                   'price_evidence_sha256':price_evidence_sha256})
        raw = self.ledger._execute(op, 'source', 'orthogonal', '/v1/run', raw_request,
                                   10_000, price_evidence_sha256, transport, quote_metadata=metadata)
        try:
            data = json.loads(raw)
            quoted = Decimal(str(data['priceCents'])) * 10000
            charged = Decimal(str(data['billing']['chargedPriceCents'])) * 10000
            if not quoted.is_finite() or not charged.is_finite() or charged < 0 or quoted < 0 or charged != charged.to_integral_value() or quoted != quoted.to_integral_value() or quoted != charged:
                raise ValueError('source billing mismatch')
            amount = int(charged)
        except (KeyError, TypeError, ValueError, InvalidOperation, json.JSONDecodeError):
            self.ledger._stop(op, 'source billing invalid; reservation retained')
            raise ValueError('source billing unknown; run stopped') from None
        self.ledger._settle(op, amount)
        if data.get('success') is not True:
            self.ledger.stop('source returned unsuccessful result')
            raise ValueError('source unsuccessful; charged amount retained')
        return raw

    def generator(self, case_id: str, arm: str):
        if not isinstance(case_id, str) or not case_id or arm not in self._tags:
            raise ValueError('case and admitted arm required')
        pair = (case_id, arm)
        if pair in self._registered:
            raise ValueError('case/arm already registered in this runtime')
        self._registered.add(pair)
        slot = hashlib.sha256(canonical_json({'case_id': case_id, 'arm': arm, 'pilot': 'anthropic-s1-v1'})).hexdigest()
        ordinal = 0
        def callback(stage: str, payload: dict) -> dict:
            nonlocal ordinal
            ordinal += 1
            if ordinal > 999:
                raise ValueError('ordinal cap')
            request = build_request(stage, payload, prompt_version=VERSION_V2)
            body = build_generation_request(request)
            if hashlib.sha256(canonical_json(body)).hexdigest() in self.snapshot['forbidden_request_hashes']:
                raise ValueError('prior uncertain request is forbidden')
            op = f'{slot}:{self._tags[arm]}:{ordinal:03d}'
            return self.adapter.complete(request, op, 'LOW').content
        return callback

    def summary(self):
        result = self.ledger.summary()
        result['new_generation_attempts'] = result['generation_attempts'] - PRIOR_GENERATIONS
        result['new_count_attempts'] = result['count_attempts'] - PRIOR_COUNTS
        result['new_exposure_micro'] = result['exposure_micro'] - PRIOR_EXPOSURE_MICRO
        result['remaining_micro'] = CAP_MICRO - result['exposure_micro']
        return result

    def close(self):
        self.ledger.close()
