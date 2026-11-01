import copy,unittest
import gate,dispatch_preflight,test_runner,test_stage_runner_integration
class T(unittest.TestCase):
 def setUp(self):
  admission,status,self.a,self.records,self.clock,k=test_runner.Tests().setup_case();self.a.s['source_attempts']=19
  self.source=test_stage_runner_integration.Source(self.a,self.clock)
  self.news=[e for e in admission['bundle']['tasks']['c_news']['evidence'] if e['kind']=='news']
  self.ops=[]
  for i in range(9):
   p={'api':'synthetic','path':'/markets','query':{'ticker':gate.TICKER}}
   t={'id':f'preflight-status-{i:02d}','category':'market','provider':'orthogonal','endpoint':'/v1/run','request_sha256':gate.sha(gate.canonical(p))}
   self.ops.append({'kind':'status_refresh','ticket':t,'payload':p})
  self.k={'news':self.news,'source_stage':self.source,'status_operations':self.ops,'source_transport':lambda *a:None,
   'decode_status':lambda *a:status,'verify_operation':lambda *a:True,'verify_news':lambda *a:True,'verify_status':lambda *a:True,
   'verify_source_stage':lambda *a:True,'record':k['record'],'clock':self.clock}
 def test_admits_with_individually_recorded_initial_status(self):
  r=dispatch_preflight.prepare(**self.k);self.assertEqual(r['schema'],'cpi-p1-prefreeze-v1');self.assertEqual(self.a.s['source_attempts'],20);self.assertEqual(len(r['remaining_status_operations']),8)
  self.assertEqual(set(r['admission']['bundle']['tasks']),{'c_news','b_news','c_no_news','b_no_news'})
 def test_no_event_no_source(self):
  self.k['news']=[];self.assertEqual(dispatch_preflight.prepare(**self.k)['status'],'pending');self.assertEqual(self.a.s['source_attempts'],19)
 def test_unverified_event_or_timestamp_cannot_trigger_source(self):
  self.k['verify_news']=lambda *a:False;self.assertEqual(dispatch_preflight.prepare(**self.k)['status'],'pending')
  self.k['verify_news']=lambda *a:True;self.k['news']=copy.deepcopy(self.news);self.k['news'][0]['published_at_utc']=gate.DURABLE
  self.assertEqual(dispatch_preflight.prepare(**self.k)['status'],'pending');self.assertEqual(self.a.s['source_attempts'],19)
 def test_expired_market_cannot_trigger_source(self):
  self.k['clock']=lambda:'2026-11-11T00:00:00+00:00'
  self.assertEqual(dispatch_preflight.prepare(**self.k)['reason'],'t1_outside_open_interval');self.assertEqual(self.a.s['source_attempts'],19)
 def test_oversized_operation_plan_and_duplicate_ids_rejected(self):
  self.a.s['source_attempts']=20
  with self.assertRaises(dispatch_preflight.Error):dispatch_preflight.prepare(**self.k)
  self.a.s['source_attempts']=19;self.k['status_operations'][1]['ticket']['id']=self.k['status_operations'][0]['ticket']['id']
  with self.assertRaises(Exception):dispatch_preflight.prepare(**self.k)
  self.assertEqual(self.a.s['source_attempts'],19)
if __name__=='__main__':unittest.main()
