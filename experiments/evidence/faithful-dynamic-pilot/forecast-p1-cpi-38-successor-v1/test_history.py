import json,sqlite3,tempfile,unittest
from pathlib import Path
import history
class T(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.p=Path(self.tmp.name).resolve()/'parent.sqlite3';db=sqlite3.connect(self.p)
  db.execute('create table run(stopped,exposure_micro,generation_attempts,count_attempts,source_attempts)');db.execute('insert into run values(1,2,3,4,5)')
  db.execute('create table effects(id,kind,state,http_status,request,request_hash,response,response_hash,actual_micro,related_id)');db.execute('create table run_events(event,reason)');db.commit();db.close();self.req={'a':1}
 def add(self,ident,status=200,state='succeeded',body=b'{}',cost=0,request=None,related=None,confirm=False):
  req=history.canonical(self.req if request is None else request);db=sqlite3.connect(self.p);db.execute('insert into effects values(?,?,?,?,?,?,?,?,?,?)',(ident,ident.split(':')[0],state,status,req,history.sha(req),body,history.sha(body) if body else None,cost,related))
  if confirm:db.execute('insert into run_events values(?,?)',('confirmed_model_429',ident))
  db.commit();db.close()
 def h(self):return history.History(self.p,history.sha(self.p.read_bytes()))
 def test_success_reused_but_changed_request_denied(self):
  i='count:p1:case-02:no_news:b:01';self.add(i,body=b'{"totalTokens":4}');h=self.h();self.assertEqual(h.inspect(i,self.req)['classification'],'success')
  with self.assertRaises(history.Error):h.inspect(i,{'a':2})
 def test_confirmed_429_attempts_cannot_reset(self):
  i='generation:p1:case-02:news:c:01';self.add(i,status=429,body=b'{"error":{"code":429,"status":"RESOURCE_EXHAUSTED"}}',cost=None,confirm=True);h=self.h();self.assertEqual(h.inspect(i,self.req)['attempts'],1);self.assertEqual(h.inspect(i,self.req)['classification'],'confirmed_429')
 def test_unconfirmed_429_and_retry_after_success_rejected(self):
  i='generation:p1:case-02:news:c:01';self.add(i,status=429,body=b'{"error":{"code":429,"status":"RESOURCE_EXHAUSTED"}}',cost=None)
  with self.assertRaises(history.Error):self.h()
 def test_unknown_not_retried(self):
  i='generation:p1:case-02:news:c:01';self.add(i,status=None,state='uncertain',body=None,cost=None);self.assertEqual(self.h().inspect(i,self.req)['classification'],'unknown')
 def test_live_ledger_not_admitted(self):
  db=sqlite3.connect(self.p);db.execute('update run set stopped=0');db.commit();db.close()
  with self.assertRaises(history.Error):self.h()
if __name__=='__main__':unittest.main()
