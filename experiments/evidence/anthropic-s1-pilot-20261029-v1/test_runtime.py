"""No-network tests for the private S-1 runtime."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import runtime


def ok(model='gemini-3.8-flash'):
    return json.dumps({'modelVersion': model, 'usageMetadata': {'promptTokenCount': 100, 'totalTokenCount': 110},
                       'candidates': [{'finishReason': 'STOP', 'content': {'parts': [{'text': '{"answer":"fixture"}'}]}}]}).encode()


class RuntimeTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir='/private/tmp')
        self.r = None
    def tearDown(self):
        if self.r:
            self.r.close()
        self.tmp.cleanup()
    def new(self, transport):
        self.r = runtime.Runtime(Path(self.tmp.name) / 'ledger', transport=transport, sleep=lambda _: None, _testing=True)
        return self.r
    def test_success_and_exact_wire_request_count(self):
        seen = []
        def t(provider, endpoint, raw):
            seen.append((provider, endpoint, raw))
            return (200, b'{"totalTokens":100}') if endpoint == 'countTokens' else (200, ok())
        r = self.new(t)
        self.assertEqual(r.generator('case-a', 'A')('baseline_initial', {'question':'fixture'}), {'answer':'fixture'})
        self.assertEqual(len(seen), 2)
        self.assertEqual(seen[0][2], seen[1][2])
        cfg = json.loads(seen[0][2])['generationConfig']
        self.assertEqual(cfg['thinkingConfig']['thinkingLevel'], 'LOW')
        self.assertEqual(cfg['maxOutputTokens'], 4096)
        self.assertEqual(r.summary()['new_generation_attempts'], 1)
        self.assertEqual(r.summary()['new_count_attempts'], 1)
        self.assertEqual(r.summary()['new_exposure_micro'], 225)
        rows = r.ledger.db.execute('select kind,state,http_status,quote_micro,actual_micro from effects order by rowid').fetchall()
        self.assertEqual(rows, [('count','succeeded',200,0,0), ('generation','succeeded',200,519996,225)])
        with self.assertRaises(ValueError): r.generator('case-a','A')
    def test_429_one_retry_same_bytes(self):
        seen=[]
        def t(provider, endpoint, raw):
            seen.append((endpoint,raw))
            if endpoint == 'countTokens': return 200,b'{"totalTokens":100}'
            if len(seen)==2: return 429,b'{"error":{"code":429,"status":"RESOURCE_EXHAUSTED"}}'
            return 200,ok()
        r=self.new(t)
        r.generator('case-b','B')('baseline_counterfactual',{'question':'fixture'})
        self.assertEqual(len(seen),3)
        self.assertEqual(seen[0][1],seen[1][1])
        self.assertEqual(seen[1][1],seen[2][1])
        self.assertEqual(r.summary()['new_generation_attempts'],2)
        self.assertEqual(r.ledger.db.execute("select state,http_status,actual_micro from effects where kind='generation' order by rowid").fetchall(), [('succeeded',429,0),('succeeded',200,225)])
    def test_429_exhaustion_is_not_resampled(self):
        seen=[]
        def t(provider,endpoint,raw):
            seen.append((endpoint,raw))
            if endpoint=='countTokens': return 200,b'{"totalTokens":100}'
            return 429,b'{"error":{"code":429,"status":"RESOURCE_EXHAUSTED"}}'
        r=self.new(t)
        with self.assertRaises(Exception):r.generator('case-c','A')('baseline_initial',{'question':'fixture'})
        self.assertEqual(len(seen),3)
        self.assertEqual(r.ledger.db.execute("select count(*) from effects where kind='generation'").fetchone()[0],2)
    def test_timeout_is_uncertain_never_repeated_and_retains_reserve(self):
        seen=[]
        def t(provider,endpoint,raw):
            seen.append(endpoint)
            if endpoint=='countTokens': return 200,b'{"totalTokens":100}'
            raise TimeoutError('fixture only')
        r=self.new(t)
        with self.assertRaises(Exception):r.generator('case-d','C')('selection',{'fixture':True})
        self.assertEqual(seen,['countTokens','gemini-3.8-flash@global'])
        self.assertEqual(r.summary()['stopped'],1)
        self.assertEqual(r.summary()['new_exposure_micro'],runtime.RESERVE_MICRO)
        self.assertEqual(r.ledger.db.execute("select state,actual_micro from effects where kind='generation'").fetchone(),('uncertain',None))
        with self.assertRaises(Exception):r.generator('other','A')('baseline_initial',{'question':'different'})
        self.assertEqual(len(seen),2)
    def test_wrong_model_is_charged_and_stops(self):
        def t(provider,endpoint,raw):
            return (200,b'{"totalTokens":100}') if endpoint=='countTokens' else (200,ok('gemini-3.5-flash'))
        r=self.new(t)
        with self.assertRaises(Exception):r.generator('case-e','A')('baseline_initial',{'question':'fixture'})
        self.assertEqual(r.summary()['stopped'],1)
        self.assertEqual(r.summary()['new_exposure_micro'],225)
        self.assertEqual(r.ledger.db.execute("select state,http_status,actual_micro from effects where kind='generation'").fetchone(),('succeeded',200,225))
    def test_count_cap_blocks_before_effect(self):
        seen=[]
        def t(*a): seen.append(a); return 200,b'{"totalTokens":100}'
        r=self.new(t)
        r.ledger.db.execute('update run set count_attempts=?', (runtime.MAX_COUNTS,))
        with self.assertRaises(Exception):r.generator('case-f','A')('baseline_initial',{'question':'fixture'})
        self.assertEqual(len(seen),0)
    def test_prior_uncertain_request_is_blocked_before_count(self):
        seen=[]
        def t(*a):seen.append(a);return 200,b'{"totalTokens":100}'
        r=self.new(t)
        request=runtime.build_request('baseline_initial',{'question':'fixture'},prompt_version=runtime.VERSION_V2)
        body=runtime.build_generation_request(request)
        r.snapshot['forbidden_request_hashes'].append(hashlib.sha256(runtime.canonical_json(body)).hexdigest())
        with self.assertRaises(ValueError):r.generator('case-g','A')('baseline_initial',{'question':'fixture'})
        self.assertEqual(seen,[])
    def test_inference_projection_rejects_question(self):
        r=self.new(lambda *_: (_ for _ in ()).throw(AssertionError('no I/O')))
        with self.assertRaises(ValueError):r.generator('case-h','C')('inference', {'selected_texts':[], 'question':'not allowed'})
        self.assertEqual(r.summary()['new_count_attempts'],0)
    def test_exact_private_production_ledger_path(self):
        with self.assertRaises(ValueError):runtime.Runtime(Path(self.tmp.name)/'other',transport=lambda *_:None)

    def test_source_success_settles_actual_once_before_models(self):
        seen=[]
        def source(provider,endpoint,raw):
            seen.append((provider,endpoint,raw))
            return 200,json.dumps({'success':True,'priceCents':0.2,'billing':{'chargedPriceCents':0.2},'data':{'news':[]}}).encode()
        r=self.new(lambda *_: (_ for _ in ()).throw(AssertionError('not model')))
        raw=r.fetch_serper_news(price_evidence_sha256='c'*64,transport=source)
        self.assertTrue(json.loads(raw)['success'])
        self.assertEqual(len(seen),1)
        self.assertEqual(seen[0][:2],('orthogonal','/v1/run'))
        self.assertEqual(json.loads(seen[0][2])['body'],{'q':'Anthropic IPO S-1 compute obligations governance','num':3})
        self.assertEqual(r.summary()['new_exposure_micro'],2000)
        self.assertEqual(r.ledger.db.execute("select state,quote_micro,actual_micro from effects where kind='source'").fetchone(),('succeeded',10000,2000))
        with self.assertRaises(ValueError):r.fetch_serper_news(price_evidence_sha256='c'*64,transport=source)
        self.assertEqual(len(seen),1)
    def test_source_timeout_retains_reserve_and_blocks_new_requests(self):
        seen=[]
        def source(*args):seen.append(args);raise TimeoutError('fixture')
        r=self.new(lambda *_: (_ for _ in ()).throw(AssertionError('model must not run')))
        with self.assertRaises(Exception):r.fetch_serper_news(price_evidence_sha256='c'*64,transport=source)
        self.assertEqual(len(seen),1)
        self.assertEqual(r.summary()['new_exposure_micro'],10000)
        self.assertEqual(r.summary()['stopped'],1)
        self.assertEqual(r.ledger.db.execute("select state,actual_micro from effects where kind='source'").fetchone(),('uncertain',None))
        with self.assertRaises(Exception):r.generator('later','A')('baseline_initial',{'question':'fixture'})
        self.assertEqual(len(seen),1)
    def test_source_unverifiable_billing_retains_reserve(self):
        r=self.new(lambda *_:None)
        with self.assertRaises(ValueError):r.fetch_serper_news(price_evidence_sha256='c'*64,transport=lambda *_:(200,b'{"success":true,"priceCents":0.2}'))
        self.assertEqual(r.summary()['new_exposure_micro'],10000)
        self.assertEqual(r.summary()['stopped'],1)
        self.assertEqual(r.ledger.db.execute("select state,actual_micro from effects where kind='source'").fetchone(),('succeeded',None))
    def test_source_billing_over_reserve_accounted_then_stopped(self):
        r=self.new(lambda *_:None)
        data={'success':True,'priceCents':1.1,'billing':{'chargedPriceCents':1.1}}
        with self.assertRaises(Exception):r.fetch_serper_news(price_evidence_sha256='c'*64,transport=lambda *_:(200,json.dumps(data).encode()))
        self.assertEqual(r.summary()['new_exposure_micro'],11000)
        self.assertEqual(r.summary()['stopped'],1)
    def test_source_disallowed_after_model(self):
        def t(provider,endpoint,raw):return (200,b'{"totalTokens":100}') if endpoint=='countTokens' else (200,ok())
        r=self.new(t)
        r.generator('a','A')('baseline_initial',{'question':'fixture'})
        with self.assertRaises(ValueError):r.fetch_serper_news(price_evidence_sha256='c'*64,transport=lambda *_:None)

    def test_resume_after_settled_source_only(self):
        def source(*_):return 200,json.dumps({'success':True,'priceCents':0.2,'billing':{'chargedPriceCents':0.2},'data':{'news':[]}}).encode()
        def model(provider,endpoint,raw):return (200,b'{"totalTokens":100}') if endpoint=='countTokens' else (200,ok())
        r=self.new(model)
        r.fetch_serper_news(price_evidence_sha256='c'*64,transport=source)
        r.close();self.r=None
        r=runtime.Runtime(Path(self.tmp.name)/'ledger',transport=model,sleep=lambda _:None,resume=True,_testing=True);self.r=r
        self.assertEqual(r.summary()['new_exposure_micro'],2000)
        self.assertEqual(r.generator('resumed','A')('baseline_initial',{'question':'fixture'}),{'answer':'fixture'})
        self.assertEqual(r.summary()['new_exposure_micro'],2225)
        with self.assertRaises(ValueError):r.fetch_serper_news(price_evidence_sha256='c'*64,transport=source)
    def test_resume_rejects_uncertain_source(self):
        r=self.new(lambda *_:None)
        with self.assertRaises(Exception):r.fetch_serper_news(price_evidence_sha256='c'*64,transport=lambda *_: (_ for _ in ()).throw(TimeoutError()))
        r.close();self.r=None
        with self.assertRaises(ValueError):runtime.Runtime(Path(self.tmp.name)/'ledger',transport=lambda *_:None,resume=True,_testing=True)
    def test_resume_rejects_source_with_prior_model_activity(self):
        def source(*_):return 200,json.dumps({'success':True,'priceCents':0.2,'billing':{'chargedPriceCents':0.2}}).encode()
        def model(provider,endpoint,raw):return (200,b'{"totalTokens":100}') if endpoint=='countTokens' else (200,ok())
        r=self.new(model);r.fetch_serper_news(price_evidence_sha256='c'*64,transport=source)
        r.generator('case','A')('baseline_initial',{'question':'fixture'})
        r.close();self.r=None
        with self.assertRaises(ValueError):runtime.Runtime(Path(self.tmp.name)/'ledger',transport=model,resume=True,_testing=True)
    def test_resume_rejects_price_receipt_tampering(self):
        def source(*_):return 200,json.dumps({'success':True,'priceCents':0.2,'billing':{'chargedPriceCents':0.2}}).encode()
        r=self.new(lambda *_:None);r.fetch_serper_news(price_evidence_sha256='c'*64,transport=source)
        r.ledger.db.execute("update effects set actual_micro=0 where kind='source'")
        r.close();self.r=None
        with self.assertRaises(ValueError):runtime.Runtime(Path(self.tmp.name)/'ledger',transport=lambda *_:None,resume=True,_testing=True)

if __name__ == '__main__': unittest.main()
