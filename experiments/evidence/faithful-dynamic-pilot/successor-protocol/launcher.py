"""Explicit live launcher; import/verification do not perform external calls.

An independently reviewed frozen challenge and prior operator SHA check of this
file are mandatory. A created successor is one-shot; no automatic retry/resume.
"""
from __future__ import annotations
import hashlib,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
FILES=('successor-protocol/launcher.py','successor-protocol/model_protocol_v2.py','successor-protocol/runner_v3.py',
 'model-accounting-successor/model_accounting.py','model-successor-ledger-contract-20261029.json',
 'budget-v2/ledger.py','source-successor/bridge.py','source-successor/reopen.py','source-successor/model_stage.py',
 'model-launch/admission.py','model-launch/news_projection.py','controller/faithful.py','harness/harness.py','transport/oneshot.py',
 'dataset-draft-20261029/assembled-v2/manifest.json','dataset-draft-20261029/assembled-v3/manifest.json',
 'source-receipt-manifest-20261029.json','ui-serper-price-20261029.json','ui-serper-price-20261029-refresh-v2.json',
 'live-model-experiment-20261029-01/summary.json','model-contract-frozen-v1.json')
PROTECTED=('model_accounting','runner_v3','model_protocol_v2','bridge','reopen','model_stage','ledger','admission','news_projection','faithful','harness','oneshot')
class Error(ValueError):pass

