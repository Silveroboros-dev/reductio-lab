"""Offline activation and ledger adapter for a later bounded model phase.

No network, credentials or run authority. Uses the same live-source successor
SQLite; no source/metadata operations allowed after activation. Caller must
separately freeze and independently challenge the full model run contract.
"""
from __future__ import annotations
import datetime as dt
import json
import os
from decimal import Decimal, InvalidOperation
from pathlib import Path
import bridge
from bridge import BridgeError, OLD_DB_SHA, SUCCESSOR_LEDGER_CONTRACT_FILE_SHA, canonical, digest
from ledger import valid_hash

class ModelStageError(BridgeError): pass

def _read_path(path):
    p=Path(path)
    if not p.is_absolute() or p.is_symlink() or p.resolve()!=p.absolute() or not p.is_file():
        raise ModelStageError('missing, relative or symlinked artifact')
    return p.read_bytes()

def _obj(raw):
    try: value=json.loads(raw)
    except (ValueError,TypeError,UnicodeDecodeError) as exc: raise ModelStageError('invalid JSON') from exc
    if not isinstance(value,dict): raise ModelStageError('object JSON required')
    return value

def _ledger_contract(phase):
    raw=_read_path(str(bridge.ROOT/'live-ledger-successor-contract-20261029.json'))
    if digest(raw)!=SUCCESSOR_LEDGER_CONTRACT_FILE_SHA: raise ModelStageError('successor ledger contract file changed')
    expected=canonical(_obj(raw))
    stored=phase.db.execute('SELECT contract,contract_hash FROM run WHERE id=1').fetchone()
    if stored is None or bytes(stored[0])!=expected or stored[1]!=digest(expected) or canonical(phase._contract)!=expected:
        raise ModelStageError('successor ledger contract mismatch')

def _source_manifest(phase):
    """Bound source bytes and billing fields; no interpretation of semantics."""
    _ledger_contract(phase)
    snapshot=phase.verify_predecessor()
    ids=[snapshot['previous_source_id']]+snapshot['remaining_source_ids']
    expected_hashes={snapshot['previous_source_id']:snapshot['previous_source_request_sha256'],**snapshot['remaining_source_request_sha256']}
    records=[]
    for op in ids:
        try: r=phase.receipt(op)
        except Exception as exc: raise ModelStageError('missing source receipt') from exc
        expected_quote=bridge.OLD_QUOTE_SHA if op==bridge.OLD_SOURCE_ID else bridge.NEW_QUOTE_SHA
        if (r.get('id')!=op or r.get('kind')!='source' or r.get('provider')!='orthogonal' or r.get('endpoint')!='/v1/run'
            or r.get('state')!='succeeded' or r.get('http_status')!=200 or type(r.get('actual_micro')) is not int
            or not 0<=r['actual_micro']<=2000 or r.get('quote_micro')!=250000 or r.get('quote_evidence_sha')!=expected_quote
            or not isinstance(r.get('request'),bytes) or not isinstance(r.get('response'),bytes)
            or digest(r['request'])!=r.get('request_hash') or r['request_hash']!=expected_hashes[op]
            or digest(r['response'])!=r.get('response_hash') or not r.get('started_at_utc') or not r.get('completed_at_utc')):
            raise ModelStageError('source receipt identity, effect, price or byte binding mismatch')
        raw=_obj(r['response'])
        try:
            cents=Decimal(str(raw['priceCents']))*10000
            if raw.get('success') is not True or not cents.is_finite() or cents!=cents.to_integral_value() or int(cents)!=r['actual_micro']:
                raise ValueError('source price mismatch')
        except (InvalidOperation,KeyError,TypeError,ValueError): raise ModelStageError('source billing mismatch') from None
        records.append({'id':op,'request_sha256':r['request_hash'],'response_sha256':r['response_hash'],
            'actual_micro':r['actual_micro'],'quote_micro':r['quote_micro'],'quote_evidence_sha256':r['quote_evidence_sha'],
            'started_at_utc':r['started_at_utc'],'completed_at_utc':r['completed_at_utc']})
    expected=ids[1:]
    for record in records[1:]:
        ev=phase.db.execute('SELECT state,detail FROM events WHERE effect_id=? ORDER BY seq',(record['id'],)).fetchall()
        if ev != [('prepared',None),('started',None),('succeeded',None),('accounted',str(record['actual_micro']))]:
            raise ModelStageError('source receipt event sequence mismatch')
    rows=phase.db.execute("SELECT id FROM effects WHERE kind='source' ORDER BY rowid").fetchall()
    if [r[0] for r in rows]!=expected: raise ModelStageError('successor source cohort/order changed')
    return {'schema':'faithful-source-receipt-manifest-v1','predecessor_db_sha256':OLD_DB_SHA,
            'source_attempts_total':8,'records':records}

