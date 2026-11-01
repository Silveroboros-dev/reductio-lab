import copy
import json
import unittest
from pathlib import Path
import runner_ui as r

class FakeLedger:
    def __init__(self, receipt): self.value=receipt
    def receipt(self, op_id): return copy.deepcopy(self.value) if op_id=='source:01' else None

class UIPriceTests(unittest.TestCase):
    def setUp(self):
        self.ui=(r.ROOT/'ui-serper-price-20261029.json').read_bytes()
        self.assertEqual(r.sha(self.ui),r.UI_PRICE_HASH)
        draft=json.loads((r.ROOT/'dataset-draft-20261029/draft.json').read_bytes())
        g=draft['groups'][0];self.row={'case_id':g['case_id'],'event_group_id':g['event_group_id']}
        body={'api':'serper','path':'/news','body':g['news_action_draft']['request_body'],'query':{}}
        self.request=json.dumps(body,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()
        self.response=b'{"success":true,"priceCents":0.2,"data":{"news":[]}}'
        self.action={'source_effect_id':'source:01','quoted_cost_micro_usd':2000}
        self.receipt={'id':'source:01','kind':'source','provider':'orthogonal','endpoint':'/v1/run',
            'state':'succeeded','http_status':200,'actual_micro':2000,'quote_micro':250000,
            'quote_evidence_sha':r.UI_PRICE_HASH,'request':self.request,'request_hash':r.sha(self.request),
            'response':self.response,'response_hash':r.sha(self.response),
            'started_at_utc':'2026-10-29T09:11:00Z'}
    def check(self): return r._paid_ui_capture(self.action,self.row,{r.UI_PRICE_HASH:self.ui},FakeLedger(self.receipt))
    def test_distinguishes_advertised_price_from_risk_reserve(self):
        self.assertEqual(self.check(),r.sha(self.response))
        self.assertEqual(self.action['quoted_cost_micro_usd'],2000)
        self.assertEqual(self.receipt['quote_micro'],250000)
    def test_false_displayed_price_and_actual_overprice_fail(self):
        self.action['quoted_cost_micro_usd']=250000
        with self.assertRaises(r.PreflightError):self.check()
        self.action['quoted_cost_micro_usd']=2000;self.receipt['actual_micro']=2001
        with self.assertRaises(r.PreflightError):self.check()
    def test_wrong_or_altered_quote_evidence_fails(self):
        self.receipt['quote_evidence_sha']='c'*64
        with self.assertRaises(r.PreflightError):self.check()
        self.receipt['quote_evidence_sha']=r.UI_PRICE_HASH;self.ui+=b' '
        with self.assertRaises(r.PreflightError):self.check()
    def test_request_from_wrong_case_not_admitted(self):
        self.row['case_id']='case-02'
        with self.assertRaises(r.PreflightError):self.check()
    def test_price_receipt_cannot_be_lower_than_raw_charge(self):
        self.receipt['actual_micro']=1999
        with self.assertRaises(r.PreflightError):self.check()
    def test_response_request_and_timing_integrity(self):
        self.receipt['response']=b'{}'
        with self.assertRaises(r.PreflightError):self.check()
        self.receipt['response']=self.response;self.receipt['started_at_utc']='2026-10-29T09:26:00Z'
        with self.assertRaises(r.PreflightError):self.check()
    def test_missing_unsettled_or_unapproved_source_fails(self):
        self.receipt['actual_micro']=None
        with self.assertRaises(r.PreflightError):self.check()
        self.receipt['actual_micro']=2000;self.receipt['endpoint']='/v1/other'
        with self.assertRaises(r.PreflightError):self.check()
    def test_fed_conflict_allows_provenance_but_not_missing_core(self):
        c={'contract_id':r.FED_CONTRACT,'field':'rules_secondary','status':'unresolved','description':'separate provenance'}
        self.assertTrue(r._fed_conflict_admitted([c]))
        c['status']='resolved'
        self.assertFalse(r._fed_conflict_admitted([c]))
        self.assertFalse(r._fed_conflict_admitted(None))


class FourArmUIIntegrationTest(unittest.TestCase):
    def test_eight_synthetic_captures_and_all_32_assignments(self):
        import tempfile
        from ledger import Ledger, canonical
        from test_ledger import contract
        ui=(r.ROOT/'ui-serper-price-20261029.json').read_bytes()
        groups=json.loads((r.ROOT/'dataset-draft-20261029/draft.json').read_bytes())['groups']
        guide=r.GUIDE.read_bytes()
        def enc(v): return json.dumps(v,ensure_ascii=False,sort_keys=True).encode()
        def ev(i,text,raw): return {'id':i,'text':text,'content_sha256':r.sha(raw),'verbatim_parts':[text]}
        with tempfile.TemporaryDirectory() as td:
            root=Path(td).resolve();data=root/'data';data.mkdir()
            (data/'ui.json').write_bytes(ui);(data/'guide.md').write_bytes(guide)
            ledger=Ledger(str(root/'ledger'),contract(),create=True)
            rows=[]; callbacks=[]
            try:
                for i,g in enumerate(groups):
                    case_id=g['case_id'];mid=g['contract_ids'][0];event=g['event_group_id']
                    snapshot=enc({'ticker':mid,'event_ticker':event,'text':mid+' sample rule'})
                    human=enc({'claim':'Fixture human claim '+str(i),'human_id':'FIXTURE_ONLY'})
                    raw=enc({'priceCents':0.2,'data':{'snippet':'Synthetic news '+str(i)}})
                    for name,value in ((f'snapshot{i}.json',snapshot),(f'human{i}.json',human),(f'source{i}.json',raw)): (data/name).write_bytes(value)
                    request=canonical({'api':'serper','path':'/news','body':g['news_action_draft']['request_body'],'query':{}})
                    q={'provider':'orthogonal','endpoint':'/v1/run','request_sha256':r.sha(request),'max_micro':250000,'evidence_sha256':r.UI_PRICE_HASH,'expires_utc':'2099-01-01T00:00:00Z'}
                    ledger.source(f'source:{i}','orthogonal','/v1/run',request,q,lambda *a,raw=raw:(200,raw))
                    # Fixture controls timestamps; no claim about a provider capture.
                    ledger.db.execute("UPDATE effects SET started_at_utc='2026-10-29T09:11:00Z' WHERE id=?",(f'source:{i}',))
                    task={'case_id':case_id,'question':'Classify '+mid,'contract_ids':[mid],
                          'allowed_labels':['direct','indirect','weak_proxy','not_an_expression','unknown'],
                          'initial_evidence':[ev('thesis','Fixture human claim '+str(i),human),ev('market',mid+' sample rule',snapshot),ev('policy',guide.decode(),guide)],
                          'actions':[{'id':'news','description':'read news','quoted_cost_micro_usd':2000,'source_effect_id':f'source:{i}'}]}
                    case={'task':task,'replay':{'news':{'evidence':[ev('news','Synthetic news '+str(i),raw)]}},
                          'attachments':[{'path':f'snapshot{i}.json','sha256':r.sha(snapshot)}, {'path':f'human{i}.json','sha256':r.sha(human)},
                                         {'path':f'source{i}.json','sha256':r.sha(raw)},{'path':'guide.md','sha256':r.sha(guide)}, {'path':'ui.json','sha256':r.UI_PRICE_HASH}]}
                    payload=enc(case);(data/f'case{i}.json').write_bytes(payload)
                    rows.append({'case_id':case_id,'event_group_id':event,'split':'dev' if i<2 else 'test','input_path':f'case{i}.json',
                                 'input_sha256':r.sha(payload),'human_attestation_path':f'human{i}.json','human_attestation_sha256':r.sha(human)})
                manifest={'schema':'faithful-dynamic-pilot-manifest-v1','cases':rows}
                def transport(provider,endpoint,body):
                    if endpoint=='countTokens': return 200,b'{"totalTokens":100}'
                    projection=json.loads(json.loads(body)['contents'][0]['parts'][0]['text'])
                    stage,p=projection['stage'],projection['input']; callbacks.append((stage,p))
                    if stage=='source_selection':
                        a=bool(p['available_actions']);ans={'action':'query' if a else 'stop','action_id':'news' if a else None,'rationale':'fixture','expectation':'fixture'}
                    elif stage=='self_check':ans={'action':'query','action_id':'news','rationale':'fixture','expectation':'fixture'}
                    elif stage in ('answer','after_query'):ans={'answers':[{'contract_id':x,'label':'direct','citations':[],'explanation':'fixture'} for x in p['contract_ids']],'stop_reason':'fixture','observed_vs_expected':None}
                    elif stage=='selection':ans={'alternatives':[['market']]}
                    elif stage=='inference':ans={'conclusion':p['selected_texts'][0]+' direct'}
                    elif stage=='halter':ans={'sufficient':True}
                    elif stage=='value':ans={'score':0.5}
                    elif stage=='formatter':ans={'answers':[{'contract_id':x,'label':'direct'} for x in p['contract_ids']]}
                    else:raise AssertionError(stage)
                    return 200,enc({'modelVersion':'gemini-3.8-flash','usageMetadata':{'promptTokenCount':100,'totalTokenCount':200,'thoughtsTokenCount':20},'candidates':[{'finishReason':'STOP','content':{'parts':[{'text':json.dumps(ans)}]}}]})
                result=r.run(manifest,data,root/'output',ledger,transport,lambda raw,*_:json.loads(raw).get('human_id')=='FIXTURE_ONLY',lambda *_:True)
                self.assertEqual(result['attempted_slots'],32)
                self.assertEqual(result['not_attempted_slots'],0)
                visible_prices=[a['quoted_cost_micro_usd'] for stage,p in callbacks if stage=='source_selection' for a in p['available_actions']]
                self.assertTrue(visible_prices)
                self.assertEqual(set(visible_prices),{2000})
                self.assertEqual(ledger.summary()['source_attempts'],8)
            finally:ledger.close()

if __name__=='__main__':unittest.main()
