import copy, json, math, unittest
import forecast as f


def task():
    return {'case_id':'case-A','contract_id':'MKT-1',
        'question':'What is the probability that MKT-1 resolves YES?',
        'as_of_utc':'2026-10-29T10:00:00Z','phase':'p0','condition':'no_news',
        'evidence':[{'id':'rule','kind':'rule','text':'YES if an official report exceeds 4.2.',
                     'source':'market snapshot','captured_at_utc':'2026-10-29T09:00:00Z'},
                    {'id':'context','kind':'context','text':'The prior official observation was 3.5.',
                     'source':'official report','available_at_utc':'2026-10-29T09:30:00Z'}],
        'prior_forecast':None}

def result(p=0.45, citations=None):
    return {'probability_yes':p,'explanation':'Estimate under stated assumptions.',
            'citations':['rule'] if citations is None else citations,
            'assumptions':['The next report is uncertain.'],
            'counterevidence':['A lower reading remains possible.']}

def p1(condition='news'):
    t=task();t['as_of_utc']='2026-10-29T12:00:00Z';t['phase']='p1';t['condition']=condition
    t['prior_forecast']=result()
    if condition=='news':
        t['evidence'].append({'id':'news-1','kind':'news','text':'A new report is available.',
            'source':'official release','available_at_utc':'2026-10-29T11:00:00Z'})
    return t

