"""Read-only predecessor validation and bounded seven-source successor bridge.

No network/credential client and no authority to execute. A freshly frozen
successor contract and independent challenge are required for any live use.
"""
from __future__ import annotations
import copy
import fcntl
import hashlib
import json
import os
import sqlite3
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT/'budget-v2'))
from ledger import Ledger, Stop, canonical, digest

OLD_DB_SHA='aeb9b4b9f6da76bf4df8797b292732a0707148b6cf9210edf1488e27f5bcb5b3'
OLD_CONTRACT_SHA='056623ba454b0093900ca7095558408546acc4b6d9abbcab063306b89d8d54d6'
OLD_STARTED_SHA='0498f9cd13ee00f6013353060a3463ac42be0d94eebd31e3d3a655fb48146fd5'
OLD_STOPPED_SHA='c29f375285ca596ecbf8e8efffe0c5ab388eb37c720a2125f16941f3a07d2c68'
OLD_LEDGER_CONTRACT_FILE_SHA='b8387bdce07de1e6f8ffb65ecd8b5c2997dccdb28b0dc781fe46eae0e43557e2'
SUCCESSOR_LEDGER_CONTRACT_FILE_SHA='4229f1df2048e37e468aa901ae865f3af80d47caa58d728c0f555ae0ab920b71'
OLD_SOURCE_ID='source:case-01:serper'
OLD_REQUEST_SHA='01fa0df49b7045c7de810ad0c1b6d54418891727ebd1564614de1b8f87dc519b'
OLD_RESPONSE_SHA='f93aed7a81230147be971b2192b952e523f3d05e34856aff029e5089f32ec7a3'
OLD_QUOTE_SHA='b77cd7bd9f5264879dc3b4b7db3cd73f1d2a836995258c4a206a91671e0e8ac9'
NEW_QUOTE_SHA='bb22abd1885a58a5fd317c5167baa1b70621dae6642343cb6c5fd341ca5ab6ac'
CLAIM_PATH=ROOT/'source-successor-claims'/(OLD_DB_SHA+'.claim.json')

class BridgeError(Stop): pass

def _read(path, expected):
    p=Path(path)
    if not p.is_absolute() or p.is_symlink() or p.resolve()!=p.absolute() or not p.is_file():
        raise BridgeError('missing, relative or symlinked evidence')
    raw=p.read_bytes()
    if digest(raw)!=expected: raise BridgeError('predecessor evidence digest mismatch')
    return raw

def _json(raw):
    def pairs(values):
        d={}
        for k,v in values:
            if k in d: raise BridgeError('duplicate JSON key')
            d[k]=v
        return d
    try: value=json.loads(raw,object_pairs_hook=pairs)
    except (ValueError,TypeError,UnicodeDecodeError) as exc: raise BridgeError('invalid JSON evidence') from exc
    if not isinstance(value,dict): raise BridgeError('object evidence required')
    return value

def _fsync_dir(path):
    fd=os.open(path,os.O_RDONLY)
    try: os.fsync(fd)
    finally: os.close(fd)

def _db_read(db_path, callback):
    p=Path(db_path)
    _read(p,OLD_DB_SHA)
    lock=p.parent/'owner.lock'
    if not lock.is_file() or lock.is_symlink(): raise BridgeError('predecessor lock missing')
    fd=os.open(lock,os.O_RDONLY|getattr(os,'O_NOFOLLOW',0))
    try:
        try: fcntl.flock(fd,fcntl.LOCK_SH|fcntl.LOCK_NB)
        except BlockingIOError as exc: raise BridgeError('predecessor is active') from exc
        _read(p,OLD_DB_SHA)
        db=sqlite3.connect(p.as_uri()+'?mode=ro&immutable=1',uri=True)
        try: result=callback(db)
        finally: db.close()
        _read(p,OLD_DB_SHA)
        return result
    finally:
        fcntl.flock(fd,fcntl.LOCK_UN); os.close(fd)

