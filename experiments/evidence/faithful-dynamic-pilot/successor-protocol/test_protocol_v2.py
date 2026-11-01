import json,sys
from pathlib import Path
import pytest
ROOT=Path(__file__).resolve().parent.parent
for x in ('successor-protocol','controller','harness'):sys.path.insert(0,str(ROOT/x))
import model_protocol_v2 as v2
import harness,faithful
from test_harness import task,replay
from test_faithful import fixture

def message(stage,payload):
    request=v2.request(stage,payload)
    return json.loads(request['contents'][0]['parts'][0]['text'])

def test_baseline_faithful_protocol_are_explicit_and_role_scoped():
    seen=[]
    def baseline(stage,payload):
        sent=message(stage,payload);seen.append((stage,sent))
        if stage=='source_selection':return {'action':'query','action_id':'a','rationale':'fixture','expectation':'fixture'}
        if stage=='self_check':return {'action':'query','action_id':'a','rationale':'fixture','expectation':'fixture'}
        if stage=='after_query':return {'answers':[{'contract_id':'contract-1','label':'unknown','citations':['pa'],'explanation':'fixture'}],'stop_reason':'fixture'}
        raise AssertionError(stage)
    for arm in ('B','B_self_check'):
        out=harness.BaselineEngine(baseline).run(task(),replay(),arm)
        assert out['status']=='completed' and out['selected_action_id']=='a'
    baseline_prompts=[x['instruction'] for stage,x in seen if stage=='source_selection']
    assert all('"query", "stop", or "reflect"' in x and 'action_id must be null' in x for x in baseline_prompts)
    sent=[]
    def faithful_gen(stage,payload):
        q=message(stage,payload);sent.append((stage,q))
        if stage=='source_selection':return {'action':'query','action_id':'a','rationale':'fixture','expectation':'fixture'}
        if stage=='selection':return {'alternatives':[['s3']]}
        if stage=='inference':return {'conclusion':'The evidence is insufficient to determine fit.'}
        if stage=='halter':return {'sufficient':True}
        if stage=='value':return {'score':0.5}
        if stage=='formatter':return {'answers':[{'contract_id':'market-A','label':'unknown'}]}
        raise AssertionError(stage)
    t,r=fixture();out=faithful.Engine(faithful_gen).run(t,r)
    assert out['status']=='proposal' and any(e.get('action_id')=='a' and e['event']=='source_replayed' for e in out['events'])
    rule=next(q['instruction'] for stage,q in sent if stage=='source_selection')
    assert '"query" or "stop"' in rule and 'Do not use "reflect"' in rule

def test_unknown_source_instruction_fails_closed():
    with pytest.raises(ValueError):message('source_selection',{'instruction':'not bound'})

def test_legacy_unexpected_actions_are_not_silently_normalized():
    for bad in ('action','call','use_tool'):
        with pytest.raises(harness.ProtocolError):
            harness.BaselineEngine(lambda stage,payload:{'action':bad,'action_id':'a'}).run(task(),replay(),'B')
        t,r=fixture();out=faithful.Engine(lambda stage,payload:{'action':bad,'action_id':'a'}).run(t,r)
        assert out['status']=='technical_failure'

def test_runner_uses_successor_prompt_adapter():
    import runner_v3
    assert runner_v3.model_protocol is v2

def test_reflect_and_self_check_list_literals_without_pipe_string():
    for stage,literals in [('reflect',('"query"','"stop"','"reflect"')),('self_check',('"query"','"stop"'))]:
        text=message(stage,{'available_actions':[]})['instruction']
        assert all(x in text for x in literals)
        assert 'query|stop' not in text
        assert 'exactly one literal' in text
    assert 'Never use reflect' in message('self_check',{})['instruction']
