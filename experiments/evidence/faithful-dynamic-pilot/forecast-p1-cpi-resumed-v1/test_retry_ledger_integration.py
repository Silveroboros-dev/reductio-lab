import copy,json,sys,tempfile,unittest
from pathlib import Path
from datetime import timedelta
sys.path.insert(0,str(Path(__file__).resolve().parent.parent/'forecast-p1-budget-successor-v1'))
import p1_retry as book
import gate,runner_retry,test_runner

class Wrapper:
 def __init__(self,b):self.b=b
 def summary(self):
  x=self.b.summary();x['source_attempts']+=16;return x
 def stop(self,reason):return self.b.stop(reason)
 def count_attempt(self,*a):return self.b.count_attempt(*a)
 def generate_attempt(self,*a):return self.b.generate_attempt(*a)
class T(unittest.TestCase):
 def test_real_retry_ledger_with_synthetic_transport_and_refresh(self):
  tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup)
  base=book.RetryBase(str(Path(tmp.name).resolve()/'db'),book.config(),create=True);self.addCleanup(base.close)
  wrap=Wrapper(base);helper=test_runner.Tests();admission,status,unused,records,clock,k=helper.setup_case();calls=[];fail={'count':True,'generation':True}
  def transport(provider,endpoint,raw):
   kind='count' if endpoint=='countTokens' else 'generation';calls.append((kind,gate.sha(raw)))
   if fail[kind]:fail[kind]=False;return 429,json.dumps({'error':{'code':429,'status':'RESOURCE_EXHAUSTED'}}).encode()
   if kind=='count':return 200,json.dumps({'totalTokens':100}).encode()
   req=json.loads(raw);x=json.loads(req['contents'][0]['parts'][0]['text']);stage=x['stage']
   if stage=='selection':v={'alternatives':[['rule:primary']]}
   elif stage=='inference':v={'conclusion':'Synthetic local inference.'}
   elif stage=='halter':v={'sufficient':True}
   elif stage=='value':v={'score':.5}
   else:v={'probability_yes':.5,'explanation':'Synthetic forecast.','citations':['rule:primary'],'assumptions':[],'counterevidence':[]}
   payload={'modelVersion':'gemini-3.8-flash','usageMetadata':{'promptTokenCount':100,'totalTokenCount':200},'candidates':[{'finishReason':'STOP','content':{'parts':[{'text':json.dumps(v)}]}}]}
   return 200,json.dumps(payload).encode()
  source_seq=[0]
  def refresh():
   source_seq[0]+=1;ident='synthetic-status-'+str(source_seq[0]);req=b'{"test":true}';proof='a'*64
   raw=base._execute(ident,'source','orthogonal','/v1/run',req,150000,proof,lambda *a:(200,b'{"priceCents":0.2,"success":true}'))
   base._settle(ident,2000)
   v=copy.deepcopy(status);v.update(observed_at_utc=clock(),captured_at_utc=clock(),quote='HIDDEN');return v
  def slp(delay):clock.t+=timedelta(seconds=delay)
  k.update(ledger=wrap,transport=transport,refresh_status=refresh,confirmed429=book.Confirmed429,rate_limit_exhausted=book.RateLimitExhausted,sleep=slp,jitter=lambda:.5)
  out=runner_retry.run(admission,status,**k)
  self.assertEqual(out['schema'],'resumed-cpi-p1-summary-v1');self.assertEqual(base.summary()['stopped'],0)
  self.assertEqual(base.summary()['generation_attempts'],320);self.assertEqual(base.summary()['count_attempts'],249)
  self.assertEqual(base.db.execute("select count(*) from effects where http_status=429").fetchone()[0],2)
  self.assertEqual(base.db.execute("select count(*) from effects where instr(id,'~retry')>0").fetchone()[0],2)
  self.assertEqual(calls[0][1],calls[1][1]);self.assertEqual(calls[2][1],calls[3][1])
  self.assertGreaterEqual(source_seq[0],2)
if __name__=='__main__':unittest.main()
