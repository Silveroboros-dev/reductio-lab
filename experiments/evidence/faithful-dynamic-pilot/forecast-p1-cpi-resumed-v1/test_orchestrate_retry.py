import copy,unittest
from datetime import timedelta
import gate,orchestrate_retry,test_runner,test_runner_retry,test_stage_runner_integration
class Model:
 kind='model'
 def __init__(self,a):self.account=a
 def count_attempt(self,*a):return self.account.count_attempt(*a)
 def generate_attempt(self,*a):return self.account.generate_attempt(*a)
class T(unittest.TestCase):
 def test_full_staged_retry_and_status_refresh(self):
  helper=test_runner.Tests();admission,status,unused,records,clock,k=helper.setup_case();account=test_runner_retry.RetryLedger('recover')
  source=test_stage_runner_integration.Source(account,clock);model=Model(account);ops=[]
  for i in range(12):
   payload={'api':'synthetic','path':'/markets','query':{'ticker':gate.TICKER}}
   ticket={'id':f'cpi-status-{i:02d}','category':'market','provider':'orthogonal','endpoint':'/v1/run','request_sha256':gate.sha(gate.canonical(payload))}
   ops.append({'kind':'status_refresh','ticket':ticket,'payload':payload})
  news=[x for x in admission['bundle']['tasks']['c_news']['evidence'] if x['kind']=='news'];delays=[]
  def sleep(delay):delays.append(delay);clock.t+=timedelta(seconds=delay)
  out=orchestrate_retry.run(news=news,initial_status=status,t1=admission['bundle']['t1'],model_stage=model,source_stage=source,status_operations=ops,
   model_transport=lambda *a:None,source_transport=lambda *a:None,decode_status=lambda raw,receipt,op:{**status,'quote':'SECRET-NEW'},
   verify_operation=lambda *a:True,verify_news=lambda *a:True,verify_status=lambda *a:True,verify_admission=lambda *a:True,verify_ledger=lambda *a:True,
   record=k['record'],clock=clock,pacer=k['pacer'],confirmed429=test_runner_retry.Confirmed429,rate_limit_exhausted=test_runner_retry.RateLimitExhausted,sleep=sleep,jitter=lambda:.5)
  self.assertEqual(out['schema'],'resumed-cpi-p1-summary-v1');self.assertEqual(delays,[1.5,1.5]);self.assertEqual(account.extra,2)
  self.assertNotIn('SECRET-NEW',str(account.requests));self.assertGreaterEqual(len(source.effects),2)
if __name__=='__main__':unittest.main()
