"""Offline bounded ledger successor. No credentials, network or run authority."""
from __future__ import annotations
import datetime as dt
import json, os, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
for p in (ROOT/'budget-v2',ROOT/'source-successor'):sys.path.insert(0,str(p))
import bridge as source_bridge
import reopen, model_stage
from ledger import Ledger, Stop, canonical, digest

PARENT_DB_SHA='51d295d335baf5673f93f6c2ddee22e7de8b1a254de36a010da7b07581d81a64'
SUMMARY_SHA='1ab76742825b7d86fee880b918513898d5887a37c761ce38c66bbe1028ae2f43'
SOURCE_MANIFEST_SHA='0b00d587a3d85e5d377023f5785a267913c3ba3a5bb6db6dcde0539bf548fcb7'
MODEL_CONTRACT_SHA='12408e79e916ce97f6394d78a0570fc4d9dec97417998159f58f7be9f10d66d8'
CONFIG_SHA='7b43f734f5cc45e551732e560d1dddcd252f6f8548d760e668f967b0907abdc6'
RUNNER_BINDING_SHA='7e494d4a78c1e45632831d27196028710783ea4ec2e8db499ff0742a44c0e867'
SOURCE_CONTRACT_SHA='82b3e4e01777801a84897c108e06ec05eea5591709937d447612210e533a55d7'
SOURCE_SUMMARY_SHA='47efb0f65a1532613b29e933f9d9990982bbae22b71118f7ff1680280b7456ab'
COHORT_SHA='0b41030efebf5f8869f0c8994ca411567d872afe7beb9b0b8486cd57cffe7092'
STOP_REASON='Operator stop: repeated source-selection action schema mismatch across cases; preserve current effect and prevent further dispatch.'
CLAIM=ROOT/'model-accounting-successor-claims'/(PARENT_DB_SHA+'.claim.json')

class AdmissionError(Stop):pass

def read(path,expected=None):
 p=Path(path)
 if not p.is_absolute() or p.is_symlink() or not p.is_file() or p.absolute()!=p.resolve():raise AdmissionError('invalid evidence path')
 b=p.read_bytes()
 if expected is not None and digest(b)!=expected:raise AdmissionError('evidence digest mismatch')
 return b

def obj(raw):
 try:v=json.loads(raw)
 except (ValueError,TypeError,UnicodeDecodeError) as exc:raise AdmissionError('invalid JSON evidence') from exc
 if not isinstance(v,dict):raise AdmissionError('object JSON required')
 return v

def _open_parent():
 root=ROOT/'live-source-ledger-20261029-02'
 oldroot,claim,paths,snapshot,cfg=reopen._claim_and_paths(str(root))
 read(root/'ledger.sqlite3',PARENT_DB_SHA)
 base=reopen._ReadOnlyBase(root,cfg)
 try:
  read(root/'ledger.sqlite3',PARENT_DB_SHA)
  return source_bridge.PhaseLedger(base,paths,snapshot,source_bridge.CLAIM_PATH,claim)
 except BaseException:base.close();raise

