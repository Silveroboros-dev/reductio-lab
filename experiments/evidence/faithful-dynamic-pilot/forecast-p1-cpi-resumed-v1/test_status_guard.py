import copy,unittest
from datetime import timedelta
import gate,status_guard,test_runner
class Account:
 def __init__(self):self.stopped=0
 def verify(self):pass
 def summary(self):return {'stopped':self.stopped,'source_attempts':20}
class T(unittest.TestCase):
 def setUp(self):
  self.admission,self.status,_,_,self.clock,_=test_runner.Tests().setup_case();self.case=gate.verify_p0()['prepared']['case'];self.a=Account();self.g=status_guard.Guard(account=self.a,clock=self.clock,verify_status=lambda *a:True)
  self.status['captured_at_utc']=self.status['observed_at_utc']=self.clock()
 def test_fresh_then_expired_and_refreshed(self):
  self.assertFalse(self.g.verify_scope());self.assertTrue(self.g.verify_status(self.status,self.case,self.clock()));self.assertTrue(self.g.verify_scope())
  self.clock.t+=timedelta(seconds=301);self.assertFalse(self.g.verify_scope())
  self.status['captured_at_utc']=self.status['observed_at_utc']=self.clock();self.assertTrue(self.g.verify_status(self.status,self.case,self.clock()));self.assertTrue(self.g.verify_scope())
 def test_reject_invalid_resolved_or_old(self):
  self.assertTrue(self.g.verify_status(self.status,self.case,self.clock()));bad=copy.deepcopy(self.status);bad['result']='yes';self.assertFalse(self.g.verify_status(bad,self.case,self.clock()))
  self.a.stopped=1;self.assertFalse(self.g.verify_scope())
 def test_scope_rechecks_freshness_after_slow_account_verify(self):
  self.assertTrue(self.g.verify_status(self.status,self.case,self.clock()))
  self.a.verify=lambda:setattr(self.clock,'t',self.clock.t+timedelta(seconds=301))
  self.assertFalse(self.g.verify_scope())
 def test_untrusted_provider_rejected(self):
  self.g.verifier=lambda *a:False;self.assertFalse(self.g.verify_status(self.status,self.case,self.clock()));self.assertFalse(self.g.verify_scope())
if __name__=='__main__':unittest.main()
