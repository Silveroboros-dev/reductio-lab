"""Offline-only p0 integration. No transport, account, provider or authority.

Injected functions and real human/source verification require separate review.
A future live executor must separately bind ledger, runtime, ticket and inputs.
"""
from __future__ import annotations
import copy, json, os, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT/'forecast-orchestrator-v1'))
import orchestrator as o

class Error(ValueError):pass

def _read(path):
 p=Path(path)
 if not p.is_absolute() or p.is_symlink() or not p.is_file() or p.resolve()!=p.absolute():raise Error('unsafe case path')
 return p.read_bytes()

def _json(raw):
 def pairs(xs):
  d={}
  for k,v in xs:
   if k in d:raise Error('duplicate JSON key')
   d[k]=v
  return d
 try:v=json.loads(raw,object_pairs_hook=pairs)
 except (ValueError,UnicodeDecodeError):raise Error('invalid case JSON') from None
 if not isinstance(v,dict):raise Error('case must be object')
 return v

def _check(fn,*a):
 if not callable(fn) or fn(*a) is not True:raise Error('independent verification required')

def prepare(case_paths, *, verify_case_record,verify_human,verify_rules,verify_evidence,clock):
 """Prepare exact, independently checked case bytes under one common cutoff.

 verify_case_record(path, raw) checks approved create-only human file and origin;
 verify_human(case) verifies exact human thesis and choice, verify_rules(case)
 checks all full rules against reviewed venue raw bytes, verify_evidence(case)
 checks each baseline item provenance, availability and no news leakage.
 These are required injected review functions, not supplied trust defaults.
 """
 if not isinstance(case_paths,list) or not 1<=len(case_paths)<=4 or not callable(clock):raise Error('1..4 cases and clock required')
 now=clock();o.instant(now);prepared=[];bindings=[]
 for path in case_paths:
  raw=_read(path);_check(verify_case_record,str(path),raw);case=_json(raw)
  _check(verify_evidence,copy.deepcopy(case))
  x=o.prepare_case(case,verify_human=verify_human,verify_rules=verify_rules)
  if o.instant(case['p0_as_of_utc'])>o.instant(now):raise Error('future as-of cutoff')
  prepared.append(x);bindings.append({'path':str(path),'raw_sha256':o.sha(raw),'case_sha256':x['case_sha256'],'task_sha256':x['task_sha256']})
 cutoffs={x['case']['p0_as_of_utc'] for x in prepared}
 if len(cutoffs)!=1:raise Error('all p0 must share one as-of cutoff')
 for key in ('case_id','event_group_id','contract_id'):
  vals=[x['case'][key] for x in prepared]
  if len(vals)!=len(set(vals)):raise Error('duplicate '+key)
 return {'schema':'forecast-p0-prepared-v1','common_as_of_utc':next(iter(cutoffs)),
  'bindings':bindings,'prepared':prepared}

def durable_recorder(directory):
 """Create-only, durable outputs; output directory must itself be new."""
 p=Path(directory)
 if not p.is_absolute() or p.parent.is_symlink() or p.parent.resolve()!=p.parent.absolute():raise Error('unsafe output directory')
 p.mkdir(mode=0o700)
 dfd=os.open(p,os.O_RDONLY)
 try:os.fsync(dfd)
 finally:os.close(dfd)
 parentfd=os.open(p.parent,os.O_RDONLY)
 try:os.fsync(parentfd)
 finally:os.close(parentfd)
 def record(name,value):
  if not isinstance(name,str) or not name or any(c not in 'abcdefghijklmnopqrstuvwxyz0123456789-' for c in name):raise Error('unsafe record name')
  raw=o.canonical(value);path=p/(name+'.json')
  fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,'O_NOFOLLOW',0),0o600)
  try:
   with os.fdopen(fd,'wb',closefd=False) as f:f.write(raw);f.flush();os.fsync(fd)
  finally:os.close(fd)
  d=os.open(p,os.O_RDONLY)
  try:os.fsync(d)
  finally:os.close(d)
 return record

def run(bundle, *, verify_bundle,generator_factory,record,clock):
 """Run p0 only; no automatic retry and no claim of market admissibility.

 The reviewed caller must freeze the exact bundle and enforce count/generate,
 source denial, budget, settlement and no external effects in its callbacks.
 """
 _check(verify_bundle,copy.deepcopy(bundle))
 if not callable(generator_factory) or not callable(record) or not callable(clock):raise Error('callbacks required')
 if bundle.get('schema')!='forecast-p0-prepared-v1' or not isinstance(bundle.get('prepared'),list):raise Error('bad bundle')
 values=bundle['prepared'];bindings=bundle['bindings']
 if len(values)!=len(bindings) or not 1<=len(values)<=4:raise Error('bundle length drift')
 for x,b in zip(values,bindings):
  if (o.sha(o.canonical(x['case']))!=b['case_sha256'] or o.sha(o.canonical(x['task']))!=b['task_sha256'] or
   x['case_sha256']!=b['case_sha256'] or x['task_sha256']!=b['task_sha256'] or x['case']['p0_as_of_utc']!=bundle['common_as_of_utc']):raise Error('bundle drift')
  if o.sha(_read(b['path']))!=b['raw_sha256']:raise Error('approved case file drift')
 # Entire frozen bundle is durable before any generator call.
 record('p0-bundle',copy.deepcopy(bundle));outputs=[]
 for idx,x in enumerate(values):
  def scoped(name,value):record(f'{idx:02d}-{name}',value)
  def factory(phase,condition,arm):
   if (phase,condition) != ('p0','no_news') or arm not in ('c','b'):raise Error('scope violation')
   return generator_factory(x['case']['case_id'],phase,condition,arm)
  outputs.append(o.run_p0(x,generator_factory=factory,record=scoped,clock=clock))
 summary={'schema':'forecast-p0-batch-v1','common_as_of_utc':bundle['common_as_of_utc'],
          'bundle_sha256':o.sha(o.canonical(bundle)),'results':outputs}
 record('p0-batch',copy.deepcopy(summary));return summary
