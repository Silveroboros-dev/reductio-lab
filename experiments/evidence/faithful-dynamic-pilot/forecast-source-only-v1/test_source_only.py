import datetime as dt,tempfile,unittest
from pathlib import Path
from unittest import mock
import source_only as p
class Test(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory(dir='/private/tmp');self.root=Path(self.tmp.name).resolve();self.parent={'synthetic':'immutable','source_history':[{'id':'old','request_sha256':p.digest(p.canonical({'old':True}))}]}
  self.i=mock.patch.object(p,'inspect',return_value=self.parent);self.i.start();self.cc=mock.patch.object(p,'CLAIM',self.root/'claim');self.cc.start();self.ledger=None
  self.contract=self.root/'contract';c={'schema':'faithful-forecast-source-only-accounting-v1','status':'frozen','caps':p.CAPS,'parent':self.parent,'ledger_config':p.config(),'bridge_sha256':p.digest(p.r.read(Path(p.__file__))),'ledger_root':str(self.root/'ledger'),'scope':{'mode':'accounting_only','provider_effects':'forbidden','max_new_sources':14,'no_retry':True}}
  self.contract.write_bytes(p.canonical(c));self.sha=p.digest(self.contract.read_bytes())
 def tearDown(self):
  if self.ledger:self.ledger.close()
  self.i.stop();self.cc.stop();self.tmp.cleanup()
 def create(self):
  self.ledger=p.create(successor_root=str(self.root/'ledger'),contract_path=str(self.contract),expected_sha=self.sha,verify_challenge=lambda _:True);return self.ledger
 def op(self,ident='news1',payload=None):
  payload=payload or {'api':'serper','path':'/news','body':{'q':'new independent query'},'query':{}}
  ticket={'id':ident,'provider':'orthogonal','endpoint':'/v1/run','request_sha256':p.digest(p.canonical(payload)),'max_micro':150000,'evidence_sha256':'a'*64,'expires_utc':(dt.datetime.now(dt.timezone.utc)+dt.timedelta(minutes=10)).isoformat(),'category':'news','settlement':'orthogonal_price_cents'}
  return {'ticket':ticket,'payload':payload}
 def activate(self,ops=None):
  a=self.create();c={'schema':'faithful-forecast-source-only-run-v1','status':'frozen','caps':p.CAPS,'accounting_contract_sha256':self.sha,'ledger_root':str(a.root),'starting_usage':a.summary(),'model_reads':0,'no_retry':True,'operations':ops or [self.op()]};f=self.root/'source';f.write_bytes(p.canonical(c));h=p.digest(f.read_bytes());self.ledger=p.activate(a,source_contract_path=str(f),expected_sha=h,verify_challenge=lambda _:True,verify_ticket=lambda *_:True);return self.ledger
 def test_accounting_carry_forbidden(self):
  a=self.create();s=a.summary();self.assertEqual((s['exposure_micro'],s['generation_attempts'],s['count_attempts'],s['source_attempts']),(1882731,274,206,14));self.assertEqual(s['prior_http429c_charge_unknown_retained_micro'],86016)
  for fn in (a.count,a.generate,a.source):
   with self.assertRaises(p.Error):fn()
 def test_source_success_and_no_model(self):
  x=self.op();a=self.activate([x]);t=x['ticket'];a.source(t['id'],t['provider'],t['endpoint'],p.canonical(x['payload']),t,lambda *_:(200,b'{"success":true,"priceCents":0.2}'))
  self.assertEqual((a.summary()['exposure_micro'],a.summary()['source_attempts']),(1884731,15))
  with self.assertRaises(p.Error):a.source(t['id'],t['provider'],t['endpoint'],p.canonical(x['payload']),t,lambda *_:None)
  for fn in (a.count,a.generate):
   with self.assertRaises(p.Error):fn()
 def test_failed_http_retains_reserve_and_stops(self):
  x=self.op();a=self.activate([x]);t=x['ticket']
  with self.assertRaises(p.Stop):a.source(t['id'],t['provider'],t['endpoint'],p.canonical(x['payload']),t,lambda *_:(429,b'{}'))
  self.assertEqual((a.summary()['stopped'],a.summary()['exposure_micro'],a.summary()['source_attempts']),(1,2032731,15))
 def test_reject_prior_or_duplicated_request(self):
  old=self.op('old',{'unrelated':True})
  with self.assertRaises(p.Error):self.activate([old])
 def test_reject_same_body_twice(self):
  x=self.op();y=self.op('other',x['payload'])
  with self.assertRaises(p.Error):self.activate([x,y])
 def test_reject_no_challenge(self):
  with self.assertRaises(p.Error):p.create(successor_root=str(self.root/'ledger'),contract_path=str(self.contract),expected_sha=self.sha,verify_challenge=lambda _:False)
  self.assertFalse((self.root/'ledger').exists())
if __name__=='__main__':unittest.main()
