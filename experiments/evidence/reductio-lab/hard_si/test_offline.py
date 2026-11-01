"""Offline adversarial checks. All providers and model responses are fixtures."""
from __future__ import annotations
import copy,importlib,json,re,sys,tempfile,unittest
from pathlib import Path
from hard_si.corpus import build
from hard_si.run import contract,_step_prompt,_intervention_payload,budget_baseline
from hard_si.runtime import Adapter,generation_request,ledger_type
from faithful_v3.prompts import bind_model,build_request
from faithful_v3.engine import StrictEngine
from reasoning_engine.engine import EngineConfig,prepare_task
from research.retry_facade import RetryFacade
from research import live_run as legacy

class CorpusChecks(unittest.TestCase):
 def test_independent_text_parser_and_iterative_closure(self):
  tasks,keys,pairs=build();truth={x['case_id']:x for x in keys}
  self.assertEqual((len(tasks),len(keys),len(pairs)),(12,12,6))
  for task in tasks:
   facts=[];rules=[]
   for e in task['evidence']:
    t=e['text'];f=re.fullmatch(r'(Entity-[0-9]+) has label ([A-Z]{5})\.',t)
    m=re.fullmatch(r'If something has label ([A-Z]{5}), then it (has label [A-Z]{5}|is authorized to enter the sanctuary|is not authorized to enter the sanctuary)\.',t)
    if f:facts.append((f[1],f[2],e['id']))
    elif m:
     target=m[2].removeprefix('has label ') if m[2].startswith('has label ') else m[2]
     rules.append((m[1],target,e['id']))
    else:self.fail('unparseable statement '+t)
   self.assertEqual(len(facts),1)
   # Independent repeated relaxation over parsed statements, not generator BFS.
   depths={facts[0][1]:0};changed=True
   while changed:
    changed=False
    for a,b,_ in rules:
     if a in depths and (b not in depths or depths[b]>depths[a]+1):depths[b]=depths[a]+1;changed=True
   key=truth[task['case_id']];yes=depths.get('is authorized to enter the sanctuary');no=depths.get('is not authorized to enter the sanctuary')
   self.assertEqual((yes,no),(6,None) if key['answer']=='YES' else (None,6))
   self.assertEqual(len(rules),12+key['distractors'])
   self.assertNotIn('proof_ids',json.dumps(task));self.assertNotIn('terminal_condition',json.dumps(task))
  byid={x['case_id']:x for x in tasks}
  for pair in pairs:
   a,b=[byid[x] for x in pair['case_ids']];self.assertEqual(a['question'],b['question'])
   diffs=[(x,y) for x,y in zip(a['evidence'],b['evidence']) if x!=y]
   self.assertEqual(len(diffs),1);self.assertEqual(diffs[0][0]['id'],diffs[0][1]['id'])
   self.assertEqual({truth[x]['answer'] for x in pair['case_ids']},{'YES','NO'})
 def test_contract_caps_and_case_budget_order(self):
  c=contract();self.assertEqual(len(c['schedule']),60);self.assertEqual(len({(x['case_id'],x['arm']) for x in c['schedule']}),60)
  for case in c['cases']:
   arms=[x['arm'] for x in c['schedule'] if x['case_id']==case]
   self.assertLess(arms.index('C'),arms.index('B_budget'))
  self.assertEqual(c['counts']['logical_generations_max'],12*(43+1+1+2+20)+4)
  self.assertEqual(c['counts']['previous_generation_attempts']+848,1910)
  self.assertEqual(c['counts']['previous_count_attempts']+848,1834)
 def test_model_levels_and_exact_count_request(self):
  r=build_request('baseline_initial',{'question':'fixture'})
  self.assertEqual(generation_request(r,'LOW')['generationConfig']['thinkingConfig']['thinkingLevel'],'LOW')
  self.assertEqual(generation_request(r,'MEDIUM')['generationConfig']['thinkingConfig']['thinkingLevel'],'MEDIUM')
  with self.assertRaises(ValueError):generation_request(r,'HIGH')
 def test_budget_baseline_one_call_overshoot_and_no_prior_C_response(self):
  task=prepare_task(build()[0][0]);spent=[0];seen=[]
  def fake(stage,payload):
   seen.append((stage,copy.deepcopy(payload)));spent[0]+=2
   return {'answer':'fixture','citations':[],'assessments':[{'id':'user-target','status':'assessed','reason':'fixture'}]}
  out=budget_baseline(task,fake,lambda:spent[0],3)
  self.assertEqual(out['calls'],2);self.assertEqual(out['reported_spend_micro'],4)
  self.assertEqual([s for s,_ in seen],['baseline_initial','baseline_recheck'])
  self.assertNotIn('target_c_micro',json.dumps(seen))
 def test_intervention_edits_exactly_one_selected_premise(self):
  task=build()[0][0];key=build()[1][0];rule=key['terminal_text'];ante=key['terminal_condition']
  payload={'selected_texts':[{'text':rule,'source':'src','kind':'observation'},{'text':f'Entity-1 has label {ante}.','source':'model','kind':'derived_claim'}]}
  out={'branches':[{'steps':[{'selected_ids':[key['terminal_rule_id'],'node:0001'],'inference_call_ordinal':3}]}],
       'events':[{'event':'model_started','stage':'inference','ordinal':3,'payload':payload}]}
  sample=_intervention_payload(out,key);self.assertIsNotNone(sample)
  self.assertEqual(sample['control']['selected_texts'][1],sample['edited']['selected_texts'][1])
  self.assertNotEqual(sample['control']['selected_texts'][0]['text'],sample['edited']['selected_texts'][0]['text'])
  self.assertIsNone(_intervention_payload({'branches':[],'events':[]},key))
 def test_six_depth_two_alternatives_with_strict_projection(self):
  task,key=build()[0][0],build()[1][0];ids=key['proof_ids'];seen=[];inferences=0;last=None
  def model(request):
   nonlocal inferences,last
   stage=request['stage'];p=request['input'];seen.append(stage)
   if stage=='selection':
    depth=inferences//2+1;first=[ids[0],ids[1]] if depth==1 else [last,ids[depth]]
    extra=next(x['id'] for x in p['available_statements'] if x['id'] not in first and x['id'] not in ids)
    return {'alternatives':[first,[extra]]}
   if stage=='inference':
    self.assertEqual(set(p),{'selected_texts'});self.assertNotIn(task['question'],json.dumps(request))
    inferences+=1;pos=(inferences-1)%2
    if pos==0:last=f'node:{inferences:04d}'
    return {'conclusion':f'scripted {inferences}'}
   if stage=='halter':return {'sufficient':inferences==11,'reason':'fixture'}
   if stage=='value':return {'score':0.9 if inferences%2 else 0.1}
   if stage=='formatter':
    self.assertNotIn(task['question'],json.dumps(request));return {'answer':'fixture','citations':[p['allowed_citation_ids'][0]]}
   self.fail(stage)
  out=StrictEngine(bind_model(model),EngineConfig(max_calls=43,max_depth=6,beam_width=1,max_alternatives=2)).run(task)
  self.assertEqual(out['status'],'proposal');self.assertEqual(out['calls'],43)
  self.assertEqual(out['inference_dependency_depth'],6)

