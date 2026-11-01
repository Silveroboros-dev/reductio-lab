import copy,json,unittest
import gate,stages
class Account:
 def __init__(self):self.s={'stopped':0,'source_attempts':16}
 def summary(self):return copy.deepcopy(self.s)
 def stop(self,reason):self.s['stopped']=1
class Stage:
 def __init__(self,account,kind):self.account=account;self.kind=kind;self.effects={}
 def count(self,*args):return 'count'
 def generate(self,*args):return 'generation'
 def source(self,ident,provider,endpoint,request,ticket,transport):
  self.account.s['source_attempts']+=1;raw=b'{"success":true}'
  self.effects[ident]={'id':ident,'kind':'source','state':'succeeded','http_status':200,'request_hash':gate.sha(request),'response_hash':gate.sha(raw),'response':raw,'actual_micro':2000,'started_at_utc':'2026-10-29T12:30:03Z','completed_at_utc':'2026-10-29T12:30:04Z'}
  return raw
 def receipt(self,ident):return copy.deepcopy(self.effects[ident])
def op():
 payload={'api':'synthetic','path':'/test','body':{'ticker':gate.TICKER}}
 return {'kind':'status_refresh','ticket':{'id':'status-01','category':'market','provider':'orthogonal','endpoint':'/v1/run','request_sha256':gate.sha(gate.canonical(payload))},'payload':payload}
class T(unittest.TestCase):
 def test_separated_stages_same_budget(self):
  a=Account();model=Stage(a,'model');source=Stage(a,'source');f=stages.ModelFacade(model,source)
  self.assertEqual(f.count(),'count');self.assertEqual(f.generate(),'generation');self.assertEqual(f.summary()['source_attempts'],16)
  with self.assertRaises(stages.Error):stages.ModelFacade(model,Stage(Account(),'source'))
  with self.assertRaises(stages.Error):stages.ModelFacade(source,model)
 def test_exact_receipt_and_actual_local_timestamp(self):
  a=Account();s=Stage(a,'source');records=[]
  def decode(raw,receipt,op):return {'contract_id':gate.TICKER,'state':'active','quote':'SENTINEL'}
  f=stages.status_refresher(s,[op()],transport=lambda *a:None,decode=decode,verify_operation=lambda *a:True,record=lambda n,v:records.append((n,v)))
  result=f();self.assertEqual(result['observed_at_utc'],'2026-10-29T12:30:04Z');self.assertEqual(result['source_op_id'],'status-01')
  self.assertEqual(a.summary()['source_attempts'],17);self.assertEqual(records[0][1]['actual_micro'],2000)
  with self.assertRaises(stages.Error):f()
 def test_duplicate_and_unreviewed_operations_rejected(self):
  a=Account();s=Stage(a,'source')
  for ops,review in [([op(),op()],lambda *a:True),([op()],lambda *a:False)]:
   with self.assertRaises(stages.Error):stages.status_refresher(s,ops,transport=lambda *a:None,decode=lambda *a:None,verify_operation=review,record=lambda *a:None)
  self.assertEqual(a.summary()['source_attempts'],16)
 def test_wrong_response_hash_rejected(self):
  a=Account();s=Stage(a,'source');original=s.receipt
  def bad(ident):r=original(ident);r['response_hash']='wrong';return r
  s.receipt=bad
  f=stages.status_refresher(s,[op()],transport=lambda *a:None,decode=lambda *a:{'contract_id':gate.TICKER},verify_operation=lambda *a:True,record=lambda *a:None)
  with self.assertRaises(stages.Error):f()
if __name__=='__main__':unittest.main()
