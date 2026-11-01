"""Offline transport fixture for the hard-run ledger, with no provider calls."""
import json
from faithful_v3.prompts import build_request
from hard_si.runtime import Adapter
from hard_si.test_offline import EffectChecks
from research.retry_facade import RetryFacade

class HardRetryChecks(EffectChecks):
 def test_confirmed_generation_429_is_retried_once_identically(self):
  seen=[]
  def transport(provider,endpoint,raw):
   seen.append((endpoint,raw))
   if endpoint=='countTokens':return 200,b'{"totalTokens":100}'
   if sum(1 for name,_ in seen if name=='gemini-3.8-flash@global')==1:
    return 429,b'{"error":{"code":429,"status":"RESOURCE_EXHAUSTED"}}'
   return 200,json.dumps({'modelVersion':'gemini-3.8-flash','usageMetadata':{'promptTokenCount':100,'totalTokenCount':110},'candidates':[{'finishReason':'STOP','content':{'parts':[{'text':'{"answer":"fixture"}'}]}}]}).encode()
  a=Adapter(RetryFacade(self.base,self.retry,sleep=lambda _:None),transport)
  a.complete(build_request('baseline_initial',{'question':'fixture'}),'c'*64+':B:001','MEDIUM')
  self.assertEqual([name for name,_ in seen],['countTokens','gemini-3.8-flash@global','gemini-3.8-flash@global'])
  self.assertEqual(seen[0][1],seen[1][1]);self.assertEqual(seen[1][1],seen[2][1])
  rows=self.base.db.execute('select kind,http_status,actual_micro from effects order by rowid').fetchall()
  self.assertEqual(rows,[('count',200,0),('generation',429,0),('generation',200,225)])
  self.assertFalse(self.base.summary()['stopped'])