def prepare_binding(phase, summary_path, source_contract_sha256):
    """Return exact canonical receipt-manifest bytes, before model authority."""
    if not isinstance(phase,bridge.PhaseLedger): raise ModelStageError('source successor phase required')
    if not valid_hash(source_contract_sha256): raise ModelStageError('source contract hash required')
    summary_raw=_read_path(summary_path); summary=_obj(summary_raw)
    if set(summary)!={'status','source_count','ledger'} or summary.get('status')!='completed' or summary.get('source_count')!=7:
        raise ModelStageError('source phase did not complete')
    if summary.get('ledger')!=phase.summary() or phase.summary()['stopped']:
        raise ModelStageError('source summary does not match shared ledger')
    events=phase.db.execute("SELECT event,reason FROM run_events WHERE event IN ('source_continuation_started','source_continuation_complete') ORDER BY seq").fetchall()
    if events!=[('source_continuation_started',source_contract_sha256),('source_continuation_complete',digest(summary_raw))]:
        raise ModelStageError('source continuation markers mismatch')
    manifest=_source_manifest(phase)
    actual_source_micro=sum(record['actual_micro'] for record in manifest['records'][1:])
    expected_values={'exposure_micro':723593+actual_source_micro,'generation_attempts':79,'count_attempts':11,
                     'source_attempts':8,'previous_source_attempts':1,'metadata_attempts':0,'metadata_retained_micro':0}
    if any(phase.summary().get(key)!=value for key,value in expected_values.items()):
        raise ModelStageError('source aggregate exposure or counters mismatch')
    if phase.db.execute('SELECT COUNT(*) FROM effects').fetchone()[0]!=7:
        raise ModelStageError('unexpected effect in successor')
    return canonical(manifest)

def activate_model_stage(phase, *, summary_path, source_contract_sha256, source_manifest_path,
                         dataset_manifest_path, runner_path, model_contract_path,
                         expected_model_contract_sha256, verify_challenge):
    """Freeze-gated, one-shot stage activation. An assertion callback is not proof."""
    receipt_bytes=prepare_binding(phase,summary_path,source_contract_sha256)
    if _read_path(source_manifest_path)!=receipt_bytes: raise ModelStageError('source manifest is not exact canonical receipt binding')
    model_raw=_read_path(model_contract_path)
    if digest(model_raw)!=expected_model_contract_sha256 or not valid_hash(expected_model_contract_sha256):
        raise ModelStageError('model contract digest mismatch')
    contract=_obj(model_raw)
    binding={'predecessor_db_sha256':OLD_DB_SHA,'source_continuation_contract_sha256':source_contract_sha256,
             'source_continuation_summary_sha256':digest(_read_path(summary_path)),
             'source_receipt_manifest_sha256':digest(receipt_bytes),
             'successor_ledger_contract_sha256':SUCCESSOR_LEDGER_CONTRACT_FILE_SHA,
             'dataset_manifest_sha256':digest(_read_path(dataset_manifest_path)),
             'runner_sha256':digest(_read_path(runner_path))}
    caps={'total_usd_micro':40000000,'total_generation_attempts':835,'total_count_attempts':767,'total_source_attempts':18}
    if contract.get('schema')!='faithful-model-stage-contract-v1' or contract.get('status')!='frozen' or contract.get('bindings')!=binding or contract.get('caps')!=caps:
        raise ModelStageError('model contract bindings or total caps mismatch')
    if not callable(verify_challenge) or verify_challenge(model_raw,receipt_bytes,summary_path) is not True:
        raise ModelStageError('independent model-stage challenge rejected or missing')
    db=phase.db
    db.execute('BEGIN IMMEDIATE')
    try:
        if phase.summary()['stopped'] or db.execute("SELECT 1 FROM run_events WHERE event='model_stage_started'").fetchone():
            raise ModelStageError('model stage stopped or already activated')
        if db.execute("SELECT 1 FROM effects WHERE kind IN ('generation','count','metadata') LIMIT 1").fetchone():
            raise ModelStageError('unregistered model or metadata effects in successor')
        db.execute("INSERT INTO run_events(event,reason,at_utc) VALUES ('model_stage_started',?,?)",(expected_model_contract_sha256,dt.datetime.now(dt.timezone.utc).isoformat()))
        db.execute('COMMIT')
    except BaseException:
        if db.in_transaction: db.execute('ROLLBACK')
        raise
    return ModelLedger(phase,summary_path,source_contract_sha256,source_manifest_path,dataset_manifest_path,
                       runner_path,model_contract_path,expected_model_contract_sha256,binding)

