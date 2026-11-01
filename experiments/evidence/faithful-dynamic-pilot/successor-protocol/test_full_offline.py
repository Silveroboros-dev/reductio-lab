"""End-to-end fake transport; real frozen input bytes, disposable model ledger."""
import json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
for p in ('successor-protocol','model-accounting-successor','source-successor','model-launch','budget-v2'):
    sys.path.insert(0,str(ROOT/p))
import model_accounting, runner_v3, admission
from ledger import Ledger

def test_full_32_slot_schedule_with_mock_transport_and_existing_inputs(tmp_path):
    config=json.loads((ROOT/'model-successor-ledger-contract-20261029.json').read_bytes())
    ledger=Ledger(str(tmp_path/'ledger'),config,create=True)
    source=model_accounting._open_parent()
    class FakeCombined:
        def __init__(self): self.db=ledger.db
        def receipt(self,op): return source.receipt(op)
        def summary(self):
            x=ledger.summary();x['source_attempts']+=8;return x
        def count(self,*x): return ledger.count(*x)
        def generate(self,*x): return ledger.generate(*x)
        def stop(self,*x): return ledger.stop(*x)
    fake=FakeCombined();called=[]
    def transport(provider,endpoint,request):
        assert provider=='vertex'
        if endpoint=='countTokens':return 200,b'{"totalTokens":100}'
        payload=json.loads(json.loads(request)['contents'][0]['parts'][0]['text']);stage=payload['stage'];p=payload['input'];called.append(stage)
        if stage=='source_selection':
            aid=p['available_actions'][0]['id'] if p['available_actions'] else None
            response={'action':'query' if aid else 'stop','action_id':aid,'rationale':'fixture','expectation':'fixture'}
        elif stage=='self_check':
            aid=p['available_actions'][0]['id'] if p['available_actions'] else None
            response={'action':'query' if aid else 'stop','action_id':aid,'rationale':'fixture','expectation':'fixture'}
        elif stage in ('answer','after_query'):
            response={'answers':[{'contract_id':x,'label':'unknown','citations':[],'explanation':'fixture'} for x in p['contract_ids']],'stop_reason':'fixture','observed_vs_expected':None}
        elif stage=='selection':response={'alternatives':[['market-id']]}
        elif stage=='inference':response={'conclusion':'Fixture: insufficient evidence.'}
        elif stage=='halter':response={'sufficient':True}
        elif stage=='value':response={'score':0.5}
        elif stage=='formatter':response={'answers':[{'contract_id':x,'label':'unknown'} for x in p['contract_ids']]}
        else:raise AssertionError(stage)
        raw={'modelVersion':'gemini-3.8-flash','usageMetadata':{'promptTokenCount':100,'totalTokenCount':200,'thoughtsTokenCount':20},'candidates':[{'finishReason':'STOP','content':{'parts':[{'text':json.dumps(response)}]}}]}
        return 200,json.dumps(raw).encode()
    ds=ROOT/'dataset-draft-20261029/assembled-v3';checker=admission.Admission(ROOT/'dataset-draft-20261029/assembled-v2',ds,fake)
    try:
        result=runner_v3.run(json.loads((ds/'manifest.json').read_bytes()),ds,tmp_path/'result',fake,transport,checker.verify_human,checker.verify_capture)
        assert (result['attempted_slots'],result['not_attempted_slots'])==(32,0)
        assert all(x.get('status')!='technical_failure' and x.get('semantic_status')!='technical_failure' for x in result['results'])
        assert 'self_check' in called and 'selection' in called and 'formatter' in called
    finally:source.close();ledger.close()