class ForecastTests(unittest.TestCase):
    def test_p0_no_news_and_no_hidden_fields(self):
        t=task(); t['condition']='news'
        with self.assertRaises(f.InvalidOutput): f.prepare_task(t)
        t=task(); t['evidence'].append({'id':'n','kind':'news','text':'later','source':'news',
                                      'available_at_utc':'2026-10-29T09:30:00Z'})
        with self.assertRaises(f.InvalidOutput): f.prepare_task(t)
        t=task();t['hidden_other_arm']={'probability_yes':0.9}
        with self.assertRaises(f.InvalidOutput): f.prepare_task(t)
    def test_p1_no_news_boundary_and_prior(self):
        t=p1('no_news'); self.assertEqual(f.prepare_task(t)['prior_forecast']['probability_yes'],0.45)
        t['evidence'].append({'id':'n','kind':'news','text':'update','source':'news',
                              'available_at_utc':'2026-10-29T11:00:00Z'})
        with self.assertRaises(f.InvalidOutput): f.prepare_task(t)
        t=p1();t['prior_forecast']['citations']=['news-1']
        with self.assertRaises(f.InvalidOutput): f.prepare_task(t)
        t=p1();t['prior_forecast']=None
        with self.assertRaises(f.InvalidOutput): f.prepare_task(t)
    def test_cutoffs_reject_future_publication_availability_and_capture(self):
        for field in ('published_at_utc','available_at_utc','captured_at_utc'):
            with self.subTest(field=field):
                t=p1();t['evidence'][-1][field]='2026-10-29T12:00:01Z'
                with self.assertRaises(f.InvalidOutput): f.prepare_task(t)
        t=p1();t['evidence'][-1].pop('available_at_utc')
        with self.assertRaises(f.InvalidOutput): f.prepare_task(t)
    def test_empty_news_and_missing_rules_are_unknown_not_model_calls(self):
        for t in (p1('no_news'),task()):
            if t['phase']=='p1': t['condition']='news'
            else:t['evidence']=t['evidence'][1:]
            calls=[]
            for cls in (lambda: f.FaithfulEngine(lambda *a:calls.append(a)),
                        lambda: f.BaselineEngine(lambda *a:calls.append(a),1)):
                answer=cls().run(t);self.assertEqual(answer['status'],'unknown')
                self.assertEqual(answer['calls'],0)
            self.assertEqual(calls,[])
    def test_forecast_validation_probability_and_citations(self):
        for p in (-0.1,1.1,True,float('nan'),float('inf'),'0.5'):
            with self.subTest(p=p),self.assertRaises(f.InvalidOutput):
                f.validate_result(result(p),{'rule'})
        for p in (0,0.5,1,None):
            self.assertEqual(f.validate_result(result(p),{'rule'})['probability_yes'],p)
        with self.assertRaises(f.InvalidOutput):f.validate_result(result(.5,['unseen']),{'rule'})
        with self.assertRaises(f.InvalidOutput):f.validate_result(result(.5,[]),{'rule'})
        self.assertIsNone(f.validate_result(result(None,[]),{'rule'})['probability_yes'])
    def test_baseline_match_preserves_first_final_and_no_other_arm_data(self):
        calls=[]
        def gen(stage,payload):
            calls.append((stage,copy.deepcopy(payload)))
            return result([.3,.4,.5][len(calls)-1])
        ans=f.BaselineEngine(gen,3).run(p1())
        self.assertEqual(ans['status'],'proposal');self.assertEqual(ans['calls'],3)
        self.assertEqual(ans['first']['probability_yes'],.3);self.assertEqual(ans['result']['probability_yes'],.5)
        self.assertEqual([x[0] for x in calls],['baseline_initial','baseline_recheck','baseline_recheck'])
        self.assertEqual(calls[1][1]['previous_forecast']['probability_yes'],.3)
        self.assertEqual(calls[0][1]['prior_forecast']['probability_yes'],.45)
        self.assertNotIn('faithful_output',json.dumps(calls))
    def test_condition_is_journal_metadata_not_model_instruction(self):
        visible=[]
        for condition in ('no_news','news'):
            calls=[]
            def gen(stage,payload):
                calls.append(copy.deepcopy(payload));return result()
            ans=f.BaselineEngine(gen,2).run(p1(condition))
            self.assertEqual(ans['status'],'proposal')
            self.assertNotIn('condition',calls[0])
            self.assertNotIn('condition',calls[1]['task'])
            visible.append(calls[0])
        self.assertEqual(set(visible[0]),set(visible[1]))
        self.assertEqual(len(visible[1]['evidence']),len(visible[0]['evidence'])+1)
    def test_baseline_invalid_recheck_never_silently_uses_first_as_final(self):
        def gen(stage,payload):return result(.2 if stage=='baseline_initial' else 1.1)
        ans=f.BaselineEngine(gen,2).run(task())
        self.assertEqual(ans['status'],'technical_failure');self.assertEqual(ans['first']['probability_yes'],.2)
        self.assertNotIn('result',ans)
    def test_baseline_unknown_is_explicit(self):
        ans=f.BaselineEngine(lambda s,p:result(None,[]),1).run(task())
        self.assertEqual(ans['status'],'unknown')
    def test_faithful_inference_is_question_blind_and_cites_selected_leaves(self):
        seen=[]
        def gen(stage,payload):
            seen.append((stage,copy.deepcopy(payload)))
            if stage=='selection':return {'alternatives':[['rule','context']]}
            if stage=='inference':return {'conclusion':'A cautious proposal is appropriate under assumptions.'}
            if stage=='halter':return {'sufficient':True}
            if stage=='value':return {'score':.7}
            if stage=='formatter':return result(.48,['rule','context'])
            raise AssertionError(stage)
        ans=f.FaithfulEngine(gen).run(task())
        self.assertEqual(ans['status'],'proposal');self.assertEqual(ans['calls'],5)
        infer=next(p for s,p in seen if s=='inference')
        self.assertEqual(set(infer),{'selected_texts'});self.assertNotIn('question',infer)
        selected=[json.loads(x) for x in infer['selected_texts']]
        self.assertEqual(selected[0],{'source':'market snapshot','kind':'rule','text':'YES if an official report exceeds 4.2.'})
        self.assertEqual(selected[1]['source'],'official report')
        fmt=next(p for s,p in seen if s=='formatter')
        self.assertEqual({x['id'] for x in fmt['selected_evidence']},{'rule','context'})
        self.assertEqual(ans['result']['citations'],['rule','context'])
    def test_faithful_cannot_cite_unselected_fact(self):
        def gen(stage,payload):
            if stage=='selection':return {'alternatives':[['rule']]}
            if stage=='inference':return {'conclusion':'A cautious proposal.'}
            if stage=='halter':return {'sufficient':True}
            if stage=='value':return {'score':.7}
            if stage=='formatter':return result(.48,['context'])
        ans=f.FaithfulEngine(gen).run(task());self.assertEqual(ans['status'],'technical_failure')
        self.assertIn('unseen',ans['reason'])
    def test_faithful_two_branches_two_depths_uses_22_not_over_23(self):
        counts={'selection':0,'halter':0}
        def gen(stage,payload):
            if stage=='selection':
                counts['selection']+=1
                if counts['selection']==1:return {'alternatives':[['rule'],['context']]}
                node=next(x['id'] for x in payload['available_statements'] if x['id'].startswith('node:'))
                return {'alternatives':[[node,'rule'],[node,'context']]}
            if stage=='inference':
                self.assertEqual(set(payload),{'selected_texts'})
                for selected in map(json.loads,payload['selected_texts']):
                    if selected['kind']=='inference':
                        self.assertEqual(selected['source'],'model inference, not source fact')
                return {'conclusion':'A cautious intermediate inference.'}
            if stage=='halter':
                counts['halter']+=1
                return {'sufficient':counts['halter']>2}
            if stage=='value':return {'score':.7}
            if stage=='formatter':return result(.4,['rule'])
            raise AssertionError(stage)
        ans=f.FaithfulEngine(gen).run(task())
        self.assertEqual(ans['status'],'proposal');self.assertEqual(ans['calls'],22)
        self.assertEqual(counts,{'selection':3,'halter':6})
        self.assertEqual(len(ans['selected_trace']),2)
    def test_faithful_cap_exhaustion_is_unknown(self):
        def gen(stage,payload):
            if stage=='selection':return {'alternatives':[['rule'],['context']]}
            if stage=='inference':return {'conclusion':'A cautious intermediate inference.'}
            if stage=='halter':return {'sufficient':False}
            if stage=='value':return {'score':.7}
        ans=f.FaithfulEngine(gen,max_calls=4).run(task())
        self.assertEqual(ans['status'],'unknown');self.assertEqual(ans['reason'],'generation_cap_exhausted')
        self.assertEqual(ans['calls'],4)
    def test_callback_error_propagates_for_external_journal(self):
        def gen(stage,payload):raise TimeoutError('unknown provider state')
        for engine in (f.BaselineEngine(gen,1),f.FaithfulEngine(gen)):
            with self.assertRaises(TimeoutError): engine.run(task())
            self.assertEqual(engine.events[-1]['event'],'callback_raised')
    def test_request_response_adapter_and_invalid_stage(self):
        body=f.build_request('baseline_initial',{'task':'data'})
        self.assertEqual(body['generationConfig']['maxOutputTokens'],4096)
        self.assertEqual(body['generationConfig']['thinkingConfig']['thinkingLevel'],'LOW')
        response={'candidates':[{'finishReason':'STOP','content':{'parts':[{'text':json.dumps(result())}]}}]}
        self.assertEqual(f.parse_response(response)['probability_yes'],.45)
        response['candidates'][0]['finishReason']='MAX_TOKENS'
        with self.assertRaises(ValueError):f.parse_response(response)
        with self.assertRaises(ValueError):f.build_request('unexpected',{})

if __name__=='__main__':unittest.main()
