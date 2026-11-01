"""Offline checks for exact-quote selection against saved evidence text."""
import hashlib
import json
import unittest

from faithful_v3.engine import StrictEngine
from faithful_v3.excerpts import resolve_selection, source_registry
from faithful_v3.prompts import VERSION, bind_model, build_request
from reasoning_engine.engine import EngineConfig, InvalidOutput
from reasoning_engine.replay_sources import digest


def saved_source(ident, payload):
    return {'id': ident, 'kind': 'observation', 'source': 'saved response for ' + ident,
            'text_representation': 'saved_payload_json',
            'text': json.dumps(payload, ensure_ascii=False, sort_keys=True),
            'raw_ref': 'sha256:' + digest(payload)}


def select(ident, *spans):
    return {'id': ident, 'spans': list(spans)}


class VerbatimSelectionTests(unittest.TestCase):
    def test_live_failure_fixture_resolves_exact_quotes_and_provenance(self):
        # These are the two synthetic saved responses from the failed live run.
        rule = saved_source('source:synthetic-rule-lark7-v1', {
            'provenance': {'captured_at': '2026-10-29T12:00:00Z',
                           'published_at': '2026-10-29T11:55:00Z', 'source_id': 'synthetic-rule-v1'},
            'text': 'For batch LARK-7, the target is met only if at least 7 of 10 final checks pass.'})
        tally = saved_source('source:synthetic-final-tally-lark7-v1', {
            'provenance': {'captured_at': '2026-10-29T12:10:00Z',
                           'published_at': '2026-10-29T12:05:00Z', 'source_id': 'synthetic-final-tally-v1'},
            'text': 'Final audit of batch LARK-7: 6 of 10 checks passed; 4 failed.'})
        self.assertEqual((len(rule['text']), len(tally['text'])), (220, 209))
        nodes = {item['id']: item for item in (rule, tally)}
        ids = set(nodes)
        registry = source_registry([rule, tally])
        failed = [select(rule['id'], {'start_char': 147, 'end_char': 226}),
                  select(tally['id'], {'start_char': 154, 'end_char': 217})]
        with self.assertRaisesRegex(InvalidOutput, 'out of bounds'):
            resolve_selection(failed, nodes, ids, registry)

        quotes = ('For batch LARK-7, the target is met only if at least 7 of 10 final checks pass.',
                  'Final audit of batch LARK-7: 6 of 10 checks passed; 4 failed.')
        choices = [select(rule['id'], {'quote': quotes[0]}), select(tally['id'], {'quote': quotes[1]})]
        selected_ids, texts, refs = resolve_selection(choices, nodes, ids, registry)
        self.assertEqual(selected_ids, [rule['id'], tally['id']])
        self.assertEqual([x['text'] for x in texts], list(quotes))
        for item, quote, ref in zip((rule, tally), quotes, refs):
            start = item['text'].index(quote)
            self.assertEqual((ref['id'], ref['start_char'], ref['end_char']),
                             (item['id'], start, start + len(quote)))
            self.assertEqual(ref['scope'], 'saved_response_text_span')
            self.assertEqual(ref['offset_unit'], 'unicode_code_points')
            self.assertEqual(ref['offset_basis'], 'saved_evidence_text_not_original_document')
            self.assertEqual(ref['text_representation'], 'saved_payload_json')
            self.assertEqual(ref['raw_ref'], item['raw_ref'])
            self.assertEqual(ref['saved_payload_sha256'], item['raw_ref'].removeprefix('sha256:'))
            self.assertEqual(ref['evidence_text_sha256'], hashlib.sha256(item['text'].encode()).hexdigest())
            self.assertEqual(ref['excerpt_sha256'], hashlib.sha256(quote.encode()).hexdigest())
            self.assertEqual(ref['binding'], 'caller_supplied_hash_consistency')

    def test_absent_ambiguous_empty_and_malformed_quotes_rejected(self):
        item = {'id': 'src', 'text': 'banana\nalpha  beta\nalpha  beta',
                'source': 'fixture', 'kind': 'observation'}
        nodes = {'src': item}
        bad = [{'quote': 'ana'},  # overlapping matches in banana
               {'quote': 'alpha  beta'}, {'quote': 'Alpha  beta'},
               {'quote': 'alpha beta'}, {'quote': 'alpha  beta\r\n'},
               {'quote': ''}, {'quote': ' \t\n'}, {'quote': None}, {'quote': 1},
               {'quote': 'banana', 'start_char': 0}]
        for span in bad:
            with self.subTest(span=span), self.assertRaises(InvalidOutput):
                resolve_selection([select('src', span)], nodes, {'src'}, {})
        with self.assertRaisesRegex(InvalidOutput, 'duplicate'):
            resolve_selection([select('src', {'quote': 'banana'}, {'quote': 'banana'})],
                              nodes, {'src'}, {})

    def test_quote_is_exact_with_unicode_and_scoped_to_source(self):
        first = {'id': 'first', 'text': 'α café😊 e\u0301\nPRIVATE',
                 'source': 'fixture', 'kind': 'observation'}
        second = {'id': 'second', 'text': 'other source: résumé',
                  'source': 'fixture', 'kind': 'observation'}
        nodes = {'first': first, 'second': second}
        _, texts, refs = resolve_selection([select('first', {'quote': 'café😊 e\u0301'})],
                                          nodes, set(nodes), {})
        self.assertEqual(texts[0]['text'], 'café😊 e\u0301')
        self.assertEqual((refs[0]['start_char'], refs[0]['end_char']), (2, 10))
        self.assertNotIn('PRIVATE', json.dumps(texts, ensure_ascii=False))
        _, spaced, spaced_refs = resolve_selection([select('first', {'quote': ' café😊 e\u0301\n'})],
                                                  nodes, set(nodes), {})
        self.assertEqual(spaced[0]['text'], ' café😊 e\u0301\n')
        self.assertEqual((spaced_refs[0]['start_char'], spaced_refs[0]['end_char']), (1, 11))
        for quote in ('cafe\u0301😊 e\u0301', 'café😊 é', 'résumé'):
            with self.subTest(quote=quote), self.assertRaises(InvalidOutput):
                resolve_selection([select('first', {'quote': quote})], nodes, set(nodes), {})

    def test_saved_json_format_and_hash_are_binding(self):
        item = saved_source('src', {'text': 'A  B\ncafé😊', 'other': 'PRIVATE'})
        nodes = {'src': item}
        choices = [select('src', {'quote': 'A  B\ncafé😊'})]
        with self.assertRaisesRegex(InvalidOutput, 'absent'):
            resolve_selection(choices, nodes, {'src'}, source_registry([item]))
        # The evidence view contains JSON-escaped newline, not a raw newline.
        choices = [select('src', {'quote': 'A  B\\ncafé😊'})]
        _, texts, _ = resolve_selection(choices, nodes, {'src'}, source_registry([item]))
        self.assertEqual(texts[0]['text'], 'A  B\\ncafé😊')
        tampered = dict(item, text=item['text'].replace('A  B', 'A  C'))
        with self.assertRaisesRegex(InvalidOutput, 'hash mismatch'):
            source_registry([tampered])
        with self.assertRaisesRegex(InvalidOutput, 'hash mismatch'):
            resolve_selection([select('src', {'quote': 'A  C'})],
                              {'src': tampered}, {'src'}, {})

    def test_structured_numeric_spans_and_legacy_unstructured_spans_unchanged(self):
        payload = {'passages': [{'id': 'p', 'start_char': 100, 'end_char': 111,
                                 'text': 'prefix café'}],
                   'coverage': {'range_unit': 'unicode_code_points',
                                'visible_char_ranges': [[100, 111]]},
                   'source_document_char_count': 111}
        structured = saved_source('structured', payload)
        plain = {'id': 'plain', 'text': 'prefix café', 'source': 'fixture', 'kind': 'observation'}
        nodes = {'structured': structured, 'plain': plain}
        registry = source_registry([structured, plain])
        ids, texts, refs = resolve_selection([
            select('structured', {'passage_id': 'p', 'start_char': 107, 'end_char': 110}),
            select('plain', {'start_char': 7, 'end_char': 10})], nodes, set(nodes), registry)
        self.assertEqual(ids, ['structured', 'plain'])
        self.assertEqual([x['text'] for x in texts], ['caf', 'caf'])
        self.assertEqual([r['scope'] for r in refs], ['saved_passage_span', 'saved_response_text_span'])
        with self.assertRaisesRegex(InvalidOutput, 'invalid source span'):
            resolve_selection([select('structured', {'quote': 'caf'})], nodes, set(nodes), registry)
        with self.assertRaises(InvalidOutput):
            resolve_selection(['structured'], nodes, set(nodes), registry)

    def test_inference_receives_only_derived_excerpt_not_question_or_full_source(self):
        text = 'context PRIVATE-SENTINEL; exact fact: 6 of 10 passed; trailing PRIVATE-SENTINEL'
        item = {'id': 'src', 'text': text, 'source': 'fixture', 'kind': 'observation',
                'text_representation': 'saved_payload_text', 'raw_ref': 'sha256:' + digest(text)}
        question = 'PRIVATE-QUESTION: did the batch pass?'
        task = {'case_id': 'quote-test', 'question': question, 'task_type': 'exploration',
                'evidence': [item],
                'required_questions': [{'id': 'q', 'question': question, 'evidence_ids': []}]}
        stages = []

        def requester(request):
            stage, payload = request['stage'], request['input']
            stages.append(stage)
            if stage == 'selection':
                self.assertEqual(request['prompt_version'], VERSION)
                self.assertIn("{'quote': exact_verbatim_substring}", request['instruction'])
                return {'alternatives': [[select('src', {'quote': 'exact fact: 6 of 10 passed'})]]}
            if stage == 'inference':
                self.assertEqual(set(payload), {'selected_texts'})
                self.assertEqual(payload['selected_texts'][0]['text'], 'exact fact: 6 of 10 passed')
                self.assertNotIn('PRIVATE-SENTINEL', json.dumps(request))
                self.assertNotIn('PRIVATE-QUESTION', json.dumps(request))
                return {'conclusion': 'The target was missed.'}
            if stage == 'halter':
                return {'sufficient': True, 'reason': 'fixture'}
            if stage == 'value':
                return {'score': 0.5}
            if stage == 'formatter':
                self.assertEqual(set(payload), {'final_inference', 'allowed_citation_ids'})
                return {'answer': payload['final_inference'],
                        'citations': payload['allowed_citation_ids']}
            raise AssertionError(stage)

        outcome = StrictEngine(bind_model(requester), EngineConfig(max_calls=5, max_depth=1,
                                                                   beam_width=1)).run(task)
        self.assertEqual((outcome['status'], stages),
                         ('proposal', ['selection', 'inference', 'halter', 'value', 'formatter']))
        self.assertEqual(outcome['selected_trace'][0]['selected_source_refs'][0]['id'], 'src')


if __name__ == '__main__':
    unittest.main()
