import importlib.util,unittest
from pathlib import Path
spec=importlib.util.spec_from_file_location('resume429_dispatch_for_tests',Path(__file__).with_name('dispatch.py'))
d=importlib.util.module_from_spec(spec);spec.loader.exec_module(d)
class TestDispatch(unittest.TestCase):
 def test_unique_imports_and_full_historical_preflight(self):
  self.assertTrue(d.accounting_launch.__file__.endswith('forecast-429-resume-account-v1/accounting_launch.py'))
  self.assertTrue(d.bridge.__file__.endswith('forecast-resume-exact-v1/bridge.py'))
  self.assertEqual(d.accounting_evidence()[1]['ledger']['source_attempts'],16)
  self.assertEqual([d.resume.verify_replay(x)['status'] for x in d.ORDER],['exact_429_reconstructed']*3)
  self.assertGreater(len(d.components()),100)
 def test_exact_limits_and_no_provider_without_gate(self):
  self.assertEqual(d.scope()['max_new_generations'],55);self.assertEqual(d.scope()['max_new_counts'],52)
  calls=[]
  class Fake:
   def retry_failed(self,*a):calls.append(a)
   def count_new(self,*a):calls.append(a)
   def generate_new(self,*a):calls.append(a)
  p=d.PacedLedger(Fake(),lambda:False)
  with self.assertRaises(Exception):p.retry_failed('x',{},None)
  self.assertEqual(calls,[])
 def test_deadline_validation(self):
  self.assertLess(d.instant('2026-10-29T12:29:59Z'),d.instant(d.DEADLINE))
  self.assertEqual(d.instant('2026-10-29T12:30:00Z'),d.instant(d.DEADLINE))
  with self.assertRaises(d.Error):d.instant('2026-10-29T12:30:00+01:00')
if __name__=='__main__':unittest.main()