def sha(b):return hashlib.sha256(b).hexdigest()
def canonical(x):return json.dumps(x,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()
def read(path):
 p=Path(path)
 if not p.is_absolute() or not p.is_file() or p.is_symlink() or p.resolve()!=p.absolute():raise Error('unsafe path')
 return p.read_bytes()
def obj(raw):
 def pairs(values):
  d={}
  for k,v in values:
   if k in d:raise Error('duplicate key')
   d[k]=v
  return d
 try:v=json.loads(raw,object_pairs_hook=pairs)
 except (ValueError,TypeError,UnicodeDecodeError) as exc:raise Error('invalid JSON') from exc
 if not isinstance(v,dict):raise Error('object required')
 return v

def verify(contract_path,challenge_path,receipt_path,*,contract_sha256,launcher_sha256):
 """Before imports/credentials/effects, verify contract and local review."""
 if any(n in sys.modules for n in PROTECTED):raise Error('fresh Python process required')
 cr,pr,rr=map(read,(contract_path,challenge_path,receipt_path));c,p,r=map(obj,(cr,pr,rr))
 if sha(cr)!=contract_sha256 or c.get('schema')!='faithful-model-successor-contract-v1' or c.get('status')!='frozen':raise Error('frozen contract mismatch')
 d=p.get('internal_digest')
 if (p.get('schema_version')!='eval_contract_challenge_packet_v1' or p.get('overall_state')!='ready'
     or p.get('witness',{}).get('identity')!='audit_go' or p.get('witness',{}).get('mode')!='read_only_offline'
     or p.get('challenged_contract',{}).get('raw_sha256')!=sha(cr) or d!=sha(canonical({k:v for k,v in p.items() if k!='internal_digest'}))
     or r.get('packet_raw_sha256')!=sha(pr) or r.get('packet_byte_count')!=len(pr) or r.get('packet_internal_digest')!=d or r.get('state')!='ready'):
  raise Error('challenge mismatch')
 bindings=c.get('component_bindings');observed=p.get('context_binding',{}).get('code_bindings_at_inspection')
 if not isinstance(bindings,dict) or set(bindings)!=set(FILES) or not isinstance(observed,dict) or bindings.get(FILES[0])!=launcher_sha256:raise Error('code bindings missing')
 for rel,h in bindings.items():
  b=read(ROOT/rel)
  if sha(b)!=h or observed.get(rel)!={'sha256':h,'size':len(b)}:raise Error('component mismatch')
 context=c.get('execution_context');w=p.get('context_binding',{})
 if not isinstance(context,dict) or context!=w.get('execution_context') or context.get('artifact_root')!=str(ROOT) or context.get('cwd')!=str(Path.cwd().resolve()) or c.get('bindings')!=w.get('bindings'):raise Error('context mismatch')
 if c.get('caps')!={'total_usd_micro':40000000,'total_generation_attempts':835,'total_count_attempts':767,'total_source_attempts':18,'slots':32}:raise Error('budget mismatch')
 return {'contract':c,'contract_raw':cr,'challenge_raw':pr,'receipt_raw':rr,'bindings':bindings}

def execute(contract_path,challenge_path,receipt_path,*,contract_sha256,launcher_sha256):
 """Live dispatch only after reviewed challenge; no retry or source calls."""
 ctx=verify(contract_path,challenge_path,receipt_path,contract_sha256=contract_sha256,launcher_sha256=launcher_sha256)
 for d in ('successor-protocol','model-accounting-successor','model-launch','source-successor','budget-v2','transport'):
  sys.path.insert(0,str(ROOT/d))
 import model_accounting,runner_v3,admission
 from oneshot import OneShotTransport
 c=ctx['contract'];context=c['execution_context'];dataset=Path(context['dataset_root']);out=Path(context['output_dir'])
 if out.exists() or context.get('claim_path')!=str(model_accounting.CLAIM):raise Error('output or claim binding mismatch')
 ledger=model_accounting.create_successor(successor_root=context['ledger_root'],claim_path=str(model_accounting.CLAIM),ledger_contract_path=str(ROOT/'model-successor-ledger-contract-20261029.json'))
 try:
  manifest_raw=read(dataset/'manifest.json')
  if sha(manifest_raw)!=c['bindings']['cohort_manifest_sha256']:raise Error('dataset drift')
  manifest=obj(manifest_raw);checker=admission.Admission(ROOT/'dataset-draft-20261029/assembled-v2',dataset,ledger)
  cases=runner_v3.preflight(manifest,dataset,ledger,checker.verify_human,checker.verify_capture)
  if len(cases)!=8 or len(runner_v3.schedule(cases))!=32:raise Error('schedule mismatch')
  summary=ledger.summary()
  if any(summary.get(k)!=v for k,v in {'stopped':0,'exposure_micro':797567,'generation_attempts':95,'count_attempts':27,'source_attempts':8}.items()):raise Error('carry mismatch')
  def reviewed(raw):
   return raw==ctx['contract_raw'] and read(challenge_path)==ctx['challenge_raw'] and read(receipt_path)==ctx['receipt_raw']
  ledger.activate(contract_path=contract_path,contract_sha256=contract_sha256,
   protocol_path=str(ROOT/'successor-protocol/model_protocol_v2.py'),runner_path=str(ROOT/'successor-protocol/runner_v3.py'),verify_challenge=reviewed)
  import google.auth
  from google.auth.transport.requests import Request
  credentials,project=google.auth.default(scopes=['https://www.googleapis.com/auth/cloud-platform'])
  if not project:raise Error('project unavailable')
  def token(provider):
   if provider!='vertex':raise Error('only Vertex permitted')
   if not credentials.valid:credentials.refresh(Request())
   if not credentials.token:raise Error('token unavailable')
   return credentials.token
  transport=OneShotTransport(project,token)
  def guarded(provider,endpoint,raw):
   if provider!='vertex':raise Error('source operations are forbidden')
   if read(contract_path)!=ctx['contract_raw'] or read(challenge_path)!=ctx['challenge_raw'] or read(receipt_path)!=ctx['receipt_raw'] or any(sha(read(ROOT/p))!=h for p,h in ctx['bindings'].items()):
    ledger.stop('successor code or challenge drift');raise Error('binding drift')
   ledger.verify_source_binding()
   return transport(provider,endpoint,raw)
  return runner_v3.run(manifest,dataset,out,ledger,guarded,checker.verify_human,checker.verify_capture)
 finally:ledger.close()
