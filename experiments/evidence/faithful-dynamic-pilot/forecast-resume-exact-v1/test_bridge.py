import copy,json,unittest,importlib.util
from pathlib import Path
from datetime import datetime,timedelta,timezone
import resume
spec=importlib.util.spec_from_file_location('resume429_bridge_test',Path(__file__).with_name('bridge.py'))
bridge=importlib.util.module_from_spec(spec);spec.loader.exec_module(bridge)
from test_resume import payload,envelope
class Ledger:
 def __init__(self):self.calls=[]
 def retry_failed(self,old,req,transport):self.calls.append(('retry',old));return envelope(payload(self.stage))
 def count_new(self,logical,req,transport):self.calls.append(('count',logical));return 10
 def generate_new(self,logical,req,transport):self.calls.append(('generation',logical));return envelope(payload(self.stage))
class T(unittest.TestCase):
 def test_reconstruct_all_calls_retry_never_recounts(self):
  for case in resume.CONFIG:
   l=Ledger();now=[datetime(2026,10,29,11,45,tzinfo=timezone.utc)]
   def clk():now[0]+=timedelta(seconds=1);return now[0].isoformat()
   def permitted(binding,stage,request):l.stage=stage;return True
   cb=bridge.generator(l,lambda *a:None,permitted)
   receipt=resume.run_case(case,generate=cb,verify_live=lambda *a:True,record=lambda *a:None,clock=clk)
   self.assertTrue(receipt['comparison_eligible'])
   self.assertEqual(sum(kind=='retry' for kind,_ in l.calls),1)
   self.assertEqual(sum(kind=='count' for kind,_ in l.calls),sum(kind=='generation' for kind,_ in l.calls))
   retried=next(x for k,x in l.calls if k=='retry')
   self.assertNotIn(('count',retried.removeprefix('generation:')),l.calls)
   self.assertEqual(len(set(l.calls)),len(l.calls))
 def test_bad_digest_never_dispatches(self):
  l=Ledger();cb=bridge.generator(l,lambda *a:None,lambda *a:True)
  with self.assertRaises(bridge.Error):cb({'request_sha256':'wrong'},'x',{})
  self.assertEqual(l.calls,[])
if __name__=='__main__':unittest.main()
