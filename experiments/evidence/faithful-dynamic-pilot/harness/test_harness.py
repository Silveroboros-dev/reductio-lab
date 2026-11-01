import unittest

from harness import BaselineEngine, ProtocolError, prepare_task, validate_manifest


def task():
    return {
        'case_id': 'opaque-case', 'question': 'Classify these contracts.',
        'contract_ids': ['contract-1'], 'allowed_labels': ['direct', 'indirect', 'weak_proxy', 'unknown'],
        'initial_evidence': [{'id': 'p0', 'text': 'Initial visible context.', 'source': 'saved'}],
        'actions': [
            {'id': 'a', 'description': 'Get source A.', 'quoted_cost_micro_usd': 1234,
             'owner_private': 'OWNER_SECRET'},
            {'id': 'b', 'description': 'Get source B.', 'quoted_cost_micro_usd': 3000}],
        'owner_reference': 'OWNER_SECRET', 'review_decision': {'label': 'SECRET_LABEL'},
    }


def replay():
    return {'a': {'evidence': [{'id': 'pa', 'text': 'chosen result', 'reference': 'OWNER_SECRET'}],
                  'review_label': 'SECRET_LABEL'},
            'b': {'evidence': [{'id': 'pb', 'text': 'UNSEEN_SECRET_RESULT'}]}}


def answer(citations=None, label='unknown', **kwargs):
    return {'answers': [{'contract_id': 'contract-1', 'label': label,
                         'citations': citations or [], 'explanation': 'limited to evidence'}],
            'stop_reason': 'done', **kwargs}


def decision(kind='stop', action_id=None, expectation=None, **kwargs):
    return {'action': kind, 'action_id': action_id, 'expectation': expectation or '',
            'rationale': 'reason', **kwargs}


class Responses:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def __call__(self, stage, payload):
        self.calls.append((stage, payload))
        value = self.responses.pop(0)
        if isinstance(value, Exception):
            raise value
        return value


