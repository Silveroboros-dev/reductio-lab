import copy,json,unittest
from datetime import datetime,timedelta,timezone
import gate,runner
import test_gate

def response(value):return json.dumps({'candidates':[{'finishReason':'STOP','content':{'parts':[{'text':json.dumps(value)}]}}]}).encode()
class Ledger:
 def __init__(self):self.s={'stopped':0,'source_attempts':16,'generation_attempts':299,'count_attempts':228,'exposure_micro':1988563};self.requests=[];self.counts={}
 def summary(self):return copy.deepcopy(self.s)
 def stop(self,reason):self.s['stopped']=1
 def count(self,ident,request,transport):
  self.s['count_attempts']+=1;self.counts[ident]=request;self.requests.append(request);return 100
 def generate(self,ident,request,count_id,transport):
  assert self.counts[count_id]==request
  self.s['generation_attempts']+=1;self.requests.append(request)
  x=json.loads(request['contents'][0]['parts'][0]['text']);stage=x['stage']
  if stage=='selection':v={'alternatives':[['rule:primary']]}
  elif stage=='inference':v={'conclusion':'Synthetic local inference.'}
  elif stage=='halter':v={'sufficient':True}
  elif stage=='value':v={'score':.5}
  else:v={'probability_yes':.5,'explanation':'Synthetic forecast.','citations':['rule:primary'],'assumptions':[],'counterevidence':[]}
  return response(v)
class Pacer:
 def __init__(self,clock):self.clock=clock
 def wait(self,scope):
  if not scope():raise runner.Error('invalid scope')
  self.clock.t+=timedelta(seconds=20)
  if not scope():raise runner.Error('invalid scope')
 def ended(self):pass
class Clock:
 def __init__(self):self.t=datetime(2026,10,29,12,30,5,tzinfo=timezone.utc)
 def __call__(self):return self.t.isoformat()
class Tests(unittest.TestCase):
 def setup_case(self):
  g=test_gate.Tests();g.setUp();admission=g.prep();self.assertEqual(admission['status'],'ready')
  clock=Clock();ledger=Ledger();records=[];status=copy.deepcopy(g.status)
  def refresh():
   ledger.s['source_attempts']+=1
   v=copy.deepcopy(status);v.update(observed_at_utc=clock(),captured_at_utc=clock(),quote='REFRESH-SECRET')
   return v
  kwargs={'ledger':ledger,'transport':lambda *a:None,'refresh_status':refresh,'verify_status':lambda *a:True,
   'verify_admission':lambda *a:True,'verify_ledger':lambda *a:True,'record':lambda n,v:records.append((n,copy.deepcopy(v))),
   'clock':clock,'pacer':Pacer(clock)}
  return admission,status,ledger,records,clock,kwargs
 def test_matched_arms_status_refresh_and_no_quote_leakage(self):
  admission,status,ledger,records,clock,k=self.setup_case()
  out=runner.run(admission,status,**k)
  self.assertEqual(ledger.s['stopped'],0);self.assertGreaterEqual(out['status_observations_during_run'],2)
  self.assertEqual(ledger.s['source_attempts'],16+out['status_observations_during_run'])
  self.assertNotIn('REFRESH-SECRET',str(ledger.requests));self.assertNotIn('SECRET-NOT-FOR-MODEL',str(ledger.requests))
  for condition in ('news','no_news'):
   self.assertEqual(out['model_results']['results'][condition]['c']['calls'],5)
   self.assertEqual(out['model_results']['results'][condition]['b']['calls'],5)
  self.assertEqual(len(ledger.counts),20)
  self.assertIn('p1-frozen',[n for n,_ in records]);self.assertIn('p1-summary',[n for n,_ in records])
 def test_status_budget_exhaustion_stops_before_first_model(self):
  admission,status,ledger,records,clock,k=self.setup_case();ledger.s['source_attempts']=28;clock.t+=timedelta(minutes=6)
  with self.assertRaises(runner.Error):runner.run(admission,status,**k)
  self.assertEqual(ledger.s['stopped'],1);self.assertEqual(ledger.s['generation_attempts'],299)
 def test_market_resolution_after_last_result_excludes_frozen(self):
  admission,status,ledger,records,clock,k=self.setup_case()
  original=k['refresh_status']
  def closed():
   x=original();x['state']='closed';x['result']='yes';return x
  k['refresh_status']=closed
  with self.assertRaises(runner.Error):runner.run(admission,status,**k)
  self.assertEqual(ledger.s['stopped'],1);self.assertNotIn('p1-frozen',[n for n,_ in records])
 def test_refresh_without_ledger_effect_rejected(self):
  admission,status,ledger,records,clock,k=self.setup_case();clock.t+=timedelta(minutes=6)
  k['refresh_status']=lambda:status
  with self.assertRaises(runner.Error):runner.run(admission,status,**k)
  self.assertEqual(ledger.s['stopped'],1)
 def test_rejects_tampered_prior_and_no_news_even_if_digest_recomputed(self):
  for kind in ('prior','leak'):
   admission,status,ledger,records,clock,k=self.setup_case()
   if kind=='prior':admission['bundle']['tasks']['b_no_news']['prior_forecast']['probability_yes']=.01
   else:admission['bundle']['tasks']['b_no_news']['evidence'].append({'id':'leak','kind':'news','text':'leak','source':'x'})
   admission['bundle_sha256']=gate.sha(gate.canonical(admission['bundle']))
   with self.assertRaises(runner.Error):runner.run(admission,status,**k)
   self.assertEqual(ledger.s['generation_attempts'],299)
if __name__=='__main__':unittest.main()