class ModelLedger:
    def __init__(self, phase, summary_path, source_contract_sha256, source_manifest_path, dataset_manifest_path,
                 runner_path, model_contract_path, model_contract_sha256, binding):
        self._phase=phase;self._summary_path=summary_path;self._source_contract_sha256=source_contract_sha256
        self._source_manifest_path=source_manifest_path;self._dataset_path=dataset_manifest_path;self._runner_path=runner_path
        self._model_contract_path=model_contract_path;self._model_contract_sha256=model_contract_sha256;self._binding=binding
    @property
    def root(self): return self._phase.root
    @property
    def db(self): return self._phase.db
    @property
    def _contract(self): return self._phase._contract
    @property
    def poisoned(self): return self._phase.poisoned
    @poisoned.setter
    def poisoned(self,value): self._phase.poisoned=value
    def verify_predecessor(self): return self._phase.verify_predecessor()
    def summary(self): return self._phase.summary()
    def receipt(self,op_id): return self._phase.receipt(op_id)
    def stop(self,reason): return self._phase.stop(reason)
    def close(self): return self._phase.close()
    def source(self,*a,**k): raise ModelStageError('sources forbidden in model stage')
    def metadata(self,*a,**k): raise ModelStageError('metadata forbidden in model stage')
    def _guard(self):
        try:
            current={'predecessor_db_sha256':OLD_DB_SHA,'source_continuation_contract_sha256':self._source_contract_sha256,
               'source_continuation_summary_sha256':digest(_read_path(self._summary_path)),
               'source_receipt_manifest_sha256':digest(canonical(_source_manifest(self._phase))),
               'successor_ledger_contract_sha256':SUCCESSOR_LEDGER_CONTRACT_FILE_SHA,
               'dataset_manifest_sha256':digest(_read_path(self._dataset_path)),
               'runner_sha256':digest(_read_path(self._runner_path))}
            if (current!=self._binding or digest(_read_path(self._source_manifest_path))!=current['source_receipt_manifest_sha256']
                or digest(_read_path(self._model_contract_path))!=self._model_contract_sha256):
                raise ModelStageError('frozen model inputs drifted')
            events=self.db.execute("SELECT event,reason FROM run_events WHERE event IN ('source_continuation_started','source_continuation_complete','model_stage_started') ORDER BY seq").fetchall()
            expected=[('source_continuation_started',self._source_contract_sha256),('source_continuation_complete',current['source_continuation_summary_sha256']),('model_stage_started',self._model_contract_sha256)]
            if events!=expected: raise ModelStageError('model stage or source markers drifted')
        except BaseException:
            try: self.stop('model stage binding or source integrity failed')
            finally: self.poisoned=True
            raise
    def verify_source_binding(self):
        self._guard()
        if self.summary()['stopped']: raise ModelStageError('shared ledger stopped')
        manifest=_source_manifest(self._phase)
        return {'schema':'faithful-model-source-binding-v1',
                'source_continuation_contract_sha256':self._source_contract_sha256,
                'source_continuation_summary_sha256':self._binding['source_continuation_summary_sha256'],
                'source_receipt_manifest_sha256':digest(canonical(manifest)),
                'source_attempts_total':manifest['source_attempts_total'],
                'records':manifest['records']}
    def count(self,*args,**kwargs):
        self._guard();return self._phase._base.count(*args,**kwargs)
    def generate(self,*args,**kwargs):
        self._guard();return self._phase._base.generate(*args,**kwargs)
