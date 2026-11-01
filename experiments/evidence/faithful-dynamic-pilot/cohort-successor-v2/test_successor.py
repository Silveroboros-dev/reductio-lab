import json, sqlite3, tempfile, unittest
from pathlib import Path
import builder_v2 as builder
import runner_v2 as runner

ROOT=builder.ROOT
PRED=ROOT/'dataset-draft-20261029/assembled-v2'
OLD=ROOT/'ui-serper-price-20261029.json'
NEW=ROOT/'ui-serper-price-20261029-refresh-v2.json'

def make_receipts():
    db=sqlite3.connect('file:'+str(ROOT/'live-source-ledger-20261029-01/ledger.sqlite3')+'?mode=ro',uri=True)
    db.row_factory=sqlite3.Row
    first=dict(db.execute("SELECT * FROM effects WHERE id='source:case-01:serper'").fetchone()); db.close()
    manifest=json.loads((PRED/'manifest.json').read_bytes()); out={first['id']:first}
    for index,row in enumerate(manifest['cases'][1:],2):
        case=json.loads((PRED/row['input_path']).read_bytes()); request=builder.request_for(case['draft_paid_source']['request_body'])
        news=[{'title':f'case {index} article {i}','snippet':f'snippet {i}','date':'2 days ago'} for i in range(10)]
        response=builder.encode({'success':True,'priceCents':0.2,'requestId':f'test-{index}','data':{'news':news}})
        op='source:'+row['case_id']+':serper'
        quote={'provider':'orthogonal','endpoint':'/v1/run','request_sha256':builder.digest(request),'max_micro':250000,
               'evidence_sha256':builder.REFRESH_UI_QUOTE_SHA,'expires_utc':'2026-10-29T09:37:20.883895+00:00'}
        out[op]={'id':op,'kind':'source','provider':'orthogonal','endpoint':'/v1/run','request':request,'request_hash':builder.digest(request),
                 'quote_micro':250000,'quote_evidence_sha':builder.REFRESH_UI_QUOTE_SHA,'quote_metadata':builder.canonical(quote),
                 'state':'succeeded','http_status':200,'response':response,'response_hash':builder.digest(response),'actual_micro':2000,
                 'started_at_utc':'2026-10-29T09:22:21+00:00','completed_at_utc':'2026-10-29T09:22:22+00:00'}
    return out

class FakeBridge:
    def __init__(self): self.data=make_receipts()
    def receipt(self,op): return self.data[op]
    def summary(self): return {'stopped':0}

