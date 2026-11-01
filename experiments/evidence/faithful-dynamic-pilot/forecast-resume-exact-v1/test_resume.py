import copy, json, unittest
from datetime import datetime, timedelta, timezone
import resume

def payload(stage):
 if stage=='halter':return {'sufficient':True}
 if stage=='value':return {'score':.6}
 if stage=='inference':return {'conclusion':'A conditional, uncertain inference.'}
 if stage=='formatter' or stage.startswith('baseline_'):
  return {'probability_yes':.5,'explanation':'A conditional model estimate.','citations':['rule:primary'],'assumptions':['An uncertain assumption.'],'counterevidence':['An alternative outcome.']}
 raise AssertionError(stage)
def envelope(value):return json.dumps({'candidates':[{'finishReason':'STOP','content':{'parts':[{'text':json.dumps(value)}]}}]}).encode()
class TestResume(unittest.TestCase):
 def test_all_three_live_free_exact_replays(self):
  for case in resume.CONFIG:
   r=resume.verify_replay(case)
   self.assertEqual(r['status'],'exact_429_reconstructed')
   self.assertEqual(r['successful_replayed'],resume.CONFIG[case]['failed']-1)
 def test_recover_without_repeating_any_success(self):
  for case in resume.CONFIG:
   calls=[];recorded=[];now=[datetime(2026,10,29,11,45,tzinfo=timezone.utc)]
   def clock():now[0]+=timedelta(seconds=1);return now[0].isoformat()
   def verify(binding,request):return resume.sha(resume.canonical(request))==binding['request_sha256']
   def generate(binding,stage,request):
    calls.append((copy.deepcopy(binding),stage));return envelope(payload(stage))
   ans=resume.run_case(case,generate=generate,verify_live=verify,record=lambda name,value:recorded.append((name,value)),clock=clock)
   retries=[b for b,s in calls if b['kind']=='retry_confirmed_429']
   self.assertEqual(len(retries),1);self.assertEqual(retries[0]['ordinal'],resume.CONFIG[case]['failed'])
   self.assertTrue(all(b['ordinal']>resume.CONFIG[case]['failed'] for b,s in calls if b['kind']=='unattempted' and b['arm']==resume.CONFIG[case]['arm']))
   self.assertEqual(len({(b['case_id'],b['arm'],b['ordinal']) for b,s in calls}),len(calls))
   self.assertEqual(ans['schema'],'resumed-original-p0-receipt-v1')
   self.assertEqual(recorded[-1][0],case+'-p0-receipt')
   if case=='case-01':self.assertEqual(len(calls),7)
   if case=='case-02':self.assertEqual(len(calls),4)
   if case=='case-04':self.assertLessEqual(len(calls),44)
 def test_no_live_on_guard_reject(self):
  hits=[]
  with self.assertRaises(resume.Error):
   resume.run_case('case-01',generate=lambda *a:hits.append(a),verify_live=lambda *a:False,record=lambda *a:None,clock=lambda:'2026-10-29T11:45:00+00:00')
  self.assertEqual(hits,[])
 def test_live_failure_does_not_produce_receipt(self):
  writes=[]
  def fail(*a):raise RuntimeError('simulated provider failure')
  with self.assertRaises(RuntimeError):
   resume.run_case('case-02',generate=fail,verify_live=lambda *a:True,record=lambda name,value:writes.append(name),clock=lambda:'2026-10-29T11:45:00+00:00')
  self.assertFalse(any(x.endswith('p0-receipt') for x in writes))
 def test_bad_historical_request_is_rejected_without_callback(self):
  s=resume.inspect('case-01');s['records'][0]['request']+=b' '
  with self.assertRaises(resume.Error):
   resume._replayer(s)('baseline_initial',{k:v for k,v in s['task'].items() if k!='condition'})
 def test_deadline_blocks_callbacks(self):
  hits=[]
  with self.assertRaises(resume.Error):
   resume.run_case('case-01',generate=lambda *a:hits.append(a),verify_live=lambda *a:True,record=lambda *a:None,clock=lambda:'2026-10-29T12:30:00+00:00')
  self.assertEqual(hits,[])
if __name__=='__main__':unittest.main()
