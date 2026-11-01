"""Accounting successor for the forecast pilot. No network or authority on import.

The previous run remains immutable. The only creation path is create-only and
requires an independently checked frozen execution contract. Operator tickets
are provenance and scope records, not a provider-enforced spending ceiling.
"""
from __future__ import annotations

import datetime as dt
from decimal import Decimal, InvalidOperation
import fcntl
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
for folder in ('budget-v2', 'source-successor', 'model-accounting-successor'):
    sys.path.insert(0, str(ROOT / folder))
from ledger import Ledger, Stop, canonical, digest, positive_int, valid_hash, now_utc
import model_accounting
import reopen

PARENT_SHA = '02b27728677f888986fa20885156a8e94cb544d4046ba7899e85277597e3a427'
SUMMARY_SHA = '8f2ae37a467defc0335a3932c9c0d678dde29592ca3e76e540daefbac34072a5'
PARENT_CONTRACT_SHA = '20f6508117e3460abb92af9fa0ee156b252d567c766cb5db7b68ee6365b6e67b'
PARENT_BINDING_SHA = '30659ae561996d2343aedbd9eee51aca907a2fb425bd62a5ce735abce4846836'
CLAIM = ROOT / 'forecast-budget-claims' / (PARENT_SHA + '.claim.json')
ALLOWED = {
    ('orthogonal', '/v1/run'): {'orthogonal_price_cents'},
    ('orthogonal', '/v1/search'): {'unknown_metadata'},
    ('orthogonal', '/v1/details'): {'unknown_metadata'},
    ('kalshi', '/trade-api/v2/markets'): {'free_public'},
    ('kalshi', '/trade-api/v2/events'): {'free_public'},
}


class AdmissionError(Stop):
    pass


def read(path, expected=None):
    p = Path(path)
    if not p.is_absolute() or p.is_symlink() or p.resolve() != p.absolute() or not p.is_file():
        raise AdmissionError('missing or unsafe artifact')
    data = p.read_bytes()
    if expected is not None and digest(data) != expected:
        raise AdmissionError('artifact digest mismatch')
    return data


def obj(raw):
    def pairs(items):
        out = {}
        for key, value in items:
            if key in out:
                raise AdmissionError('duplicate JSON key')
            out[key] = value
        return out
    try:
        result = json.loads(raw, object_pairs_hook=pairs)
    except (ValueError, TypeError, UnicodeDecodeError) as exc:
        raise AdmissionError('invalid JSON') from exc
    if not isinstance(result, dict):
        raise AdmissionError('JSON object required')
    return result


