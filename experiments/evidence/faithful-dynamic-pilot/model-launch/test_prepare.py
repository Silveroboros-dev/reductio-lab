import json,sys
from pathlib import Path
import pytest
ROOT=Path(__file__).resolve().parent.parent
for d in ('model-launch','source-successor','cohort-successor-v2'):sys.path.insert(0,str(ROOT/d))
import prepare

def enc(x):return json.dumps(x,sort_keys=True,separators=(',',':')).encode()

def setup(tmp,monkeypatch):
    ds=tmp/'dataset';ds.mkdir();(ds/'manifest.json').write_bytes(b'{}');ledger=tmp/'ledger';ledger.mkdir()
    class Phase:
        root=ledger
    phase=Phase();source=tmp/'source-contract';source.write_bytes(enc({'schema':'faithful-source-capture-contract-v4','status':'frozen'}));summary=tmp/'summary';summary.write_bytes(b'{}')
    monkeypatch.setattr(prepare.runner_v2,'preflight',lambda *a:[None]*8)
    monkeypatch.setattr(prepare.runner_v2,'schedule',lambda *a:[None]*32)
    monkeypatch.setattr(prepare.model_stage,'prepare_binding',lambda *a:enc({'source_attempts_total':8,'records':[{'fixture':i} for i in range(8)]}))
    return {'phase':phase,'source_contract_path':source,'source_summary_path':summary,'source_manifest_path':tmp/'source-manifest','dataset_root':ds,'output_dir':tmp/'output','model_contract_path':tmp/'model-contract'}

def test_create_only_contract_has_exact_source_and_component_bindings(tmp_path,monkeypatch):
    kw=setup(tmp_path,monkeypatch); result=prepare.prepare(**kw)
    c=json.loads(kw['model_contract_path'].read_bytes())
    assert result['model_contract_sha256']==prepare.model_dispatch.sha(kw['model_contract_path'].read_bytes())
    assert c['bindings']['source_receipt_manifest_sha256']==prepare.model_dispatch.sha(kw['source_manifest_path'].read_bytes())
    assert set(c['component_bindings'])==set(prepare.model_dispatch.COMPONENTS)
    with pytest.raises(FileExistsError):prepare.prepare(**kw)

def test_preflight_failure_writes_nothing(tmp_path,monkeypatch):
    kw=setup(tmp_path,monkeypatch)
    monkeypatch.setattr(prepare.runner_v2,'preflight',lambda *a:[])
    with pytest.raises(ValueError):prepare.prepare(**kw)
    assert not kw['source_manifest_path'].exists() and not kw['model_contract_path'].exists()
