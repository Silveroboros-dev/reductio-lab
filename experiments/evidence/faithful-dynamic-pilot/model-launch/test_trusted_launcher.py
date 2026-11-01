import hashlib,json,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT/'model-launch'))
import model_dispatch as m

def sha(x):return hashlib.sha256(x).hexdigest()
def enc(x):return json.dumps(x,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()

def runcheck(tmp,bad=False):
    bindings={x:sha((ROOT/x).read_bytes()) for x in m.COMPONENTS}
    if bad:bindings['source-successor/reopen.py']='0'*64
    context={'artifact_root':str(ROOT),'cwd':str(Path.cwd().resolve())}
    c={'schema':'faithful-model-stage-contract-v1','status':'frozen','execution_mode':'live','component_bindings':bindings,'execution_context':context,'dataset_manifest_sha256':'fixture','source_binding':{'fixture':True}}
    cp=tmp/'contract';cp.write_bytes(enc(c));code={x:{'sha256':h,'size':len((ROOT/x).read_bytes())} for x,h in bindings.items()}
    p={'schema_version':'eval_contract_challenge_packet_v1','overall_state':'ready','witness':{'identity':'audit_go','mode':'read_only_offline'},'challenged_contract':{'raw_sha256':sha(cp.read_bytes())},'context_binding':{'code_bindings_at_inspection':code,'execution_context':context,'dataset_manifest_sha256':'fixture','source_binding':{'fixture':True}}};p['internal_digest']=sha(enc(p))
    pp=tmp/'packet';pp.write_bytes(enc(p));r=pp.read_bytes();rp=tmp/'receipt';rp.write_bytes(enc({'state':'ready','packet_raw_sha256':sha(r),'packet_byte_count':len(r),'packet_internal_digest':p['internal_digest']}))
    snippet="import sys;sys.path.insert(0,sys.argv[1]);import trusted_launcher as t;t.verify_before_import(sys.argv[2],sys.argv[3],sys.argv[4],expected_contract_sha256=sys.argv[5],expected_launcher_sha256=sys.argv[6]);assert 'reopen' not in sys.modules"
    return subprocess.run([sys.executable,'-c',snippet,str(ROOT/'model-launch'),str(cp),str(pp),str(rp),sha(cp.read_bytes()),sha((ROOT/'model-launch/trusted_launcher.py').read_bytes())],capture_output=True)

def test_bootstrap_accepts_reviewed_files_before_import(tmp_path):assert runcheck(tmp_path).returncode==0

def test_bootstrap_rejects_altered_reopen_before_import(tmp_path):assert runcheck(tmp_path,True).returncode!=0
