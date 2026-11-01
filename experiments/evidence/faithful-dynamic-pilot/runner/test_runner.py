import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import runner as module
from runner import GUIDE, PreflightError, preflight, run, sha
from ledger import Ledger, Stop, canonical
from test_ledger import contract


def encoded(v): return json.dumps(v, ensure_ascii=False, sort_keys=True).encode()

class RunnerTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        self.data = self.root / 'dataset'; self.data.mkdir()
        self.ledger = Ledger(str(self.root / 'ledger'), contract(), create=True)
        self.guide = GUIDE.read_bytes(); (self.data / 'guide.md').write_bytes(self.guide)
        rows = []
        for i in range(8):
            cid = f'case-{i}'; mid=f'market-{i}'; source_text=f'fresh source {i}'
            snap = encoded({'ticker':mid, 'event_ticker':f'event-{i}', 'rule':f'{mid} resolves on outcome {i}'})
            human = encoded({'claim': f'Human thesis {i}', 'human_id': 'FIXTURE_ONLY'})
            raw = encoded({'priceCents':0.25,'data': {'text':source_text}})
            for n,v in [(f'snap{i}.json',snap),(f'human{i}.json',human),(f'src{i}.json',raw)]: (self.data/n).write_bytes(v)
            src_request=canonical({'api':'serper','path':'/news','body':{'q':'fixture','num':3},'query':{}})
            q={'provider':'orthogonal','endpoint':'/v1/run','request_sha256':sha(src_request), 'max_micro':2500,
               'evidence_sha256':'c'*64,'expires_utc':'2099-01-01T00:00:00Z'}
            self.ledger.source(f'source{i}','orthogonal','/v1/run',src_request,q,lambda *a,r=raw:(200,r))
            def ev(eid,text,body): return {'id':eid,'text':text,'content_sha256':sha(body),'verbatim_parts':[text]}
            snap_ev={'id':'market','text':f'{mid} resolves on outcome {i}', 'content_sha256':sha(snap),
                     'verbatim_parts':[f'{mid} resolves on outcome {i}']}
            task={'case_id':cid,'question':f'Assess {mid}', 'contract_ids':[mid],
                  'allowed_labels':['direct','indirect','weak_proxy','not_an_expression','unknown'],
                  'initial_evidence':[ev('thesis',f'Human thesis {i}',human),snap_ev,ev('policy',self.guide.decode(),self.guide)],
                  'actions':[{'id':'news','description':'fetch news','quoted_cost_micro_usd':2500,'source_effect_id':f'source{i}'}]}
            case={'task':task, 'replay':{'news':{'evidence':[ev('news',source_text,raw)]}},
                  'attachments':[{'path':f'snap{i}.json','sha256':sha(snap)}, {'path':f'human{i}.json','sha256':sha(human)},
                                 {'path':f'src{i}.json','sha256':sha(raw)},{'path':'guide.md','sha256':sha(self.guide)}]}
            b=encoded(case); (self.data/f'case{i}.json').write_bytes(b)
            rows.append({'case_id':cid,'event_group_id':f'event-{i}','split':'dev' if i<2 else 'test',
                         'input_path':f'case{i}.json','input_sha256':sha(b),
                         'human_attestation_path':f'human{i}.json','human_attestation_sha256':sha(human)})
        self.manifest={'schema':'faithful-dynamic-pilot-manifest-v1','cases':rows}
        self.callbacks=[]
    def tearDown(self): self.ledger.close();self.tmp.cleanup()
    def verify(self,raw,case,row): return json.loads(raw).get('human_id')=='FIXTURE_ONLY'
    def transport(self,provider,endpoint,body):
        if endpoint=='countTokens': return 200,b'{"totalTokens":100}'
        request=json.loads(body); payload=json.loads(request['contents'][0]['parts'][0]['text'])
        stage, view=payload['stage'],payload['input']; self.callbacks.append((stage,view))
        if stage=='source_selection':
            action='query' if view['available_actions'] else 'stop'
            answer={'action':action,'action_id':'news' if action=='query' else None,'rationale':'fixture','expectation':'fixture'}
        elif stage=='self_check': answer={'action':'query','action_id':'news','rationale':'fixture','expectation':'fixture'}
        elif stage in ('answer','after_query'):
            answer={'answers':[{'contract_id':c,'label':'direct','citations':[],'explanation':'fixture'} for c in view['contract_ids']],
                    'stop_reason':'fixture','observed_vs_expected':None}
        elif stage=='selection': answer={'alternatives':[['market']]}
        elif stage=='inference':
            assert set(view)=={'selected_texts'}
            answer={'conclusion':view['selected_texts'][0]+' direct'}
        elif stage=='halter': answer={'sufficient':True}
        elif stage=='value': answer={'score':0.5}
        elif stage=='formatter':
            assert 'question' not in view
            answer={'answers':[{'contract_id':c,'label':'direct'} for c in view['contract_ids']]}
        else: raise AssertionError(stage)
        response={'modelVersion':'gemini-3.8-flash', 'usageMetadata':{'promptTokenCount':100,'totalTokenCount':200,'thoughtsTokenCount':20},
                  'candidates':[{'finishReason':'STOP','content':{'parts':[{'text':json.dumps(answer)}]}}]}
        return 200,encoded(response)
    def test_four_arm_replay_balanced_32_and_usage_counted(self):
        before=self.ledger.summary().copy()
        result=run(self.manifest,self.data,self.root/'result',self.ledger,self.transport,self.verify,lambda *a:True)
        self.assertEqual((result['requested_slots'],result['attempted_slots'],result['not_attempted_slots']),(32,32,0))
        self.assertEqual({arm:sum(r['arm']==arm for r in result['results']) for arm in ('A','B','B_self_check','C')},
                         {'A':8,'B':8,'B_self_check':8,'C':8})
        self.assertTrue(all(r['outcome']['status'] == ('proposal' if r['arm']=='C' else 'completed') for r in result['results']))
        self.assertEqual(result['review'],'not adjudicated')
        self.assertEqual(result['ledger']['generation_attempts']-before['generation_attempts'],
                         result['ledger']['count_attempts']-before['count_attempts'])
        self.assertEqual(result['ledger']['source_attempts'],8)
        for s,p in self.callbacks:
            self.assertNotIn('FIXTURE_ONLY',json.dumps(p))
            if s=='inference':self.assertEqual(set(p),{'selected_texts'})
        seq=json.loads((self.root/'result'/'schedule.json').read_text())
        self.assertEqual([x['arm'] for x in seq[:4]],['A','B','B_self_check','C'])
        self.assertEqual([x['arm'] for x in seq[4:8]],['B','B_self_check','C','A'])
    def test_absent_human_verifier_fails_before_any_model_call(self):
        b=self.ledger.summary().copy()
        with self.assertRaises(PreflightError): run(self.manifest,self.data,self.root/'result',self.ledger,self.transport)
        self.assertEqual(self.ledger.summary(),b);self.assertFalse((self.root/'result').exists())
    def test_case_digest_drift_fails_before_any_model_call(self):
        (self.data/'case2.json').write_text('{}')
        b=self.ledger.summary().copy()
        with self.assertRaises(PreflightError):run(self.manifest,self.data,self.root/'result',self.ledger,self.transport,self.verify,lambda *a:True)
        self.assertEqual(self.ledger.summary(),b)
    def test_incomplete_manifest_and_rejected_attestation_fail_closed(self):
        m=dict(self.manifest,cases=self.manifest['cases'][:-1])
        with self.assertRaises(PreflightError):preflight(m,self.data,self.ledger,self.verify,lambda *a:True)
        with self.assertRaises(PreflightError):preflight(self.manifest,self.data,self.ledger,lambda *a:False,lambda *a:True)
    def test_source_bytes_and_capture_verifier_required(self):
        (self.data/'src2.json').write_text('{}')
        before=self.ledger.summary().copy()
        with self.assertRaises(PreflightError):run(self.manifest,self.data,self.root/'result',self.ledger,self.transport,self.verify,lambda *a:True)
        self.assertEqual(self.ledger.summary(),before)
        with self.assertRaises(PreflightError):preflight(self.manifest,self.data,self.ledger,self.verify,None)

    def test_negation_cannot_be_removed_by_stitched_fragments(self):
        raw=encoded({'rule':'The rate is not reduced.'})
        item={'id':'e','content_sha256':sha(raw),'text':'The rate is\nreduced.',
              'verbatim_parts':['The rate is','reduced.']}
        with self.assertRaises(PreflightError):module._evidence_bound(item,{sha(raw):raw})
        raw=encoded({'rule':'It is not true that the rate is reduced.'})
        item={'id':'e','content_sha256':sha(raw),'text':'the rate is reduced.',
              'verbatim_parts':['the rate is reduced.']}
        with self.assertRaises(PreflightError):module._evidence_bound(item,{sha(raw):raw})

    def test_paid_capture_raw_corruption_and_label_drift_are_blocked(self):
        self.ledger.db.execute("UPDATE effects SET response=? WHERE id='source0'",(b'{}',))
        with self.assertRaises(PreflightError):preflight(self.manifest,self.data,self.ledger,self.verify,lambda *a:True)
        self.ledger.db.execute("UPDATE effects SET response=? WHERE id='source0'",((self.data/'src0.json').read_bytes(),))
        case=json.loads((self.data/'case1.json').read_bytes())
        case['task']['allowed_labels']=['direct','invented']
        raw=encoded(case);(self.data/'case1.json').write_bytes(raw);self.manifest['cases'][1]['input_sha256']=sha(raw)
        with self.assertRaises(PreflightError):preflight(self.manifest,self.data,self.ledger,self.verify,lambda *a:True)

    def test_manual_source_replay_same_bytes_and_unknown_cost(self):
        row=self.manifest['cases'][0];path=self.data/'case0.json';case=json.loads(path.read_bytes())
        raw=encoded({'content':'manual source fixture'})
        (self.data/'manual.json').write_bytes(raw)
        receipt={'source_sha256':sha(raw),'url_reported':module.KALSHI_URL,'utc_request_time_reported':module.MANUAL_REPORTED_TIME,
                 'http_status_reported':200,'reported_direct_http':True,'report_attribution':'user relaying Grok statement','independent_attestation':False}
        receipt_raw=encoded(receipt);(self.data/'manual-receipt.json').write_bytes(receipt_raw)
        case['attachments'].append({'path':'manual.json','sha256':sha(raw)})
        case['task']['actions'][0].update({'capture_kind':'manual_capture','quoted_cost_micro_usd':None,
            'manual_receipt_path':'manual-receipt.json','manual_receipt_sha256':sha(receipt_raw)})
        case['task']['actions'][0].pop('source_effect_id')
        case['replay']['news']['evidence'][0].update({'text':'manual source fixture','content_sha256':sha(raw),'verbatim_parts':['manual source fixture']})
        case_bytes=encoded(case);path.write_bytes(case_bytes);row['input_sha256']=sha(case_bytes)
        with patch.object(module,'MANUAL_SOURCE_HASH',sha(raw)):
            result=run(self.manifest,self.data,self.root/'result',self.ledger,self.transport,self.verify,lambda *a:True)
        self.assertEqual(result['manual_capture_external_cost'],'unknown')
        for r in result['results']:
            if r['case_id']!='case-0' or r['arm']=='A': continue
            outcome=r['outcome']
            if r['arm']=='C':
                replay=next(x for x in outcome['events'] if x['event']=='source_replayed')
                self.assertIsNone(replay['quoted_cost_micro_usd'])
            else:
                replay=next(x for x in outcome['trace'] if x['event']=='source_replayed')
                self.assertIsNone(outcome['shadow_source_cost_micro_usd'])
            self.assertEqual(replay['evidence'][0]['text'],'manual source fixture')
        self.assertEqual(result['ledger']['source_attempts'],8)
        self.assertTrue((self.root/'result'/'00-started.json').exists())
        before=self.ledger.summary()['generation_attempts']
        with patch.object(module,'MANUAL_SOURCE_HASH',sha(raw)):
            with self.assertRaises(Stop):run(self.manifest,self.data,self.root/'result2',self.ledger,self.transport,self.verify,lambda *a:True)
        self.assertEqual(self.ledger.summary()['generation_attempts'],before)

    def test_slot_start_persistence_failure_stops_ledger(self):
        original=module._write_once
        def broken(path,value):
            if str(path).endswith('-started.json'):raise OSError('fixture')
            return original(path,value)
        with patch.object(module,'_write_once',broken):
            with self.assertRaises(OSError):run(self.manifest,self.data,self.root/'result',self.ledger,self.transport,self.verify,lambda *a:True)
        self.assertEqual(self.ledger.summary()['stopped'],1)
        self.assertEqual(self.ledger.summary()['generation_attempts'],79)

    def test_targeted_grok_capture_fed_conflict_cannot_be_hidden(self):
        candidate=module.ROOT/'kalshi_preflight'/'user_supplied_targeted_kalshi_markets.json'
        receipt_file=module.ROOT/'kalshi_preflight'/'user_reported_targeted_capture.json'
        raw, receipt_raw = candidate.read_bytes(), receipt_file.read_bytes()
        self.assertEqual(sha(raw),module.TARGET_SOURCE_HASH)
        (self.data/'target.json').write_bytes(raw);(self.data/'target-receipt.json').write_bytes(receipt_raw)
        fed=next(m for m in json.loads(raw)['markets'] if m['ticker']==module.FED_CONTRACT)
        row=self.manifest['cases'][0];case_path=self.data/'case0.json';case=json.loads(case_path.read_bytes())
        row['event_group_id']=fed['event_ticker'];case['task']['contract_ids']=[fed['ticker']]
        case['task']['initial_evidence'][1]={'id':'market','text':fed['ticker'],'content_sha256':sha(raw),'verbatim_parts':[fed['ticker']]}
        case['attachments'].append({'path':'target.json','sha256':sha(raw)})
        case['task']['actions'][0].update({'capture_kind':'manual_capture','quoted_cost_micro_usd':None,
            'manual_receipt_path':'target-receipt.json','manual_receipt_sha256':sha(receipt_raw)})
        case['task']['actions'][0].pop('source_effect_id')
        case['replay']['news']['evidence'][0].update({'text':fed['rules_secondary'],'content_sha256':sha(raw),'verbatim_parts':[fed['rules_secondary']]})
        b=encoded(case);case_path.write_bytes(b);row['input_sha256']=sha(b)
        with self.assertRaisesRegex(PreflightError,'conflict'):preflight(self.manifest,self.data,self.ledger,self.verify,lambda *a:True)
        case['source_conflicts']=[{'contract_id':module.FED_CONTRACT,'field':'rules_secondary','status':'unresolved'}]
        b=encoded(case);case_path.write_bytes(b);row['input_sha256']=sha(b)
        result=run(self.manifest,self.data,self.root/'result',self.ledger,self.transport,self.verify,lambda *a:True)
        for r in result['results']:
            if r['case_id']=='case-0':self.assertEqual(r['semantic_status'],'unassessed_source_conflict')

    def test_uncertain_model_stops_all_other_slots(self):
        def error(*a): raise TimeoutError('fixture')
        result=run(self.manifest,self.data,self.root/'result',self.ledger,error,self.verify,lambda *a:True)
        self.assertEqual(result['attempted_slots'],1)
        self.assertEqual(result['not_attempted_slots'],31)
        self.assertEqual(result['ledger']['stopped'],1)
if __name__=='__main__':unittest.main()
