import copy, json, unittest
import exploration as e

def task():
 return {'case_id':'case-A','thought':'Will inflation affect policy?', 'thought_origin':'assistant_proposal_unaccepted', 'as_of_utc':'2026-10-29T12:00:00Z',
         'evidence':[{'id':'src-1','text':'One report described a possible link.','source':'report',
                      'published_at_utc':'2026-10-29T10:00:00Z','available_at_utc':'2026-10-29T10:01:00Z'}],
         'market_leads':[{'market_id':'MKT-1','title':'Official CPI above 4.2?',
                          'source':'dated catalog','captured_at_utc':'2026-10-29T11:00:00Z'}]}

def answer():
 return {'directions':[{'candidate':'Inflation falls by a specified date',
  'connection':'A possible upstream factor for rate decisions.',
  'mechanism':'Lower inflation might affect policy decisions.',
  'observable':'A named CPI release', 'horizon':'year end', 'falsifier':'CPI rises',
  'alternatives':['Policy might respond mainly to employment.'],
  'counterevidence':['Other objectives could dominate.'],
  'suggested_market_ids':[], 'citations':['input:thought','src-1']}], 'unknown_reason':None}

class ExplorationTests(unittest.TestCase):
 def test_thought_attribution_is_explicit_and_model_visible(self):
  for bad in (None, 'user input', 'unknown'):
   t=task();t['thought_origin']=bad
   with self.assertRaises(e.InvalidOutput):e.prepare_task(t)
  t=task();del t['thought_origin']
  with self.assertRaises(e.InvalidOutput):e.prepare_task(t)
  seen=[]
  def gen(stage,payload):
   seen.append(copy.deepcopy(payload))
   return answer()
  e.BaselineEngine(gen,1).run(task())
  self.assertEqual(seen[0]['thought_origin'],'assistant_proposal_unaccepted')
  self.assertEqual(seen[0]['evidence'][0]['source'],'input provenance: assistant_proposal_unaccepted')
  seen=[]
  def cgen(stage,payload):
   seen.append((stage,copy.deepcopy(payload)))
   if stage=='explore_selection':return {'selected_ids':['input:thought','src-1']}
   if stage=='explore_inference':return {'conclusion':'A tentative connection.'}
   if stage=='explore_halter':return {'sufficient':True}
   if stage=='explore_formatter':return answer()
  e.FaithfulEngine(cgen).run(task())
  source=seen[0][1]['available_statements'][0]['source']
  self.assertEqual(source,'input provenance: assistant_proposal_unaccepted')
 def test_accepts_and_projects_exact_task_without_automatic_decision(self):
  x=e.prepare_task(task());self.assertEqual(x['case_id'],'case-A');self.assertNotIn('accepted',x)
  t=task();t['hidden_decision']='approved'
  with self.assertRaises(e.InvalidOutput):e.prepare_task(t)
 def test_rejects_future_timestamps_duplicate_ids_and_unknown_market_fields(self):
  t=task();t['evidence'][0]['available_at_utc']='2026-10-29T12:00:01Z'
  with self.assertRaises(e.InvalidOutput):e.prepare_task(t)
  t=task();t['evidence'].append(copy.deepcopy(t['evidence'][0]))
  with self.assertRaises(e.InvalidOutput):e.prepare_task(t)
  t=task();t['market_leads'][0]['fit']='direct'
  with self.assertRaises(e.InvalidOutput):e.prepare_task(t)
 def test_result_rejects_unseen_citation_or_market_and_enforces_size(self):
  a=answer();a['directions'][0]['citations']=['invented']
  with self.assertRaises(e.InvalidOutput):e.validate_result(a,{'input:thought','src-1'},{'MKT-1'})
  a=answer();a['directions'][0]['suggested_market_ids']=['invented']
  with self.assertRaises(e.InvalidOutput):e.validate_result(a,{'input:thought','src-1'},{'MKT-1'})
  a=answer();a['directions']*=4
  with self.assertRaises(e.InvalidOutput):e.validate_result(a,{'input:thought','src-1'},{'MKT-1'})
 def test_unknown_and_missing_fields_remain_unknown(self):
  self.assertEqual(e.validate_result({'directions':[],'unknown_reason':'Insufficient information'},set(),set())['directions'],[])
  a=answer();a['directions'][0]['mechanism']=None;a['directions'][0]['falsifier']=None
  self.assertIsNone(e.validate_result(a,{'input:thought','src-1'},{'MKT-1'})['directions'][0]['mechanism'])
 def test_baseline_first_and_matched_receive_no_c_output(self):
  calls=[]
  def gen(stage,payload):calls.append((stage,copy.deepcopy(payload)));return answer()
  ans=e.BaselineEngine(gen,3).run(task())
  self.assertEqual(ans['status'],'proposal');self.assertEqual(ans['calls'],3)
  self.assertEqual(ans['first'],ans['result']);self.assertNotIn('C_result',json.dumps(calls))
  self.assertEqual([s for s,_ in calls],['explore_baseline_initial','explore_baseline_recheck','explore_baseline_recheck'])
 def test_c_inference_question_blind_proposals_never_accepted(self):
  calls=[]
  def gen(stage,payload):
   calls.append((stage,copy.deepcopy(payload)))
   if stage=='explore_selection':return {'selected_ids':['input:thought','src-1']}
   if stage=='explore_inference':return {'conclusion':'Inflation is a plausible factor, not an established causal effect.'}
   if stage=='explore_halter':return {'sufficient':True}
   if stage=='explore_formatter':return answer()
   raise AssertionError(stage)
  ans=e.FaithfulEngine(gen).run(task())
  self.assertEqual(ans['status'],'proposal');self.assertEqual(ans['calls'],4)
  self.assertNotIn('accepted',ans)
  self.assertEqual(set(next(p for s,p in calls if s=='explore_inference')) ,{'selected_texts'})
  selected=next(p for s,p in calls if s=='explore_inference')['selected_texts']
  self.assertEqual(json.loads(selected[1]),{'source':'report','text':'One report described a possible link.'})
  fmt=next(p for s,p in calls if s=='explore_formatter')
  self.assertNotIn('selected_market_leads',fmt)
 def test_c_cannot_output_unselected_market_lead(self):
  def gen(stage,payload):
   if stage=='explore_selection':return {'selected_ids':['input:thought','src-1']}
   if stage=='explore_inference':return {'conclusion':'A possible connection.'}
   if stage=='explore_halter':return {'sufficient':True}
   if stage=='explore_formatter':
    a=answer();a['directions'][0]['suggested_market_ids']=['MKT-1'];return a
  ans=e.FaithfulEngine(gen).run(task())
  self.assertEqual(ans['status'],'technical_failure');self.assertIn('unavailable market',ans['reason'])
 def test_c_cannot_cite_unselected_source(self):
  def gen(stage,payload):
   if stage=='explore_selection':return {'selected_ids':['input:thought']}
   if stage=='explore_inference':return {'conclusion':'A possible connection.'}
   if stage=='explore_halter':return {'sufficient':True}
   if stage=='explore_formatter':return answer()
  ans=e.FaithfulEngine(gen).run(task());self.assertEqual(ans['status'],'technical_failure')
 def test_nonhalting_returns_unknown_no_more_than_six_calls(self):
  def gen(stage,payload):
   if stage=='explore_selection':return {'selected_ids':['input:thought']}
   if stage=='explore_inference':return {'conclusion':'Still insufficient.'}
   if stage=='explore_halter':return {'sufficient':False}
   raise AssertionError(stage)
  ans=e.FaithfulEngine(gen).run(task());self.assertEqual(ans['status'],'unknown')
  self.assertEqual(ans['reason'],'reasoning_depth_exhausted');self.assertEqual(ans['calls'],6)
 def test_second_halt_true_cannot_skip_formatter_at_cap(self):
  n=0
  def gen(stage,payload):
   nonlocal n
   if stage=='explore_selection':return {'selected_ids':['input:thought']}
   if stage=='explore_inference':return {'conclusion':'A tentative inference.'}
   if stage=='explore_halter':
    n+=1;return {'sufficient':n==2}
   raise AssertionError(stage)
  ans=e.FaithfulEngine(gen).run(task());self.assertEqual(ans['status'],'unknown')
  self.assertEqual(ans['reason'],'generation_cap_exhausted');self.assertEqual(ans['calls'],6)
 def test_callback_exceptions_propagate_to_effect_journal(self):
  def gen(*args):raise TimeoutError('unknown')
  for engine in (e.BaselineEngine(gen),e.FaithfulEngine(gen)):
   with self.assertRaises(TimeoutError):engine.run(task())
   self.assertEqual(engine.events[-1]['event'],'callback_raised')
 def test_request_adapter(self):
  req=e.build_request('explore_baseline_initial',task())
  self.assertEqual(req['generationConfig']['maxOutputTokens'],4096)
  with self.assertRaises(ValueError):e.build_request('unknown',{})
 def test_seed_never_discloses_market_ids_or_titles_to_either_model(self):
  for kind in ('B','C'):
   with self.subTest(kind=kind):
    t=task();t['market_leads'][0]['market_id']='SENTINEL-MARKET-ID'
    t['market_leads'][0]['title']='SENTINEL-MARKET-TITLE'
    seen=[]
    def gen(stage,payload):
     seen.append(copy.deepcopy(payload))
     if stage in ('explore_baseline_initial','explore_baseline_recheck','explore_formatter'):return answer()
     if stage=='explore_selection':return {'selected_ids':['input:thought','src-1']}
     if stage=='explore_inference':return {'conclusion':'A possible connection.'}
     if stage=='explore_halter':return {'sufficient':True}
     raise AssertionError(stage)
    engine=e.BaselineEngine(gen,2) if kind=='B' else e.FaithfulEngine(gen)
    outcome=engine.run(t)
    self.assertEqual(outcome['status'],'proposal')
    self.assertEqual(outcome['stage'],'seed')
    self.assertNotIn('SENTINEL-MARKET-ID',json.dumps(seen))
    self.assertNotIn('SENTINEL-MARKET-TITLE',json.dumps(seen))
 def test_known_market_id_or_exact_title_in_original_seed_fails_closed(self):
  for field in ('thought','evidence'):
   for leak in ('MKT-1','Official CPI above 4.2?'):
    with self.subTest(field=field,leak=leak):
     t=task()
     if field=='thought':t['thought']+=' '+leak
     else:t['evidence'][0]['text']+=' '+leak
     original=copy.deepcopy(t);calls=[]
     for engine in (e.BaselineEngine(lambda *a:calls.append(a)),e.FaithfulEngine(lambda *a:calls.append(a))):
      result=engine.run(t);self.assertEqual(result['status'],'technical_failure')
      self.assertIn('known market ID/title',result['reason']);self.assertEqual(result['calls'],0)
     self.assertEqual(t,original);self.assertEqual(calls,[])
 def test_post_market_is_distinct_parent_bound_and_does_not_mutate_seed(self):
  original=answer()
  seed={'status':'proposal','calls':4,'result':copy.deepcopy(original)}
  snapshot=copy.deepcopy(seed);captured=[]
  def gen(stage,payload):
   captured.append(copy.deepcopy(payload))
   row=copy.deepcopy(original['directions'][0]);row['suggested_market_ids']=['MKT-1']
   return {'post_market_directions':[{'parent_seed_sha256':payload['seed_directions'][0]['seed_sha256'],'direction':row}], 'unknown_reason':None}
  ans=e.PostMarketEngine(gen,seed).run(task())
  self.assertEqual(ans['status'],'proposal');self.assertEqual(ans['calls'],1);self.assertEqual(ans['total_calls'],5)
  self.assertEqual(ans['stage'],'post_market');self.assertEqual(seed,snapshot)
  row=ans['result']['post_market_directions'][0]
  self.assertEqual(row['stage'],'post_market');self.assertEqual(row['parent_seed_sha256'],e._digest(original['directions'][0]))
  self.assertEqual(captured[0]['market_leads'][0]['market_id'],'MKT-1')
 def test_post_market_rejects_invented_seed_parent(self):
  seed={'status':'proposal','calls':4,'result':answer()}
  def gen(stage,payload):return {'post_market_directions':[{'parent_seed_sha256':'invented','direction':answer()['directions'][0]}],'unknown_reason':None}
  ans=e.PostMarketEngine(gen,seed).run(task());self.assertEqual(ans['status'],'technical_failure')
 def test_post_market_does_not_run_when_combined_cap_exhausted(self):
  seed={'status':'proposal','calls':6,'result':answer()};called=[]
  ans=e.PostMarketEngine(lambda *args:called.append(args),seed).run(task())
  self.assertEqual(ans['status'],'unknown');self.assertEqual(ans['reason'],'combined_generation_cap_exhausted')
  self.assertEqual(ans['calls'],0);self.assertEqual(ans['total_calls'],6);self.assertEqual(called,[])

if __name__=='__main__':unittest.main()
