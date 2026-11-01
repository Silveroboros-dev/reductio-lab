import json,sqlite3,tempfile,unittest
from pathlib import Path
import gate,conditional_capture,venue_capture,venue_recovery
class T(unittest.TestCase):
 def test_successor_receipt_bound_status(self):
  case=gate.verify_p0()['prepared']['case'];contract=json.loads(conditional_capture.CONTRACT.read_bytes());op=next(x for x in contract['operations'] if x['ticket']['id']=='p1-cpi-status-04');req=gate.canonical(op['payload'])
  market={'ticker':gate.TICKER,'status':'active','result':'','rules_primary':case['rules_primary'],'rules_secondary':case['rules_secondary'],'yes_bid_dollars':'0.99'}
  raw=gate.canonical({'success':True,'data':{'markets':[market]}});at='2026-10-29T13:00:00Z'
  with tempfile.TemporaryDirectory() as td:
   dbp=Path(td)/'ledger.sqlite3';db=sqlite3.connect(dbp);db.execute('create table effects(id,kind,provider,endpoint,state,http_status,request,request_hash,response,response_hash,actual_micro,completed_at_utc)');db.execute('insert into effects values(?,?,?,?,?,?,?,?,?,?,?,?)',('p1-cpi-status-04','source','orthogonal','/v1/run','succeeded',200,req,gate.sha(req),raw,gate.sha(raw),0,at));db.commit();db.close()
   s=venue_capture.extract(raw);s.update(source_op_id='p1-cpi-status-04',response_sha256=gate.sha(raw),observed_at_utc=at,captured_at_utc=at)
   self.assertTrue(venue_recovery.verify_status(s,case,at,recovery_db=dbp));self.assertNotIn('0.99',str(s));s['response_sha256']='a'*64;self.assertFalse(venue_recovery.verify_status(s,case,at,recovery_db=dbp))
if __name__=='__main__':unittest.main()
