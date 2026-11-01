import copy,json,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parent))
import dispatch as d

class VerifyTest(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.base=Path(self.tmp.name).resolve()
  self.bundle={'test':'bundle'};self.usage={'test':'usage'}
  self.c={'schema':'faithful-forecast-p0-model-contract-v1','status':'frozen','caps':d.CAPS,
   'ledger_root':str(d.LEDGER),'source_reads':0,'accounting_contract_sha256':d.ACCOUNTING_SHA,
   'accounting_receipt_sha256':d.sha(b'fake accounting'),'starting_usage':self.usage,
   'execution_context':{'cwd':str(d.ROOT),'output_root':str(d.OUTPUT)},
   'case_binding':{'bundle_sha256':d.sha(d.canonical(self.bundle))},
   'limits':{'arms':['c','b'],'max_calls_per_arm':23,'match':'B gets only C call count',
    'model':'gemini-3.8-flash','location':'global','max_output_tokens':4096,'no_source':True,
    'no_p1':True,'no_retry':True,'strict_completion_before_utc':d.DEADLINE},'component_bindings':{}}
 def tearDown(self):self.tmp.cleanup()
 def run_verify(self,c,mutate=lambda x:x):
  contract=d.canonical(c);digest=d.sha(contract)
  packet={'schema_version':'eval_contract_challenge_packet_v1','overall_state':'ready',
   'witness':{'identity':'p0_model_witness','mode':'read_only_offline'},'challenged_contract':{'raw_sha256':digest},
   'context_binding':{'execution_context':c['execution_context'],'case_binding':c['case_binding'],
    'limits':c['limits'],'code_bindings_at_inspection':{}}}
  packet=mutate(packet);packet['internal_digest']=d.sha(d.canonical(packet));pb=d.canonical(packet)
  receipt=d.canonical({'packet_raw_sha256':d.sha(pb),'packet_byte_count':len(pb),'packet_internal_digest':packet['internal_digest'],'state':'ready'})
  cp=self.base/'contract';pp=self.base/'packet';rp=self.base/'receipt';ap=self.base/'accounting'
  cp.write_bytes(contract);pp.write_bytes(pb);rp.write_bytes(receipt);ap.write_bytes(b'fake accounting')
  with patch.object(d,'CONTRACT',cp),patch.object(d,'PACKET',pp),patch.object(d,'RECEIPT',rp),patch.object(d,'ACCOUNTING_RECEIPT',ap),patch.object(d,'components',return_value={}),patch.object(d,'accounting_evidence',return_value={'ledger':self.usage}),patch.object(d.case_binding,'prepare',return_value=self.bundle):
   return d.verify(digest)
 def test_challenged_binding(self):
  self.assertEqual(self.run_verify(self.c)[0],self.c)
 def test_wrong_witness_and_source_admission_denied(self):
  with self.assertRaises(d.Error):self.run_verify(self.c,lambda x:dict(x,witness={'identity':'other','mode':'read_only_offline'}))
  bad=copy.deepcopy(self.c);bad['source_reads']=1
  with self.assertRaises(d.Error):self.run_verify(bad)
 def test_changed_bundle_denied(self):
  bad=copy.deepcopy(self.c);bad['case_binding']['bundle_sha256']='0'*64
  with self.assertRaises(d.Error):self.run_verify(bad)
if __name__=='__main__':unittest.main()
