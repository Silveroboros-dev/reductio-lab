import copy,unittest
import gate,runner,stages,test_runner

class Model:
 kind='model'
 def __init__(self,a):self.account=a
 def count(self,*args):return self.account.count(*args)
 def generate(self,*args):return self.account.generate(*args)
class Source:
 kind='source'
 def __init__(self,a,clock):self.account=a;self.clock=clock;self.effects={}
 def source(self,ident,provider,endpoint,request,ticket,transport):
  self.account.s['source_attempts']+=1;raw=b'{"success":true,"market":{"status":"active"}}';when=self.clock()
  self.effects[ident]={'id':ident,'kind':'source','state':'succeeded','http_status':200,'request_hash':gate.sha(request),'response_hash':gate.sha(raw),'response':raw,'actual_micro':2000,'started_at_utc':when,'completed_at_utc':when}
  return raw
 def receipt(self,ident):return copy.deepcopy(self.effects[ident])
class T(unittest.TestCase):
 def test_full_injected_stage_composition(self):
  tests=test_runner.Tests();a0,status,account,records,clock,k=tests.setup_case()
  source=Source(account,clock);facade=stages.ModelFacade(Model(account),source)
  operations=[]
  for i in range(12):
   payload={'api':'synthetic','path':'/markets','query':{'ticker':gate.TICKER}}
   ticket={'id':f'cpi-status-{i:02d}','category':'market','provider':'orthogonal','endpoint':'/v1/run','request_sha256':gate.sha(gate.canonical(payload))}
   operations.append({'kind':'status_refresh','ticket':ticket,'payload':payload})
  def decode(raw,receipt,op):return {**status,'quote':'HIDDEN-NEW-QUOTE'}
  refresh=stages.status_refresher(source,operations,transport=lambda *a:None,decode=decode,verify_operation=lambda *a:True,record=k['record'])
  k.update(ledger=facade,refresh_status=refresh)
  result=runner.run(a0,status,**k)
  self.assertEqual(result['schema'],'resumed-cpi-p1-summary-v1')
  self.assertGreaterEqual(len(source.effects),2);self.assertEqual(account.s['source_attempts'],16+len(source.effects))
  self.assertNotIn('HIDDEN-NEW-QUOTE',str(account.requests))
  self.assertEqual(len([n for n,v in records if n=='p1-frozen']),1)
if __name__=='__main__':unittest.main()