def inspect_parent():
 summary=obj(read(ROOT/'live-model-experiment-20261029-01/summary.json',SUMMARY_SHA))
 if tuple(summary.get(k) for k in ('requested_slots','attempted_slots','not_attempted_slots','stop_slot'))!=(32,9,23,8):raise AdmissionError('interrupted cohort mismatch')
 read(ROOT/'model-contract-frozen-v1.json',MODEL_CONTRACT_SHA)
 read(ROOT/'dataset-draft-20261029/assembled-v3/manifest.json',COHORT_SHA)
 source_raw=read(ROOT/'source-receipt-manifest-20261029.json',SOURCE_MANIFEST_SHA)
 phase=_open_parent()
 try:
  if canonical(model_stage._source_manifest(phase))!=source_raw:raise AdmissionError('source manifest mismatch')
  run=phase.db.execute('SELECT stopped,exposure_micro,generation_attempts,count_attempts,source_attempts FROM run').fetchone()
  if run!=(1,797567,95,27,7) or summary.get('ledger')!=phase.summary():raise AdmissionError('accounting state mismatch')
  rows=phase.db.execute('SELECT id,kind,state,http_status,request,request_hash,response,response_hash,quote_micro,actual_micro FROM effects ORDER BY rowid').fetchall()
  if len(rows)!=39:raise AdmissionError('effect count mismatch')
  counts={'source':0,'count':0,'generation':0};sums={'source':0,'count':0,'generation':0};checks={}
  for ident,kind,state,status,req,rh,raw,sh,reserve,actual in rows:
   if kind not in counts or state!='succeeded' or status!=200 or not isinstance(req,bytes) or not isinstance(raw,bytes) or digest(req)!=rh or digest(raw)!=sh or type(actual) is not int or actual<0:raise AdmissionError('unsettled or corrupt effect')
   counts[kind]+=1;sums[kind]+=actual
   if kind=='count':
    n=obj(raw).get('totalTokens')
    if not ident.startswith('count:') or actual!=0 or type(n) is not int or n<0:raise AdmissionError('invalid count receipt')
    checks[ident.removeprefix('count:')]=rh
   elif kind=='generation':
    x=obj(raw);u=x.get('usageMetadata',{});p=u.get('promptTokenCount');t=u.get('totalTokenCount')
    if not ident.startswith('generation:') or type(p) is not int or type(t) is not int or p<0 or t<p or x.get('modelVersion')!='gemini-3.8-flash' or reserve!=86016 or (3*p+15*(t-p)+1)//2!=actual or checks.get(ident.removeprefix('generation:'))!=rh:raise AdmissionError('generation usage or count binding mismatch')
   elif actual!=2000:raise AdmissionError('source cost mismatch')
   ev=phase.db.execute('SELECT state,detail FROM events WHERE effect_id=? ORDER BY seq',(ident,)).fetchall()
   if ev!=[('prepared',None),('started',None),('succeeded',None),('accounted',str(actual))]:raise AdmissionError('effect event sequence mismatch')
  if counts!={'source':7,'count':16,'generation':16} or sums!={'source':14000,'count':0,'generation':59974}:raise AdmissionError('effect accounting mismatch')
  events=phase.db.execute('SELECT event,reason FROM run_events ORDER BY seq').fetchall()
  if events!=[('source_continuation_started',SOURCE_CONTRACT_SHA),('source_continuation_complete',SOURCE_SUMMARY_SHA),('model_stage_started',MODEL_CONTRACT_SHA),('runner_started',RUNNER_BINDING_SHA),('stopped',STOP_REASON)]:raise AdmissionError('operator stop or lineage mismatch')
  read(ROOT/'live-source-ledger-20261029-02/ledger.sqlite3',PARENT_DB_SHA)
 finally:phase.close()
 return {'schema':'faithful-stopped-model-parent-v1','parent_db_sha256':PARENT_DB_SHA,'source_manifest_sha256':SOURCE_MANIFEST_SHA,'interrupted_summary_sha256':SUMMARY_SHA,'cohort_sha256':COHORT_SHA,'prior_micro':797567,'prior_generations':95,'prior_counts':27,'prior_sources':8,'source_actual_micro':16000,'model_usage_estimate_micro':59974,'uncertain_current_effects':0,'operator_stop_reason':STOP_REASON}

