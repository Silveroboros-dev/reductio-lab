import copy
import json
import unittest

from faithful import Engine


def fixture():
    return ({'case_id': 'case-1', 'question': 'QUESTION_ONLY_SENTINEL',
             'contract_ids': ['market-A'], 'allowed_labels': ['direct', 'indirect', 'weak_proxy', 'unknown'],
             'initial_evidence': [
                 {'id': 's1', 'text': 'A confirmed thesis', 'source': 'human-record',
                  'captured_at': '2026-10-29T10:00:00Z', 'private_truth': 'HIDDEN_REVIEW_SENTINEL'},
                 {'id': 's2', 'text': 'A market rule'}],
             'actions': [
                 {'id': 'a', 'description': 'Read saved rule', 'quoted_cost_micro_usd': 5000,
                  'hidden': 'UNSEEN_ACTION_METADATA'},
                 {'id': 'b', 'description': 'Read another saved source', 'quoted_cost_micro_usd': 0}],
             'reference_answer': 'HIDDEN_REFERENCE_SENTINEL'},
            {'a': {'evidence': [{'id': 's3', 'text': 'SELECTED_SOURCE', 'source': 'source-a',
                                 'captured_at': '2026-10-29T10:01:00Z'}]},
             'b': {'evidence': [{'id': 's4', 'text': 'UNSEEN_SOURCE_SENTINEL'}]}})


class Fake:
    def __init__(self, *, query=False):
        self.calls = []
        self.query = query

    def __call__(self, stage, payload):
        self.calls.append((stage, copy.deepcopy(payload)))
        if stage == 'source_selection':
            return {'action': 'query' if self.query else 'stop', 'action_id': 'a' if self.query else None}
        if stage == 'selection':
            return {'alternatives': [['s3' if self.query else 's1']]}
        if stage == 'inference':
            return {'conclusion': 'market-A is supported by the selected statements'}
        if stage == 'halter':
            return {'sufficient': True}
        if stage == 'value':
            return {'score': 0.7}
        if stage == 'formatter':
            return {'answers': [{'contract_id': 'market-A', 'label': 'direct'}]}
        raise AssertionError(stage)