class HarnessTests(unittest.TestCase):
    def test_manual_capture_has_unknown_shadow_cost_paid_capture_needs_quote(self):
        t = task(); t['actions'][0].update(capture_kind='manual_capture', quoted_cost_micro_usd=None)
        gen = Responses([decision('query', 'a'), answer(['pa'])])
        outcome = BaselineEngine(gen).run(t, replay(), 'B')
        self.assertIsNone(outcome['shadow_source_cost_micro_usd'])
        self.assertEqual(gen.calls[0][1]['available_actions'][0]['capture_kind'], 'manual_capture')
        t['actions'][0]['capture_kind'] = 'paid_api'
        with self.assertRaises(ProtocolError): prepare_task(t, replay())
        t['actions'][0].update(capture_kind='manual_capture', quoted_cost_micro_usd=0)
        with self.assertRaises(ProtocolError): prepare_task(t, replay())
    def test_unselected_results_owner_references_and_extra_fields_are_not_projected(self):
        gen = Responses([decision('query', 'a', 'will report target'),
                         answer(['pa'], observed_vs_expected='matched')])
        result = BaselineEngine(gen).run(task(), replay(), 'B')
        self.assertEqual([x[0] for x in gen.calls], ['source_selection', 'after_query'])
        self.assertNotIn('chosen result', repr(gen.calls[0][1]))
        self.assertIn('chosen result', repr(gen.calls[1][1]))
        for _, payload in gen.calls:
            self.assertNotIn('UNSEEN_SECRET_RESULT', repr(payload))
            self.assertNotIn('OWNER_SECRET', repr(payload))
            self.assertNotIn('SECRET_LABEL', repr(payload))
        self.assertEqual(result['shadow_source_cost_micro_usd'], 1234)
        self.assertEqual(result['live_provider_calls_during_replay'], 0)
        events = [x['event'] for x in result['trace']]
        self.assertLess(events.index('query_selected'), events.index('source_replayed'))
        self.assertTrue(result['expectation_recorded'])
        self.assertEqual(result['result']['observed_vs_expected'], 'matched')

    def test_self_check_can_change_action_before_source_is_revealed(self):
        gen = Responses([decision('query', 'a'), decision('query', 'b', 'expect b'),
                         answer(['pb'], observed_vs_expected='matched')])
        result = BaselineEngine(gen).run(task(), replay(), 'B_self_check')
        self.assertEqual(result['selected_action_id'], 'b')
        self.assertEqual(result['shadow_source_cost_micro_usd'], 3000)
        self.assertEqual([x[0] for x in gen.calls], ['source_selection', 'self_check', 'after_query'])
        self.assertNotIn('chosen result', repr(gen.calls[2][1]))
        self.assertIn('UNSEEN_SECRET_RESULT', repr(gen.calls[2][1]))
        events = [x['event'] for x in result['trace']]
        self.assertLess(events.index('self_check_completed'), events.index('query_selected'))
        self.assertLess(events.index('query_selected'), events.index('source_replayed'))

    def test_missing_expectation_cannot_be_reconstructed_by_callback(self):
        gen = Responses([decision('query', 'a'), answer(['pa'], observed_vs_expected='invented later')])
        result = BaselineEngine(gen).run(task(), replay(), 'B')
        self.assertFalse(result['expectation_recorded'])
        self.assertIsNone(result['expectation'])
        self.assertIsNone(result['result']['observed_vs_expected'])
        self.assertIsNone(gen.calls[1][1]['pre_query_expectation'])

    def test_a_cannot_access_tool_catalog_or_choose_query(self):
        gen = Responses([decision('query', 'a')])
        engine = BaselineEngine(gen)
        with self.assertRaises(ProtocolError):
            engine.run(task(), replay(), 'A')
        self.assertEqual(gen.calls[0][1]['available_actions'], [])
        self.assertEqual(gen.calls[0][1]['remaining_source_reads'], 0)
        self.assertEqual(engine.last_calls, 1)
        self.assertNotIn('source_replayed', [x['event'] for x in engine.last_trace])

    def test_b_is_free_to_reflect_using_same_budget(self):
        gen = Responses([decision('reflect'), decision('stop', answers=answer(['p0'])['answers'],
                                                       stop_reason='done')])
        result = BaselineEngine(gen).run(task(), replay(), 'B')
        self.assertEqual([x[0] for x in gen.calls], ['source_selection', 'reflect'])
        self.assertEqual(result['model_calls'], 2)
        self.assertEqual(result['shadow_source_cost_micro_usd'], 0)

    def test_b_and_self_check_have_same_initial_visibility_and_limits(self):
        b = Responses([decision('stop', answers=answer(['p0'])['answers'])])
        sc = Responses([decision('stop'), decision('stop', answers=answer(['p0'])['answers'])])
        BaselineEngine(b).run(task(), replay(), 'B')
        BaselineEngine(sc).run(task(), replay(), 'B_self_check')
        self.assertEqual(b.calls[0][1], sc.calls[0][1])
        self.assertEqual(b.calls[0][1]['max_model_calls'], 23)
        self.assertEqual(b.calls[0][1]['remaining_source_reads'], 1)

    def test_unseen_citation_and_unknown_action_fail_closed(self):
        gen = Responses([decision('stop', answers=answer(['pb'])['answers'])])
        with self.assertRaises(ProtocolError):
            BaselineEngine(gen).run(task(), replay(), 'B')
        gen = Responses([decision('query', 'not-available')])
        with self.assertRaises(ProtocolError):
            BaselineEngine(gen).run(task(), replay(), 'B')

    def test_unknown_price_and_conflicting_replay_evidence_fail_closed(self):
        inp = task()
        inp['actions'][0]['quoted_cost_micro_usd'] = None
        with self.assertRaises(ProtocolError):
            BaselineEngine(Responses([decision('query', 'a')])).run(inp, replay(), 'B')
        bad = replay()
        bad['a']['evidence'][0]['id'] = 'p0'
        with self.assertRaises(ProtocolError):
            BaselineEngine(Responses([decision('query', 'a')])).run(task(), bad, 'B')

    def test_cap_counts_reflection_and_preserves_partial_trace(self):
        gen = Responses([decision('reflect') for _ in range(24)])
        engine = BaselineEngine(gen)
        with self.assertRaises(ProtocolError):
            engine.run(task(), replay(), 'B')
        self.assertEqual(engine.last_calls, 23)
        self.assertEqual(len(gen.calls), 23)
        self.assertEqual(len([e for e in engine.last_trace if e['event'] == 'generation_started']), 23)

    def test_uncertain_callback_error_is_propagated_not_converted_to_unknown(self):
        gen = Responses([TimeoutError('no response')])
        engine = BaselineEngine(gen)
        with self.assertRaises(TimeoutError):
            engine.run(task(), replay(), 'B')
        self.assertEqual(engine.last_calls, 1)
        self.assertEqual(engine.last_trace[-1]['event'], 'generation_exception')
        self.assertEqual(engine.last_trace[-1]['exception_type'], 'TimeoutError')
        self.assertNotIn('no response', repr(engine.last_trace[-1]))

    def test_manifest_separates_event_groups_and_cannot_assert_human_truth(self):
        rows = [{'case_id': f'case-{i}', 'event_group_id': f'event-{i}',
                 'input_sha256': f'{i:064x}', 'split': 'dev' if i < 2 else 'test'} for i in range(8)]
        value = {'schema': 'faithful-dynamic-pilot-manifest-v1', 'cases': rows}
        self.assertIsNone(validate_manifest(value))
        rows[-1]['event_group_id'] = rows[0]['event_group_id']
        with self.assertRaises(ProtocolError):
            validate_manifest(value)

    def test_exact_replay_action_membership_required(self):
        r = replay()
        r.pop('b')
        with self.assertRaises(ProtocolError):
            prepare_task(task(), r)

    def test_preflight_rejects_all_arms_before_callback(self):
        for fault in ('pair_aggregate', 'same_initial_id', 'reserved_id', 'bad_hash', 'bad_unselected'):
            for arm in ('A', 'B', 'B_self_check'):
                inp, hidden = task(), replay()
                if fault == 'pair_aggregate':
                    inp['allowed_labels'].append('no_clean_expression')
                elif fault == 'same_initial_id':
                    hidden['a']['evidence'][0] = dict(inp['initial_evidence'][0])
                elif fault == 'reserved_id':
                    hidden['a']['evidence'][0]['id'] = 'node:secret'
                elif fault == 'bad_hash':
                    hidden['a']['evidence'][0]['content_sha256'] = 'not-a-digest'
                else:
                    hidden['b']['evidence'] = 'malformed even when unselected'
                gen = Responses([decision('stop')])
                with self.subTest(fault=fault, arm=arm), self.assertRaises(ProtocolError):
                    BaselineEngine(gen).run(inp, hidden, arm)
                self.assertEqual(gen.calls, [])

    def test_different_replays_can_share_id_when_only_one_can_be_selected(self):
        hidden = replay()
        hidden['b']['evidence'][0]['id'] = hidden['a']['evidence'][0]['id']
        self.assertIsNotNone(prepare_task(task(), hidden))


if __name__ == '__main__':
    unittest.main()