def inspect_predecessor(db_path, source_contract_path, started_path, stopped_path, expected_db_sha256):
    """Verify exact stored bytes/state; digest does not establish external provenance."""
    if expected_db_sha256!=OLD_DB_SHA: raise BridgeError('wrong predecessor binding')
    contract=_json(_read(source_contract_path,OLD_CONTRACT_SHA))
    started=_json(_read(started_path,OLD_STARTED_SHA))
    stopped=_json(_read(stopped_path,OLD_STOPPED_SHA))
    base_config=_json(_read(ROOT/'live-ledger-contract-20261029.json',OLD_LEDGER_CONTRACT_FILE_SHA))
    if (contract.get('schema')!='faithful-source-capture-contract-v3' or contract.get('status')!='frozen'
        or contract.get('known_prior_exposure_micro_usd')!=721593 or contract.get('source_budget_micro_usd')!=5000000
        or contract.get('total_cap_micro_usd')!=40000000 or contract.get('source_attempts')!=8):
        raise BridgeError('predecessor contract envelope mismatch')
    rows=contract.get('source_requests')
    if not isinstance(rows,list) or len(rows)!=8 or [r.get('case_id') for r in rows]!=[f'case-{i:02}' for i in range(1,9)]:
        raise BridgeError('predecessor request cohort mismatch')
    ids=[f"source:{r['case_id']}:serper" for r in rows]
    requests={}
    for r,op_id in zip(rows,ids):
        b=r.get('body')
        if r.get('api')!='serper' or r.get('path')!='/news' or not isinstance(b,dict) or set(b)!={'q','num'} or b.get('num')!=3:
            raise BridgeError('request definition mismatch')
        request=canonical({'api':'serper','path':'/news','body':b,'query':{}})
        if digest(request)!=r.get('request_sha256'): raise BridgeError('request hash mismatch')
        requests[op_id]=r['request_sha256']
    if (started.get('state')!='started' or started.get('mode')!='live' or started.get('contract_sha256')!=OLD_CONTRACT_SHA
        or started.get('source_ids')!=ids or stopped!={'case_id':'case-01','error_type':'PreflightError','status':'stopped'}):
        raise BridgeError('capture start/stop receipt mismatch')
    def read(db):
        run=db.execute('SELECT contract,contract_hash,stopped,exposure_micro,generation_attempts,count_attempts,source_attempts FROM run WHERE id=1').fetchone()
        if run is None or bytes(run[0])!=canonical(base_config) or digest(bytes(run[0]))!=run[1] or tuple(run[2:])!=(1,723593,79,11,1):
            raise BridgeError('predecessor budget or state mismatch')
        fields=('id','kind','provider','endpoint','request','request_hash','quote_micro','quote_evidence_sha','state','http_status','response','response_hash','actual_micro','detail','related_id','quote_metadata','started_at_utc','completed_at_utc')
        effects=db.execute('SELECT '+','.join(fields)+' FROM effects').fetchall()
        if len(effects)!=1: raise BridgeError('unexpected predecessor effects')
        item=dict(zip(fields,effects[0]))
        if (item['id']!=OLD_SOURCE_ID or item['kind']!='source' or item['provider']!='orthogonal' or item['endpoint']!='/v1/run'
            or item['state']!='succeeded' or item['http_status']!=200 or item['actual_micro']!=2000
            or item['quote_micro']!=250000 or item['quote_evidence_sha']!=OLD_QUOTE_SHA
            or item['request_hash']!=OLD_REQUEST_SHA or digest(item['request'])!=OLD_REQUEST_SHA
            or item['response_hash']!=OLD_RESPONSE_SHA or digest(item['response'])!=OLD_RESPONSE_SHA
            or requests[OLD_SOURCE_ID]!=OLD_REQUEST_SHA or not item['started_at_utc'] or not item['completed_at_utc']):
            raise BridgeError('source01 receipt integrity mismatch')
        data=_json(item['response'])
        news=data.get('data',{}).get('news') if isinstance(data.get('data'),dict) else None
        if data.get('success') is not True or data.get('priceCents')!=0.2 or not isinstance(news,list) or len(news)!=10:
            raise BridgeError('source01 does not reproduce source capture schema rejection')
        events=db.execute('SELECT effect_id,state,detail FROM events ORDER BY seq').fetchall()
        if events!=[(OLD_SOURCE_ID,'prepared',None),(OLD_SOURCE_ID,'started',None),(OLD_SOURCE_ID,'succeeded',None),(OLD_SOURCE_ID,'accounted','2000')]:
            raise BridgeError('effect state sequence mismatch')
        events=db.execute('SELECT event,reason FROM run_events ORDER BY seq').fetchall()
        if events!=[('source_capture_started',OLD_CONTRACT_SHA),('stopped','source capture halted')]:
            raise BridgeError('stop event or additional run events mismatch')
        return item
    _db_read(db_path,read)
    return {'schema_version':'faithful-source-predecessor-binding-v1','predecessor_db_sha256':OLD_DB_SHA,
        'predecessor_source_contract_sha256':OLD_CONTRACT_SHA,'predecessor_started_sha256':OLD_STARTED_SHA,
        'predecessor_stopped_sha256':OLD_STOPPED_SHA,'previous_exposure_micro':723593,
        'previous_source_attempts':1,'previous_generation_attempts':79,'previous_count_attempts':11,
        'previous_source_actual_micro':2000,'previous_source_id':OLD_SOURCE_ID,
        'previous_source_request_sha256':OLD_REQUEST_SHA,'previous_source_response_sha256':OLD_RESPONSE_SHA,
        'previous_source_news_count':10,'reported_error_type':'PreflightError',
        'stop_reason_evidence':'source capture halted; >3 news reproduced from immutable response; original exception text not retained',
        'remaining_source_ids':ids[1:], 'remaining_source_request_sha256':{key:requests[key] for key in ids[1:]}}

