"""Explicit model dispatch, no action on import.

This is not authority by itself: exact inputs, source receipts, one shared ledger,
a frozen contract and a separately reviewed challenge are required. Semantic
outputs are proposals; this module does not independently adjudicate labels.
"""
from __future__ import annotations
import hashlib,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
for d in ('model-launch','source-successor','cohort-successor-v2','transport'):
    sys.path.insert(0,str(ROOT/d))
import admission
import runner_v2
from oneshot import OneShotTransport

COMPONENTS=('model-launch/trusted_launcher.py','model-launch/model_dispatch.py','model-launch/prepare.py','model-launch/admission.py',
    'source-successor/model_stage.py','source-successor/reopen.py','source-successor/bridge.py','budget-v2/ledger.py',
    'cohort-successor-v2/runner_v2.py','cohort-successor-v2/builder_v2.py',
    'model-launch/news_projection.py','controller/faithful.py','harness/harness.py',
    'model_protocol.py','transport/oneshot.py','dataset-draft-20261029/assembled-v2/manifest.json',
    'ui-serper-price-20261029.json','ui-serper-price-20261029-refresh-v2.json',
    'live-ledger-successor-contract-20261029.json','live-pricing-evidence-20261029.json')
class ModelAdmissionError(ValueError): pass

def sha(b): return hashlib.sha256(b).hexdigest()
def canonical(v): return json.dumps(v,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()
def read(p):
    p=Path(p)
    if not p.is_absolute() or not p.is_file() or p.is_symlink() or p.resolve()!=p.absolute(): raise ModelAdmissionError('invalid evidence path')
    return p.read_bytes()
def decode(raw):
    def pairs(items):
        d={}
        for k,v in items:
            if k in d: raise ModelAdmissionError('duplicate JSON key')
            d[k]=v
        return d
    try: x=json.loads(raw,object_pairs_hook=pairs)
    except (ValueError,TypeError,UnicodeDecodeError) as exc: raise ModelAdmissionError('invalid JSON') from exc
    if not isinstance(x,dict): raise ModelAdmissionError('expected JSON object')
    return x

def activation_verifier(contract_path,challenge_path,receipt_path):
    """Read-only callback for model_stage.activate_model_stage; no credentials.

    Witness identity is an attributed local review, not a cryptographic seal.
    Check the exact challenge, contract, source receipt bytes, summary and code.
    """
    def verify(contract_raw,source_manifest_raw,summary_path):
        try:
            cr,pr,rr=map(read,(contract_path,challenge_path,receipt_path));c,p,r=map(decode,(cr,pr,rr))
            if contract_raw!=cr or c.get('schema')!='faithful-model-stage-contract-v1' or c.get('status')!='frozen' or c.get('execution_mode')!='live': return False
            internal=p.get('internal_digest')
            if (p.get('schema_version')!='eval_contract_challenge_packet_v1' or p.get('overall_state')!='ready'
                or p.get('witness',{}).get('identity')!='audit_go' or p.get('witness',{}).get('mode')!='read_only_offline'
                or p.get('challenged_contract',{}).get('raw_sha256')!=sha(cr)
                or internal!=sha(canonical({k:v for k,v in p.items() if k!='internal_digest'}))
                or r.get('packet_raw_sha256')!=sha(pr) or r.get('packet_byte_count')!=len(pr)
                or r.get('packet_internal_digest')!=internal or r.get('state')!='ready'): return False
            binding=c.get('bindings',{})
            if binding.get('source_receipt_manifest_sha256')!=sha(source_manifest_raw) or binding.get('source_continuation_summary_sha256')!=sha(read(summary_path)): return False
            component=c.get('component_bindings'); observed=p.get('context_binding',{}).get('code_bindings_at_inspection')
            if not isinstance(component,dict) or set(component)!=set(COMPONENTS) or not isinstance(observed,dict): return False
            for rel,h in component.items():
                b=read(ROOT/rel)
                if sha(b)!=h or observed.get(rel)!={'sha256':h,'size':len(b)}: return False
            context=c.get('execution_context')
            if not isinstance(context,dict) or context!=p.get('context_binding',{}).get('execution_context'): return False
            if (c.get('dataset_manifest_sha256')!=binding.get('dataset_manifest_sha256') or
                p.get('context_binding',{}).get('dataset_manifest_sha256')!=binding.get('dataset_manifest_sha256') or
                c.get('source_binding')!=p.get('context_binding',{}).get('source_binding')): return False
            return True
        except (ModelAdmissionError,OSError,ValueError,TypeError,KeyError): return False
    return verify

def validate(contract_path,challenge_path,receipt_path,*,ledger,dataset_root,output_dir):
    """No credentials or network. Immutable challenge is provenance, not a signature."""
    import model_stage
    if not isinstance(ledger,model_stage.ModelLedger): raise ModelAdmissionError('model-stage ledger required')
    cr,pr,rr=map(read,(contract_path,challenge_path,receipt_path)); c,p,r=map(decode,(cr,pr,rr))
    if c.get('schema')!='faithful-model-stage-contract-v1' or c.get('status')!='frozen' or c.get('execution_mode')!='live': raise ModelAdmissionError('live frozen model contract required')
    if (p.get('schema_version')!='eval_contract_challenge_packet_v1' or p.get('overall_state')!='ready'
        or p.get('witness',{}).get('mode')!='read_only_offline' or p.get('witness',{}).get('identity')!='audit_go'
        or p.get('challenged_contract',{}).get('raw_sha256')!=sha(cr)): raise ModelAdmissionError('independent ready challenge required')
    internal=p.get('internal_digest')
    if internal!=sha(canonical({k:v for k,v in p.items() if k!='internal_digest'})) or r.get('packet_raw_sha256')!=sha(pr) or r.get('packet_byte_count')!=len(pr) or r.get('packet_internal_digest')!=internal or r.get('state')!='ready': raise ModelAdmissionError('challenge receipt mismatch')
    bindings=c.get('component_bindings'); observed=p.get('context_binding',{}).get('code_bindings_at_inspection')
    if not isinstance(bindings,dict) or set(bindings)!=set(COMPONENTS) or not isinstance(observed,dict): raise ModelAdmissionError('exact implementation bindings required')
    for rel,h in bindings.items():
        path=ROOT/rel
        if not path.resolve().is_relative_to(ROOT): raise ModelAdmissionError('component outside root')
        data=read(path)
        if sha(data)!=h or observed.get(rel)!={'sha256':h,'size':len(data)}: raise ModelAdmissionError('implementation binding mismatch')
    dataset=Path(dataset_root).resolve();out=Path(output_dir).absolute()
    if out.exists() or out.parent.resolve()!=out.parent.absolute(): raise ModelAdmissionError('output exists or has unsafe path')
    context={'artifact_root':str(ROOT),'dataset_root':str(dataset),'ledger_root':str(ledger.root.resolve()),'output_dir':str(out),'cwd':str(Path.cwd().resolve())}
    if c.get('execution_context')!=context or p.get('context_binding',{}).get('execution_context')!=context: raise ModelAdmissionError('execution context mismatch')
    manifest_raw=read(dataset/'manifest.json'); manifest=decode(manifest_raw)
    if sha(manifest_raw)!=c.get('dataset_manifest_sha256') or c.get('bindings',{}).get('dataset_manifest_sha256')!=sha(manifest_raw) or p.get('context_binding',{}).get('dataset_manifest_sha256')!=sha(manifest_raw): raise ModelAdmissionError('dataset mismatch')
    # Bridge is responsible for validating all eight exact settled receipts,
    # their raw hashes, completion marker and the prior carry.
    binding=ledger.verify_source_binding()
    if binding!=c.get('source_binding') or p.get('context_binding',{}).get('source_binding')!=binding: raise ModelAdmissionError('source receipt binding mismatch')
    limits={'total_cap_micro_usd':40000000,'known_pre_source_exposure_micro_usd':721593,
        'max_generation_attempts_including_prior':835,'max_countTokens_including_prior':767,
        'model':'gemini-3.8-flash','location':'global','slots':32,'timeout_seconds':420,'retries':0}
    if any(c.get(k)!=v for k,v in limits.items()) or c.get('caps')!={'total_usd_micro':40000000,'total_generation_attempts':835,'total_count_attempts':767,'total_source_attempts':18}: raise ModelAdmissionError('budget or design mismatch')
    summary=ledger.summary()
    if (summary.get('stopped') or summary.get('generation_attempts')!=79 or summary.get('count_attempts')!=11
        or summary.get('source_attempts')!=8 or not 723593<=summary.get('exposure_micro',-1)<40000000):
        raise ModelAdmissionError('ledger counts, status or prior carry mismatch')
    pred=ROOT/'dataset-draft-20261029/assembled-v2'; checker=admission.Admission(pred,dataset,ledger)
    cases=runner_v2.preflight(manifest,dataset,ledger,checker.verify_human,checker.verify_capture)
    if len(cases)!=8 or len(runner_v2.schedule(cases))!=32: raise ModelAdmissionError('model schedule differs from frozen design')
    return {'contract':c,'contract_raw':cr,'challenge_raw':pr,'receipt_raw':rr,'manifest':manifest,'checker':checker,'bindings':bindings,'paths':(Path(contract_path),Path(challenge_path),Path(receipt_path)),'dataset':dataset,'out':out,'source_binding':binding}

def execute(contract_path,challenge_path,receipt_path,*,ledger,dataset_root,output_dir):
    """Run only a reviewed live contract, no fixture transport or retry."""
    ctx=validate(contract_path,challenge_path,receipt_path,ledger=ledger,dataset_root=dataset_root,output_dir=output_dir)
    # ADC resolution happens only after admission; no token is serialized or logged.
    import google.auth
    from google.auth.transport.requests import Request
    credentials,project=google.auth.default(scopes=['https://www.googleapis.com/auth/cloud-platform'])
    if not project: raise ModelAdmissionError('project unavailable')
    def token(provider):
        if provider!='vertex': raise ValueError('only vertex model is permitted')
        if not credentials.valid: credentials.refresh(Request())
        if not credentials.token: raise ValueError('token unavailable')
        return credentials.token
    transport=OneShotTransport(project,token)
    def guarded(provider,endpoint,raw):
        if provider!='vertex': raise ModelAdmissionError('provider outside scope')
        if tuple(read(p) for p in ctx['paths'])!=(ctx['contract_raw'],ctx['challenge_raw'],ctx['receipt_raw']):
            ledger.stop('model contract or challenge drift');raise ModelAdmissionError('model binding drift')
        for rel,h in ctx['bindings'].items():
            if sha(read(ROOT/rel))!=h:
                ledger.stop('model component drift');raise ModelAdmissionError('model binding drift')
        if ledger.verify_source_binding()!=ctx['source_binding']:
            ledger.stop('source receipt binding drift');raise ModelAdmissionError('model source drift')
        return transport(provider,endpoint,raw)
    return runner_v2.run(ctx['manifest'],ctx['dataset'],ctx['out'],ledger,guarded,
                         ctx['checker'].verify_human,ctx['checker'].verify_capture)
