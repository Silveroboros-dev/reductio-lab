import copy,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parent))
import dispatch_final_two as d

class VerifyTest(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name).resolve()
  self.bundle={'prepared':[{'case':{'case_id':v}} for v in d.rem.EXPECTED]};self.info={'bundle_sha256':'a'*64};self.usage={'test':'usage'}
  self.c={'schema':'faithful-forecast-post429b-model-v1','status':'frozen','caps':d.CAPS,'ledger_root':str(d.LEDGER),
   'accounting_contract_sha256':d.ACCOUNT_SHA,'accounting_receipt_sha256':d.sha(b'accounting'),'starting_usage':self.usage,
   'case_ids':list(d.rem.EXPECTED),'source_reads':0,'no_retry':True,'pacing_min_seconds':20,'pacing_scope':'all_provider_calls',
   'execution_context':{'cwd':str(d.ROOT),'output_root':str(d.OUTPUT)},'original_binding':self.info,
   'limits':{'arms':['c','b'],'max_calls_per_arm':23,'match':'B gets only C call count','model':'gemini-3.8-flash',
    'location':'global','max_output_tokens':4096,'no_source':True,'no_p1':True,'strict_completion_before_utc':d.DEADLINE,'first_provider_not_before_utc':d.NOT_BEFORE,'previous_429_started_utc':d.FAILED_START,'previous_429_completed_utc':d.FAILED_END},'component_bindings':{}}
 def tearDown(self):self.tmp.cleanup()
 def check(self,c,mutate=lambda x:x):
  cr=d.canonical(c);sha=d.sha(cr)
  packet={'schema_version':'eval_contract_challenge_packet_v1','overall_state':'ready',
   'witness':{'identity':'p0_final_two_witness','mode':'read_only_offline'},'challenged_contract':{'raw_sha256':sha},
   'context_binding':{'execution_context':c['execution_context'],'original_binding':c['original_binding'],
    'limits':c['limits'],'code_bindings_at_inspection':{}}}
  packet=mutate(packet);packet['internal_digest']=d.sha(d.canonical(packet));pb=d.canonical(packet)
  rb=d.canonical({'packet_raw_sha256':d.sha(pb),'packet_byte_count':len(pb),'packet_internal_digest':packet['internal_digest'],'state':'ready'})
  for name,data in [('contract',cr),('packet',pb),('receipt',rb),('account',b'accounting')]:(self.root/name).write_bytes(data)
  with patch.object(d,'CONTRACT',self.root/'contract'),patch.object(d,'PACKET',self.root/'packet'),patch.object(d,'RECEIPT',self.root/'receipt'),patch.object(d,'ACCOUNT_LOCAL',self.root/'account'),patch.object(d,'components',return_value={}),patch.object(d,'accounting_evidence',return_value={'ledger':self.usage}),patch.object(d,'verify_last_429_time'),patch.object(d.rem,'build',return_value=dict(self.info,bundle=self.bundle)):
   return d.verify(sha)
 def test_expected_scope(self):self.assertEqual(self.check(self.c)[0],self.c)
 def test_reject_case01_and_retry(self):
  x=copy.deepcopy(self.c);x['case_ids'][0]='case-02'
  with self.assertRaises(d.Error):self.check(x)
  x=copy.deepcopy(self.c);x['no_retry']=False
  with self.assertRaises(d.Error):self.check(x)
  x=copy.deepcopy(self.c);x['pacing_min_seconds']=19
  with self.assertRaises(d.Error):self.check(x)
 def test_reject_unreviewed_witness(self):
  with self.assertRaises(d.Error):self.check(self.c,lambda x:dict(x,witness={'identity':'other','mode':'read_only_offline'}))
if __name__=='__main__':unittest.main()