class EffectChecks(unittest.TestCase):
 def setUp(self):
  self.cfg=contract()['config'];sys.path.insert(0,str(legacy.OLD/'forecast-p1-budget-successor-v1'));sys.path.insert(0,str(legacy.OLD/'transport'))
  self.retry=importlib.import_module('p1_retry');self.prior_extra=self.retry.MAX_EXTRA;self.retry.MAX_EXTRA=40
  self.tmp=tempfile.TemporaryDirectory(dir='/private/tmp');self.base=ledger_type(self.retry,self.cfg)(str(Path(self.tmp.name)/'ledger'),self.cfg,create=True)
 def tearDown(self):self.base.close();self.retry.MAX_EXTRA=self.prior_extra;self.tmp.cleanup()
 def test_medium_level_body_identical_count_and_generation(self):
  bodies=[]
  def transport(provider,endpoint,raw):
   bodies.append(raw)
   if endpoint=='countTokens':return 200,b'{"totalTokens":100}'
   return 200,json.dumps({'modelVersion':'gemini-3.8-flash','usageMetadata':{'promptTokenCount':100,'totalTokenCount':110},'candidates':[{'finishReason':'STOP','content':{'parts':[{'text':'{"answer":"fixture"}'}]}}]}).encode()
  adapter=Adapter(RetryFacade(self.base,self.retry,sleep=lambda _:None),transport)
  adapter.complete(build_request('baseline_initial',{'question':'fixture'}),'a'*64+':B:001','MEDIUM')
  self.assertEqual(bodies[0],bodies[1]);self.assertEqual(json.loads(bodies[0])['generationConfig']['thinkingConfig']['thinkingLevel'],'MEDIUM')
  self.assertEqual(self.base.summary()['exposure_micro'],self.cfg['prior_micro']+225)
 def test_ambiguous_effect_stops_and_retains_quote(self):
  calls=[]
  def transport(provider,endpoint,raw):
   calls.append(endpoint)
   if endpoint=='countTokens':return 200,b'{"totalTokens":100}'
   raise RuntimeError('offline disconnect')
  adapter=Adapter(RetryFacade(self.base,self.retry,sleep=lambda _:None),transport)
  with self.assertRaises(Exception):adapter.complete(build_request('baseline_initial',{'question':'fixture'}),'b'*64+':B:001','LOW')
  self.assertEqual(len(calls),2);self.assertTrue(self.base.summary()['stopped'])
  self.assertEqual(self.base.db.execute("select state,actual_micro,quote_micro from effects where kind='generation'").fetchone(),('uncertain',None,519996))
  with self.assertRaises(Exception):adapter.complete(build_request('baseline_initial',{'question':'fixture'}),'b'*64+':B:001','LOW')
  self.assertEqual(len(calls),2)

if __name__=='__main__':unittest.main()
