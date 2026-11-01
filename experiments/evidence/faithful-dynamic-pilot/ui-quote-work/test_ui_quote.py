import datetime as dt
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT/'budget-v2'))
from ledger import Ledger, Stop, UnknownEffect
from test_ledger import contract
from ui_quote import AdmissionError,EvidenceError,URL,bind_quote,execute
import serper

NOW=dt.datetime(2026,10,29,9,11,0,tzinfo=dt.timezone.utc)
def observation():
    obj={'observation':'Direct visible inspection of authenticated Orthogonal dashboard through browser UI; not raw metadata response or billing receipt',
         'observed_at_utc':'2026-10-29T09:10:43.338228+00:00','url':URL,'provider':'orthogonal','api':'serper','path':'/news','method':'POST',
         'reported_rate':'$0.002 per call','scope':'first page; one non-paginated query with q and num',
         'additional_fields_observed':['q required string','num number default 10 max 100','actual priceCents and billing.requestId in response'],
         'credential_identity':'Keychain configured credential suffix matches default dashboard key, checked in memory without displaying credential',
         'limits':'UI is observed evidence, not contractual hard cap; account billing and changes remain possible; source receipts required',
         'transport':'read-only dashboard browsing, no discovery API or paid provider operation'}
    return json.dumps(obj,ensure_ascii=False).encode()

def fingerprint(raw): return hashlib.sha256(raw).hexdigest()

def quote(request,raw,verify=lambda _:True,at=NOW,expected=None):
    return bind_quote(request,raw,expected_sha256=expected or fingerprint(raw),verify_provenance=verify,now=at)

class Admission(unittest.TestCase):
    def setUp(self):self.req=serper.build_request('US CPI current report',3);self.view=observation()
    def test_binds_observed_price_to_exact_request(self):
        q=quote(self.req,self.view)
        self.assertEqual(q['max_micro'],250000);self.assertEqual(q['request_sha256'],serper.sha(self.req));self.assertEqual(q['evidence_sha256'],fingerprint(self.view))
    def test_unknown_hash_or_provenance_block_before_effect(self):
        with self.assertRaises(AdmissionError):quote(self.req,self.view,verify=lambda _:False)
        with self.assertRaises(AdmissionError):quote(self.req,self.view,verify=None)
        with self.assertRaises(AdmissionError):quote(self.req,self.view,expected='0'*64)
    def test_stale_future_and_naive_timestamps_rejected(self):
        for instant in [NOW-dt.timedelta(minutes=5),NOW+dt.timedelta(minutes=20),dt.datetime(2026,10,29)]:
            with self.subTest(instant=instant),self.assertRaises((AdmissionError,ValueError)):quote(self.req,self.view,at=instant)
    def test_wrong_price_scope_provider_or_binding_rejected(self):
        for field,value in [('reported_rate','$0.0025 per call'),('path','/search'),('url','https://bad.example'),('scope','dynamic'),('credential_identity','unknown')]:
            obj=json.loads(self.view);obj[field]=value;bad=json.dumps(obj).encode()
            with self.subTest(field=field),self.assertRaises(AdmissionError):quote(self.req,bad)
    def test_noncanonical_or_paged_request_rejected(self):
        body=serper.canonical({'api':'serper','path':'/news','body':{'q':'x','num':3,'page':2},'query':{}})
        with self.assertRaises(AdmissionError):quote(body,self.view)

class LedgerIntegration(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.l=Ledger(str(Path(self.tmp.name).resolve()/'run'),contract(),create=True)
        self.req=serper.build_request('US CPI current report',3);self.view=observation()
    def tearDown(self):self.l.close();self.tmp.cleanup()
    def go(self,transport):
        return execute(self.l,'source:case-01:serper',self.req,self.view,expected_sha256=fingerprint(self.view),verify_provenance=lambda _:True,transport=transport,now=NOW)
    def test_actual_price_and_bytes_are_bound(self):
        raw=b'{"success":true,"priceCents":0.2,"requestId":"r1","data":{"news":[]}}'; calls=[]
        result=self.go(lambda *x:(calls.append(x) or (200,raw)))
        self.assertEqual(len(calls),1);self.assertEqual(result['price_micro_usd'],2000)
        self.assertEqual(self.l.receipt('source:case-01:serper')['response'],raw)
        self.assertEqual(self.l.summary()['exposure_micro'],721593+2000)
        self.assertEqual(result['quote_evidence_kind'],'attributed_dashboard_observation')
    def test_billing_id_accepted_and_conflict_stops_after_success(self):
        raw=b'{"success":true,"priceCents":0.2,"billing":{"requestId":"r1"},"data":{"news":[]}}'
        self.assertEqual(self.go(lambda *_:(200,raw))['request_id'],'r1')
        # Different operation is a new source, and a conflict is not concealed.
        raw2=b'{"success":true,"priceCents":0.2,"requestId":"r1","billing":{"requestId":"r2"},"data":{}}'
        with self.assertRaises(EvidenceError):
            execute(self.l,'source:case-02:serper',self.req,self.view,expected_sha256=fingerprint(self.view),verify_provenance=lambda _:True,transport=lambda *_:(200,raw2),now=NOW)
        self.assertEqual(self.l.receipt('source:case-02:serper')['state'],'succeeded');self.assertEqual(self.l.summary()['stopped'],1)
    def test_timeout_does_not_repeat_and_retains_reservation(self):
        calls=[]
        def timeout(*args):calls.append(1);raise TimeoutError()
        with self.assertRaises(UnknownEffect):self.go(timeout)
        self.assertEqual(len(calls),1);self.assertEqual(self.l.receipt('source:case-01:serper')['state'],'uncertain')
        self.assertEqual(self.l.summary()['exposure_micro'],721593+250000)
    def test_lower_actual_does_not_claim_different_quote(self):
        raw=b'{"success":true,"priceCents":0.1,"requestId":"r1","data":{}}'
        result=self.go(lambda *_:(200,raw))
        self.assertEqual(result['price_micro_usd'],1000)
        self.assertEqual(result['advertised_price_micro_usd'],2000)
        self.assertEqual(self.l.summary()['stopped'],0)
    def test_over_reserve_remains_accounted_and_stops(self):
        raw=b'{"success":true,"priceCents":30,"requestId":"r1","data":{}}'
        with self.assertRaises(Stop):self.go(lambda *_:(200,raw))
        self.assertEqual(self.l.receipt('source:case-01:serper')['actual_micro'],300000)
        self.assertEqual(self.l.receipt('source:case-01:serper')['state'],'succeeded')
        self.assertEqual(self.l.summary()['stopped'],1)
    def test_charged_more_than_quote_stops_and_records_actual(self):
        raw=b'{"success":true,"priceCents":0.25,"requestId":"r1","data":{}}'
        with self.assertRaises(EvidenceError):self.go(lambda *_:(200,raw))
        self.assertEqual(self.l.receipt('source:case-01:serper')['actual_micro'],2500);self.assertEqual(self.l.summary()['stopped'],1)

if __name__=='__main__':unittest.main()
