import json
import sys
import tempfile
import unittest
from pathlib import Path

import builder

sys.path.insert(0,str(builder.ROOT/'budget-v2'))
sys.path.insert(0,str(builder.ROOT/'runner-ui'))
from ledger import Ledger
import runner_ui as runner

PRED=builder.ROOT/'dataset-draft-20261029/assembled-v2'
QUOTE=builder.ROOT/'ui-serper-price-20261029.json'

def contract():
    return {'run_id':'builder-offline-fixture','cap_micro':40_000_000,'prior_micro':721_593,
            'prior_generations':79,'prior_counts':11,'max_generations':835,'max_counts':767,
            'max_sources':18,'source_cap_micro':5_000_000,'model':'gemini-3.8-flash',
            'location':'global','input_limit':16384,'output_reserve':8192,'max_output_tokens':4096,
            'input_rate_half_micro':3,'output_rate_half_micro':15,
            'model_price_evidence_sha256':'a'*64,'count_price_evidence_sha256':'b'*64}

class CohortTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.base=Path(self.tmp.name).resolve()
        self.ledger=Ledger(str(self.base/'ledger'),contract(),create=True)
        self.out=self.base/'successor'
    def tearDown(self):
        self.ledger.close(); self.tmp.cleanup()
    def fill(self,n=8, *, bad_case=None,duplicate_request_id=False):
        manifest=json.loads((PRED/'manifest.json').read_bytes())
        for i,row in enumerate(manifest['cases'][:n]):
            case=json.loads((PRED/row['input_path']).read_bytes())
            body=case['draft_paid_source']['request_body'].copy()
            if row['case_id']==bad_case: body['q']='unregistered query'
            request=builder.request_for(body)
            quote={'provider':'orthogonal','endpoint':'/v1/run','request_sha256':builder.digest(request),
                   'max_micro':250000,'evidence_sha256':builder.UI_QUOTE_SHA,'expires_utc':'2099-01-01T00:00:00Z'}
            rid='same' if duplicate_request_id else 'provider-'+str(i)
            response={'success':True,'priceCents':0.2,'requestId':rid,
                      'data':{'news':[{'title':'Fixture title '+str(i),'snippet':'Fixture snippet '+str(i),
                                       'link':'https://example.invalid/'+str(i),'source':'Fixture','date':'2026-10-29'}]}}
            self.ledger.source('source:'+row['case_id']+':serper','orthogonal','/v1/run',request,quote,
                               lambda *args, b=builder.encode(response):(200,b))
    def build(self,**kwargs):
        return builder.build(PRED,self.out,self.ledger,QUOTE,kwargs.get('vq',lambda *a:True),
                             kwargs.get('vh',lambda *a:True),kwargs.get('vc',lambda *a:True))
    def test_all_captures_bind_and_hidden_news_stays_out_of_initial(self):
        self.fill(); m=self.build(); self.assertEqual(m['schema'],'faithful-dynamic-pilot-manifest-v1')
        self.assertEqual(len(m['cases']),8)
        for row in m['cases']:
            case=json.loads((self.out/row['input_path']).read_bytes())
            self.assertEqual([a['id'] for a in case['task']['actions']],['manual-rules','news'])
            self.assertEqual(case['task']['actions'][1]['quoted_cost_micro_usd'],2000)
            self.assertTrue(case['replay']['news']['evidence'])
            self.assertNotIn('Fixture snippet',json.dumps(case['task']['initial_evidence']))
        cases=runner.preflight(m,self.out,self.ledger,lambda *a:True,lambda *a:True)
        self.assertEqual(len(cases),8)
        fed=json.loads((self.out/m['cases'][0]['input_path']).read_bytes())
        self.assertEqual(fed['source_conflicts'][0]['status'],'unresolved')
    def test_successor_executes_32_fake_slots_and_charges_each_source_once(self):
        self.fill(); m=self.build();calls=[]
        def transport(provider,endpoint,request):
            if endpoint=='countTokens':return 200,b'{"totalTokens":100}'
            payload=json.loads(json.loads(request)['contents'][0]['parts'][0]['text'])
            stage,p=payload['stage'],payload['input'];calls.append((stage,p))
            if stage=='source_selection':
                news=next((a for a in p['available_actions'] if a['id']=='news'),None)
                ans={'action':'query' if news else 'stop','action_id':'news' if news else None,'rationale':'fixture','expectation':'fixture'}
            elif stage=='self_check':ans={'action':'query','action_id':'news','rationale':'fixture','expectation':'fixture'}
            elif stage in ('answer','after_query'):
                ans={'answers':[{'contract_id':x,'label':'unknown','citations':[],'explanation':'fixture'} for x in p['contract_ids']],
                     'stop_reason':'fixture','observed_vs_expected':None}
            elif stage=='selection':ans={'alternatives':[['market-id']]}
            elif stage=='inference':ans={'conclusion':p['selected_texts'][0]+' insufficient evidence'}
            elif stage=='halter':ans={'sufficient':True}
            elif stage=='value':ans={'score':0.5}
            elif stage=='formatter':ans={'answers':[{'contract_id':x,'label':'unknown'} for x in p['contract_ids']]}
            else:raise AssertionError(stage)
            return 200,builder.encode({'modelVersion':'gemini-3.8-flash',
                'usageMetadata':{'promptTokenCount':100,'totalTokenCount':200,'thoughtsTokenCount':20},
                'candidates':[{'finishReason':'STOP','content':{'parts':[{'text':json.dumps(ans)}]}}]})
        result=runner.run(m,self.out,self.base/'results',self.ledger,transport,lambda *a:True,lambda *a:True)
        self.assertEqual((result['attempted_slots'],result['not_attempted_slots']),(32,0))
        self.assertEqual(self.ledger.summary()['source_attempts'],8)
        self.assertEqual(self.ledger.summary()['stopped'],0)
        prices=[a['quoted_cost_micro_usd'] for stage,p in calls if stage=='source_selection'
                for a in p['available_actions'] if a['id']=='news']
        self.assertTrue(prices);self.assertEqual(set(prices),{2000})
    def test_missing_paid_capture_fails_without_creating_output(self):
        self.fill(7)
        with self.assertRaises(builder.AdmissionError):self.build()
        self.assertFalse(self.out.exists())
    def test_request_must_equal_frozen_case_query(self):
        self.fill(bad_case='case-03')
        with self.assertRaises(builder.AdmissionError):self.build()
        self.assertFalse(self.out.exists())
    def test_quote_and_human_verifiers_required(self):
        self.fill()
        with self.assertRaises(builder.AdmissionError): self.build(vq=lambda *a:False)
        self.assertFalse(self.out.exists())
        with self.assertRaises(builder.AdmissionError): self.build(vh=None)
        self.assertFalse(self.out.exists())
    def test_provider_request_id_must_not_repeat(self):
        self.fill(duplicate_request_id=True)
        with self.assertRaises(builder.AdmissionError):self.build()
        self.assertFalse(self.out.exists())
    def test_quote_and_source_amount_cannot_be_forged(self):
        self.fill()
        self.ledger.db.execute("UPDATE effects SET actual_micro=999 WHERE id='source:case-01:serper'")
        with self.assertRaises(builder.AdmissionError):self.build()
        self.assertFalse(self.out.exists())
    def test_no_overwriting_successor(self):
        self.fill(); self.build()
        with self.assertRaises(builder.AdmissionError):self.build()
    def test_news_unavailable_is_not_invented_as_empty(self):
        with self.assertRaises(builder.AdmissionError):
            builder.extract_news(b'{"success":true,"priceCents":0.2,"requestId":"x","data":{}}')
        _,_,values=builder.extract_news(b'{"success":true,"priceCents":0.2,"requestId":"x","data":{"news":[]}}')
        self.assertEqual(values,[])
    def test_two_provider_request_ids_must_agree(self):
        with self.assertRaises(builder.AdmissionError):
            builder.extract_news(b'{"success":true,"requestId":"a","billing":{"requestId":"b"},"data":{"news":[]}}')

if __name__=='__main__':unittest.main()
