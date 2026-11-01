import copy,sys,unittest
from datetime import datetime,timezone
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import remaining_binding as r

class RemainingTest(unittest.TestCase):
 def test_real_unchanged_subset_and_no_case01_generation(self):
  info=r.build(clock=lambda:datetime.now(timezone.utc).isoformat());bundle=info['bundle']
  self.assertEqual(bundle['common_as_of_utc'],'2026-10-29T10:55:04.930181+00:00')
  self.assertEqual(tuple(x['case']['case_id'] for x in bundle['prepared']),r.EXPECTED)
  calls=[]
  def factory(cid,phase,condition,arm):
   self.assertIn(cid,r.EXPECTED);self.assertEqual((phase,condition),('p0','no_news'));calls.append((cid,arm))
   def gen(stage,payload):
    if arm=='b':self.assertNotIn('C-SECRET',str(payload))
    if stage=='selection':return {'alternatives':[['rule:primary']]}
    if stage=='inference':return {'conclusion':'cautious'}
    if stage=='halter':return {'sufficient':True}
    if stage=='value':return {'score':0.8}
    return {'probability_yes':0.4,'explanation':'C-SECRET' if arm=='c' else 'B-own','citations':['rule:primary'],'assumptions':[],'counterevidence':[]}
   return gen
  out=r.p.run(bundle,verify_bundle=lambda x:True,generator_factory=factory,record=lambda *x:None,
   clock=lambda:'2026-10-29T11:00:00Z')
  self.assertEqual(len(out['results']),3);self.assertTrue(all(cid!='case-01' for cid,_ in calls))
  for item in out['results']:self.assertEqual(item['c']['calls'],item['b']['calls'])
 def test_changed_subset_denied_before_output(self):
  info=r.build(clock=lambda:datetime.now(timezone.utc).isoformat());bundle=copy.deepcopy(info['bundle'])
  bundle['prepared'][0]['task']['question']='changed';effects=[]
  with self.assertRaises(r.p.Error):r.p.run(bundle,verify_bundle=lambda x:True,generator_factory=lambda *x:effects.append(x),record=lambda *x:effects.append(x),clock=lambda:'2026-10-29T11:00:00Z')
  self.assertEqual(effects,[])
if __name__=='__main__':unittest.main()
