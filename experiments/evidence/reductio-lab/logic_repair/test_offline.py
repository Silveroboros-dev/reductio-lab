"""Offline semantic and budget checks for the explicitly corrected corpus."""
import unittest
from logic_repair.corpus import corpus
from logic_repair.run import make_contract

class CorrectedCorpus(unittest.TestCase):
 def test_universal_rules_prove_each_target(self):
  tasks,keys=corpus();byid={x['case_id']:x for x in tasks};self.assertEqual(len(tasks),3)
  for key in keys:
   task=byid[key['case_id']];ev={x['id']:x['text'] for x in task['evidence']}
   self.assertTrue(all(not x['text'].startswith('If a creature ') for x in task['evidence']))
   proof=[ev[i] for i in key['proof_ids']]
   subject=proof[0].split(' is ',1)[0];pred=proof[0][len(subject)+1:].removesuffix('.')
   for rule in proof[1:]:
    prefix='If something '+pred+', then it '
    self.assertTrue(rule.startswith(prefix),(pred,rule))
    pred=rule[len(prefix):].removesuffix('.')
   self.assertEqual(pred,'is authorized to enter the sanctuary' if key['answer']=='YES' else 'is not authorized to enter the sanctuary')
 def test_pair_only_final_rule_changes(self):
  tasks,keys=corpus(); a,b=tasks[:2]
  self.assertEqual(a['question'],b['question'])
  diffs=[(x,y) for x,y in zip(a['evidence'],b['evidence']) if x!=y]
  self.assertEqual(len(diffs),1);self.assertEqual(diffs[0][0]['id'],diffs[0][1]['id'])
  self.assertEqual({x['answer'] for x in keys[:2]},{'YES','NO'})
 def test_budget_and_single_shot_limits(self):
  c=make_contract();self.assertEqual(len(c['schedule']),9);self.assertEqual(c['max_logical_calls'],60)
  self.assertEqual(c['generation_prior']+c['max_new_generation_attempts'],c['model_call_limit'])
  self.assertLessEqual(c['count_prior']+c['max_new_count_attempts'],c['count_limit'])
  self.assertFalse(c['uncertain_retry'])

if __name__=='__main__':unittest.main()
