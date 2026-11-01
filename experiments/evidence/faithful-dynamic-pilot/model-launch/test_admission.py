import json,sys,copy
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT/'model-launch'))
from admission import Admission
PRED=ROOT/'dataset-draft-20261029/assembled-v2'

def test_approved_human_wording_and_historical_reviews_are_bound():
    m=json.loads((PRED/'manifest.json').read_bytes()); a=Admission(PRED,ROOT/'unused',None)
    for row in m['cases']:
        case=json.loads((PRED/row['input_path']).read_bytes());raw=(PRED/row['human_attestation_path']).read_bytes()
        assert a.verify_human(raw,case,row)
        changed=copy.deepcopy(case)
        for e in changed['task']['initial_evidence']:
            if e.get('id')=='thesis':e['text']+=' drift'
        assert not a.verify_human(raw,changed,row)
        assert not a.verify_human(raw+b' ',case,row)

def test_builder_with_bound_fake_receipts_and_real_verifiers(tmp_path, monkeypatch):
    sys.path.insert(0,str(ROOT/'cohort-successor-v2'))
    import builder_v2,runner_v2
    old=ROOT/'ui-serper-price-20261029.json';new=ROOT/'ui-serper-price-20261029-refresh-v2.json'
    rows=json.loads((PRED/'manifest.json').read_bytes())['cases'];receipts={}
    for i,row in enumerate(rows,1):
        case=json.loads((PRED/row['input_path']).read_bytes());request=builder_v2.request_for(case['draft_paid_source']['request_body'])
        raw=builder_v2.encode({'success':True,'priceCents':0.2,'requestId':f'fixture-{i}','data':{'news':[{'title':f'item {j}','date':'2 days ago'} for j in range(10)]}})
        view=json.loads((old if i==1 else new).read_bytes());seen=__import__('datetime').datetime.fromisoformat(view['observed_at_utc']);start=seen+__import__('datetime').timedelta(seconds=2);expiry=seen+__import__('datetime').timedelta(seconds=900)
        quote_hash=builder_v2.UI_QUOTE_SHA if i==1 else builder_v2.REFRESH_UI_QUOTE_SHA
        quote={'provider':'orthogonal','endpoint':'/v1/run','request_sha256':builder_v2.digest(request),'max_micro':250000,'evidence_sha256':quote_hash,'expires_utc':expiry.isoformat()}
        op='source:'+row['case_id']+':serper';receipts[op]={'id':op,'kind':'source','provider':'orthogonal','endpoint':'/v1/run','request':request,'request_hash':builder_v2.digest(request),'quote_micro':250000,'quote_evidence_sha':quote_hash,'quote_metadata':builder_v2.canonical(quote),'state':'succeeded','http_status':200,'response':raw,'response_hash':builder_v2.digest(raw),'actual_micro':2000,'started_at_utc':start.isoformat(),'completed_at_utc':start.isoformat()}
    monkeypatch.setattr(builder_v2,'FIRST_RESPONSE_SHA',receipts['source:case-01:serper']['response_hash'])
    monkeypatch.setattr(runner_v2,'FIRST_RESPONSE_SHA',receipts['source:case-01:serper']['response_hash'])
    class Fake:
        def summary(self):return {'stopped':0}
        def receipt(self,op):return receipts[op]
    a=Admission(PRED,tmp_path/'cohort',Fake())
    m=builder_v2.build(PRED,tmp_path/'cohort',a.ledger,old,new,a.verify_quote,a.verify_human,a.verify_capture)
    assert len(m['cases'])==8
    bad=receipts['source:case-02:serper'].copy();bad['quote_evidence_sha']=builder_v2.UI_QUOTE_SHA
    assert not a.verify_quote(new.read_bytes(),json.loads(bad['quote_metadata']),bad)
