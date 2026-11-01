import copy,json,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parent))
import launcher

class InputTest(unittest.TestCase):
 def test_real_saved_projection_preserves_provenance_and_no_market_leads(self):
  rows=launcher.tasks('2026-10-29T10:40:00Z')
  self.assertEqual([r['case_id'] for r in rows],['case-01','case-02','case-03','case-04'])
  self.assertEqual([len(r['task']['evidence']) for r in rows],[2,2,2,2])
  self.assertEqual(rows[0]['task']['thought_origin'],'prior_user_approved')
  self.assertTrue(all(r['task']['thought_origin']=='assistant_proposal_unaccepted' for r in rows[1:]))
  self.assertTrue(all(r['task']['market_leads']==[] for r in rows))
  self.assertIn('search_snippet_unverified',rows[0]['task']['evidence'][0]['source'])
  self.assertIn('factual correctness not independently verified',rows[0]['task']['evidence'][0]['source'])
 def test_cutoff_before_capture_fails_closed(self):
  with self.assertRaises(launcher.Error):launcher.tasks('2026-10-29T10:00:00Z')
 def test_known_title_or_id_in_projection_fails(self):
  with patch.object(launcher,'FORBIDDEN',('OPEC+',)):
   with self.assertRaises(launcher.Error):launcher.tasks('2026-10-29T10:40:00Z')

class VerifyTest(unittest.TestCase):
 def _write(self,p,v):p.write_bytes(launcher.canonical(v))
 def test_exact_ready_challenge_and_mismatch_are_detected_offline(self):
  with tempfile.TemporaryDirectory() as temp:
   # resolve macOS /var -> /private/var before using strict absolute paths
   d=Path(temp).resolve();cp=d/'contract.json';pp=d/'packet.json';rp=d/'receipt.json'
   rows=[{'task_sha256':'a'*64}];source={'source_contract_sha256':'b'*64}
   c={'schema':'faithful-forecast-seed-model-contract-v1','status':'frozen',
      'caps':{'total_usd_micro':60000000,'total_generation_attempts':835,'total_count_attempts':767,'total_source_attempts':28},
      'scope':{'cases':4,'slots':8,'model':'gemini-3.8-flash','location':'global','max_calls_per_slot':6,
        'timeout_seconds_per_io':420,'retries':0,'source_reads':0,'seed_only':True,'human_acceptance_or_market_selection':False},
      'component_bindings':{},'task_bindings':rows,'source_binding':source,
      'as_of_utc':'2026-10-29T10:35:00Z','execution_context':{'cwd':str(Path.cwd().resolve()),'artifact_root':str(launcher.ROOT)}}
   self._write(cp,c);cr=cp.read_bytes()
   p={'schema_version':'eval_contract_challenge_packet_v1','overall_state':'ready',
      'witness':{'identity':'seed_model_witness','mode':'read_only_offline'},
      'challenged_contract':{'raw_sha256':launcher.sha(cr)},
      'context_binding':{'code_bindings_at_inspection':{},'execution_context':c['execution_context'],
                         'task_bindings':rows,'source_binding':source}}
   p['internal_digest']=launcher.sha(launcher.canonical(p));self._write(pp,p);pr=pp.read_bytes()
   r={'packet_raw_sha256':launcher.sha(pr),'packet_byte_count':len(pr),'packet_internal_digest':p['internal_digest'],'state':'ready'}
   self._write(rp,r)
   with patch.object(launcher,'components',return_value={}),patch.object(launcher,'tasks',return_value=rows):
    self.assertEqual(launcher.verify(cp,pp,rp,launcher.sha(cr))['contract'],c)
    p['overall_state']='blocked';self._write(pp,p)
    with self.assertRaises(launcher.Error):launcher.verify(cp,pp,rp,launcher.sha(cr))

if __name__=='__main__':unittest.main()
