"""Single-run SQLite accounting primitive; injected transport, no network clients.

This ledger enforces local reservations against a caller-supplied price and token
contract. It does not establish that the contract matches a provider's bill.
"""
from __future__ import annotations
import hashlib
import json
import math
import os
import sqlite3
import fcntl
import datetime as dt
from pathlib import Path

PRIOR_MICRO = 721_593
CAP_MICRO = 40_000_000

class Stop(RuntimeError): pass
class UnknownEffect(Stop): pass

def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def valid_hash(value: str) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(c in '0123456789abcdef' for c in value)

def canonical(value) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()

def positive_int(x):
    return type(x) is int and x >= 0

def now_utc():
    return dt.datetime.now(dt.timezone.utc).isoformat()

class Ledger:
    """Exclusive single-run ledger. Close/reopen are supported; no retry after started crash.

    All effects and continuation decisions must be routed through this object.
    A price contract is immutable after initial creation. `transport` has to be
    one-shot and not retry; its trustworthiness is outside this class.
    """
    def __init__(self, directory: str, contract: dict, *, create: bool):
        contract = json.loads(canonical(contract))
        self.root = Path(directory)
        if self.root.parent.resolve() != self.root.parent.absolute():
            raise ValueError('symlinked parent rejected')
        if create:
            self.root.mkdir(mode=0o700)
        elif not self.root.is_dir() or self.root.is_symlink():
            raise ValueError('missing or symlinked ledger root')
        self.lock_fd = os.open(self.root / 'owner.lock', os.O_CREAT | os.O_RDWR | getattr(os, 'O_NOFOLLOW', 0), 0o600)
        try:
            fcntl.flock(self.lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BaseException:
            os.close(self.lock_fd)
            raise Stop('ledger already in use')
        self.db = None
        self.poisoned = False
        try:
            path = self.root / 'ledger.sqlite3'
            if path.is_symlink() or (create and path.exists()) or (not create and not path.exists()):
                raise ValueError('invalid ledger path')
            self.db = sqlite3.connect(path, isolation_level=None)
            os.chmod(path, 0o600)
            self.db.execute('PRAGMA journal_mode=DELETE')
            self.db.execute('PRAGMA synchronous=FULL')
            if create:
                self._validate_contract(contract)
                self.db.executescript('''CREATE TABLE run (id INTEGER PRIMARY KEY CHECK(id=1), contract BLOB NOT NULL, contract_hash TEXT NOT NULL, stopped INTEGER NOT NULL, exposure_micro INTEGER NOT NULL, generation_attempts INTEGER NOT NULL, count_attempts INTEGER NOT NULL, source_attempts INTEGER NOT NULL); CREATE TABLE effects (id TEXT PRIMARY KEY, kind TEXT NOT NULL, provider TEXT NOT NULL, endpoint TEXT NOT NULL, request BLOB NOT NULL, request_hash TEXT NOT NULL, quote_micro INTEGER NOT NULL, quote_evidence_sha TEXT NOT NULL, state TEXT NOT NULL, http_status INTEGER, response BLOB, response_hash TEXT, actual_micro INTEGER, detail TEXT, related_id TEXT, quote_metadata BLOB, started_at_utc TEXT NOT NULL, completed_at_utc TEXT); CREATE TABLE events (seq INTEGER PRIMARY KEY AUTOINCREMENT, effect_id TEXT NOT NULL, state TEXT NOT NULL, detail TEXT); CREATE TABLE run_events (seq INTEGER PRIMARY KEY AUTOINCREMENT, event TEXT NOT NULL, reason TEXT NOT NULL, at_utc TEXT NOT NULL);''')
                b = canonical(contract)
                self.db.execute('INSERT INTO run VALUES (1,?,?,0,?,?,?,0)', (b, digest(b), contract['prior_micro'], contract['prior_generations'], contract['prior_counts']))
            else:
                b, h = self.db.execute('SELECT contract,contract_hash FROM run WHERE id=1').fetchone()
                if digest(bytes(b)) != h or canonical(contract) != bytes(b):
                    raise Stop('contract drift or corruption')
                self.db.execute('BEGIN IMMEDIATE')
                pending = self.db.execute("SELECT COUNT(*) FROM effects WHERE state IN ('prepared','started')").fetchone()[0]
                unsettled = self.db.execute("SELECT COUNT(*) FROM effects WHERE state='succeeded' AND actual_micro IS NULL").fetchone()[0]
                if pending or unsettled:
                    self.db.execute("INSERT INTO events(effect_id,state,detail) SELECT id,'uncertain','process restart' FROM effects WHERE state IN ('prepared','started')")
                    self.db.execute("UPDATE effects SET state='uncertain',detail='process restarted after preparation/start' WHERE state IN ('prepared','started')")
                    self.db.execute("UPDATE effects SET detail='process restarted after succeeded but before settlement' WHERE state='succeeded' AND actual_micro IS NULL")
                    self.db.execute('UPDATE run SET stopped=1 WHERE id=1')
                self.db.execute('COMMIT')
            self._contract = contract
        except BaseException:
            if self.db is not None: self.db.close()
            fcntl.flock(self.lock_fd, fcntl.LOCK_UN)
            os.close(self.lock_fd)
            raise

    @staticmethod
    def _validate_contract(c):
        required = ('run_id','cap_micro','prior_micro','prior_generations','prior_counts','max_generations','max_counts','max_sources','source_cap_micro','model','location','input_limit','output_reserve','max_output_tokens','input_rate_half_micro','output_rate_half_micro','model_price_evidence_sha256','count_price_evidence_sha256')
        if not isinstance(c, dict) or set(c) != set(required): raise ValueError('exact contract keys required')
        for k in ('run_id','model','location'):
            if not isinstance(c[k],str) or not c[k]: raise ValueError('invalid contract identity')
        for k in ('model_price_evidence_sha256','count_price_evidence_sha256'):
            if not valid_hash(c[k]): raise ValueError('price evidence digest required')
        for k in set(required) - {'run_id','model','location','model_price_evidence_sha256','count_price_evidence_sha256'}:
            if not positive_int(c[k]): raise ValueError('nonnegative integer contract required')
        if c['cap_micro'] > CAP_MICRO or c['prior_micro'] < PRIOR_MICRO or c['prior_micro'] > c['cap_micro']:
            raise ValueError('total cap or prior exposure invalid')
        if c['prior_generations'] < 79 or c['prior_counts'] < 11 or c['max_generations'] > 835 or c['max_counts'] > 767 or c['max_sources'] > 18 or c['source_cap_micro'] > 5_000_000:
            raise ValueError('authorized operation ceilings exceeded')
        if c['prior_generations'] > c['max_generations'] or c['prior_counts'] > c['max_counts'] or c['output_reserve'] < c['max_output_tokens']:
            raise ValueError('inconsistent ceilings')
        if c['model'] != 'gemini-3.8-flash' or c['location'] != 'global' or c['input_rate_half_micro'] < 3 or c['output_rate_half_micro'] < 15 or c['max_output_tokens'] != 4096 or c['output_reserve'] < 8192 or c['input_limit'] > 16384 or not c['input_limit']:
            raise ValueError('model, region, conservative rate or token bound mismatch')

    def close(self):
        if self.db is not None:
            self.db.close(); self.db = None
            fcntl.flock(self.lock_fd, fcntl.LOCK_UN); os.close(self.lock_fd)

    def summary(self):
        r=self.db.execute('SELECT stopped,exposure_micro,generation_attempts,count_attempts,source_attempts FROM run').fetchone()
        result=dict(zip(('stopped','exposure_micro','generation_attempts','count_attempts','source_attempts'),r))
        count, retained = self.db.execute("SELECT COUNT(*),COALESCE(SUM(CASE WHEN actual_micro IS NULL THEN quote_micro ELSE 0 END),0) FROM effects WHERE kind='metadata'").fetchone()
        result.update(metadata_attempts=count, metadata_retained_micro=retained)
        return result

    def stop(self, reason):
        """Permanently stop after an external adapter's post-effect gate fails."""
        if not isinstance(reason,str) or not reason or len(reason)>200: raise ValueError('short reason required')
        self.db.execute('BEGIN IMMEDIATE')
        try:
            self.db.execute("INSERT INTO run_events(event,reason,at_utc) VALUES ('stopped',?,?)",(reason,now_utc()))
            self.db.execute('UPDATE run SET stopped=1 WHERE id=1')
            self.db.execute('COMMIT')
        except BaseException:
            self.poisoned = True
            if self.db.in_transaction: self.db.execute('ROLLBACK')
            raise

    def receipt(self, op_id):
        fields=('id','kind','provider','endpoint','request','request_hash','quote_micro','quote_evidence_sha','state','http_status','response','response_hash','actual_micro','detail','related_id','quote_metadata','started_at_utc','completed_at_utc')
        row=self.db.execute('SELECT '+','.join(fields)+' FROM effects WHERE id=?',(op_id,)).fetchone()
        if row is None: raise KeyError(op_id)
        return dict(zip(fields,row))

    def _model_bound(self):
        c=self._contract
        return (c['input_limit']*c['input_rate_half_micro']+c['output_reserve']*c['output_rate_half_micro']+1)//2

    def _start(self, op_id, kind, provider, endpoint, request, quote, proof, related_id=None, quote_metadata=None):
        if self.poisoned: raise Stop('journal failure; object cannot continue')
        registered = self.db.execute('SELECT contract_hash FROM run WHERE id=1').fetchone()
        if registered is None or digest(canonical(self._contract)) != registered[0]:
            self.poisoned = True
            raise Stop('immutable price contract changed')
        if not isinstance(op_id,str) or not op_id or not isinstance(request,bytes): raise ValueError('id and request bytes required')
        if not positive_int(quote) or not valid_hash(proof): raise ValueError('price quote and evidence digest required')
        c=self._contract
        self.db.execute('BEGIN IMMEDIATE')
        try:
            stopped, exposure, gens, counts, sources = self.db.execute('SELECT stopped,exposure_micro,generation_attempts,count_attempts,source_attempts FROM run').fetchone()
            if stopped: raise Stop('ledger stopped')
            if self.db.execute("SELECT 1 FROM effects WHERE state IN ('prepared','started') OR (state='succeeded' AND actual_micro IS NULL) LIMIT 1").fetchone(): raise Stop('unreconciled effect blocks dispatch')
            if self.db.execute('SELECT 1 FROM effects WHERE id=?',(op_id,)).fetchone(): raise Stop('operation ID already used')
            if exposure+quote > c['cap_micro']: raise Stop('total budget exceeded')
            if kind in ('source', 'metadata'):
                used=self.db.execute("SELECT COALESCE(SUM(COALESCE(actual_micro,quote_micro)),0) FROM effects WHERE kind IN ('source','metadata')").fetchone()[0]
                if used+quote > c['source_cap_micro']: raise Stop('source cap')
                if kind == 'source':
                    if sources >= c['max_sources']: raise Stop('source attempt cap')
                    sources+=1
                elif self.db.execute("SELECT 1 FROM effects WHERE kind='metadata' LIMIT 1").fetchone():
                    raise Stop('metadata attempt cap')
            elif kind == 'count':
                if counts >= c['max_counts']: raise Stop('count cap')
                counts+=1
            elif kind == 'generation':
                if self.db.execute("SELECT 1 FROM effects WHERE kind='generation' AND related_id=?",(related_id,)).fetchone(): raise Stop('count receipt already used')
                if gens >= c['max_generations']: raise Stop('generation cap')
                gens+=1
            else: raise ValueError('invalid operation')
            self.db.execute('INSERT INTO effects (id,kind,provider,endpoint,request,request_hash,quote_micro,quote_evidence_sha,state,related_id,quote_metadata,started_at_utc) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',(op_id,kind,provider,endpoint,request,digest(request),quote,proof,'started',related_id,quote_metadata,now_utc()))
            self.db.execute("INSERT INTO events(effect_id,state) VALUES (?, 'prepared')",(op_id,))
            self.db.execute("INSERT INTO events(effect_id,state) VALUES (?, 'started')",(op_id,))
            self.db.execute('UPDATE run SET exposure_micro=?,generation_attempts=?,count_attempts=?,source_attempts=? WHERE id=1',(exposure+quote,gens,counts,sources))
            self.db.execute('COMMIT')
        except BaseException:
            self.db.execute('ROLLBACK'); raise

    def _execute(self, op_id, kind, provider, endpoint, request, quote, proof, transport, related_id=None, quote_metadata=None):
        if not callable(transport): raise ValueError('one-shot transport required')
        self._start(op_id,kind,provider,endpoint,request,quote,proof,related_id,quote_metadata)
        try:
            status, raw=transport(provider,endpoint,bytes(request))
            if type(status) is not int or not isinstance(raw,bytes): raise TypeError('transport response must be status and bytes')
        except BaseException as exc:
            self.poisoned = True
            self.db.execute('BEGIN IMMEDIATE')
            self.db.execute("UPDATE effects SET state='uncertain',detail=? WHERE id=?",(type(exc).__name__,op_id))
            self.db.execute("INSERT INTO events(effect_id,state,detail) VALUES (?, 'uncertain',?)",(op_id,type(exc).__name__))
            self.db.execute('UPDATE run SET stopped=1 WHERE id=1')
            self.db.execute('COMMIT')
            raise UnknownEffect('effect uncertain; reserve retained and run stopped') from exc
        # Effect completion and capture are independent of parse/gate status.
        self.db.execute('BEGIN IMMEDIATE')
        try:
            self.db.execute("UPDATE effects SET state='succeeded',http_status=?,response=?,response_hash=?,completed_at_utc=? WHERE id=?",(status,raw,digest(raw),now_utc(),op_id))
            self.db.execute("INSERT INTO events(effect_id,state) VALUES (?, 'succeeded')",(op_id,))
            self.db.execute('COMMIT')
        except BaseException:
            self.poisoned = True
            self.db.execute('ROLLBACK')
            # Existing started state makes reopening fail closed.
            raise
        if status != 200:
            self._stop(op_id, 'non-200; billed status unknown')
            raise Stop('non-200, reservation retained')
        return raw

    def _stop(self, op_id, detail):
        self.db.execute('BEGIN IMMEDIATE')
        try:
            self.db.execute('UPDATE effects SET detail=? WHERE id=?',(detail,op_id))
            self.db.execute('UPDATE run SET stopped=1 WHERE id=1')
            self.db.execute('COMMIT')
        except BaseException:
            self.db.execute('ROLLBACK'); raise

    def _settle(self, op_id, amount):
        if not positive_int(amount): raise ValueError('invalid actual')
        self.db.execute('BEGIN IMMEDIATE')
        try:
            quote=self.db.execute('SELECT quote_micro FROM effects WHERE id=? AND state="succeeded" AND actual_micro IS NULL',(op_id,)).fetchone()
            if quote is None: raise Stop('operation not settleable')
            self.db.execute('UPDATE effects SET actual_micro=? WHERE id=?',(amount,op_id))
            self.db.execute("INSERT INTO events(effect_id,state,detail) VALUES (?, 'accounted',?)",(op_id,str(amount)))
            self.db.execute('UPDATE run SET exposure_micro=exposure_micro+? WHERE id=1',(amount-quote[0],))
            if amount>quote[0]: self.db.execute('UPDATE run SET stopped=1 WHERE id=1')
            self.db.execute('COMMIT')
            if amount>quote[0]: raise Stop('provider amount exceeded quote; run stopped after effect')
        except BaseException:
            if self.db.in_transaction: self.db.execute('ROLLBACK')
            raise

    def count(self, op_id, generation_request, transport):
        """Count exactly the following generation's canonical body, model bound separately."""
        if not isinstance(generation_request,dict) or 'model' in generation_request: raise ValueError('count request must use pinned model')
        request=canonical(generation_request)
        raw=self._execute(op_id,'count','vertex','countTokens',request,0,self._contract['count_price_evidence_sha256'],transport)
        try:
            value=json.loads(raw)['totalTokens']
            if not positive_int(value): raise ValueError('count missing')
        except (KeyError,ValueError,TypeError,json.JSONDecodeError):
            self._stop(op_id,'invalid token count'); raise Stop('invalid count')
        self._settle(op_id,0)
        return value

    def generate(self, op_id, generation_request, count_id, transport):
        c=self._contract
        if not isinstance(generation_request,dict) or 'model' in generation_request or generation_request.get('generationConfig',{}).get('maxOutputTokens') != c['max_output_tokens']:
            raise ValueError('generation model/config mismatch')
        if any(k in generation_request for k in ('tools','toolConfig','cachedContent')): raise ValueError('billable tools/cache not admitted')
        expected=canonical(generation_request)
        row=self.db.execute("SELECT request_hash,response FROM effects WHERE id=? AND kind='count' AND state='succeeded' AND actual_micro=0",(count_id,)).fetchone()
        if row is None or row[0] != digest(expected): raise Stop('no matching count receipt')
        value=json.loads(row[1])['totalTokens']
        if value > c['input_limit']: raise Stop('input token limit')
        request=canonical(generation_request)
        raw=self._execute(op_id,'generation','vertex',c['model']+'@'+c['location'],request,self._model_bound(),c['model_price_evidence_sha256'],transport,count_id)
        try:
            parsed=json.loads(raw); u=parsed['usageMetadata']; p=u['promptTokenCount']; total=u['totalTokenCount']; out=total-p
            thought=u.get('thoughtsTokenCount')
            if not positive_int(p) or not positive_int(out) or (thought is not None and (not positive_int(thought) or thought>out)): raise ValueError('malformed usage')
            amount=(p*c['input_rate_half_micro']+out*c['output_rate_half_micro']+1)//2
        except (KeyError,TypeError,ValueError,json.JSONDecodeError):
            self._stop(op_id,'invalid usage'); raise Stop('usage invalid; reserve retained')
        self._settle(op_id,amount)
        version=parsed.get('modelVersion')
        if not isinstance(version,str) or not (version == c['model'] or version.startswith(c['model']+'-')):
            self._stop(op_id,'model version missing or inconsistent with admitted model')
            raise Stop('model identity mismatch; actual accounted and stopped')
        if p>c['input_limit'] or out>c['output_reserve']:
            self._stop(op_id,'usage exceeded admitted token envelope')
            raise Stop('actual usage exceeded token envelope; actual accounted and stopped')
        return raw

    def metadata(self, op_id, request, reserve_micro, bound_evidence_sha256, transport, *, verify_bound):
        """One Serper /news discovery operation, with unknown metadata actual cost.

        Admission callback is trusted and must independently verify an enforceable
        whole-operation bound for the direct account; its presence or truth value
        alone is not evidence. A 200's endpoint price is NOT the metadata charge.
        Capture is returned only after ledger is stopped with actual=NULL and the
        reservation retained. A separately authorized successor is needed to reconcile.
        """
        expected=canonical({'api':'serper','path':'/news'})
        if request != expected: raise ValueError('metadata body is not the exact approved request')
        if not positive_int(reserve_micro) or not 0 < reserve_micro <= 250_000:
            raise ValueError('metadata reservation must be between 1 micro and $0.25')
        if not valid_hash(bound_evidence_sha256) or not callable(verify_bound):
            raise ValueError('bound evidence and verification callback required')
        try:
            admitted=verify_bound('orthogonal','/v1/details',request,reserve_micro,bound_evidence_sha256)
        except Exception:
            raise Stop('metadata bound verification failed before effect') from None
        if admitted is not True: raise Stop('metadata maximum not verified; no effect')
        info=canonical({'cost_status':'unknown','reserve_type':'conditional_verified_bound',
                        'bound_evidence_sha256':bound_evidence_sha256})
        raw=self._execute(op_id,'metadata','orthogonal','/v1/details',request,
                          reserve_micro,bound_evidence_sha256,transport,quote_metadata=info)
        self._stop(op_id,'metadata actual cost unknown; reserve retained')
        return raw

    def source(self, op_id, provider, endpoint, request, quote, transport):
        """One bounded Serper /news call; provider, body, and quote all fail closed."""
        if provider != 'orthogonal' or endpoint != '/v1/run':
            raise ValueError('only Orthogonal /v1/run is admitted')
        if not isinstance(request,bytes) or len(request)>8192:
            raise ValueError('bounded canonical JSON request bytes required')
        try:
            payload=json.loads(request)
            body=payload['body']
            if (not isinstance(payload,dict) or set(payload)!={'api','path','body','query'} or
                    payload['api']!='serper' or payload['path']!='/news' or payload['query']!={} or
                    not isinstance(body,dict) or set(body)!={'q','num'} or
                    not isinstance(body['q'],str) or not body['q'].strip() or len(body['q'])>500 or
                    any(ord(char)<32 or ord(char)==127 for char in body['q']) or
                    type(body['num']) is not int or not 1<=body['num']<=3 or canonical(payload)!=request):
                raise ValueError('invalid Serper News request shape')
        except (ValueError,TypeError,KeyError,UnicodeDecodeError):
            raise ValueError('invalid canonical Serper News request') from None
        if not isinstance(quote,dict) or set(quote)!={'provider','endpoint','request_sha256','max_micro','evidence_sha256','expires_utc'}: raise ValueError('exact source price pin required')
        if not positive_int(quote['max_micro']) or quote['max_micro'] > 250_000: raise ValueError('source quote exceeds per-call ceiling')
        if provider!=quote['provider'] or endpoint!=quote['endpoint'] or digest(request)!=quote['request_sha256'] or not valid_hash(quote['evidence_sha256']): raise ValueError('price pin mismatch')
        expiry=dt.datetime.fromisoformat(quote['expires_utc'].replace('Z','+00:00'))
        if expiry.tzinfo is None or expiry <= dt.datetime.now(dt.timezone.utc): raise ValueError('price pin expired')
        raw=self._execute(op_id,'source',provider,endpoint,request,quote['max_micro'],quote['evidence_sha256'],transport,quote_metadata=canonical(quote))
        try:
            from decimal import Decimal, InvalidOperation
            price=json.loads(raw)['priceCents']
            amount=Decimal(str(price))*Decimal(10_000)
            if not amount.is_finite() or amount<0 or amount!=amount.to_integral_value(): raise ValueError('priceCents invalid')
            amount=int(amount)
        except (KeyError,ValueError,TypeError,json.JSONDecodeError,InvalidOperation):
            self._stop(op_id,'source price missing or invalid'); raise Stop('source price unknown; reserve retained')
        self._settle(op_id,amount)
        return raw
