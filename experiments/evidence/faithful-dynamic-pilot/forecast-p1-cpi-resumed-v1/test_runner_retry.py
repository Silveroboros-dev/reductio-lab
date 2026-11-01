import copy,json,unittest
from datetime import timedelta
import gate,runner_retry,test_runner

class Confirmed429(Exception):pass
class RateLimitExhausted(Exception):pass
class RetryLedger(test_runner.Ledger):
 def __init__(self,mode):
  super().__init__();self.mode=mode;self.seen={};self.attempts=[];self.successes=set();self.extra=0
 def _attempt(self,logical,request,attempt,kind,countid=None):
  assert logical not in self.successes,'successful logical operation repeated'
  assert self.seen.get((kind,logical),0)==attempt,'nonsequential attempt'
  self.seen[(kind,logical)]=attempt+1;self.attempts.append((kind,logical,attempt,gate.sha(gate.canonical(request))))
  if attempt:self.extra+=1
  if kind=='count':self.s['count_attempts']+=1
  else:self.s['generation_attempts']+=1
  transient=(self.mode=='recover' and logical.endswith('no_news:c:01') and attempt==0)
  exhausted=(self.mode=='exhaust_b' and kind=='generation' and logical.endswith('no_news:b:02')) or (self.mode=='exhaust_c' and kind=='generation' and logical.endswith('no_news:c:02'))
  if self.mode=='unknown' and kind=='generation' and logical.endswith('no_news:c:01'):raise RuntimeError('ambiguous transport')
  if transient:raise Confirmed429('confirmed 429')
  if exhausted:
   if attempt<3:raise Confirmed429('confirmed 429')
   raise RateLimitExhausted('confirmed 429 exhausted')
  self.successes.add(logical)
  if kind=='count':self.counts[logical]=request;self.requests.append(request);return 100
  assert countid in self.counts and self.counts[countid]==request
  self.requests.append(request);x=json.loads(request['contents'][0]['parts'][0]['text']);stage=x['stage']
  if stage=='selection':v={'alternatives':[['rule:primary']]}
  elif stage=='inference':v={'conclusion':'Synthetic local inference.'}
  elif stage=='halter':v={'sufficient':True}
  elif stage=='value':v={'score':.5}
  else:v={'probability_yes':.5,'explanation':'Synthetic forecast.','citations':['rule:primary'],'assumptions':[],'counterevidence':[]}
  return test_runner.response(v)
 def count_attempt(self,logical,request,attempt,transport):return self._attempt(logical,request,attempt,'count')
 def generate_attempt(self,logical,request,countid,attempt,transport):return self._attempt(logical,request,attempt,'generation',countid)
class Tests(unittest.TestCase):
 def fixture(self,mode):
  t=test_runner.Tests();admission,status,old,records,clock,k=t.setup_case();ledger=RetryLedger(mode);k['ledger']=ledger;del k['refresh_status']
  def refresh():
   ledger.s['source_attempts']+=1;v=copy.deepcopy(status);v.update(observed_at_utc=clock(),captured_at_utc=clock(),quote='HIDDEN-NEW-QUOTE');return v
  delays=[]
  def sleep(t):delays.append(t);clock.t+=timedelta(seconds=t)
  k.update(refresh_status=refresh,confirmed429=Confirmed429,rate_limit_exhausted=RateLimitExhausted,sleep=sleep,jitter=lambda:.5)
  return admission,status,ledger,records,k,delays
 def test_confirmed_429_retry_exact_bytes_count_reused(self):
  a,s,l,records,k,delays=self.fixture('recover');out=runner_retry.run(a,s,**k)
  self.assertEqual(out['model_results']['results']['no_news']['c']['status'],'proposal')
  self.assertEqual(delays,[1.5,1.5]);self.assertEqual(l.extra,2)
  for kind in ('count','generation'):
   subset=[x for x in l.attempts if x[0]==kind and x[1].endswith('no_news:c:01')]
   self.assertEqual([x[2] for x in subset],[0,1]);self.assertEqual(len({x[3] for x in subset}),1)
  self.assertNotIn('HIDDEN-NEW-QUOTE',str(l.requests))
 def test_exhausted_b_partial_but_news_condition_completes(self):
  a,s,l,records,k,delays=self.fixture('exhaust_b');out=runner_retry.run(a,s,**k);r=out['model_results']['results']
  self.assertEqual(r['no_news']['c']['status'],'proposal');self.assertEqual(r['no_news']['b']['reason'],'confirmed_429_retry_budget_exhausted')
  self.assertEqual(r['news']['c']['status'],'proposal');self.assertEqual(r['news']['b']['status'],'proposal')
  self.assertEqual(delays,[1.5,3,6]);self.assertEqual(l.s['stopped'],0)
 def test_exhausted_c_skips_only_dependent_b(self):
  a,s,l,records,k,delays=self.fixture('exhaust_c');out=runner_retry.run(a,s,**k);r=out['model_results']['results']
  self.assertEqual(r['no_news']['c']['reason'],'confirmed_429_retry_budget_exhausted');self.assertEqual(r['no_news']['b']['status'],'unavailable')
  self.assertFalse(any(':no_news:b:' in x[1] for x in l.attempts));self.assertEqual(r['news']['b']['status'],'proposal')
 def test_unknown_stops_without_retry(self):
  a,s,l,records,k,delays=self.fixture('unknown')
  with self.assertRaises(RuntimeError):runner_retry.run(a,s,**k)
  self.assertEqual(l.s['stopped'],1);self.assertEqual(delays,[]);self.assertFalse(any(x[2] for x in l.attempts))
  self.assertNotIn('p1-frozen',[name for name,value in records])
 def test_source_exception_is_not_misclassified_as_model_429(self):
  a,s,l,records,k,delays=self.fixture('normal');k['clock'].t+=timedelta(minutes=6)
  def failed_source():raise Confirmed429('source 429 must never become model retry')
  k['refresh_status']=failed_source
  with self.assertRaises(Confirmed429):runner_retry.run(a,s,**k)
  self.assertEqual(l.s['stopped'],1);self.assertEqual(l.attempts,[]);self.assertEqual(delays,[])
if __name__=='__main__':unittest.main()
