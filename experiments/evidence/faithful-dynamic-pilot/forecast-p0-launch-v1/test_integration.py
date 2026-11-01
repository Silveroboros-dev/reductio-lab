import copy,json,sys,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parent))
import approved_inputs as a,recovery_adapter as r,p0_launcher as p

def yes(*x):return True
class Ledger:
 def __init__(self):self.ops=[];self.stops=[];self.poisoned=False
 def count(self,ident,req,transport):
  self.ops.append(('count',ident,copy.deepcopy(req)));transport('vertex','countTokens',b'{}');return 10
 def generate(self,ident,req,countid,transport):
  self.ops.append(('generation',ident,countid,copy.deepcopy(req)));transport('vertex','gemini-3.8-flash@global',b'{}')
  return json.dumps({'candidates':[{'finishReason':'STOP','content':{'parts':[{'text':'{"conclusion":"uncertain"}'}]}}]}).encode()
 def stop(self,reason):self.stops.append(reason)
class IntegrationTest(unittest.TestCase):
 def test_real_input_projection_and_exact_rules(self):
  observed=[]
  cases=a.build('2026-10-29T11:00:00Z',verify_human_origin=yes,verify_relays_and_fit=lambda c,m,meta:(observed.append((c,m,meta)) or True))
  self.assertEqual(len(cases),4);self.assertEqual(tuple(c['contract_id'] for c in cases),a.TICKERS)
  self.assertEqual(len(observed),4)
  for c,m,meta in observed:
   self.assertEqual(c['rules_primary'],m['rules_primary']);self.assertEqual(c['rules_secondary'],m['rules_secondary'])
   self.assertEqual(c['rules_captured_at_utc'],meta['recorded_at_utc'])
   self.assertFalse(meta['origin']['claims_independently_verified'])
   p.o.prepare_case(c,verify_human=yes,verify_rules=yes)
  self.assertIn('IPO или первичном раунде',cases[0]['thesis'])
  self.assertNotIn('Trillion',cases[0]['rules_primary'])
 def test_real_input_requires_attestation_and_time(self):
  with self.assertRaises(a.Error):a.build('2026-10-29T11:00:00Z',verify_human_origin=lambda x:False,verify_relays_and_fit=yes)
  with self.assertRaises(a.Error):a.build('2026-10-29T11:00:00Z',verify_human_origin=yes,verify_relays_and_fit=lambda *x:False)
  with self.assertRaises(a.Error):a.build('2026-10-29T10:00:00Z',verify_human_origin=yes,verify_relays_and_fit=yes)
 def test_one_shot_ledger_and_no_source(self):
  ledger=Ledger();calls=[]
  with patch.object(r.recovery,'ModelOnlyLedger',Ledger):
   factory=r.generator_factory(ledger,case_ids=['case-01'],transport=lambda *x:(calls.append(x) or (200,b'{}')),verify_p0_binding=yes)
  gen=factory('case-01','p0','no_news','c');result=gen('inference',{'selected_texts':['x']})
  self.assertEqual(result,{'conclusion':'uncertain'})
  self.assertEqual([v[0] for v in ledger.ops],['count','generation'])
  self.assertEqual(ledger.ops[0][2],ledger.ops[1][3])
  self.assertEqual(ledger.ops[1][2],ledger.ops[0][1])
  with self.assertRaises(r.Error):factory('case-01','p0','no_news','c')
  with self.assertRaises(r.Error):factory('case-01','p1','news','b')
  self.assertEqual(len(calls),2)
 def test_guard_failure_stops_without_external_call(self):
  ledger=Ledger();calls=[]
  with patch.object(r.recovery,'ModelOnlyLedger',Ledger):
   factory=r.generator_factory(ledger,case_ids=['case-01'],transport=lambda *x:calls.append(x),verify_p0_binding=lambda:False)
  with self.assertRaises(r.Error):factory('case-01','p0','no_news','c')('inference',{'selected_texts':['x']})
  self.assertFalse(calls);self.assertTrue(ledger.stops)
 def test_accounting_or_unactivated_ledger_rejected(self):
  with self.assertRaises(r.Error):r.generator_factory(Ledger(),case_ids=['case-01'],transport=yes,verify_p0_binding=yes)
 def test_persistence_failure_stops_ledger(self):
  ledger=Ledger();fn=r.stop_on_record_error(ledger,lambda *x:(_ for _ in ()).throw(OSError('disk')))
  with self.assertRaises(OSError):fn('entry',{})
  self.assertTrue(ledger.stops);self.assertTrue(ledger.poisoned)
if __name__=='__main__':unittest.main()
