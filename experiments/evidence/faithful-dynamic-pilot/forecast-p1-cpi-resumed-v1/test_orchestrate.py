import copy,unittest
import gate,orchestrate,test_runner,test_stage_runner_integration

class T(unittest.TestCase):
 def fixture(self):
  test=test_runner.Tests();admission,status,account,records,clock,kwargs=test.setup_case()
  source=test_stage_runner_integration.Source(account,clock);model=test_stage_runner_integration.Model(account)
  ops=[]
  for i in range(12):
   payload={'api':'synthetic','path':'/markets','query':{'ticker':gate.TICKER}}
   ticket={'id':f'cpi-status-{i:02d}','category':'market','provider':'orthogonal','endpoint':'/v1/run','request_sha256':gate.sha(gate.canonical(payload))}
   ops.append({'kind':'status_refresh','ticket':ticket,'payload':payload})
  cpi_news=[x for x in admission['bundle']['tasks']['c_news']['evidence'] if x['kind']=='news']
  result={'news':cpi_news,'initial_status':status,'t1':admission['bundle']['t1'],'model_stage':model,'source_stage':source,'status_operations':ops,
   'model_transport':lambda *a:None,'source_transport':lambda *a:None,'decode_status':lambda raw,receipt,op:{**status,'quote':'NEW-SECRET'},
   'verify_operation':lambda *a:True,'verify_news':lambda *a:True,'verify_status':lambda *a:True,'verify_admission':lambda *a:True,'verify_ledger':lambda *a:True,
   'record':kwargs['record'],'clock':clock,'pacer':kwargs['pacer']}
  return result,account,source,records
 def test_full_mock_orchestration(self):
  kwargs,a,s,records=self.fixture();out=orchestrate.run(**kwargs)
  self.assertEqual(out['schema'],'resumed-cpi-p1-summary-v1');self.assertEqual(a.s['generation_attempts'],319)
  self.assertNotIn('NEW-SECRET',str(a.requests));self.assertGreaterEqual(len(s.effects),2)
 def test_no_event_means_no_effects(self):
  kwargs,a,s,_=self.fixture();kwargs['news']=[];self.assertEqual(orchestrate.run(**kwargs)['status'],'pending')
  self.assertEqual(a.s['generation_attempts'],299);self.assertEqual(len(s.effects),0)
 def test_no_frozen_review_means_no_effects(self):
  kwargs,a,s,_=self.fixture();kwargs['verify_admission']=lambda *a:False
  with self.assertRaises(orchestrate.Error):orchestrate.run(**kwargs)
  self.assertEqual(a.s['generation_attempts'],299);self.assertEqual(len(s.effects),0)
if __name__=='__main__':unittest.main()