class ModelSuccessorLedger:
 def __init__(self,base,claim,parent):self._base=base;self._claim_hash=digest(claim);self._parent=parent;self._activation=None
 @property
 def root(self):return self._base.root
 @property
 def db(self):return self._base.db
 @property
 def _contract(self):return self._base._contract
 @property
 def poisoned(self):return self._base.poisoned
 @poisoned.setter
 def poisoned(self,v):self._base.poisoned=v
 def verify_parent(self):
  read(CLAIM,self._claim_hash)
  x=inspect_parent()
  if x!=self._parent:raise AdmissionError('parent binding drift')
  return x
 def summary(self):
  x=self._base.summary();x['source_attempts']+=8;x['previous_source_attempts']=8;return x
 def stop(self,reason):return self._base.stop(reason)
 def close(self):return self._base.close()
 def source(self,*a,**k):raise AdmissionError('new source effects forbidden')
 def metadata(self,*a,**k):raise AdmissionError('metadata effects forbidden')
 def receipt(self,ident):
  self.verify_parent()
  if ident not in {f'source:case-{i:02}:serper' for i in range(1,9)}:return self._base.receipt(ident)
  p=_open_parent()
  try:return p.receipt(ident)
  finally:p.close()
 def verify_source_binding(self):
  self.verify_parent();m=obj(read(ROOT/'source-receipt-manifest-20261029.json',SOURCE_MANIFEST_SHA))
  return {'schema':'faithful-model-source-binding-v1','source_continuation_contract_sha256':SOURCE_CONTRACT_SHA,'source_continuation_summary_sha256':SOURCE_SUMMARY_SHA,'source_receipt_manifest_sha256':SOURCE_MANIFEST_SHA,'source_attempts_total':8,'records':m['records']}
 def activate(self,*,contract_path,contract_sha256,protocol_path,runner_path,verify_challenge):
  self.verify_parent();raw=read(contract_path,contract_sha256);c=obj(raw)
  bindings={'parent_db_sha256':PARENT_DB_SHA,'parent_summary_sha256':SUMMARY_SHA,'source_manifest_sha256':SOURCE_MANIFEST_SHA,'ledger_contract_sha256':CONFIG_SHA,'cohort_manifest_sha256':COHORT_SHA,'protocol_sha256':digest(read(protocol_path)),'runner_sha256':digest(read(runner_path))}
  caps={'total_usd_micro':40000000,'total_generation_attempts':835,'total_count_attempts':767,'total_source_attempts':18,'slots':32}
  if c.get('schema')!='faithful-model-successor-contract-v1' or c.get('status')!='frozen' or c.get('bindings')!=bindings or c.get('caps')!=caps:raise AdmissionError('model successor contract mismatch')
  if not callable(verify_challenge) or verify_challenge(raw) is not True:raise AdmissionError('independent challenge required')
  self.db.execute('BEGIN IMMEDIATE')
  try:
   if self.summary()['stopped'] or self.db.execute("SELECT 1 FROM run_events WHERE event='model_successor_started'").fetchone() or self.db.execute('SELECT 1 FROM effects LIMIT 1').fetchone():raise AdmissionError('successor already started or stopped')
   self.db.execute("INSERT INTO run_events(event,reason,at_utc) VALUES ('model_successor_started',?,?)",(contract_sha256,dt.datetime.now(dt.timezone.utc).isoformat()));self.db.execute('COMMIT')
  except BaseException:
   if self.db.in_transaction:self.db.execute('ROLLBACK')
   raise
  self._activation=(str(contract_path),contract_sha256,str(protocol_path),str(runner_path),bindings)
 def _guard(self):
  if self._activation is None:raise AdmissionError('model successor not activated')
  try:
   cp,ch,pp,rp,b=self._activation;self.verify_parent()
   if digest(read(cp))!=ch or digest(read(pp))!=b['protocol_sha256'] or digest(read(rp))!=b['runner_sha256'] or self.db.execute("SELECT reason FROM run_events WHERE event='model_successor_started'").fetchall()!=[(ch,)]:raise AdmissionError('successor binding drift')
  except BaseException:
   try:self.stop('model successor lineage or code drift')
   finally:self.poisoned=True
   raise
 def count(self,*a,**k):self._guard();return self._base.count(*a,**k)
 def generate(self,*a,**k):self._guard();return self._base.generate(*a,**k)

def create_successor(*,successor_root,claim_path,ledger_contract_path):
 parent=inspect_parent();raw=read(ledger_contract_path,CONFIG_SHA);cfg=obj(raw)
 if (cfg.get('prior_micro'),cfg.get('prior_generations'),cfg.get('prior_counts'),cfg.get('max_sources'),cfg.get('source_cap_micro'),cfg.get('cap_micro'))!=(797567,95,27,10,4984000,40000000):raise AdmissionError('successor limit mismatch')
 root=Path(successor_root);claim=Path(claim_path)
 if not root.is_absolute() or root.parent.resolve()!=root.parent.absolute() or root.exists() or claim!=CLAIM or claim.parent.resolve()!=claim.parent.absolute():raise AdmissionError('successor path or singleton claim invalid')
 data=canonical({'schema':'faithful-model-accounting-claim-v1','parent':parent,'successor_root':str(root),'ledger_contract_sha256':CONFIG_SHA})
 fd=os.open(claim,os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,'O_NOFOLLOW',0),0o600)
 try:
  n=0
  while n<len(data):
   m=os.write(fd,data[n:])
   if m<=0:raise OSError('short write')
   n+=m
  os.fsync(fd)
 finally:os.close(fd)
 fd=os.open(claim.parent,os.O_RDONLY)
 try:os.fsync(fd)
 finally:os.close(fd)
 return ModelSuccessorLedger(Ledger(str(root),cfg,create=True),data,parent)
