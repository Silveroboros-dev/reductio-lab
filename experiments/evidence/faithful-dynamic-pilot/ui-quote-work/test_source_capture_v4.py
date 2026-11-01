import datetime as dt
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import httpx
ROOT=Path(__file__).resolve().parent.parent
for d in ('budget-v2','source-adapter','source-successor','ui-quote-work'):
    sys.path.insert(0,str(ROOT/d))
import bridge, serper, source_capture_v4 as sc
from ledger import Ledger
NOW=dt.datetime(2026,10,29,9,23,0,tzinfo=dt.timezone.utc)
class FrozenDatetime(dt.datetime):
    @classmethod
    def now(cls,tz=None): return NOW if tz else NOW.replace(tzinfo=None)
def encode(x): return json.dumps(x,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()
def review(packet,receipt,contract): return json.loads(packet).get('fixture') is True

a=serper.canonical
class CaptureV4(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name).resolve()
        self.config=json.loads((ROOT/'live-ledger-successor-contract-20261029.json').read_bytes())
        base=Ledger(str(self.root/'ledger'),self.config,create=True)
        groups=json.loads((ROOT/'dataset-draft-20261029/draft.json').read_bytes())['groups']
        first=serper.build_request(groups[0]['news_action_draft']['request_body']['q'],3)
        prior_raw=encode({'success':True,'priceCents':0.2,'requestId':'prior', 'data':{'searchParameters':{'q':groups[0]['news_action_draft']['request_body']['q'],'num':10,'page':1},'news':[{'title':str(i)} for i in range(10)]}})
        self.prior={'state':'succeeded','http_status':200,'actual_micro':2000,'request':first,'request_hash':sc.sha(first),'response':prior_raw,'response_hash':sc.sha(prior_raw)}
        self.snapshot={'previous_exposure_micro':723593,'previous_source_attempts':1,'previous_generation_attempts':79,'previous_count_attempts':11,'previous_source_actual_micro':2000,'previous_source_id':'source:case-01:serper','previous_source_request_sha256':sc.sha(first),'previous_source_response_sha256':sc.sha(prior_raw),'remaining_source_ids':[f'source:case-{n:02}:serper' for n in range(2,9)],'remaining_source_request_sha256':{}}
        self.req=[]
        for g in groups[1:]:
            n=g['news_action_draft'];b=n['request_body']; raw=serper.build_request(b['q'],b['num']);h=sc.sha(raw)
            self.snapshot['remaining_source_request_sha256'][f"source:{g['case_id']}:serper"]=h
            self.req.append({'case_id':g['case_id'],'event_group_id':g['event_group_id'],'api':'serper','path':'/news','body':b,'relevance_gap':n['predeclared_relevance_gap'],'request_sha256':h})
        self.ledger=bridge.PhaseLedger(base,(),self.snapshot,bridge.CLAIM_PATH,b'fixture')
        self.ledger.verify_predecessor=lambda:self.snapshot.copy()
        self.ledger.receipt=lambda op: self.prior if op=='source:case-01:serper' else base.receipt(op)
        bind={p:sc.sha((ROOT/p).read_bytes()) for p in sc.REQUIRED_COMPONENTS}
        context={'artifact_root':str(ROOT),'ledger_root':str(self.ledger.root.resolve()),'output_dir':str(self.root/'out'),'cwd':str(Path.cwd().resolve()),'claim_path':str(bridge.CLAIM_PATH)}
        policy={'selection':'provider order, first up to 3; content-independent','max_returned':100,'request_num':3,'date_policy':'preserve verbatim','amendment':'after observing provider returned 10 for num=3'}
        self.contract={'schema':sc.SCHEMA,'status':'frozen','execution_mode':'offline_fixture','component_bindings':bind,'execution_context':context,'predecessor_binding':self.snapshot,'projection_policy':policy,'known_prior_exposure_micro_usd':721593,'total_cap_micro_usd':40000000,'source_budget_micro_usd':5000000,'per_source_reserve_micro_usd':250000,'ui_price_micro_usd':2000,'source_attempts':7,'max_source_attempts':18,'max_generation_attempts_including_prior':835,'max_countTokens_including_prior':767,'model':'gemini-3.8-flash','location':'global','input_rate_per_million_usd':1.5,'output_rate_per_million_usd':7.5,'input_limit':16384,'max_output_tokens':4096,'output_reserve':8192,'retry_policy':'none','uncertain_policy':'stop and retain reserve','ui_price_evidence_sha256':sc.PRICE_SHA,'draft_sha256':sc.DRAFT_SHA,'source_requests':self.req}
        self.sent=[]; self.project_calls=[];self.token_calls=[];self.save()
    def tearDown(self): self.ledger.close();self.tmp.cleanup()
    def save(self):
        self.cp=self.root/'contract';self.cp.write_bytes(encode(self.contract));code={p:{'sha256':h,'size':len((ROOT/p).read_bytes())} for p,h in self.contract['component_bindings'].items()}
        context={'code_bindings_at_inspection':code,'ledger_contract_sha256':sc.sha(a(self.config)),'execution_context':self.contract['execution_context'],'predecessor_binding':self.contract['predecessor_binding'],'projection_policy':self.contract['projection_policy']}
        packet={'schema_version':'eval_contract_challenge_packet_v1','overall_state':'ready','fixture':True,'challenged_contract':{'raw_sha256':sc.sha(self.cp.read_bytes())},'witness':{'mode':'read_only_offline'},'context_binding':context};packet['internal_digest']=sc.sha(a(packet))
        self.ch=self.root/'challenge';self.ch.write_bytes(encode(packet));self.rp=self.root/'receipt';b=self.ch.read_bytes();self.rp.write_bytes(encode({'packet_raw_sha256':sc.sha(b),'packet_byte_count':len(b),'packet_internal_digest':packet['internal_digest'],'state':'ready'}))
    def handler(self,req):
        self.sent.append(req)
        return httpx.Response(200,stream=httpx.ByteStream(encode({'success':True,'priceCents':0.2,'requestId':f'fixture-{len(self.sent)}','data':{'news':[{'title':str(i)} for i in range(10)]}})))
    def project(self):self.project_calls.append(1);return 'fixture-project'
    def token(self,p):self.token_calls.append(p);return 'fixture-token'
    def go(self,handler=None):
        with patch('ledger.dt',SimpleNamespace(datetime=FrozenDatetime,timezone=dt.timezone)):
            return sc.execute(self.cp,self.ch,self.rp,self.root/'out',ledger=self.ledger,verify_challenge=review,verify_ui=lambda raw:sc.sha(raw)==sc.PRICE_SHA,project_id_provider=self.project,token_provider=self.token,fixture_http_transport=httpx.MockTransport(handler or self.handler),now=NOW)
    def test_seven_only_and_projection(self):
        result=self.go();self.assertEqual(len(result),7);self.assertEqual(len(self.sent),7)
        self.assertEqual(self.ledger.summary()['source_attempts'],8)
        self.assertEqual(self.ledger.summary()['exposure_micro'],723593+14000)
        x=json.loads((self.root/'out/case-02.json').read_bytes())['projection'];self.assertEqual((x['provider_returned_count'],x['selected_count']),(10,3))
    def test_missing_news_stops_before_second_call(self):
        def bad(req):
            self.sent.append(req);return httpx.Response(200,stream=httpx.ByteStream(encode({'success':True,'priceCents':0.2,'requestId':'r1','data':{}})))
        with self.assertRaises(Exception): self.go(bad)
        self.assertEqual(len(self.sent),1);self.assertEqual(self.ledger.summary()['stopped'],1)
        self.assertEqual(self.ledger.receipt('source:case-02:serper')['actual_micro'],2000)
    def test_predecessor_change_and_policy_drift_fail_before_credentials(self):
        self.snapshot['previous_source_actual_micro']=3000
        with self.assertRaises(sc.PreflightError): self.go()
        self.assertEqual(self.project_calls,[]);self.assertEqual(self.sent,[])
    def test_challenge_mismatch_fails_before_credentials(self):
        packet=json.loads(self.ch.read_bytes());packet['overall_state']='blocked';self.ch.write_bytes(encode(packet))
        with self.assertRaises(sc.PreflightError): self.go()
        self.assertEqual(self.project_calls,[]);self.assertEqual(self.sent,[])
    def test_timeout_keeps_reserve_and_stops(self):
        def bad(req): self.sent.append(req);raise httpx.ReadTimeout('fixture timeout')
        with self.assertRaises(Exception): self.go(bad)
        self.assertEqual(len(self.sent),1);self.assertEqual(self.ledger.summary()['stopped'],1)
        self.assertEqual(self.ledger.receipt('source:case-02:serper')['state'],'uncertain')
        self.assertEqual(self.ledger.summary()['exposure_micro'],723593+250000)
    def test_price_drift_records_actual_and_stops(self):
        def bad(req):
            self.sent.append(req);return httpx.Response(200,stream=httpx.ByteStream(encode({'success':True,'priceCents':0.3,'requestId':'r1','data':{'news':[]}})))
        with self.assertRaises(Exception):self.go(bad)
        self.assertEqual(len(self.sent),1);self.assertEqual(self.ledger.summary()['stopped'],1)
        self.assertEqual(self.ledger.receipt('source:case-02:serper')['actual_micro'],3000)
    def test_no_replay_case01(self):
        prior=self.prior['request']
        with self.assertRaises(bridge.BridgeError):self.ledger.source('source:case-01:serper','orthogonal','/v1/run',prior,{'max_micro':250000,'evidence_sha256':sc.PRICE_SHA},lambda *_:None)
        self.assertEqual(self.sent,[]);self.assertEqual(self.ledger.summary()['source_attempts'],1)
    def test_live_mode_rejects_fake_time(self):
        self.contract['execution_mode']='live';self.save()
        with self.assertRaises(sc.PreflightError):self.go()
        self.assertEqual(self.project_calls,[]);self.assertEqual(self.sent,[])
