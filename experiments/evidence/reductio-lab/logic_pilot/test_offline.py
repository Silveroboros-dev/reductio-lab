"""Offline checks; no provider access or new live effects."""
import copy, json, unittest
from logic_pilot.corpus import corpus
from logic_pilot.run import make_contract
from faithful_v3.engine import StrictEngine
from faithful_v3.prompts import bind_model
from reasoning_engine.engine import EngineConfig

class OfflinePilot(unittest.TestCase):
 def test_truth_keys_and_minimal_pairs(self):
  tasks,keys=corpus();self.assertEqual(len(tasks),8)
  self.assertEqual(sum(k['answer']=='YES' for k in keys),4)
  self.assertEqual(sum(k['answer']=='NO' for k in keys),4)
  self.assertEqual({k['inference_depth'] for k in keys},{4})
  byid={t['case_id']:t for t in tasks}; byproof={k['case_id']:k for k in keys}
  for i in range(0,8,2):
   ka,kb=keys[i:i+2]; a,b=byid[ka['case_id']],byid[kb['case_id']]
   self.assertEqual(a['question'],b['question'])
   self.assertEqual(len(a['evidence']),len(b['evidence']))
   diffs=[(x,y) for x,y in zip(a['evidence'],b['evidence']) if x!=y]
   self.assertEqual(len(diffs),1)
   self.assertEqual(diffs[0][0]['id'],diffs[0][1]['id'])
   self.assertEqual(ka['proof_ids'],kb['proof_ids'])
   self.assertNotIn('yes',a['case_id']);self.assertNotIn('no',a['case_id'])
 def test_contract_is_within_inherited_caps(self):
  c=make_contract();self.assertEqual(c['max_logical_calls'],8*(1+2+17))
  self.assertLessEqual(c['generation_prior']+c['max_new_generation_attempts'],c['model_call_limit'])
  self.assertLessEqual(c['count_prior']+c['max_new_count_attempts'],c['count_limit'])
  self.assertEqual(len(c['schedule']),24)
 def test_four_step_si_stateless_role_boundary(self):
  tasks,keys=corpus(); task=tasks[0]; key=next(k for k in keys if k['case_id']==task['case_id'])
  reqs=[]; depth=0; latest=None
  def model(request):
   nonlocal depth,latest
   stage=request['stage'];p=request['input'];reqs.append(copy.deepcopy(request))
   if stage=='selection':
    self.assertIn(task['question'],p['question'])
    ids=key['proof_ids']
    return {'alternatives': [[ids[0],ids[1]]] if latest is None else [[latest,ids[depth+1]]]}
   if stage=='inference':
    self.assertEqual(set(p),{'selected_texts'})
    self.assertNotIn(task['question'],json.dumps(request))
    depth+=1;latest=f'node:{depth:04d}'
    return {'conclusion':f'FIXTURE STEP {depth}'}
   if stage=='halter':return {'sufficient':depth==4,'reason':'fixture only'}
   if stage=='value':return {'score':0.5}
   if stage=='formatter':
    self.assertNotIn(task['question'],json.dumps(request))
    return {'answer':'FIXTURE STEP 4','citations':[p['allowed_citation_ids'][0]]}
   raise AssertionError(stage)
  out=StrictEngine(bind_model(model),EngineConfig(max_calls=17,max_depth=4,beam_width=1,max_alternatives=1)).run(task)
  self.assertEqual(out['status'],'proposal');self.assertEqual(out['calls'],17)
  self.assertEqual(out['inference_dependency_depth'],4)
  self.assertEqual([r['stage'] for r in reqs],['selection','inference','halter','value']*4+['formatter'])

if __name__=='__main__':unittest.main()
