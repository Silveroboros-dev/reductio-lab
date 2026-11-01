import json,sys,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parent))
import binding,pace

class Clock:
 def __init__(self):self.t=0;self.waits=[]
 def monotonic(self):return self.t
 def sleep(self,x):self.waits.append(x);self.t+=x
class Ledger:
 def __init__(self,clock):self.clock=clock;self.events=[];self.stops=[]
 def count(self,id,req,transport):
  self.events.append(('count',self.clock.t,id));transport('vertex','countTokens',b'{}');self.clock.t+=3
 def generate(self,id,req,countid,transport):
  self.events.append(('generate',self.clock.t,id));transport('vertex','gemini-3.8-flash@global',b'{}');self.clock.t+=4
  return json.dumps({'candidates':[{'finishReason':'STOP','content':{'parts':[{'text':'{"conclusion":"ok"}'}]}}]}).encode()
 def stop(self,reason):self.stops.append(reason)
class FinalTwoTest(unittest.TestCase):
 def test_actual_saved_subset_and_cutoff(self):
  x=binding.build();b=x['bundle'];self.assertEqual(tuple(c['case']['case_id'] for c in b['prepared']),binding.EXPECTED)
  self.assertEqual(b['common_as_of_utc'],'2026-10-29T10:55:04.930181+00:00')
  self.assertEqual(x['bundle_sha256'],'1667f6675db84b779f2434a025f72c9498e5b41c28eb3fb5f46d3f1c56af7c67')
 def test_pacing_before_every_provider_effect(self):
  clock=Clock();ledger=Ledger(clock);paced=pace.Pacer(monotonic=clock.monotonic,sleep=clock.sleep);transport_calls=[]
  with patch.object(pace.recovery,'ModelOnlyLedger',Ledger):
   f=pace.factory(ledger,case_ids=['case-03','case-04'],transport=lambda *x:(transport_calls.append(x) or (200,b'{}')),verify_scope=lambda:True,pacer=paced)
  call=f('case-03','p0','no_news','c');call('inference',{'selected_texts':['a']});call('inference',{'selected_texts':['b']})
  self.assertEqual([x[0] for x in ledger.events],['count','generate','count','generate'])
  self.assertGreaterEqual(ledger.events[0][1],20)
  # Delay is from prior returned effect, stricter than 20 sec between starts.
  self.assertEqual([x[1] for x in ledger.events],[20,43,67,90])
  self.assertEqual(len(transport_calls),4)
  with self.assertRaises(pace.Error):f('case-03','p0','no_news','c')
  with self.assertRaises(pace.Error):f('case-02','p0','no_news','b')
 def test_revoked_scope_before_sleep_prevents_effect(self):
  clock=Clock();ledger=Ledger(clock);paced=pace.Pacer(monotonic=clock.monotonic,sleep=clock.sleep)
  with patch.object(pace.recovery,'ModelOnlyLedger',Ledger):f=pace.factory(ledger,case_ids=['case-03','case-04'],transport=lambda *x:None,verify_scope=lambda:False,pacer=paced)
  with self.assertRaises(pace.Error):f('case-04','p0','no_news','c')('inference',{})
  self.assertEqual(ledger.events,[])
if __name__=='__main__':unittest.main()
