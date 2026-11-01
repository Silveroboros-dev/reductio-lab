import copy,json,sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
sys.path.insert(0,str(Path(__file__).resolve().parent.parent/'forecast-orchestrator-v1'))
import p0_launcher as l
from test_orchestrator import case,mkresult,yes

class TestP0(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name).resolve();self.paths=[]
  for i in range(2):
   c=case();c.update(case_id=f'case-{i}',event_group_id=f'group-{i}',contract_id=f'market-{i}')
   p=self.root/f'{i}.json';p.write_text(json.dumps(c));self.paths.append(str(p))
 def tearDown(self):self.temp.cleanup()
 def prep(self):return l.prepare(self.paths,verify_case_record=yes,verify_human=yes,verify_rules=yes,verify_evidence=yes,clock=lambda:'2026-10-29T10:01:00Z')
 def factory(self,case_id,phase,condition,arm):
  self.assertEqual((phase,condition),('p0','no_news'))
  def gen(stage,payload):
   if arm=='b':self.assertNotIn('C-SECRET',str(payload))
   if stage=='selection':return {'alternatives':[['rule:primary']]}
   if stage=='inference':return {'conclusion':'A cautious conclusion.'}
   if stage=='halter':return {'sufficient':True}
   if stage=='value':return {'score':.8}
   if stage in ('formatter','baseline_initial','baseline_recheck'):return mkresult(arm)
   self.fail(stage)
  return gen
 def test_isolation_and_create_only_durable(self):
  bundle=self.prep();rec=l.durable_recorder(self.root/'out')
  result=l.run(bundle,verify_bundle=yes,generator_factory=self.factory,record=rec,clock=lambda:'2026-10-29T10:30:00Z')
  self.assertEqual(len(result['results']),2)
  for r in result['results']:
   self.assertEqual(r['c']['result']['explanation'],'C-SECRET')
   self.assertEqual(r['b']['result']['explanation'],'B-own')
   self.assertEqual(r['b']['calls'],r['c']['calls'])
  with self.assertRaises(FileExistsError):rec('p0-bundle',{})
  with self.assertRaises(FileExistsError):l.durable_recorder(self.root/'out')
 def test_missing_approval_and_drift(self):
  with self.assertRaises(l.o.EligibilityError):l.prepare(self.paths,verify_case_record=yes,verify_human=lambda x:False,verify_rules=yes,verify_evidence=yes,clock=lambda:'2026-10-29T10:01:00Z')
  bundle=self.prep();Path(self.paths[0]).write_text('{}');effects=[]
  with self.assertRaises(l.Error):l.run(bundle,verify_bundle=yes,generator_factory=self.factory,record=lambda *x:effects.append(x),clock=lambda:'2026-10-29T10:30:00Z')
  self.assertEqual(effects,[])
 def test_common_cutoff_and_source_review(self):
  x=json.loads(Path(self.paths[1]).read_text());x['p0_as_of_utc']='2026-10-29T10:00:01Z';Path(self.paths[1]).write_text(json.dumps(x))
  with self.assertRaises(l.Error):self.prep()
  with self.assertRaises(l.Error):l.prepare(self.paths,verify_case_record=yes,verify_human=yes,verify_rules=yes,verify_evidence=lambda x:False,clock=lambda:'2026-10-29T10:01:00Z')
 def test_bundle_reviewer_and_disk_failure_block_generators(self):
  bundle=self.prep();calls=[]
  with self.assertRaises(l.Error):l.run(bundle,verify_bundle=lambda x:False,generator_factory=lambda *x:calls.append(x),record=lambda *x:None,clock=lambda:'2026-10-29T10:30:00Z')
  with self.assertRaises(OSError):l.run(bundle,verify_bundle=yes,generator_factory=lambda *x:calls.append(x),record=lambda *x:(_ for _ in ()).throw(OSError('disk')),clock=lambda:'2026-10-29T10:30:00Z')
  self.assertEqual(calls,[])
if __name__=='__main__':unittest.main()
