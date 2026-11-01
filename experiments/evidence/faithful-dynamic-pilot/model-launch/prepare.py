"""Prepare content-bound model contract and source receipt manifest offline.

Does not activate the model stage, obtain credentials, issue requests or assert
that an independent witness approved anything. Inputs must already be settled.
"""
from __future__ import annotations
import json, os, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
for d in ('model-launch','source-successor','cohort-successor-v2'):
    sys.path.insert(0,str(ROOT/d))
import admission, model_dispatch, model_stage, runner_v2

def put(path,raw):
    path=Path(path)
    if not path.is_absolute() or path.parent.resolve()!=path.parent.absolute(): raise ValueError('absolute create-only path required')
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,'O_NOFOLLOW',0),0o600)
    try:
        view=memoryview(raw)
        while view:
            n=os.write(fd,view)
            if n<=0: raise OSError('short write')
            view=view[n:]
        os.fsync(fd)
    finally: os.close(fd)
    fd=os.open(path.parent,os.O_RDONLY)
    try: os.fsync(fd)
    finally: os.close(fd)

def prepare(*,phase, source_contract_path, source_summary_path, source_manifest_path,
            dataset_root, output_dir, model_contract_path):
    """Write exact receipt manifest then model contract, no provider effects.

    Partial creation is retained on failure. Each output is create-only.
    A separately reviewed challenge is still mandatory.
    """
    source_contract_raw=model_dispatch.read(source_contract_path)
    source_contract=model_dispatch.decode(source_contract_raw)
    if source_contract.get('schema')!='faithful-source-capture-contract-v4' or source_contract.get('status')!='frozen': raise ValueError('wrong frozen source contract')
    source_contract_sha=model_dispatch.sha(source_contract_raw)
    source_summary_raw=model_dispatch.read(source_summary_path)
    dataset=Path(dataset_root).resolve(); dataset_raw=model_dispatch.read(dataset/'manifest.json');manifest=model_dispatch.decode(dataset_raw)
    output=Path(output_dir)
    if not output.is_absolute() or output.exists() or output.parent.resolve()!=output.parent.absolute(): raise ValueError('model output path unavailable')
    checker=admission.Admission(ROOT/'dataset-draft-20261029/assembled-v2',dataset,phase)
    cases=runner_v2.preflight(manifest,dataset,phase,checker.verify_human,checker.verify_capture)
    if len(cases)!=8 or len(runner_v2.schedule(cases))!=32: raise ValueError('wrong experiment cohort')
    receipt_bytes=model_stage.prepare_binding(phase,source_summary_path,source_contract_sha)
    receipts=model_dispatch.decode(receipt_bytes)
    if receipts.get('source_attempts_total')!=8 or len(receipts.get('records',[]))!=8: raise ValueError('source cohort incomplete')
    source_binding={'schema':'faithful-model-source-binding-v1',
        'source_continuation_contract_sha256':source_contract_sha,
        'source_continuation_summary_sha256':model_dispatch.sha(source_summary_raw),
        'source_receipt_manifest_sha256':model_dispatch.sha(receipt_bytes),
        'source_attempts_total':8,'records':receipts['records']}
    files={rel:model_dispatch.sha(model_dispatch.read(ROOT/rel)) for rel in model_dispatch.COMPONENTS}
    context={'artifact_root':str(ROOT),'dataset_root':str(dataset),'ledger_root':str(phase.root.resolve()),
        'output_dir':str(output),'cwd':str(Path.cwd().resolve())}
    bindings={'predecessor_db_sha256':model_stage.OLD_DB_SHA,'source_continuation_contract_sha256':source_contract_sha,
        'source_continuation_summary_sha256':model_dispatch.sha(source_summary_raw),
        'source_receipt_manifest_sha256':model_dispatch.sha(receipt_bytes),
        'successor_ledger_contract_sha256':model_stage.SUCCESSOR_LEDGER_CONTRACT_FILE_SHA,
        'dataset_manifest_sha256':model_dispatch.sha(dataset_raw),
        'runner_sha256':files['cohort-successor-v2/runner_v2.py']}
    contract={'schema':'faithful-model-stage-contract-v1','status':'frozen','execution_mode':'live',
        'bindings':bindings,'component_bindings':files,'execution_context':context,
        'dataset_manifest_sha256':model_dispatch.sha(dataset_raw),'source_binding':source_binding,
        'caps':{'total_usd_micro':40000000,'total_generation_attempts':835,'total_count_attempts':767,'total_source_attempts':18},
        'total_cap_micro_usd':40000000,'known_pre_source_exposure_micro_usd':721593,
        'max_generation_attempts_including_prior':835,'max_countTokens_including_prior':767,
        'model':'gemini-3.8-flash','location':'global','slots':32,'timeout_seconds':420,'retries':0,
        'review_status':'not adjudicated; operator provenance checks are not independent semantic review'}
    if Path(source_manifest_path)==Path(model_contract_path): raise ValueError('outputs must be distinct')
    put(source_manifest_path,receipt_bytes)
    contract_raw=model_dispatch.canonical(contract)
    put(model_contract_path,contract_raw)
    return {'model_contract_sha256':model_dispatch.sha(contract_raw),'source_manifest_sha256':model_dispatch.sha(receipt_bytes),
            'source_binding':source_binding,'execution_context':context,'component_bindings':files}