def inspect_parent():
    """Reconcile 105 settled generations and their predecessor, read-only."""
    prev = model_accounting.inspect_parent()
    summary = obj(read(ROOT/'live-model-successor-experiment-20261029-01/summary.json', SUMMARY_SHA))
    if (summary.get('requested_slots'), summary.get('attempted_slots'), summary.get('not_attempted_slots'), summary.get('stop_slot')) != (32, 32, 0, None):
        raise AdmissionError('predecessor results incomplete')
    read(ROOT/'successor-protocol/contract-frozen-v1.json', PARENT_CONTRACT_SHA)
    path = ROOT/'live-model-successor-ledger-20261029-01'
    db_path = path/'ledger.sqlite3'
    read(db_path, PARENT_SHA)
    cfg = obj(read(ROOT/'model-successor-ledger-contract-20261029.json', model_accounting.CONFIG_SHA))
    base = reopen._ReadOnlyBase(path, cfg)
    try:
        db = base.db
        if db.execute('SELECT stopped,exposure_micro,generation_attempts,count_attempts,source_attempts FROM run').fetchone() != (0, 1210590, 200, 132, 0):
            raise AdmissionError('predecessor counters mismatch')
        expected_summary = base.summary(); expected_summary.update(source_attempts=8, previous_source_attempts=8)
        if summary.get('ledger') != expected_summary:
            raise AdmissionError('predecessor summary mismatch')
        b, h = db.execute('SELECT contract,contract_hash FROM run WHERE id=1').fetchone()
        if bytes(b) != canonical(cfg) or h != digest(bytes(b)):
            raise AdmissionError('predecessor ledger contract mismatch')
        rows = db.execute('SELECT id,kind,state,http_status,request,request_hash,response,response_hash,quote_micro,actual_micro,related_id FROM effects ORDER BY rowid').fetchall()
        if len(rows) != 210:
            raise AdmissionError('unexpected predecessor effects')
        counts = {'count': 0, 'generation': 0}; costs = 0; counted = {}
        for ident, kind, state, status, req, rh, response, sh, reserve, actual, related in rows:
            if kind not in counts or state != 'succeeded' or status != 200 or not isinstance(req, bytes) or not isinstance(response, bytes) or digest(req) != rh or digest(response) != sh or type(actual) is not int or actual < 0:
                raise AdmissionError('unsettled or corrupt prior effect')
            counts[kind] += 1
            parsed = obj(response)
            if kind == 'count':
                if actual != 0 or not positive_int(parsed.get('totalTokens')):
                    raise AdmissionError('invalid prior count')
                counted[ident] = rh
            else:
                usage = parsed.get('usageMetadata', {}); prompt = usage.get('promptTokenCount'); total = usage.get('totalTokenCount')
                if (not positive_int(prompt) or not positive_int(total) or total < prompt or
                    parsed.get('modelVersion') != 'gemini-3.8-flash' or reserve != 86016 or
                    (3 * prompt + 15 * (total - prompt) + 1) // 2 != actual or counted.get(related) != rh):
                    raise AdmissionError('prior model usage or count binding mismatch')
                costs += actual
            events = db.execute('SELECT state,detail FROM events WHERE effect_id=? ORDER BY seq', (ident,)).fetchall()
            if events != [('prepared', None), ('started', None), ('succeeded', None), ('accounted', str(actual))]:
                raise AdmissionError('prior effect state mismatch')
        if counts != {'count': 105, 'generation': 105} or costs != 413023:
            raise AdmissionError('prior usage totals mismatch')
        if db.execute('SELECT event,reason FROM run_events ORDER BY seq').fetchall() != [('model_successor_started', PARENT_CONTRACT_SHA), ('runner_started', PARENT_BINDING_SHA)]:
            raise AdmissionError('prior event chain mismatch')
        read(db_path, PARENT_SHA)
    finally:
        base.close()
    return {'schema': 'faithful-forecast-parent-v1', 'parent_db_sha256': PARENT_SHA,
            'parent_summary_sha256': SUMMARY_SHA, 'parent_contract_sha256': PARENT_CONTRACT_SHA,
            'prior_micro': 1210590, 'prior_generations': 200, 'prior_counts': 132,
            'prior_sources': 8, 'prior_model_usage_micro': 413023,
            'previous_lineage': prev, 'new_uncertain_effects': 0}


class ForecastBase(Ledger):
    @staticmethod
    def _validate_contract(c):
        expected = obj(read(ROOT/'forecast-budget-v1/ledger_contract.json'))
        if c != expected or (c['cap_micro'], c['prior_micro'], c['prior_generations'], c['prior_counts'], c['max_generations'], c['max_counts'], c['max_sources'], c['source_cap_micro']) != (60000000, 1210590, 200, 132, 835, 767, 20, 3000000):
            raise ValueError('forecast contract or limits invalid')
        if (c['model'], c['location'], c['input_limit'], c['output_reserve'], c['max_output_tokens'], c['input_rate_half_micro'], c['output_rate_half_micro']) != ('gemini-3.8-flash', 'global', 16384, 8192, 4096, 3, 15):
            raise ValueError('forecast model or pricing mismatch')
        if not valid_hash(c['model_price_evidence_sha256']) or not valid_hash(c['count_price_evidence_sha256']):
            raise ValueError('model price evidence missing')


class ForecastLedger:
    def __init__(self, base, claim, parent, contract_path, contract_sha, verifier):
        self._base = base; self._claim_sha = digest(claim); self._parent = parent
        self._contract_path = Path(contract_path); self._contract_sha = contract_sha; self._verify_ticket = verifier

    @property
    def db(self): return self._base.db
    @property
    def root(self): return self._base.root
    @property
    def poisoned(self): return self._base.poisoned
    @poisoned.setter
    def poisoned(self, value): self._base.poisoned = value
    def close(self): self._base.close()
    def stop(self, reason): self._base.stop(reason)
    def summary(self):
        s = self._base.summary(); s['source_attempts'] += 8; s['previous_source_attempts'] = 8
        rows = self.db.execute("SELECT quote_metadata FROM effects WHERE kind='source'").fetchall()
        s['metadata_attempts'] = sum(1 for (v,) in rows if v and obj(v).get('category') == 'metadata')
        return s
    def verify_parent(self):
        read(CLAIM, self._claim_sha)
        if inspect_parent() != self._parent: raise AdmissionError('predecessor changed')
        return self._parent
    def _guard(self):
        try:
            self.verify_parent()
            read(self._contract_path, self._contract_sha)
            if self.db.execute("SELECT reason FROM run_events WHERE event='forecast_started'").fetchall() != [(self._contract_sha,)]:
                raise AdmissionError('forecast stage marker mismatch')
        except BaseException:
            try: self.stop('forecast lineage or contract changed')
            finally: self.poisoned = True
            raise
    def receipt(self, op):
        if op in {f'source:case-{i:02}:serper' for i in range(1, 9)}:
            self.verify_parent(); old = model_accounting._open_parent()
            try: return old.receipt(op)
            finally: old.close()
        return self._base.receipt(op)
    def count(self, *args, **kwargs): self._guard(); return self._base.count(*args, **kwargs)
    def generate(self, *args, **kwargs): self._guard(); return self._base.generate(*args, **kwargs)

    def source(self, op_id, provider, endpoint, request, ticket, transport):
        """Count every provider request, including metadata, in the 20 new sources.

        verify_ticket must bind operation, request and quoted source/expiry against
        a frozen scope; it is not proof of an enforced provider price ceiling.
        """
        self._guard()
        required = {'id', 'provider', 'endpoint', 'request_sha256', 'max_micro', 'evidence_sha256', 'expires_utc', 'category', 'settlement'}
        if not isinstance(ticket, dict) or set(ticket) != required or not isinstance(request, bytes) or not request or len(request) > 32768:
            raise AdmissionError('invalid operation ticket or request')
        if op_id in {f'source:case-{i:02}:serper' for i in range(1, 9)}:
            raise AdmissionError('historical source identity cannot be reused')
        if (ticket['id'], ticket['provider'], ticket['endpoint'], ticket['request_sha256']) != (op_id, provider, endpoint, digest(request)) or ticket['settlement'] not in ALLOWED.get((provider, endpoint), set()):
            raise AdmissionError('ticket operation mismatch')
        if ticket['category'] not in ('metadata', 'search', 'market', 'news', 'fetch') or (ticket['settlement'] == 'unknown_metadata') != (ticket['category'] == 'metadata'):
            raise AdmissionError('ticket category mismatch')
        if not positive_int(ticket['max_micro']) or ticket['max_micro'] > 150000 or not valid_hash(ticket['evidence_sha256']):
            raise AdmissionError('source price reservation invalid')
        try: expires = dt.datetime.fromisoformat(ticket['expires_utc'].replace('Z', '+00:00'))
        except (TypeError, ValueError, AttributeError): raise AdmissionError('invalid source expiry') from None
        if expires.tzinfo is None or expires <= dt.datetime.now(dt.timezone.utc): raise AdmissionError('expired source quote')
        if not callable(self._verify_ticket) or self._verify_ticket(ticket, request) is not True:
            raise AdmissionError('source ticket verification failed')
        raw = self._base._execute(op_id, 'source', provider, endpoint, request, ticket['max_micro'], ticket['evidence_sha256'], transport, quote_metadata=canonical(ticket))
        if ticket['settlement'] == 'unknown_metadata':
            self._base._stop(op_id, 'metadata charge unknown; reserve retained')
            raise Stop('metadata charge unknown; stop and reconcile')
        if ticket['settlement'] == 'free_public':
            amount = 0
        else:
            try:
                value = obj(raw)['priceCents']; cost = Decimal(str(value)) * 10000
                if not cost.is_finite() or cost < 0 or cost != cost.to_integral_value(): raise ValueError('invalid price')
                amount = int(cost)
            except (AdmissionError, KeyError, InvalidOperation, ValueError, TypeError):
                self._base._stop(op_id, 'source charge unavailable')
                raise Stop('source charge unknown; reserve retained') from None
        self._base._settle(op_id, amount)
        return raw


def create_successor(*, successor_root, claim_path, ledger_contract_path, run_contract_path, expected_contract_sha256, verify_challenge, verify_ticket):
    """Create the only successor for this predecessor; does not invoke providers."""
    parent = inspect_parent()
    cfg = obj(read(ledger_contract_path))
    ForecastBase._validate_contract(cfg)
    raw = read(run_contract_path, expected_contract_sha256); contract = obj(raw)
    caps = {'total_usd_micro': 60000000, 'total_generation_attempts': 835, 'total_count_attempts': 767, 'total_source_attempts': 28}
    if contract.get('schema') != 'faithful-forecast-run-contract-v1' or contract.get('status') != 'frozen' or contract.get('caps') != caps or contract.get('parent') != parent or contract.get('ledger_contract_sha256') != digest(read(ledger_contract_path)):
        raise AdmissionError('frozen run contract or prior binding mismatch')
    if not callable(verify_challenge) or verify_challenge(raw) is not True or not callable(verify_ticket):
        raise AdmissionError('independent challenge and ticket verifier required')
    root = Path(successor_root); claim = Path(claim_path)
    if not root.is_absolute() or root.parent.resolve() != root.parent.absolute() or root.exists() or claim != CLAIM or claim.parent.resolve() != claim.parent.absolute():
        raise AdmissionError('unsafe successor path or claim')
    claim_data = canonical({'schema': 'faithful-forecast-budget-claim-v1', 'parent': parent, 'ledger_root': str(root), 'run_contract_sha256': expected_contract_sha256})
    fd = os.open(claim, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_NOFOLLOW', 0), 0o600)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(claim_data); stream.flush(); os.fsync(stream.fileno())
    finally:
        pass
    fd = os.open(claim.parent, os.O_RDONLY)
    try: os.fsync(fd)
    finally: os.close(fd)
    base = ForecastBase(str(root), cfg, create=True)
    try:
        base.db.execute('BEGIN IMMEDIATE')
        base.db.execute("INSERT INTO run_events(event,reason,at_utc) VALUES ('forecast_started',?,?)", (expected_contract_sha256, now_utc()))
        base.db.execute('COMMIT')
        return ForecastLedger(base, claim_data, parent, run_contract_path, expected_contract_sha256, verify_ticket)
    except BaseException:
        if base.db.in_transaction: base.db.execute('ROLLBACK')
        base.close(); raise


def _check_resumable(base, cfg, run_contract_sha):
    """Reconcile all settled effects before a later phase; no pending retries."""
    db = base.db
    blob, stored_hash = db.execute('SELECT contract,contract_hash FROM run WHERE id=1').fetchone()
    if bytes(blob) != canonical(cfg) or stored_hash != digest(bytes(blob)):
        raise AdmissionError('successor accounting contract changed')
    if db.execute("SELECT reason FROM run_events WHERE event='forecast_started'").fetchall() != [(run_contract_sha,)]:
        raise AdmissionError('forecast stage identity mismatch')
    effects = db.execute('SELECT id,kind,provider,endpoint,state,http_status,request,request_hash,response,response_hash,actual_micro,related_id,quote_micro,quote_metadata FROM effects ORDER BY rowid').fetchall()
    counts = {'count': 0, 'generation': 0, 'source': 0}; actual_total = 0; source_total = 0; counts_by_id = {}; used_counts = set()
    for op_id, kind, provider, endpoint, state, status, request, request_hash, response, response_hash, actual, related_id, quote, meta in effects:
        if (kind not in counts or state != 'succeeded' or status != 200 or
            not isinstance(request, bytes) or not isinstance(response, bytes) or
            digest(request) != request_hash or digest(response) != response_hash or
            not positive_int(actual)):
            raise AdmissionError('unsettled, corrupt or unexpected successor effect')
        counts[kind] += 1; actual_total += actual
        events = db.execute('SELECT state,detail FROM events WHERE effect_id=? ORDER BY seq', (op_id,)).fetchall()
        if events != [('prepared',None), ('started',None), ('succeeded',None), ('accounted',str(actual))]:
            raise AdmissionError('effect transition chain mismatch')
        if kind == 'count':
            if actual != 0 or not positive_int(obj(response).get('totalTokens')): raise AdmissionError('bad count receipt')
            counts_by_id[op_id] = request_hash
        elif kind == 'generation':
            result = obj(response); u = result.get('usageMetadata', {}); p = u.get('promptTokenCount'); t = u.get('totalTokenCount')
            version = result.get('modelVersion')
            if (not positive_int(p) or not positive_int(t) or t < p or
                not isinstance(version, str) or not (version == cfg['model'] or version.startswith(cfg['model']+'-')) or
                p > cfg['input_limit'] or t-p > cfg['output_reserve'] or quote != 86016 or
                related_id in used_counts or counts_by_id.get(related_id) != request_hash or
                (3*p+15*(t-p)+1)//2 != actual):
                raise AdmissionError('bad model receipt')
            used_counts.add(related_id)
        elif kind == 'source':
            ticket = obj(meta)
            if (ticket.get('id'), ticket.get('provider'), ticket.get('endpoint'), ticket.get('request_sha256'), ticket.get('max_micro')) != (op_id, provider, endpoint, request_hash, quote):
                raise AdmissionError('source ticket mismatch')
            settlement = ticket.get('settlement')
            if settlement not in ALLOWED.get((provider,endpoint),set()) or settlement == 'unknown_metadata':
                raise AdmissionError('source settlement unavailable')
            if settlement == 'free_public':
                amount = 0
            else:
                try:
                    value = Decimal(str(obj(response)['priceCents']))*10000
                    if not value.is_finite() or value < 0 or value != value.to_integral_value(): raise ValueError('bad amount')
                    amount = int(value)
                except (KeyError, InvalidOperation, ValueError, TypeError):
                    raise AdmissionError('source billing invalid') from None
            if actual != amount or amount > quote: raise AdmissionError('source charge mismatch')
            source_total += amount
    expected = (0, cfg['prior_micro'] + actual_total, cfg['prior_generations'] + counts['generation'],
                cfg['prior_counts'] + counts['count'], counts['source'])
    actual_run = db.execute('SELECT stopped,exposure_micro,generation_attempts,count_attempts,source_attempts FROM run').fetchone()
    if actual_run != expected or expected[1] > cfg['cap_micro'] or expected[2] > cfg['max_generations'] or expected[3] > cfg['max_counts'] or expected[4] > cfg['max_sources'] or source_total > cfg['source_cap_micro']:
        raise AdmissionError('stopped ledger or counter/cost mismatch')


def reopen_successor(*, successor_root, claim_path, ledger_contract_path, run_contract_path, expected_contract_sha256, verify_challenge, verify_ticket):
    """Resume only settled, non-stopped same-run phases; never retry pending effects.

    Intended for a prospective wait between a registered t0 and t1, not for
    reusing an uncertain call. A new/changed protocol needs separate authority.
    """
    parent = inspect_parent(); cfg = obj(read(ledger_contract_path)); ForecastBase._validate_contract(cfg)
    raw = read(run_contract_path, expected_contract_sha256); contract = obj(raw)
    caps = {'total_usd_micro': 60000000, 'total_generation_attempts': 835, 'total_count_attempts': 767, 'total_source_attempts': 28}
    if contract.get('schema') != 'faithful-forecast-run-contract-v1' or contract.get('status') != 'frozen' or contract.get('caps') != caps or contract.get('parent') != parent or contract.get('ledger_contract_sha256') != digest(read(ledger_contract_path)):
        raise AdmissionError('run contract or prior binding mismatch')
    if not callable(verify_challenge) or verify_challenge(raw) is not True or not callable(verify_ticket):
        raise AdmissionError('review or ticket verifier required')
    root = Path(successor_root); claim = Path(claim_path)
    if not root.is_absolute() or root.is_symlink() or root.resolve() != root.absolute() or not root.is_dir() or claim != CLAIM:
        raise AdmissionError('unsafe successor path or claim')
    claim_data = read(claim)
    expected_claim = {'schema': 'faithful-forecast-budget-claim-v1', 'parent': parent, 'ledger_root': str(root), 'run_contract_sha256': expected_contract_sha256}
    if claim_data != canonical(expected_claim): raise AdmissionError('successor claim mismatch')
    ro = reopen._ReadOnlyBase(root, cfg)
    try: _check_resumable(ro, cfg, expected_contract_sha256)
    finally: ro.close()
    base = ForecastBase(str(root), cfg, create=False)
    try:
        _check_resumable(base, cfg, expected_contract_sha256)
        return ForecastLedger(base, claim_data, parent, run_contract_path, expected_contract_sha256, verify_ticket)
    except BaseException:
        base.close(); raise