class SuccessorTests(unittest.TestCase):
    def setUp(self): self.tmp=tempfile.TemporaryDirectory(); self.out=Path(self.tmp.name)/'dataset';self.bridge=FakeBridge()
    def tearDown(self): self.tmp.cleanup()
    def build(self): return builder.build(PRED,self.out,self.bridge,OLD,NEW,lambda *x:True,lambda *x:True,lambda *x:True)
    def test_real_first_and_fake_others_keep_exact_raw_and_order(self):
        manifest=self.build(); self.assertIn('After observing',manifest['protocol_amendment'])
        cases=runner.preflight(manifest,self.out,self.bridge,lambda *x:True,lambda *x:True)
        self.assertEqual(len(cases),8)
        for row,task,replay in cases:
            case=json.loads((self.out/row['input_path']).read_bytes()); raw=(self.out/f"source/{row['case_id']}-serper-response.json").read_bytes()
            self.assertEqual(raw,self.bridge.receipt('source:'+row['case_id']+':serper')['response'])
            self.assertEqual(case['paid_capture']['provider_returned_count'],10)
            self.assertEqual(case['paid_capture']['selected_count'],3)
            evidence=replay['news']['evidence']; self.assertEqual(evidence[0]['id'],'news:metadata')
            self.assertIn('returned_count=10; selected_count=3',evidence[0]['text'])
            self.assertFalse(any(e['id'].startswith('news:3:') for e in evidence))
            self.assertFalse(any('returned_count=' in json.dumps(a) for a in task['actions']))
        self.assertEqual(builder.digest((self.out/'source/case-01-serper-response.json').read_bytes()),builder.FIRST_RESPONSE_SHA)
    def test_missing_capture_rejected_before_output(self):
        del self.bridge.data['source:case-08:serper']
        with self.assertRaises(builder.AdmissionError): self.build()
        self.assertFalse(self.out.exists())
    def test_empty_array_is_not_invented(self):
        x=builder.encode({'success':True,'requestId':'x','data':{'news':[]}})
        _,_,p=builder.extract_news(x); self.assertEqual((p['provider_returned_count'],p['selected_count'],p['fields']),(0,0,[]))
    def test_wrong_quote_is_rejected(self):
        self.bridge.data['source:case-02:serper']['quote_evidence_sha']=builder.UI_QUOTE_SHA
        with self.assertRaises(builder.AdmissionError): self.build()
        self.assertFalse(self.out.exists())
    def test_projection_tampering_rejected(self):
        manifest=self.build(); row=manifest['cases'][1]; path=self.out/row['input_path']; case=json.loads(path.read_bytes())
        case['replay']['news']['evidence'][1]['text']='semantic replacement'; raw=builder.encode(case);path.write_bytes(raw);row['input_sha256']=builder.digest(raw)
        with self.assertRaises(runner.PreflightError): runner.preflight(manifest,self.out,self.bridge,lambda *x:True,lambda *x:True)
    def test_full_mock_model_schedule_replays_metadata_only_after_news_selected(self):
        import sys
        sys.path.insert(0,str(ROOT/'budget-v2'))
        from ledger import Ledger
        contract={'run_id':'mock-model','cap_micro':40_000_000,'prior_micro':737593,
                  'prior_generations':79,'prior_counts':11,'max_generations':835,'max_counts':767,
                  'max_sources':18,'source_cap_micro':5_000_000,'model':'gemini-3.8-flash',
                  'location':'global','input_limit':16384,'output_reserve':8192,'max_output_tokens':4096,
                  'input_rate_half_micro':3,'output_rate_half_micro':15,
                  'model_price_evidence_sha256':'a'*64,'count_price_evidence_sha256':'b'*64}
        base=Ledger(str(Path(self.tmp.name).resolve()/'model-ledger'),contract,create=True)
        class TestModelBridge:
            def __init__(self,base,source): self.base=base; self.source=source; self.db=base.db
            def receipt(self,op): return self.source.receipt(op)
            def summary(self): return self.base.summary()
            def count(self,*a): return self.base.count(*a)
            def generate(self,*a): return self.base.generate(*a)
            def stop(self,*a): return self.base.stop(*a)
        bridge=TestModelBridge(base,self.bridge); calls=[]
        def transport(provider,endpoint,request):
            if endpoint=='countTokens': return 200,b'{"totalTokens":100}'
            payload=json.loads(json.loads(request)['contents'][0]['parts'][0]['text'])
            stage,p=payload['stage'],payload['input']; calls.append((stage,p))
            if stage=='source_selection':
                news=next((a for a in p['available_actions'] if a['id']=='news'),None)
                ans={'action':'query' if news else 'stop','action_id':'news' if news else None,'rationale':'fixture','expectation':'fixture'}
            elif stage=='self_check': ans={'action':'query','action_id':'news','rationale':'fixture','expectation':'fixture'}
            elif stage in ('answer','after_query'):
                ans={'answers':[{'contract_id':x,'label':'unknown','citations':[],'explanation':'fixture'} for x in p['contract_ids']],
                     'stop_reason':'fixture','observed_vs_expected':None}
            elif stage=='selection': ans={'alternatives':[['market-id']]}
            elif stage=='inference': ans={'conclusion':p['selected_texts'][0]+' insufficient evidence'}
            elif stage=='halter': ans={'sufficient':True}
            elif stage=='value': ans={'score':0.5}
            elif stage=='formatter': ans={'answers':[{'contract_id':x,'label':'unknown'} for x in p['contract_ids']]}
            else: raise AssertionError(stage)
            return 200,builder.encode({'modelVersion':'gemini-3.8-flash',
                'usageMetadata':{'promptTokenCount':100,'totalTokenCount':200,'thoughtsTokenCount':20},
                'candidates':[{'finishReason':'STOP','content':{'parts':[{'text':json.dumps(ans)}]}}]})
        try:
            manifest=builder.build(PRED,self.out,bridge,OLD,NEW,lambda *x:True,lambda *x:True,lambda *x:True)
            result=runner.run(manifest,self.out,Path(self.tmp.name)/'results',bridge,transport,lambda *x:True,lambda *x:True)
            self.assertEqual((result['attempted_slots'],result['not_attempted_slots']),(32,0))
            source_calls=[p for stage,p in calls if stage=='source_selection']
            self.assertTrue(source_calls)
            self.assertFalse(any('returned_count=' in json.dumps(p) for p in source_calls))
            self.assertTrue(any('returned_count=10; selected_count=3' in json.dumps(p) for stage,p in calls if stage!='source_selection'))
        finally: base.close()
    def test_duplicate_request_id_rejected(self):
        b=self.bridge.data['source:case-03:serper'];x=json.loads(b['response']);x['requestId']='test-2';b['response']=builder.encode(x);b['response_hash']=builder.digest(b['response'])
        with self.assertRaises(builder.AdmissionError):self.build()
        self.assertFalse(self.out.exists())
    def test_malformed_or_absent_news_blocked(self):
        for raw in [b'{}', b'{"success":true,"requestId":"x","data":{}}', b'{"success":true,"requestId":"x","data":{"news":[4]}}']:
            with self.assertRaises(builder.AdmissionError): builder.extract_news(raw)

if __name__=='__main__': unittest.main()
