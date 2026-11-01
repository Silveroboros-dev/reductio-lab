import copy,sqlite3,unittest
from datetime import datetime,timedelta
import gate,admission_evidence,venue_capture,replay,reconstruct,runner38,test_runner,test_runner_retry
class Pacer:
 def __init__(self,clock):self.clock=clock;self.last=clock.t
 def wait(self,scope):
  assert scope();self.clock.t=max(self.clock.t,self.last+timedelta(seconds=20));assert scope()
 def ended(self):self.last=self.clock.t
class T(unittest.TestCase):
 def fixture(self,mode='normal'):
  pre=admission_evidence.inspect();a=pre['admission'];db=sqlite3.connect('file:'+str(reconstruct.PARENT)+'?mode=ro',uri=True);db.row_factory=sqlite3.Row
  try:r=dict(db.execute("select * from effects where id='p1-cpi-status-05'").fetchone())
  finally:db.close()
  status=venue_capture.extract(bytes(r['response']));status.update(source_op_id=r['id'],response_sha256=r['response_hash'],observed_at_utc=r['completed_at_utc'],captured_at_utc=r['completed_at_utc'])
  clock=test_runner.Clock();clock.t=datetime.fromisoformat(r['completed_at_utc'])+timedelta(seconds=1);l=test_runner_retry.RetryLedger(mode);l.s.update(source_attempts=25,generation_attempts=315,count_attempts=244,exposure_micro=2069419);records=[]
  def refresh():
   l.s['source_attempts']+=1;x=copy.deepcopy(status);x.update(observed_at_utc=clock(),captured_at_utc=clock());return x
  k={'ledger':l,'transport':lambda *a:None,'refresh_status':refresh,'verify_status':lambda *a:True,'verify_admission':lambda x:x==a,'verify_ledger':lambda *a:True,
   'record':lambda n,v:records.append((n,copy.deepcopy(v))),'clock':clock,'pacer':Pacer(clock),
   'confirmed429':test_runner_retry.Confirmed429,'rate_limit_exhausted':test_runner_retry.RateLimitExhausted,'sleep':lambda delay:setattr(clock,'t',clock.t+timedelta(seconds=delay)),'jitter':lambda:0}
  return a,status,l,records,k
 def test_repaired_c_offline_remaining_arms(self):
  a,s,l,records,k=self.fixture();out=runner38.run(a,s,**k);r=out['model_results']['results']
  self.assertEqual(r['no_news']['c']['result']['probability_yes'],.57);self.assertEqual(r['no_news']['c']['calls'],8)
  self.assertEqual(r['no_news']['b']['calls'],8);self.assertEqual(r['news']['b']['calls'],r['news']['c']['calls'])
  self.assertFalse(any(':no_news:' in x[1] for x in l.attempts));self.assertIn('post-hoc',out['limitation']);self.assertEqual(l.s['stopped'],0)
 def test_unparseable_c_skips_only_dependent_b(self):
  a,s,l,records,k=self.fixture();old=l.generate_attempt
  def malformed(ident,request,countid,attempt,transport):
   if ident.endswith('news:c:01'):
    l.s['generation_attempts']+=1;return b'{invalid'
   return old(ident,request,countid,attempt,transport)
  l.generate_attempt=malformed;out=runner38.run(a,s,**k);r=out['model_results']['results']
  self.assertEqual(r['news']['c']['reason'],'unparseable_successful_http_response');self.assertEqual(r['news']['b']['status'],'unavailable')
  self.assertFalse(any(':news:b:' in x[1] for x in l.attempts));self.assertEqual(l.s['stopped'],0)
if __name__=='__main__':unittest.main()
