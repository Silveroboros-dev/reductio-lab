import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from vertex_runtime import VertexRuntime, RuntimeStop, UncertainEffect, OutputError, PRIOR_MICRO, RESERVE_MICRO

BODY = {'contents':[{'role':'user','parts':[{'text':'offline fixture'}]}],
        'generationConfig':{'maxOutputTokens':4096}}

def encoded(value):
    return json.dumps(value).encode()

def success(op, model, body):
    if op == 'countTokens':
        return 200, encoded({'totalTokens':100})
    return 200, encoded({'usageMetadata':{'promptTokenCount':100, 'totalTokenCount':180,
                                         'thoughtsTokenCount':30}, 'candidates':[]})

class TestRuntime(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.directory = Path(self.temp.name).resolve()/'run'
        self.runtimes = []

    def tearDown(self):
        for r in self.runtimes:
            r.close()
        self.temp.cleanup()

    def runtime(self, transport=success, **options):
        r = VertexRuntime(self.directory, transport, 'pinned-model', **options)
        self.runtimes.append(r)
        return r

    def events(self):
        return [json.loads(x) for x in (self.directory/'events.jsonl').read_text().splitlines()]

    def test_accounting_counts_thought_and_includes_prior_and_reserved_sources(self):
        r = self.runtime()
        r.generate(BODY, case_id='c1', stage='inference')
        self.assertEqual(r.exposure_micro, PRIOR_MICRO + 5_000_000 + 750)
        self.assertEqual((r.generations, r.counts), (80,12))
        entries = self.events()
        gen = [x for x in entries if x.get('operation') == 'generateContent']
        self.assertEqual([x['state'] for x in gen], ['prepared','started','succeeded','accounted'])
        self.assertEqual(gen[-1]['thought_tokens'],30)
        self.assertEqual(gen[-1]['output_including_thought_tokens'],80)
        self.assertEqual(gen[-1]['cost_micro'],750)
        self.assertEqual((self.directory/gen[2]['capture']).stat().st_mode & 0o777, 0o600)

    def test_ambiguous_generation_timeout_keeps_reserve_and_cannot_retry(self):
        seen = []
        def transport(op, model, body):
            seen.append(op)
            if op == 'countTokens': return 200, encoded({'totalTokens':100})
            raise TimeoutError()
        r = self.runtime(transport)
        with self.assertRaises(UncertainEffect): r.generate(BODY, case_id='c', stage='s')
        self.assertEqual(r.exposure_micro, PRIOR_MICRO+5_000_000+RESERVE_MICRO)
        with self.assertRaises(RuntimeStop): r.generate(BODY, case_id='c', stage='s')
        self.assertEqual(seen, ['countTokens','generateContent'])
        self.assertEqual(self.events()[-1]['state'],'uncertain')

    def test_ambiguous_count_never_starts_generation(self):
        def transport(op, model, body): raise TimeoutError()
        r = self.runtime(transport)
        with self.assertRaises(UncertainEffect): r.generate(BODY, case_id='c', stage='s')
        self.assertEqual((r.generations, r.counts), (79,12))
        self.assertEqual(self.events()[-1]['operation'],'countTokens')

    def test_cap_blocks_all_calls(self):
        seen = []
        def transport(*args): seen.append(args); return success(*args)
        r = self.runtime(transport, cap_micro=PRIOR_MICRO+5_000_000+RESERVE_MICRO-1)
        with self.assertRaises(RuntimeStop): r.generate(BODY, case_id='c', stage='s')
        self.assertEqual(seen, [])

    def test_large_count_fails_before_generation(self):
        seen=[]
        def transport(op, model, body):
            seen.append(op)
            return 200, encoded({'totalTokens':16385})
        r = self.runtime(transport)
        with self.assertRaises(RuntimeStop): r.generate(BODY, case_id='c', stage='s')
        self.assertEqual(seen, ['countTokens'])
        self.assertEqual(self.events()[-1]['state'], 'failed_before_effect')
        self.assertEqual(r.generations,79)

    def test_missing_usage_retains_reserve_and_stops(self):
        def transport(op, model, body):
            return (200, encoded({'totalTokens':1})) if op == 'countTokens' else (200, b'{}')
        r = self.runtime(transport)
        with self.assertRaises(OutputError): r.generate(BODY, case_id='c', stage='s')
        self.assertEqual(r.exposure_micro, PRIOR_MICRO+5_000_000+RESERVE_MICRO)
        with self.assertRaises(RuntimeStop): r.generate(BODY, case_id='c', stage='s')

    def test_count_and_generation_attempt_caps(self):
        r = self.runtime(max_counts=11)
        with self.assertRaises(RuntimeStop): r.generate(BODY, case_id='c', stage='s')
        self.assertEqual(r.generations,79)

    def test_generation_config_enforced_before_call(self):
        r = self.runtime()
        with self.assertRaises(ValueError): r.generate({}, case_id='c', stage='s')
        self.assertEqual((r.generations,r.counts), (79,11))

    def test_body_model_cannot_override_pinned_model(self):
        r = self.runtime()
        body = {**BODY, 'model':'other-model'}
        with self.assertRaises(ValueError): r.generate(body, case_id='c', stage='s')
        self.assertEqual((r.generations, r.counts), (79,11))

    def test_journal_write_failure_stops_object(self):
        r = self.runtime()
        with patch('vertex_runtime.os.write', side_effect=OSError('disk full')):
            with self.assertRaises(OSError): r.generate(BODY, case_id='c', stage='s')
        with self.assertRaises(RuntimeStop): r.generate(BODY, case_id='c', stage='s')
        self.assertEqual((r.generations, r.counts), (79,11))

    def test_transport_cannot_mutate_generation_request(self):
        seen = []
        def transport(op, model, body):
            if op == 'countTokens':
                body['generateContentRequest']['contents'][0]['parts'][0]['text'] = 'mutated'
                return 200, encoded({'totalTokens': 1})
            seen.append(body['contents'][0]['parts'][0]['text'])
            return success(op, model, body)
        r = self.runtime(transport)
        r.generate(BODY, case_id='c', stage='s')
        self.assertEqual(seen, ['offline fixture'])

    def test_no_resume_or_overwrite_existing_ledger(self):
        self.runtime()
        with self.assertRaises(FileExistsError): VertexRuntime(self.directory, success, 'pinned-model')

    def test_actual_usage_over_reserve_stops_and_records_actual(self):
        def transport(op, model, body):
            return (200, encoded({'totalTokens':1})) if op == 'countTokens' else (200, encoded({'usageMetadata':{'promptTokenCount':1, 'totalTokenCount':10002}}))
        r = self.runtime(transport)
        with self.assertRaises(RuntimeStop): r.generate(BODY, case_id='c', stage='s')
        self.assertEqual(self.events()[-1]['state'],'accounted')
        self.assertEqual(self.events()[-1]['cost_micro'],75009)

if __name__ == '__main__': unittest.main()
