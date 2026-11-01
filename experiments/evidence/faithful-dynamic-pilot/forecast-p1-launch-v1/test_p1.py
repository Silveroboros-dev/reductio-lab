import copy,json,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
sys.path.insert(0,str(Path(__file__).resolve().parent.parent/'forecast-orchestrator-v1'))
import p1,source
from test_orchestrator import case,news,yes,mkresult

def prep0():
 p=p1.o.prepare_case(case(),verify_human=yes,verify_rules=yes)
 def fac(phase,cond,arm):
  def gen(stage,payload):
   if stage=='selection':return {'alternatives':[['rule:primary']]}
   if stage=='inference':return {'conclusion':'supported only by selected premises'}
   if stage=='halter':return {'sufficient':True}
   if stage=='value':return {'score':0.8}
   if stage in ('baseline_initial','baseline_recheck','formatter'):return mkresult(arm)
   raise AssertionError(stage)
  return gen
 z=p1.o.run_p0(p,generator_factory=fac,record=lambda *x:None,clock=lambda:'2026-10-29T10:30:00Z')
 return p,z

def status():
 c=case();return {'contract_id':c['contract_id'],'rules_primary':c['rules_primary'],'rules_secondary':c['rules_secondary'],
  'state':'active','result':'','observed_at_utc':'2026-10-29T11:29:00Z','captured_at_utc':'2026-10-29T11:29:10Z'}

def ready(p,z,n=None,s=None):return p1.prepare(p,z,news() if n is None else n,status() if s is None else s,t1='2026-10-29T11:30:00Z',verify_p0=yes,verify_news=yes,verify_status=yes)

class Ledger:
 def __init__(self):self.calls=[];self.stops=[];self.poisoned=False
 def summary(self):return {'stopped':0,'exposure_micro':1616450,'generation_attempts':242,'count_attempts':174,'source_attempts':14}
 def count(self,id,req,transport):self.calls.append((id,copy.deepcopy(req)));transport('vertex','countTokens',b'{}')
 def generate(self,id,req,countid,transport):
  self.calls.append((id,copy.deepcopy(req)));transport('vertex','gemini-3.8-flash@global',b'{}')
  stage=json.loads(req['contents'][0]['parts'][0]['text'])['stage'];arm='b' if ':b:' in id else 'c'
  if arm=='b':assert 'C-SECRET' not in json.dumps(req)
  if stage=='selection':value={'alternatives':[['rule:primary']]}
  elif stage=='inference':value={'conclusion':'cautious inference'}
  elif stage=='halter':value={'sufficient':True}
  elif stage=='value':value={'score':0.8}
  else:value=mkresult(arm)
  return json.dumps({'candidates':[{'finishReason':'STOP','content':{'parts':[{'text':json.dumps(value)}]}}]}).encode()
 def stop(self,reason):self.stops.append(reason)
class SourceLedger(Ledger):
 def __init__(self):super().__init__();self.n=0;self.raw=b'{"success":true}'
 def summary(self):return {'stopped':0,'exposure_micro':1510458,'generation_attempts':240,'count_attempts':172,'source_attempts':14+self.n}
 def source(self,id,provider,endpoint,request,ticket,transport):
  self.n+=1;transport(provider,endpoint,request);return self.raw
 def receipt(self,id):return {'state':'succeeded','http_status':200,'response_hash':p1.o.sha(self.raw),'actual_micro':2000,'started_at_utc':'2026-10-29T11:30:00Z','completed_at_utc':'2026-10-29T11:30:01Z'}