class FaithfulTest(unittest.TestCase):
    def test_manual_capture_unknown_price_and_paid_price_required(self):
        task, replay = fixture()
        task['actions'][0].update(capture_kind='manual_capture', quoted_cost_micro_usd=None)
        result = Engine(Fake(query=True)).run(task, replay)
        self.assertEqual(result['status'], 'proposal')
        event = next(e for e in result['events'] if e['event'] == 'source_replayed')
        self.assertEqual(event['capture_kind'], 'manual_capture')
        self.assertIsNone(event['quoted_cost_micro_usd'])
        task['actions'][0]['capture_kind'] = 'paid_api'
        self.assertEqual(Engine(Fake(query=True)).run(task, replay)['status'], 'technical_failure')
        task['actions'][0].update(capture_kind='manual_capture', quoted_cost_micro_usd=0)
        self.assertEqual(Engine(Fake(query=True)).run(task, replay)['status'], 'technical_failure')
    def test_only_selected_source_visible_and_inference_question_blind(self):
        task, replay = fixture(); fake = Fake(query=True)
        result = Engine(fake).run(task, replay)
        self.assertEqual(result['status'], 'proposal')
        payloads = [json.dumps(p, sort_keys=True) for _, p in fake.calls]
        forbidden = ('UNSEEN_SOURCE_SENTINEL', 'UNSEEN_ACTION_METADATA',
                     'HIDDEN_REFERENCE_SENTINEL', 'HIDDEN_REVIEW_SENTINEL')
        self.assertTrue(all(secret not in p for secret in forbidden for p in payloads))
        self.assertNotIn('SELECTED_SOURCE', payloads[0])
        self.assertIn('SELECTED_SOURCE', payloads[1])
        inference = next(p for s,p in fake.calls if s == 'inference')
        self.assertEqual(inference, {'selected_texts': ['SELECTED_SOURCE']})
        formatter = next(p for s,p in fake.calls if s == 'formatter')
        self.assertNotIn('question', formatter)
        self.assertNotIn('SELECTED_SOURCE', json.dumps(formatter))
        event = next(e for e in result['events'] if e['event'] == 'source_replayed')
        self.assertEqual(event['action_id'], 'a')
        self.assertEqual(event['quoted_cost_micro_usd'], 5000)
        self.assertEqual(event['evidence'][0]['captured_at'], '2026-10-29T10:01:00Z')
        self.assertNotIn('UNSEEN_SOURCE_SENTINEL', json.dumps(result))

    def test_source_has_same_task_and_budget_fields_as_baseline(self):
        task, replay = fixture(); fake = Fake(query=True)
        self.assertEqual(Engine(fake).run(task, replay)['status'], 'proposal')
        source = fake.calls[0][1]
        self.assertEqual(source['case_id'], 'case-1')
        self.assertEqual(source['contract_ids'], ['market-A'])
        self.assertEqual(source['allowed_labels'], task['allowed_labels'])
        self.assertEqual((source['max_model_calls'], source['remaining_model_calls'],
                          source['remaining_source_reads']), (23, 23, 1))

    def test_source_expectation_is_recorded_before_replay_and_not_reconstructed(self):
        task, replay = fixture(); fake = Fake(query=True)
        def generate(stage, payload):
            if stage == 'source_selection':
                return {'action': 'query', 'action_id': 'a', 'rationale': 'need rules',
                        'expectation': 'expected rule context'}
            return fake(stage, payload)
        result = Engine(generate).run(task, replay)
        events = result['events']
        idx = next(i for i,e in enumerate(events) if e['event'] == 'source_decision')
        later = next(i for i,e in enumerate(events) if e['event'] == 'source_replayed')
        self.assertLess(idx, later)
        self.assertEqual(events[idx]['expectation'], 'expected rule context')
        self.assertEqual(events[idx]['rationale'], 'need rules')
        missing = Engine(Fake(query=True)).run(task, replay)
        decision = next(e for e in missing['events'] if e['event'] == 'source_decision')
        self.assertEqual(decision['expectation'], '')

    def test_two_wide_two_deep_full_budget_23_calls(self):
        task, replay = fixture(); counts = {'halter': 0, 'value': 0}
        def generate(stage, payload):
            if stage == 'source_selection': return {'action': 'stop', 'action_id': None}
            if stage == 'selection': return {'alternatives': [['s1'], ['s2']]}
            if stage == 'inference': return {'conclusion': 'derived from ' + payload['selected_texts'][0]}
            if stage == 'halter':
                counts['halter'] += 1
                return {'sufficient': counts['halter'] > 2}
            if stage == 'value':
                counts['value'] += 1
                return {'score': counts['value'] / 10}
            if stage == 'formatter': return {'answers': [{'contract_id': 'market-A', 'label': 'direct'}]}
            raise AssertionError(stage)
        result = Engine(generate).run(task, replay)
        self.assertEqual(result['status'], 'proposal')
        self.assertEqual(result['calls'], 23)
        self.assertEqual(counts, {'halter': 6, 'value': 6})
        beams = [e for e in result['events'] if e['event'] == 'beam_selected']
        self.assertEqual([len(b['branch_ids']) for b in beams], [2, 2])
        self.assertEqual(len(result['selected_trace']), 2)

    def test_branch_isolation_rejects_other_branches_derived_node(self):
        task, replay = fixture(); selections = 0; values = 0
        def generate(stage, payload):
            nonlocal selections, values
            if stage == 'source_selection': return {'action': 'stop', 'action_id': None}
            if stage == 'selection':
                selections += 1
                if selections == 1: return {'alternatives': [['s1'], ['s2']]}
                # node:0001 is first candidate and chosen as highest score;
                # node:0002 belongs only to the other branch.
                return {'alternatives': [['node:0002']]}
            if stage == 'inference': return {'conclusion': 'branch-local inference'}
            if stage == 'halter': return {'sufficient': False}
            if stage == 'value':
                values += 1
                return {'score': 1 if values == 1 else 0}
            raise AssertionError(stage)
        result = Engine(generate).run(task, replay)
        self.assertEqual(result['status'], 'technical_failure')
        self.assertIn('another branch', result['reason'])

    def test_beam_ranks_candidates_by_value(self):
        task, replay = fixture(); values = iter([0.1, 0.9])
        def generate(stage, payload):
            if stage == 'source_selection': return {'action': 'stop', 'action_id': None}
            if stage == 'selection': return {'alternatives': [['s1'], ['s2']]}
            if stage == 'inference': return {'conclusion': payload['selected_texts'][0]}
            if stage == 'halter': return {'sufficient': True}
            if stage == 'value': return {'score': next(values)}
            if stage == 'formatter':
                self.assertEqual(payload['current_inference'], 'A market rule')
                return {'answers': [{'contract_id': 'market-A', 'label': 'direct'}]}
            raise AssertionError(stage)
        result = Engine(generate).run(task, replay)
        self.assertEqual(result['status'], 'proposal')
        self.assertEqual(result['selected_trace'][0]['selected_ids'], ['s2'])

    def test_invalid_unseen_premise_is_never_inferred(self):
        task, replay = fixture(); stages = []
        def generate(stage, payload):
            stages.append(stage)
            if stage == 'source_selection': return {'action': 'stop', 'action_id': None}
            if stage == 'selection': return {'alternatives': [['s4']]}
            raise AssertionError('unseen premise reached inference')
        result = Engine(generate).run(task, replay)
        self.assertEqual(result['status'], 'technical_failure')
        self.assertEqual(stages, ['source_selection', 'selection'])

    def test_invalid_source_action_never_replays(self):
        task, replay = fixture()
        result = Engine(lambda s,p: {'action': 'query', 'action_id': 'not-available'}).run(task, replay)
        self.assertEqual(result['status'], 'technical_failure')
        self.assertFalse(any(e['event'] == 'source_replayed' for e in result['events']))

    def test_unpriced_action_fails_before_any_generation(self):
        task, replay = fixture(); del task['actions'][0]['quoted_cost_micro_usd']
        fake = Fake()
        result = Engine(fake).run(task, replay)
        self.assertEqual(result['status'], 'technical_failure')
        self.assertIn('quoted cost', result['reason'])
        self.assertEqual(fake.calls, [])

    def test_all_hidden_replays_structurally_checked_without_leaking_to_model(self):
        task, replay = fixture()
        replay['b']['evidence'].append(copy.deepcopy(replay['b']['evidence'][0]))
        fake = Fake(query=True)
        result = Engine(fake).run(task, replay)
        self.assertEqual(result['status'], 'technical_failure')
        self.assertEqual(fake.calls, [])
        self.assertNotIn('UNSEEN_SOURCE_SENTINEL', json.dumps(result))

    def test_hash_shape_checked_but_hash_is_not_asserted_as_verified(self):
        task, replay = fixture()
        task['initial_evidence'][0]['content_sha256'] = 'not-sha'
        self.assertEqual(Engine(Fake()).run(task, replay)['status'], 'technical_failure')
        task['initial_evidence'][0]['content_sha256'] = 'a' * 64
        self.assertEqual(Engine(Fake()).run(task, replay)['status'], 'proposal')

    def test_insufficient_inference_returns_unknown_not_semantic_claim(self):
        task, replay = fixture()
        def generate(stage, payload):
            if stage == 'source_selection': return {'action': 'stop', 'action_id': None}
            if stage == 'selection': return {'alternatives': []}
            raise AssertionError(stage)
        result = Engine(generate).run(task, replay)
        self.assertEqual((result['status'], result['reason']), ('unknown', 'no_valid_candidate'))

    def test_depth_cap_returns_unknown(self):
        task, replay = fixture()
        def generate(stage, payload):
            if stage == 'source_selection': return {'action': 'stop', 'action_id': None}
            if stage == 'selection': return {'alternatives': [['s1']]}
            if stage == 'inference': return {'conclusion': 'not enough'}
            if stage == 'halter': return {'sufficient': False}
            if stage == 'value': return {'score': 0.5}
            raise AssertionError(stage)
        result = Engine(generate).run(task, replay)
        self.assertEqual((result['status'], result['reason']), ('unknown', 'reasoning_depth_exhausted'))

    def test_incomplete_three_contract_vector_returns_unknown(self):
        task, replay = fixture(); task['contract_ids'] = ['market-A', 'market-B', 'market-C']
        result = Engine(Fake()).run(task, replay)
        self.assertEqual((result['status'], result['reason']), ('unknown', 'incomplete_contract_vector'))

    def test_formatter_cannot_invent_contract_or_pair_label(self):
        task, replay = fixture(); fake = Fake()
        def generate(stage, payload):
            if stage == 'formatter': return {'answers': [{'contract_id': 'invented', 'label': 'direct'}]}
            return fake(stage, payload)
        result = Engine(generate).run(task, replay)
        self.assertEqual(result['status'], 'technical_failure')
        self.assertIn('unavailable contract', result['reason'])
        task['allowed_labels'].append('no_clean_expression')
        self.assertEqual(Engine(Fake()).run(task, replay)['status'], 'technical_failure')

    def test_budget_counts_before_dispatch_and_stops(self):
        task, replay = fixture(); fake = Fake()
        result = Engine(fake, max_calls=1).run(task, replay)
        self.assertEqual((result['status'], result['reason'], result['calls']),
                         ('unknown', 'generation_cap_exhausted', 1))
        self.assertEqual(len(fake.calls), 1)

    def test_duplicate_alternatives_not_resampled(self):
        task, replay = fixture(); fake = Fake()
        def generate(stage, payload):
            if stage == 'selection':
                fake.calls.append((stage, copy.deepcopy(payload)))
                return {'alternatives': [['s1'], ['s1']]}
            return fake(stage, payload)
        result = Engine(generate).run(task, replay)
        self.assertEqual(result['status'], 'proposal')
        self.assertEqual(sum(s == 'inference' for s,_ in fake.calls), 1)
        self.assertEqual(sum(e['event'] == 'duplicate_selection_skipped' for e in result['events']), 1)

    def test_callback_cannot_mutate_engine_or_original_task(self):
        task, replay = fixture(); before = copy.deepcopy(task); fake = Fake()
        def generate(stage, payload):
            if stage == 'source_selection':
                payload['available_actions'].clear()
                payload['evidence'][0]['text'] = 'rewritten locally'
            return fake(stage, payload)
        result = Engine(generate).run(task, replay)
        self.assertEqual(result['status'], 'proposal')
        self.assertEqual(task, before)
        inference = next(p for s,p in fake.calls if s == 'inference')
        self.assertEqual(inference['selected_texts'], ['A confirmed thesis'])

    def test_callback_timeout_propagates_to_run_controller(self):
        task, replay = fixture()
        def generate(stage, payload):
            raise TimeoutError('effect may be uncertain')
        engine = Engine(generate)
        with self.assertRaises(TimeoutError):
            engine.run(task, replay)
        self.assertEqual(engine.calls, 1)
        self.assertEqual(engine.events[-1]['event'], 'callback_raised')


if __name__ == '__main__':
    unittest.main()
