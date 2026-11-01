import hashlib,json,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT/'successor-protocol'))
import launcher

def sha(b):return hashlib.sha256(b).hexdigest()
def enc(x):return json.dumps(x,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()
def runfixture(tmp,bad=False):
    files={p:sha((ROOT/p).read_bytes()) for p in launcher.FILES}
    if bad:files['model-accounting-successor/model_accounting.py']='0'*64
    context={'artifact_root':str(ROOT),'cwd':str(Path.cwd().resolve())};bindings={'fixture':'binding'}
    c={'schema':'faithful-model-successor-contract-v1','status':'frozen','component_bindings':files,'execution_context':context,'bindings':bindings,'caps':{'total_usd_micro':40000000,'total_generation_attempts':835,'total_count_attempts':767,'total_source_attempts':18,'slots':32}}
    cp=tmp/'c';cp.write_bytes(enc(c));observed={p:{'sha256':h,'size':len((ROOT/p).read_bytes())} for p,h in files.items()}
    p={'schema_version':'eval_contract_challenge_packet_v1','overall_state':'ready','witness':{'identity':'audit_go','mode':'read_only_offline'},'challenged_contract':{'raw_sha256':sha(cp.read_bytes())},'context_binding':{'code_bindings_at_inspection':observed,'execution_context':context,'bindings':bindings}};p['internal_digest']=sha(enc(p))
    pp=tmp/'p';pp.write_bytes(enc(p));r=pp.read_bytes();rp=tmp/'r';rp.write_bytes(enc({'state':'ready','packet_raw_sha256':sha(r),'packet_byte_count':len(r),'packet_internal_digest':p['internal_digest']}))
    script="import sys;sys.path.insert(0,sys.argv[1]);import launcher as x;x.verify(sys.argv[2],sys.argv[3],sys.argv[4],contract_sha256=sys.argv[5],launcher_sha256=sys.argv[6]);assert 'model_accounting' not in sys.modules"
    return subprocess.run([sys.executable,'-c',script,str(ROOT/'successor-protocol'),str(cp),str(pp),str(rp),sha(cp.read_bytes()),sha((ROOT/'successor-protocol/launcher.py').read_bytes())],capture_output=True)

def test_verifies_all_code_before_project_import(tmp_path):assert runfixture(tmp_path).returncode==0

def test_changed_accounting_fails_before_import(tmp_path):assert runfixture(tmp_path,True).returncode!=0
