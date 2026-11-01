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
sys.path.insert(0,str(ROOT/'budget-v2'))
sys.path.insert(0,str(ROOT/'source-adapter'))
from ledger import Ledger, Stop, UnknownEffect
from test_ledger import contract as ledger_contract
import serper
import source_capture_v3 as sc
import ui_quote

NOW=dt.datetime(2026,10,29,9,11,0,tzinfo=dt.timezone.utc)
class FrozenDatetime(dt.datetime):
    @classmethod
    def now(cls,tz=None):
        return NOW if tz is not None else NOW.replace(tzinfo=None)

def encode(value): return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()
def ready_challenge(packet,receipt,contract):
    # Test fake only: production requires a separately reviewed trusted verifier.
    return json.loads(packet).get('fixture') is True

def verify_ui(raw):
    # Test fake only: this is not independent proof of UI/account provenance.
    return hashlib.sha256(raw).hexdigest()==sc.PRICE_SHA

class CaptureTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.root=Path(self.tmp.name).resolve()
        self.config=json.loads((ROOT/'live-ledger-contract-20261029.json').read_bytes()); self.ledger=Ledger(str(self.root/'ledger'),self.config,create=True)
        self.token_calls=[];self.project_calls=[];self.sent=[]
        bindings={p:sc.sha((ROOT/p).read_bytes()) for p in sc.REQUIRED_COMPONENTS}
        draft=json.loads((ROOT/'dataset-draft-20261029/draft.json').read_bytes())
        req=[]
        for g in draft['groups']:
            n=g['news_action_draft']; body=n['request_body'];r=serper.build_request(body['q'],body['num'])
            req.append({'case_id':g['case_id'],'event_group_id':g['event_group_id'],'api':'serper','path':'/news',
                        'body':body,'relevance_gap':n['predeclared_relevance_gap'],'request_sha256':sc.sha(r)})
        execution_context={'artifact_root':str(ROOT),'ledger_root':str(self.ledger.root.resolve()),'output_dir':str(self.root/'out'),'cwd':str(Path.cwd().resolve())}
        self.contract={'schema':sc.SCHEMA,'status':'frozen','execution_mode':'offline_fixture','component_bindings':bindings,'execution_context':execution_context,
            'known_prior_exposure_micro_usd':721593,'total_cap_micro_usd':40000000,'source_budget_micro_usd':5000000,
            'per_source_reserve_micro_usd':250000,'ui_price_micro_usd':2000,'source_attempts':8,'max_source_attempts':18,
            'max_generation_attempts_including_prior':835,'max_countTokens_including_prior':767,'model':'gemini-3.8-flash',
            'location':'global','input_rate_per_million_usd':1.5,'output_rate_per_million_usd':7.5,'input_limit':16384,
            'max_output_tokens':4096,'output_reserve':8192,'retry_policy':'none','uncertain_policy':'stop and retain reserve',
            'ui_price_evidence_sha256':sc.PRICE_SHA,'draft_sha256':sc.DRAFT_SHA,'source_requests':req}
        self.save_binding()
    def tearDown(self):self.ledger.close();self.tmp.cleanup()
    def save_binding(self):
        self.contract_path=self.root/'contract.json'; self.contract_path.write_bytes(encode(self.contract))
        code={p:{'sha256':h,'size':len((ROOT/p).read_bytes())} for p,h in self.contract['component_bindings'].items()}
        challenge={'schema_version':'eval_contract_challenge_packet_v1','overall_state':'ready','fixture':True,
                   'challenged_contract':{'raw_sha256':sc.sha(self.contract_path.read_bytes())},'witness':{'mode':'read_only_offline'},
                   'context_binding':{'code_bindings_at_inspection':code,'ledger_contract_sha256':sc.sha(serper.canonical(self.config)),'execution_context':self.contract['execution_context']}}
        challenge['internal_digest']=sc.sha(serper.canonical(challenge))
        self.challenge_path=self.root/'challenge.json';self.challenge_path.write_bytes(encode(challenge))
        b=self.challenge_path.read_bytes();self.receipt_path=self.root/'challenge-receipt.json'
        self.receipt_path.write_bytes(encode({'packet_raw_sha256':sc.sha(b),'packet_byte_count':len(b),'packet_internal_digest':challenge['internal_digest'],'state':'ready'}))
    def project(self):self.project_calls.append(1);return 'fixture-project'
    def token(self,p):self.token_calls.append(p);return 'fixture-secret'
    def handler(self,request):
        self.sent.append(request)
        return httpx.Response(200,stream=httpx.ByteStream(encode({'success':True,'priceCents':0.2,'requestId':f'r{len(self.sent)}','data':{'news':[]}})))
    def go(self,handler=None,verify=ready_challenge,ui=verify_ui):
        with patch('ledger.dt', SimpleNamespace(datetime=FrozenDatetime,timezone=dt.timezone)):
            return sc.execute(self.contract_path,self.challenge_path,self.receipt_path,self.root/'out',ledger=self.ledger,
                verify_challenge=verify,verify_ui=ui,project_id_provider=self.project,token_provider=self.token,
                fixture_http_transport=httpx.MockTransport(handler or self.handler),now=NOW)
    def test_eight_exact_successes_all_effects_in_ledger(self):
        result=self.go();self.assertEqual(len(result),8);self.assertEqual(len(self.sent),8)
        self.assertEqual([r.url.path for r in self.sent],['/v1/run']*8)
        self.assertEqual(self.ledger.summary()['source_attempts'],8)
        self.assertEqual(self.ledger.summary()['exposure_micro'],721593+8*2000)
        self.assertEqual(self.ledger.summary()['generation_attempts'],79)
        self.assertEqual(self.ledger.summary()['count_attempts'],11)
        self.assertEqual(json.loads((self.root/'out/summary.json').read_text())['status'],'completed')
        for i in range(1,9):
            row=self.ledger.receipt(f'source:case-{i:02}:serper');self.assertEqual(row['actual_micro'],2000)
            self.assertNotIn(b'fixture-secret',row['request']);self.assertNotIn(b'fixture-secret',row['response'])
    def test_unready_or_tampered_challenge_blocks_before_credentials(self):
        bad=json.loads(self.challenge_path.read_bytes());bad['overall_state']='blocked';self.challenge_path.write_bytes(encode(bad))
        with self.assertRaises(sc.PreflightError):self.go()
        self.assertEqual(self.sent,[]);self.assertEqual(self.token_calls,[]);self.assertEqual(self.project_calls,[])
    def test_challenge_receipt_binding_and_independent_reviewer_required(self):
        self.receipt_path.write_bytes(encode({'packet_raw_sha256':'0'*64,'packet_byte_count':0}))
        with self.assertRaises(sc.PreflightError):self.go()
        self.assertEqual(self.project_calls,[])
        self.save_binding()
        with self.assertRaises(sc.PreflightError):self.go(verify=lambda *_:False)
        self.assertEqual(self.project_calls,[])
    def test_wrong_query_binding_blocks_before_credentials(self):
        self.contract['source_requests'][0]['body']['q']='rewritten';self.save_binding()
        with self.assertRaises(sc.PreflightError):self.go()
        self.assertEqual(self.sent,[]);self.assertEqual(self.project_calls,[])
    def test_modified_component_binding_blocks_before_credentials(self):
        self.contract['component_bindings']['ui-quote-work/ui_quote.py']='0'*64;self.save_binding()
        with self.assertRaises(sc.PreflightError):self.go()
        self.assertEqual(self.sent,[]);self.assertEqual(self.project_calls,[])
    def test_success_then_uncertain_stops_and_does_not_repeat(self):
        def handler(request):
            self.sent.append(request)
            if len(self.sent)==2:raise httpx.ReadTimeout('fake')
            return httpx.Response(200,stream=httpx.ByteStream(encode({'success':True,'priceCents':0.2,'requestId':'r1','data':{'news':[]}})))
        with self.assertRaises(UnknownEffect):self.go(handler)
        self.assertEqual(len(self.sent),2);self.assertEqual(self.ledger.summary()['source_attempts'],2)
        self.assertEqual(self.ledger.receipt('source:case-02:serper')['state'],'uncertain')
        self.assertEqual(self.ledger.summary()['stopped'],1)
        self.assertEqual(self.ledger.summary()['exposure_micro'],721593+2000+250000)
        self.assertFalse((self.root/'out/case-03.json').exists())
    def test_price_drift_stops_after_actual_accounted(self):
        def handler(request):
            self.sent.append(request)
            return httpx.Response(200,stream=httpx.ByteStream(encode({'success':True,'priceCents':0.3,'requestId':'r1','data':{'news':[]}})))
        with self.assertRaises(Exception):self.go(handler)
        self.assertEqual(len(self.sent),1);r=self.ledger.receipt('source:case-01:serper')
        self.assertEqual(r['actual_micro'],3000);self.assertEqual(r['state'],'succeeded');self.assertEqual(self.ledger.summary()['stopped'],1)
    def test_other_output_and_other_fresh_ledger_are_blocked(self):
        with patch('ledger.dt', SimpleNamespace(datetime=FrozenDatetime,timezone=dt.timezone)):
            with self.assertRaises(sc.PreflightError):
                sc.execute(self.contract_path,self.challenge_path,self.receipt_path,self.root/'out-other',ledger=self.ledger,
                    verify_challenge=ready_challenge,verify_ui=verify_ui,project_id_provider=self.project,token_provider=self.token,
                    fixture_http_transport=httpx.MockTransport(self.handler),now=NOW)
        self.assertEqual(self.project_calls,[]);self.assertEqual(self.sent,[])
        second=Ledger(str(self.root/'other-ledger'),self.config,create=True)
        try:
            with self.assertRaises(sc.PreflightError):
                sc.validate(self.contract_path,self.challenge_path,self.receipt_path,ledger=second,output_dir=self.root/'out',
                            verify_challenge=ready_challenge,verify_ui=verify_ui,now=NOW)
        finally: second.close()
        self.assertEqual(self.sent,[])
    def test_summary_persistence_failure_stops_after_recording_effects(self):
        original=sc._write_once
        def fail_summary(path,value):
            if path.name=='summary.json':raise OSError('fake failure')
            return original(path,value)
        with patch('source_capture_v3._write_once',side_effect=fail_summary):
            with self.assertRaises(OSError):self.go()
        self.assertEqual(len(self.sent),8);self.assertEqual(self.ledger.summary()['stopped'],1)
        self.assertEqual(self.ledger.receipt('source:case-08:serper')['actual_micro'],2000)
        self.assertEqual(self.ledger.receipt('source:case-08:serper')['state'],'succeeded')
    def test_stale_ui_quote_fails_before_any_token(self):
        with patch('ledger.dt', SimpleNamespace(datetime=FrozenDatetime,timezone=dt.timezone)):
            with self.assertRaises((sc.PreflightError,ui_quote.AdmissionError)):
                sc.execute(self.contract_path,self.challenge_path,self.receipt_path,self.root/'out',ledger=self.ledger,
                    verify_challenge=ready_challenge,verify_ui=verify_ui,project_id_provider=self.project,token_provider=self.token,
                    fixture_http_transport=httpx.MockTransport(self.handler),now=NOW+dt.timedelta(hours=1))
        self.assertEqual(self.sent,[]);self.assertEqual(self.project_calls,[])
    def test_missing_news_stops_after_first_successful_effect(self):
        def handler(request):
            self.sent.append(request)
            return httpx.Response(200,stream=httpx.ByteStream(encode({'success':True,'priceCents':0.2,'requestId':'r1','data':{}})))
        with self.assertRaises(sc.PreflightError):self.go(handler)
        self.assertEqual(len(self.sent),1);self.assertEqual(self.ledger.summary()['stopped'],1)
        r=self.ledger.receipt('source:case-01:serper');self.assertEqual(r['state'],'succeeded');self.assertEqual(r['actual_micro'],2000)
        with self.assertRaises(KeyError):self.ledger.receipt('source:case-02:serper')
    def test_too_many_or_malformed_news_stops_after_effect(self):
        for news in [[{}, {}, {}, {}],[{'title':13}],['not an object']]:
            with self.subTest(news=news):
                with tempfile.TemporaryDirectory() as sub:
                    previous=self.ledger; previous.close()
                    self.ledger=Ledger(str(Path(sub).resolve()/'ledger'),self.config,create=True)
                    self.contract['execution_context']['ledger_root']=str(self.ledger.root.resolve())
                    self.contract['execution_context']['output_dir']=str(Path(sub).resolve()/'out')
                    self.root=Path(sub).resolve();self.save_binding();self.sent=[]
                    def handler(request):
                        self.sent.append(request)
                        return httpx.Response(200,stream=httpx.ByteStream(encode({'success':True,'priceCents':0.2,'requestId':'r1','data':{'news':news}})))
                    with self.assertRaises(sc.PreflightError):self.go(handler)
                    self.assertEqual(len(self.sent),1);self.assertEqual(self.ledger.summary()['stopped'],1)
                    self.assertEqual(self.ledger.receipt('source:case-01:serper')['actual_micro'],2000)
                    self.ledger.close()
    def test_live_mode_cannot_override_time(self):
        self.contract['execution_mode']='live';self.save_binding()
        with self.assertRaises(sc.PreflightError):self.go()
        self.assertEqual(self.project_calls,[]);self.assertEqual(self.sent,[])
    def test_live_mode_cannot_accept_fixture_transport(self):
        self.contract['execution_mode']='live';self.save_binding()
        with self.assertRaises(sc.PreflightError):
            sc.execute(self.contract_path,self.challenge_path,self.receipt_path,self.root/'out',ledger=self.ledger,
                verify_challenge=ready_challenge,verify_ui=verify_ui,project_id_provider=self.project,token_provider=self.token,
                fixture_http_transport=httpx.MockTransport(self.handler))
        self.assertEqual(self.project_calls,[]);self.assertEqual(self.sent,[])

if __name__=='__main__':unittest.main()
