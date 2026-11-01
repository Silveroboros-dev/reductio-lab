import datetime as dt
import json
import tempfile
from pathlib import Path
import unittest
from unittest import mock

import forecast_ledger as f


class LedgerTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir='/private/tmp')
        self.path = Path(self.tmp.name).resolve()
        self.claim = self.path/'claim.json'
        self.parent = {'dummy_parent': True}
        self.parent_patch = mock.patch.object(f, 'inspect_parent', return_value=self.parent)
        self.claim_patch = mock.patch.object(f, 'CLAIM', self.claim)
        self.parent_patch.start(); self.claim_patch.start()
        self.cfg = f.ROOT/'forecast-budget-v1/ledger_contract.json'
        self.contract = self.path/'run.json'
        self.contract.write_bytes(f.canonical({
            'schema': 'faithful-forecast-run-contract-v1', 'status': 'frozen',
            'caps': {'total_usd_micro': 60000000, 'total_generation_attempts': 835,
                     'total_count_attempts': 767, 'total_source_attempts': 28},
            'parent': self.parent, 'ledger_contract_sha256': f.digest(self.cfg.read_bytes())}))
        self.contract_sha = f.digest(self.contract.read_bytes())
        self.ledger = None

    def tearDown(self):
        if self.ledger is not None: self.ledger.close()
        self.claim_patch.stop(); self.parent_patch.stop(); self.tmp.cleanup()

    def create(self, *, challenge=lambda raw: True, ticket=lambda value, raw: True):
        self.ledger = f.create_successor(successor_root=str(self.path/'ledger'), claim_path=str(self.claim),
            ledger_contract_path=str(self.cfg), run_contract_path=str(self.contract), expected_contract_sha256=self.contract_sha,
            verify_challenge=challenge, verify_ticket=ticket)
        return self.ledger

    def ticket(self, op, request=b'{}', **overrides):
        result = {'id': op, 'provider': 'orthogonal', 'endpoint': '/v1/run',
            'request_sha256': f.digest(request), 'max_micro': 150000,
            'evidence_sha256': 'a'*64,
            'expires_utc': (dt.datetime.now(dt.timezone.utc)+dt.timedelta(minutes=10)).isoformat(),
            'category': 'news', 'settlement': 'orthogonal_price_cents'}
        result.update(overrides); return result

    def test_model_accounting_and_no_duplicate(self):
        ledger = self.create()
        request = {'contents': [{'role': 'user', 'parts': [{'text': 'hello'}]}], 'generationConfig': {'maxOutputTokens': 4096}}
        def transport(provider, endpoint, raw):
            if endpoint == 'countTokens': return 200, b'{"totalTokens":100}'
            return 200, b'{"modelVersion":"gemini-3.8-flash","usageMetadata":{"promptTokenCount":100,"totalTokenCount":140}}'
        ledger.count('count:1', request, transport)
        ledger.generate('gen:1', request, 'count:1', transport)
        self.assertEqual(ledger.summary()['generation_attempts'], 201)
        self.assertEqual(ledger.summary()['count_attempts'], 133)
        self.assertEqual(ledger.summary()['exposure_micro'], 1211040)
        with self.assertRaises(f.Stop): ledger.generate('gen:2', request, 'count:1', transport)

    def test_source_actual_and_prior_count(self):
        ledger = self.create(); body = b'{}'; ticket = self.ticket('new-1')
        ledger.source('new-1', 'orthogonal', '/v1/run', body, ticket, lambda *_: (200,b'{"priceCents":0.2}'))
        self.assertEqual(ledger.summary()['source_attempts'], 9)
        self.assertEqual(ledger.summary()['exposure_micro'], 1212590)
        self.assertEqual(ledger.receipt('new-1')['actual_micro'], 2000)
        with self.assertRaises(f.Stop): ledger.source('new-1','orthogonal','/v1/run',body,ticket,lambda *_:(200,b'{}'))

    def test_metadata_counts_and_stops_with_reserve(self):
        ledger = self.create(); body = b'{}'
        ticket = self.ticket('metadata-1', endpoint='/v1/details', category='metadata', settlement='unknown_metadata')
        with self.assertRaises(f.Stop): ledger.source('metadata-1','orthogonal','/v1/details',body,ticket,lambda *_:(200,b'{}'))
        s=ledger.summary()
        self.assertEqual((s['source_attempts'],s['metadata_attempts'],s['stopped']), (9,1,1))
        self.assertEqual(s['exposure_micro'], 1360590)
        self.assertIsNone(ledger.receipt('metadata-1')['actual_micro'])

    def test_unknown_effect_stops_no_repeat(self):
        ledger = self.create(); body=b'{}'; ticket=self.ticket('new-1')
        def fail(*_): raise TimeoutError()
        with self.assertRaises(f.Stop): ledger.source('new-1','orthogonal','/v1/run',body,ticket,fail)
        self.assertEqual(ledger.receipt('new-1')['state'], 'uncertain')
        self.assertEqual(ledger.summary()['stopped'], 1)
        with self.assertRaises(f.Stop): ledger.source('new-1','orthogonal','/v1/run',body,ticket,lambda *_:(200,b'{}'))

    def test_invalid_receipt_keeps_reserve_and_stops(self):
        ledger=self.create(); ticket=self.ticket('new-1')
        with self.assertRaises(f.Stop): ledger.source('new-1','orthogonal','/v1/run',b'{}',ticket,lambda *_:(200,b'not json'))
        self.assertEqual(ledger.summary()['stopped'],1)
        self.assertIsNone(ledger.receipt('new-1')['actual_micro'])

    def test_invalid_ticket_not_started(self):
        ledger=self.create(ticket=lambda *_:False)
        with self.assertRaises(f.Stop): ledger.source('new-1','orthogonal','/v1/run',b'{}',self.ticket('new-1'),lambda *_:(200,b'{}'))
        self.assertEqual(ledger.summary()['source_attempts'],8)

    def test_expiry_quote_or_historical_identity_not_started(self):
        ledger=self.create(); body=b'{}'
        for ticket in (self.ticket('new-1', max_micro=150001), self.ticket('new-1', expires_utc='2000-01-01T00:00:00+00:00')):
            with self.assertRaises(f.Stop): ledger.source('new-1','orthogonal','/v1/run',body,ticket,lambda *_:(200,b'{}'))
        old='source:case-01:serper'
        with self.assertRaises(f.Stop): ledger.source(old,'orthogonal','/v1/run',body,self.ticket(old),lambda *_:(200,b'{}'))
        self.assertEqual(ledger.summary()['source_attempts'],8)

    def test_twenty_new_source_cap(self):
        ledger=self.create(); body=b'{}'
        for i in range(20):
            op=f'new-{i}'; t=self.ticket(op,provider='kalshi',endpoint='/trade-api/v2/markets',category='market',settlement='free_public')
            ledger.source(op,'kalshi','/trade-api/v2/markets',body,t,lambda *_:(200,b'{}'))
        self.assertEqual(ledger.summary()['source_attempts'],28)
        op='new-20'; t=self.ticket(op,provider='kalshi',endpoint='/trade-api/v2/markets',category='market',settlement='free_public')
        with self.assertRaises(f.Stop): ledger.source(op,'kalshi','/trade-api/v2/markets',body,t,lambda *_:(200,b'{}'))

    def test_claim_prevents_duplicate_successor(self):
        self.create(); self.ledger.close(); self.ledger=None
        with self.assertRaises(FileExistsError):
            f.create_successor(successor_root=str(self.path/'ledger2'),claim_path=str(self.claim),ledger_contract_path=str(self.cfg),
                run_contract_path=str(self.contract),expected_contract_sha256=self.contract_sha,verify_challenge=lambda _:True,verify_ticket=lambda *_:True)

    def test_rejected_challenge_no_creation(self):
        with self.assertRaises(f.Stop): self.create(challenge=lambda _: False)
        self.assertFalse(self.claim.exists())
        self.assertFalse((self.path/'ledger').exists())

    def test_contract_drift_stops(self):
        ledger=self.create(); self.contract.write_text('{}')
        with self.assertRaises(f.Stop): ledger.count('count:1',{},lambda *_:(200,b'{}'))
        self.assertEqual(ledger.summary()['stopped'],1)

    def reopen(self):
        self.ledger = f.reopen_successor(successor_root=str(self.path/'ledger'), claim_path=str(self.claim),
            ledger_contract_path=str(self.cfg), run_contract_path=str(self.contract), expected_contract_sha256=self.contract_sha,
            verify_challenge=lambda _:True, verify_ticket=lambda *_:True)
        return self.ledger

    def test_reopen_preserves_prior_and_successful_source(self):
        ledger=self.create(); ticket=self.ticket('s1')
        ledger.source('s1','orthogonal','/v1/run',b'{}',ticket,lambda *_:(200,b'{"priceCents":0.2}'))
        ledger.close(); self.ledger=None
        resumed=self.reopen()
        self.assertEqual((resumed.summary()['source_attempts'],resumed.summary()['exposure_micro']), (9,1212590))
        self.assertEqual(resumed.receipt('s1')['actual_micro'],2000)
        with self.assertRaises(f.Stop): resumed.source('s1','orthogonal','/v1/run',b'{}',ticket,lambda *_:(200,b'{}'))

    def test_reopen_uncertain_fails_closed(self):
        ledger=self.create(); ticket=self.ticket('s1')
        def fail(*_): raise TimeoutError()
        with self.assertRaises(f.Stop): ledger.source('s1','orthogonal','/v1/run',b'{}',ticket,fail)
        ledger.close(); self.ledger=None
        with self.assertRaises(f.Stop): self.reopen()

    def test_reopen_model_version_suffix(self):
        ledger=self.create()
        request={'contents': [], 'generationConfig': {'maxOutputTokens':4096}}
        def transport(provider,endpoint,raw):
            if endpoint=='countTokens': return 200,b'{"totalTokens":100}'
            return 200,b'{"modelVersion":"gemini-3.8-flash-001","usageMetadata":{"promptTokenCount":100,"totalTokenCount":140}}'
        ledger.count('count:suffix',request,transport)
        ledger.generate('gen:suffix',request,'count:suffix',transport)
        ledger.close(); self.ledger=None
        self.assertEqual(self.reopen().summary()['generation_attempts'],201)


class RealParentTest(unittest.TestCase):
    def test_prior_read_only(self):
        path=f.ROOT/'live-model-successor-ledger-20261029-01/ledger.sqlite3'
        before=f.digest(path.read_bytes()); parent=f.inspect_parent(); after=f.digest(path.read_bytes())
        self.assertEqual(before,after)
        self.assertEqual((parent['prior_micro'],parent['prior_generations'],parent['prior_counts'],parent['prior_sources']), (1210590,200,132,8))


if __name__ == '__main__': unittest.main()