class PhaseLedger:
    """A shared successor ledger. Only seven pre-bound, not-yet-started sources."""
    def __init__(self, base, predecessor_paths, snapshot, claim_path, claim_bytes):
        self._base=base; self._paths=predecessor_paths; self._snapshot=copy.deepcopy(snapshot)
        self._claim_path=Path(claim_path); self._claim_sha256=digest(claim_bytes)
    @property
    def root(self): return self._base.root
    @property
    def db(self): return self._base.db
    @property
    def _contract(self): return self._base._contract
    @property
    def poisoned(self): return self._base.poisoned
    @poisoned.setter
    def poisoned(self,value): self._base.poisoned=value
    def verify_predecessor(self):
        _read(self._claim_path,self._claim_sha256)
        result=inspect_predecessor(*self._paths,OLD_DB_SHA)
        if result!=self._snapshot: raise BridgeError('predecessor binding drift')
        return result
    def summary(self):
        r=self._base.summary(); r['source_attempts']+=1
        r['previous_source_attempts']=1
        return r
    def stop(self,reason): return self._base.stop(reason)
    def close(self): return self._base.close()
    def source(self, op_id, provider, endpoint, request, quote, transport):
        self.verify_predecessor()
        allowed=self._snapshot['remaining_source_request_sha256']
        if op_id not in allowed or digest(request)!=allowed[op_id]:
            raise BridgeError('operation is outside the seven unstarted request bindings')
        if provider!='orthogonal' or endpoint!='/v1/run' or not isinstance(quote,dict) or quote.get('evidence_sha256')!=NEW_QUOTE_SHA or quote.get('max_micro')!=250000:
            raise BridgeError('successor source price/provider binding mismatch')
        n=self.db.execute("SELECT COUNT(*) FROM effects WHERE kind='source'").fetchone()[0]
        if n>=7: raise BridgeError('seven-source phase cap')
        if op_id!=self._snapshot['remaining_source_ids'][n]:
            raise BridgeError('predeclared source order mismatch')
        return self._base.source(op_id,provider,endpoint,request,quote,transport)
    def metadata(self,*args,**kwargs): raise BridgeError('metadata outside successor phase')
    def count(self,*args,**kwargs):
        raise BridgeError('model calls outside this seven-source phase')
    def generate(self,*args,**kwargs):
        raise BridgeError('model calls outside this seven-source phase')
    def receipt(self,op_id):
        if op_id!=OLD_SOURCE_ID: return self._base.receipt(op_id)
        self.verify_predecessor()
        fields=('id','kind','provider','endpoint','request','request_hash','quote_micro','quote_evidence_sha','state','http_status','response','response_hash','actual_micro','detail','related_id','quote_metadata','started_at_utc','completed_at_utc')
        def read(db):
            row=db.execute('SELECT '+','.join(fields)+' FROM effects WHERE id=?',(OLD_SOURCE_ID,)).fetchone()
            if row is None: raise BridgeError('predecessor receipt missing')
            return dict(zip(fields,row))
        return _db_read(self._paths[0],read)

def create_successor(db_path,source_contract_path,started_path,stopped_path,*,successor_root,claim_path,ledger_contract_path):
    """Claim once and create a new empty ledger; never alter the predecessor.

    claim_path and all other execution paths must be bound to a separately
    reviewed contract. A consumed claim is not automatically reset on failure.
    """
    paths=tuple(str(Path(p)) for p in (db_path,source_contract_path,started_path,stopped_path))
    snapshot=inspect_predecessor(*paths,OLD_DB_SHA)
    config_raw=_read(ledger_contract_path,SUCCESSOR_LEDGER_CONTRACT_FILE_SHA)
    config=_json(config_raw)
    if (config.get('prior_micro')!=723593 or config.get('prior_generations')!=79 or config.get('prior_counts')!=11
        or config.get('max_sources')!=17 or config.get('source_cap_micro')!=4998000 or config.get('cap_micro')!=40000000):
        raise BridgeError('successor budget mismatch')
    new_root=Path(successor_root); claim=Path(claim_path)
    if (not new_root.is_absolute() or new_root.parent.resolve()!=new_root.parent.absolute()
        or not claim.is_absolute() or claim != CLAIM_PATH or claim.parent.resolve()!=claim.parent.absolute() or new_root.exists()):
        raise BridgeError('successor/claim path invalid')
    binding={'schema_version':'faithful-source-successor-claim-v1','predecessor':snapshot,
             'successor_root':str(new_root),'successor_ledger_contract_sha256':digest(config_raw)}
    fd=os.open(claim,os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,'O_NOFOLLOW',0),0o600)
    try:
        data=canonical(binding); n=0
        while n<len(data):
            written=os.write(fd,data[n:])
            if written<=0: raise OSError('short claim write')
            n+=written
        os.fsync(fd)
    finally: os.close(fd)
    _fsync_dir(claim.parent)
    base=Ledger(str(new_root),config,create=True)
    return PhaseLedger(base,paths,snapshot,claim,data)
