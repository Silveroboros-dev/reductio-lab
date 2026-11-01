import json,tempfile,types,unittest
from pathlib import Path
from unittest import mock
import accounting_launch as a

class FakeLedger:
 def __init__(self):self.closed=False
 def summary(self):return {'stopped':0,'exposure_micro':1510458,'generation_attempts':232,'count_attempts':164,'source_attempts':14,'prior_http400_charge_unknown_retained_micro':150000}
 def close(self):self.closed=True

class Tests(unittest.TestCase):
 def test_frozen_scope_caps_and_parent(self):
  c=a.obj(a.read(a.ROOT/'forecast-recovery-accounting-contract-20261029-v1.json'))
  self.assertEqual(c['caps'],a.CAPS);self.assertEqual(c['scope'],{'mode':'accounting_only','provider_effects':'forbidden'})
  self.assertEqual(c['parent']['failed_operation']['effect_state'],'succeeded')
  self.assertEqual(c['parent']['failed_operation']['gate_state'],'failed')
  self.assertIsNone(c['parent']['failed_operation']['charged_micro'])
  self.assertEqual(c['parent']['failed_operation']['retained_micro'],150000)
 def test_fake_accounting_create_no_provider(self):
  with tempfile.TemporaryDirectory(dir='/private/tmp') as t:
   p=Path(t).resolve();ledger=FakeLedger();claim=p/'claim'
   c={'execution_context':{'ledger_root':str(p/'ledger'),'receipt_path':str(p/'receipt.json'),'claim_path':str(claim)}}
   def create(**kw):
    self.assertTrue(kw['verify_challenge'](b'contract'));self.assertFalse(kw['verify_ticket']({},b''))
    return ledger
   fake=types.SimpleNamespace(CLAIM=claim,create_successor=create,AccountingOnlyLedger=FakeLedger)
   with mock.patch.object(a,'verify',return_value=(c,b'contract',b'challenge',b'receipt')):
    with mock.patch.dict('sys.modules',{'recovery':fake}):
     result=a.execute(p/'contract',p/'challenge',p/'receipt','hash')
   self.assertTrue(ledger.closed);self.assertTrue((p/'receipt.json').is_file())
   self.assertEqual(result['authority'],'accounting-only; no provider effects')
 def test_provider_call_never_referenced(self):
  source=(a.ROOT/'forecast-stopped-successor-v1/accounting_launch.py').read_text()
  self.assertNotIn('OneShotTransport',source);self.assertNotIn('google.auth',source)

if __name__=='__main__':unittest.main()
