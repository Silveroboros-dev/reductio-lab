import json,sys
from pathlib import Path
import pytest
ROOT=Path(__file__).resolve().parent.parent
for d in ('model-launch','source-successor'):sys.path.insert(0,str(ROOT/d))
import model_dispatch as m, model_stage

def enc(x):return json.dumps(x,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()
class FakeLedger:
    def __init__(self,root):self.root=root
    def verify_source_binding(self):return {'fixture':'8 settled receipts'}
    def summary(self):return {'stopped':0,'generation_attempts':79,'count_attempts':11,'source_attempts':8,'exposure_micro':737593}

def fixture(tmp_path,monkeypatch):
    monkeypatch.setattr(model_stage,'ModelLedger',FakeLedger)
    monkeypatch.setattr(m.runner_v2,'preflight',lambda *a:[None]*8)
    monkeypatch.setattr(m.runner_v2,'schedule',lambda c:[None]*32)
    ds=tmp_path/'dataset';ds.mkdir();(ds/'manifest.json').write_bytes(enc({'fixture':True}))
    ledger=FakeLedger(tmp_path/'ledger');ledger.root.mkdir();out=tmp_path/'out'
    bindings={x:m.sha((ROOT/x).read_bytes()) for x in m.COMPONENTS}
    context={'artifact_root':str(ROOT),'dataset_root':str(ds),'ledger_root':str(ledger.root),'output_dir':str(out),'cwd':str(Path.cwd().resolve())}
    c={'schema':'faithful-model-stage-contract-v1','status':'frozen','execution_mode':'live','component_bindings':bindings,'execution_context':context,'dataset_manifest_sha256':m.sha((ds/'manifest.json').read_bytes()),'bindings':{'dataset_manifest_sha256':m.sha((ds/'manifest.json').read_bytes())},'source_binding':ledger.verify_source_binding(),'total_cap_micro_usd':40000000,'known_pre_source_exposure_micro_usd':721593,'max_generation_attempts_including_prior':835,'max_countTokens_including_prior':767,'model':'gemini-3.8-flash','location':'global','slots':32,'timeout_seconds':420,'retries':0,'caps':{'total_usd_micro':40000000,'total_generation_attempts':835,'total_count_attempts':767,'total_source_attempts':18}}
    cp=tmp_path/'contract';ch=tmp_path/'challenge';rp=tmp_path/'receipt'
    def save():
        cp.write_bytes(enc(c));obs={x:{'sha256':h,'size':len((ROOT/x).read_bytes())} for x,h in bindings.items()}
        p={'schema_version':'eval_contract_challenge_packet_v1','overall_state':'ready','witness':{'mode':'read_only_offline','identity':'audit_go'},'challenged_contract':{'raw_sha256':m.sha(cp.read_bytes())},'context_binding':{'code_bindings_at_inspection':obs,'execution_context':context,'dataset_manifest_sha256':c['dataset_manifest_sha256'],'source_binding':c['source_binding']}}
        p['internal_digest']=m.sha(m.canonical(p));ch.write_bytes(enc(p));r=ch.read_bytes();rp.write_bytes(enc({'state':'ready','packet_raw_sha256':m.sha(r),'packet_byte_count':len(r),'packet_internal_digest':p['internal_digest']}))
    save()
    return c,cp,ch,rp,ledger,ds,out,save

def test_freeze_and_challenge_accept_only_exact_bytes(tmp_path,monkeypatch):
    c,cp,ch,rp,ledger,ds,out,save=fixture(tmp_path,monkeypatch)
    assert m.validate(cp,ch,rp,ledger=ledger,dataset_root=ds,output_dir=out)['manifest']=={'fixture':True}
    (ds/'manifest.json').write_bytes(b'{}')
    with pytest.raises(m.ModelAdmissionError):m.validate(cp,ch,rp,ledger=ledger,dataset_root=ds,output_dir=out)

def test_invalid_budget_or_challenge_blocks_before_credentials(tmp_path,monkeypatch):
    c,cp,ch,rp,ledger,ds,out,save=fixture(tmp_path,monkeypatch)
    c['caps']['total_usd_micro']=40000001;save()
    with pytest.raises(m.ModelAdmissionError):m.validate(cp,ch,rp,ledger=ledger,dataset_root=ds,output_dir=out)
    c['caps']['total_usd_micro']=40000000;save();packet=json.loads(ch.read_bytes());packet['overall_state']='blocked';ch.write_bytes(enc(packet))
    with pytest.raises(m.ModelAdmissionError):m.validate(cp,ch,rp,ledger=ledger,dataset_root=ds,output_dir=out)

def test_activation_verifier_binds_exact_manifest_and_summary(tmp_path,monkeypatch):
    c,cp,ch,rp,ledger,ds,out,save=fixture(tmp_path,monkeypatch)
    summary=tmp_path/'source-summary';summary.write_bytes(b'{"status":"completed"}')
    source=b'{"records":[]}';c['bindings']['source_receipt_manifest_sha256']=m.sha(source);c['bindings']['source_continuation_summary_sha256']=m.sha(summary.read_bytes());save()
    verify=m.activation_verifier(cp,ch,rp)
    assert verify(cp.read_bytes(),source,summary)
    assert not verify(cp.read_bytes(),source+b' ',summary)
    summary.write_bytes(b'{}');assert not verify(cp.read_bytes(),source,summary)
