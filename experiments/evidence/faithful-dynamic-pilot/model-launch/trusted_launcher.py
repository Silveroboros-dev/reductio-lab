"""Minimal bootstrap for a separately challenged model run.

Import this module only after a trusted operator has checked its exact file SHA
against the independently reviewed contract. Import performs no network or
ledger write. `execute_reviewed` is the explicit live action.
"""
from __future__ import annotations
import hashlib,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
REQUIRED={'model-launch/trusted_launcher.py','model-launch/model_dispatch.py',
          'source-successor/reopen.py','source-successor/model_stage.py',
          'source-successor/bridge.py','budget-v2/ledger.py'}
PROTECTED=('reopen','model_stage','bridge','ledger','runner_v2','faithful','harness',
           'model_protocol','admission','news_projection','oneshot','model_dispatch')
class BootstrapError(ValueError):pass

def sha(raw):return hashlib.sha256(raw).hexdigest()
def canonical(obj):return json.dumps(obj,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()
def read(path):
    p=Path(path)
    if not p.is_absolute() or not p.is_file() or p.is_symlink() or p.resolve()!=p.absolute():raise BootstrapError('unsafe input path')
    return p.read_bytes()
def obj(raw):
    def pairs(items):
        d={}
        for k,v in items:
            if k in d:raise BootstrapError('duplicate key')
            d[k]=v
        return d
    try:x=json.loads(raw,object_pairs_hook=pairs)
    except (ValueError,UnicodeDecodeError,TypeError) as exc:raise BootstrapError('invalid JSON') from exc
    if not isinstance(x,dict):raise BootstrapError('object required')
    return x

def verify_before_import(contract_path,challenge_path,receipt_path,*,expected_contract_sha256,expected_launcher_sha256):
    """Verify challenge and all bound file bytes before importing project modules."""
    if any(name in sys.modules for name in PROTECTED):raise BootstrapError('fresh Python process required')
    cr,pr,rr=map(read,(contract_path,challenge_path,receipt_path));c,p,r=map(obj,(cr,pr,rr))
    if sha(cr)!=expected_contract_sha256 or c.get('schema')!='faithful-model-stage-contract-v1' or c.get('status')!='frozen' or c.get('execution_mode')!='live':raise BootstrapError('contract mismatch')
    digest=p.get('internal_digest')
    if (p.get('schema_version')!='eval_contract_challenge_packet_v1' or p.get('overall_state')!='ready'
        or p.get('witness',{}).get('identity')!='audit_go' or p.get('witness',{}).get('mode')!='read_only_offline'
        or p.get('challenged_contract',{}).get('raw_sha256')!=sha(cr)
        or digest!=sha(canonical({k:v for k,v in p.items() if k!='internal_digest'}))
        or r.get('packet_raw_sha256')!=sha(pr) or r.get('packet_byte_count')!=len(pr)
        or r.get('packet_internal_digest')!=digest or r.get('state')!='ready'):
        raise BootstrapError('review challenge mismatch')
    bindings=c.get('component_bindings');observed=p.get('context_binding',{}).get('code_bindings_at_inspection')
    if not isinstance(bindings,dict) or not REQUIRED.issubset(bindings) or not isinstance(observed,dict):raise BootstrapError('missing bootstrap bindings')
    if bindings.get('model-launch/trusted_launcher.py')!=expected_launcher_sha256:raise BootstrapError('launcher SHA mismatch')
    for rel,h in bindings.items():
        if not isinstance(rel,str) or Path(rel).is_absolute():raise BootstrapError('invalid component path')
        path=ROOT/rel
        if not path.resolve().is_relative_to(ROOT):raise BootstrapError('component escapes root')
        raw=read(path)
        if sha(raw)!=h or observed.get(rel)!={'sha256':h,'size':len(raw)}:raise BootstrapError('component drift')
    context=c.get('execution_context')
    if not isinstance(context,dict) or context!=p.get('context_binding',{}).get('execution_context') or context.get('artifact_root')!=str(ROOT) or context.get('cwd')!=str(Path.cwd().resolve()):raise BootstrapError('execution context mismatch')
    if c.get('dataset_manifest_sha256')!=p.get('context_binding',{}).get('dataset_manifest_sha256') or c.get('source_binding')!=p.get('context_binding',{}).get('source_binding'):raise BootstrapError('reviewed inputs mismatch')
    return c

def execute_reviewed(contract_path,challenge_path,receipt_path,*,expected_contract_sha256,expected_launcher_sha256,
                     source_summary_path,source_manifest_path):
    """Reopen once, activate and run live only after complete bootstrap review."""
    c=verify_before_import(contract_path,challenge_path,receipt_path,expected_contract_sha256=expected_contract_sha256,expected_launcher_sha256=expected_launcher_sha256)
    for d in ('model-launch','source-successor','cohort-successor-v2','budget-v2','transport'):
        sys.path.insert(0,str(ROOT/d))
    import reopen, model_stage, model_dispatch
    source_sha=c['bindings']['source_continuation_contract_sha256'];context=c['execution_context']
    phase=reopen.reopen_completed_successor(context['ledger_root'],summary_path=source_summary_path,source_contract_sha256=source_sha)
    try:
        ledger=model_stage.activate_model_stage(phase,summary_path=source_summary_path,source_contract_sha256=source_sha,
            source_manifest_path=source_manifest_path,dataset_manifest_path=Path(context['dataset_root'])/'manifest.json',
            runner_path=ROOT/'cohort-successor-v2'/'runner_v2.py',model_contract_path=contract_path,
            expected_model_contract_sha256=expected_contract_sha256,
            verify_challenge=model_dispatch.activation_verifier(contract_path,challenge_path,receipt_path))
        return model_dispatch.execute(contract_path,challenge_path,receipt_path,ledger=ledger,
            dataset_root=context['dataset_root'],output_dir=context['output_dir'])
    finally:phase.close()