class P1Test(unittest.TestCase):
 def test_absent_event_or_status_never_dispatches(self):
  p,z=prep0()
  self.assertEqual(p1.prepare(p,z,[],None,t1='2026-10-29T11:30:00Z',verify_p0=yes,verify_news=yes,verify_status=yes)['status'],'pending')
  self.assertEqual(p1.prepare(p,z,news(),None,t1='2026-10-29T11:30:00Z',verify_p0=yes,verify_news=yes,verify_status=yes)['status'],'pending')
  calls=[];out=p1.run({'status':'pending'},verify_bundle=yes,verify_ledger=yes,ledger=Ledger(),transport=lambda *x:calls.append(x),record=lambda *x:None,clock=lambda:'2026-10-29T11:30:00Z')
  self.assertEqual(out['status'],'pending');self.assertFalse(calls)
 def test_prior_and_true_prospective_time(self):
  p,z=prep0();n=news();n[0]['published_at_utc']='2026-10-29T10:29:59Z'
  self.assertEqual(ready(p,z,n=n)['status'],'pending')
  z['b']['result']=None;self.assertEqual(ready(p,z)['status'],'pending')
 def test_unresolved_expired_changed_rules(self):
  p,z=prep0()
  for mutate in ('settled','rules','old'):
   s=status()
   if mutate=='settled':s['result']='yes'
   if mutate=='rules':s['rules_primary']='changed'
   if mutate=='old':s['captured_at_utc']='2026-10-29T11:20:00Z';s['observed_at_utc']='2026-10-29T11:19:00Z'
   self.assertEqual(ready(p,z,s=s)['status'],'pending')
  self.assertEqual(p1.prepare(p,z,news(),status(),t1='2026-10-29T11:30:00Z',verify_p0=yes,verify_news=yes,verify_status=lambda *x:False)['status'],'pending')
 def test_status_must_follow_news_capture(self):
  p,z=prep0();n=news();n[0]['published_at_utc']='2026-10-29T11:29:20Z';n[0]['available_at_utc']='2026-10-29T11:29:21Z';n[0]['captured_at_utc']='2026-10-29T11:29:22Z'
  self.assertEqual(ready(p,z,n=n)['reason'],'market_status_predates_news_capture')
 def test_four_arms_preserve_own_prior_and_c_equal_b_count(self):
  p,z=prep0();ad=ready(p,z);self.assertEqual(ad['status'],'ready')
  b=ad['bundle'];self.assertEqual(b['tasks']['c_news']['prior_forecast']['explanation'],'C-SECRET')
  self.assertEqual(b['tasks']['b_news']['prior_forecast']['explanation'],'B-own')
  ledger=Ledger();records=[]
  result=p1.run(ad,verify_bundle=yes,verify_ledger=yes,ledger=ledger,transport=lambda *x:(200,b'{}'),record=lambda *x:records.append(x),clock=lambda:'2026-10-29T11:30:00Z')
  self.assertEqual(set(result['results']),{'no_news','news'})
  for cond in result['results']:self.assertEqual(result['results'][cond]['c']['calls'],result['results'][cond]['b']['calls'])
  self.assertFalse(ledger.stops)
 def test_scope_stale_stops_before_transport(self):
  p,z=prep0();ad=ready(p,z);ledger=Ledger();calls=[]
  result=p1.run(ad,verify_bundle=yes,verify_ledger=yes,ledger=ledger,transport=lambda *x:calls.append(x),record=lambda *x:None,clock=lambda:'2026-10-29T11:40:00Z')
  self.assertEqual(result['status'],'pending');self.assertFalse(calls)
 def test_unreviewed_ledger_or_exhausted_budget_prohibits_effects(self):
  p,z=prep0();ad=ready(p,z);ledger=Ledger();calls=[]
  with self.assertRaises(p1.Error):
   p1.run(ad,verify_bundle=yes,verify_ledger=lambda x:False,ledger=ledger,transport=lambda *x:calls.append(x),record=lambda *x:None,clock=lambda:'2026-10-29T11:30:00Z')
  self.assertFalse(calls)
  ledger.summary=lambda:{'stopped':0,'exposure_micro':60000000,'generation_attempts':242,'count_attempts':174,'source_attempts':14}
  with self.assertRaises(p1.Error):
   p1.run(ad,verify_bundle=yes,verify_ledger=yes,ledger=ledger,transport=lambda *x:calls.append(x),record=lambda *x:None,clock=lambda:'2026-10-29T11:30:00Z')
  self.assertFalse(calls)
 def test_source_effect_ledger_and_no_repeat(self):
  ledger=SourceLedger();payload={'q':'example'};ident='p1:one:news:01';raw=p1.o.canonical(payload)
  ticket={'id':ident,'provider':'orthogonal','endpoint':'/v1/run','request_sha256':p1.o.sha(raw),'max_micro':150000,'expires_utc':'2026-10-29T12:00:00Z'}
  plan={'schema':'forecast-p1-source-plan-v1','status':'frozen','starting_usage':ledger.summary(),'not_before_utc':'2026-10-29T11:20:00Z','operations':[{'id':ident,'provider':'orthogonal','endpoint':'/v1/run','payload':payload,'ticket':ticket}]}
  saved=[];transports=[]
  result=source.execute(plan,ledger=ledger,transport=lambda *x:transports.append(x),record_raw=lambda *x:saved.append(x),verify_contract=yes,verify_completed_p0=yes,clock=lambda:'2026-10-29T11:30:00Z')
  self.assertEqual(result['records'][0]['actual_micro'],2000);self.assertEqual(len(saved),1);self.assertEqual(len(transports),1)
  with self.assertRaises(source.Error):source.execute(plan,ledger=ledger,transport=lambda *x:None,record_raw=lambda *x:None,verify_contract=yes,verify_completed_p0=yes,clock=lambda:'2026-10-29T11:30:00Z')
 def test_bad_quote_blocks_without_source(self):
  ledger=SourceLedger();plan={'schema':'forecast-p1-source-plan-v1','status':'frozen','starting_usage':ledger.summary(),'not_before_utc':'2026-10-29T11:20:00Z','operations':[{'id':'p1:one:news:01','provider':'orthogonal','endpoint':'/v1/run','payload':{},'ticket':{}}]}
  with self.assertRaises(source.Error):source.execute(plan,ledger=ledger,transport=lambda *x:None,record_raw=lambda *x:None,verify_contract=yes,verify_completed_p0=yes,clock=lambda:'2026-10-29T11:30:00Z')
  self.assertEqual(ledger.n,0)
if __name__=='__main__':unittest.main()
