import pytest
from reasoning_engine.reviewer import review_packet, validate_review
from reasoning_engine.replay_sources import digest


def test_review_packet_never_includes_unchosen_source_or_arm_identity():
    inp={'task':'Q','thesis':'T','initial_evidence':[],'preconsumed_action_ids':[],
         'replay_max_actions':1,'replay_max_simulated_micro_usd':2,
         'tool_catalog':[{'action_id':'x','description':'first','quoted_micro_usd':1,'capture_ref':'x'},
                         {'action_id':'y','description':'second','quoted_micro_usd':1,'capture_ref':'y'}]}
    cp={'case_id':'c','input':inp,'input_version':digest(inp)}
    rows=[]
    for aid in ('x','y'):
        payload={'text':'secret-'+aid}
        rows.append({'case_id':'c','action_id':aid,'capture_ref':aid,'saved_response':{'payload':payload,'response_sha256':digest(payload)}})
    out={'arm':'C','result':{'answer':'one'},'history':[{'kind':'replay_retrieval','action_id':'x'}]}
    packet=review_packet(cp,rows,out,{'status':'candidate'})
    assert 'secret-x' in str(packet) and 'secret-y' not in str(packet)
    assert 'arm' not in packet and 'C' not in str(packet['actions_taken'])


def test_advisory_review_is_not_human_approval():
    review={'answer_verdict':'unclear','action_verdict':'unclear','alignment_verdict':'unclear','explanation':'Insufficient.'}
    result=validate_review(review)
    assert result['human_review']=='not_performed' and 'not_independent' in result['independence']
    review['answer_verdict']='invented'
    with pytest.raises(ValueError):validate_review(review)
