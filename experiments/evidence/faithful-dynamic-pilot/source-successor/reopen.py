"""Reopen a completed source successor without retrying any source effect.

The read-only path never changes the ledger; the writable path is for a
separately authorized, challenged model execution and must not be used for
preparation. Neither path starts a provider operation.
"""
from __future__ import annotations
import fcntl
import json
import os
import sqlite3
from pathlib import Path
import bridge
import model_stage
from ledger import Ledger, canonical, digest

class ReopenError(bridge.BridgeError): pass

class _ReadOnlyBase:
    def __init__(self, root, config):
        self.root=Path(root); self._contract=config; self.poisoned=False
        lock=self.root/'owner.lock'
        if lock.is_symlink() or not lock.is_file(): raise ReopenError('successor lock missing')
        for suffix in ('-journal','-wal'):
            if (self.root/('ledger.sqlite3'+suffix)).exists(): raise ReopenError('unreconciled sqlite journal')
        self.fd=os.open(lock,os.O_RDONLY|getattr(os,'O_NOFOLLOW',0))
        try:
            try: fcntl.flock(self.fd,fcntl.LOCK_SH|fcntl.LOCK_NB)
            except BlockingIOError as exc: raise ReopenError('successor ledger is active') from exc
            p=self.root/'ledger.sqlite3'
            if p.is_symlink() or not p.is_file(): raise ReopenError('successor db missing')
            self.db=sqlite3.connect(p.as_uri()+'?mode=ro&immutable=1',uri=True)
            self.db.execute('PRAGMA query_only=ON')
        except BaseException:
            os.close(self.fd);raise
    def summary(self):
        row=self.db.execute('SELECT stopped,exposure_micro,generation_attempts,count_attempts,source_attempts FROM run').fetchone()
        result=dict(zip(('stopped','exposure_micro','generation_attempts','count_attempts','source_attempts'),row))
        count,retained=self.db.execute("SELECT COUNT(*),COALESCE(SUM(CASE WHEN actual_micro IS NULL THEN quote_micro ELSE 0 END),0) FROM effects WHERE kind='metadata'").fetchone()
        result.update(metadata_attempts=count,metadata_retained_micro=retained)
        return result
    def receipt(self,op_id):
        fields=('id','kind','provider','endpoint','request','request_hash','quote_micro','quote_evidence_sha','state','http_status','response','response_hash','actual_micro','detail','related_id','quote_metadata','started_at_utc','completed_at_utc')
        row=self.db.execute('SELECT '+','.join(fields)+' FROM effects WHERE id=?',(op_id,)).fetchone()
        if row is None:raise KeyError(op_id)
        return dict(zip(fields,row))
    def close(self):
        self.db.close();fcntl.flock(self.fd,fcntl.LOCK_UN);os.close(self.fd)

def _claim_and_paths(successor_root):
    claim=bridge.CLAIM_PATH
    if not claim.is_absolute() or claim.is_symlink() or claim.resolve()!=claim.absolute() or not claim.is_file():raise ReopenError('singleton claim missing')
    raw=claim.read_bytes();value=bridge._json(raw)
    if canonical(value)!=raw or value.get('schema_version')!='faithful-source-successor-claim-v1' or value.get('successor_ledger_contract_sha256')!=bridge.SUCCESSOR_LEDGER_CONTRACT_FILE_SHA:
        raise ReopenError('claim contents invalid')
    root=Path(successor_root)
    if not root.is_absolute() or root.is_symlink() or root.resolve()!=root.absolute() or not root.is_dir() or value.get('successor_root')!=str(root):raise ReopenError('claim successor root mismatch')
    oldroot=bridge.ROOT
    paths=tuple(str(oldroot/p) for p in ('live-source-ledger-20261029-01/ledger.sqlite3','live-source-capture-contract-frozen-v3.json','live-source-capture-20261029-01/started.json','live-source-capture-20261029-01/case-01-stopped.json'))
    snapshot=bridge.inspect_predecessor(*paths,bridge.OLD_DB_SHA)
    if value.get('predecessor')!=snapshot:raise ReopenError('claim predecessor mismatch')
    config=bridge._json(bridge._read(bridge.ROOT/'live-ledger-successor-contract-20261029.json',bridge.SUCCESSOR_LEDGER_CONTRACT_FILE_SHA))
    return root,raw,paths,snapshot,config

def _validate_phase(phase, summary_path, source_contract_sha256):
    # This also verifies complete source receipts, checks aggregate cost/counters,
    # and rejects an already started model stage through the exact summary check.
    if phase.db.execute("SELECT 1 FROM run_events WHERE event IN ('model_stage_started','runner_started') LIMIT 1").fetchone():
        raise ReopenError('model stage already started; no automatic resume')
    receipt_manifest=model_stage.prepare_binding(phase,summary_path,source_contract_sha256)
    return receipt_manifest

def open_completed_readonly(successor_root, *, summary_path, source_contract_sha256):
    """Return (read-only PhaseLedger, canonical source manifest bytes, db sha)."""
    root,claim_raw,paths,snapshot,config=_claim_and_paths(successor_root)
    base=_ReadOnlyBase(root,config)
    try:
        db_path=root/'ledger.sqlite3';db_before=digest(db_path.read_bytes())
        phase=bridge.PhaseLedger(base,paths,snapshot,bridge.CLAIM_PATH,claim_raw)
        manifest=_validate_phase(phase,summary_path,source_contract_sha256)
        if digest(db_path.read_bytes())!=db_before:raise ReopenError('successor db changed during read')
        return phase,manifest,db_before
    except BaseException:
        base.close();raise

def reopen_completed_successor(successor_root, *, summary_path, source_contract_sha256):
    """For separately approved dispatch only; no provider effect performed here.

    This obtains an exclusive ledger lock and may write SQLite bookkeeping on
    open. After a concurrent-read gap it repeats all checks under that lock.
    """
    ro,manifest,before=open_completed_readonly(successor_root,summary_path=summary_path,source_contract_sha256=source_contract_sha256)
    ro.close()
    root,claim_raw,paths,snapshot,config=_claim_and_paths(successor_root)
    if digest((root/'ledger.sqlite3').read_bytes())!=before:raise ReopenError('successor changed before exclusive reopen')
    base=Ledger(str(root),config,create=False)
    try:
        phase=bridge.PhaseLedger(base,paths,snapshot,bridge.CLAIM_PATH,claim_raw)
        if _validate_phase(phase,summary_path,source_contract_sha256)!=manifest:raise ReopenError('source bindings changed across reopen')
        return phase
    except BaseException:
        base.close();raise
