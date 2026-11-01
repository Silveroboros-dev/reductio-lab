"""Synthetic integration checks only; no network, provider, or semantic review."""
from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'controller'))
sys.path.insert(0, str(ROOT / 'harness'))
from faithful import Engine  # noqa: E402
from harness import BaselineEngine  # noqa: E402


def fixture():
    task = {
        'case_id': 'case-opaque',
        'question': 'Assess the listed hypothetical contract.',
        'contract_ids': ['contract-opaque'],
        'allowed_labels': ['direct', 'indirect', 'weak_proxy', 'unknown'],
        'initial_evidence': [{'id': 'initial', 'text': 'INITIAL SYNTHETIC THESIS'}],
        'actions': [
            {'id': 'action-1', 'description': 'Read captured source one', 'quoted_cost_micro_usd': 10},
            {'id': 'action-2', 'description': 'Read captured source two', 'quoted_cost_micro_usd': 20},
        ],
        'owner_reference': 'SECRET REVIEW FIELD',
    }
    replay = {
        'action-1': {'evidence': [{'id': 'chosen', 'text': 'CHOSEN SYNTHETIC PAYLOAD'}]},
        'action-2': {'evidence': [{'id': 'unselected', 'text': 'UNSELECTED SYNTHETIC PAYLOAD'}]},
    }
    return task, replay


class Generator:
    """Deterministic stage simulator; outputs are proposals, not ground truth."""
    def __init__(self, arm):
        self.arm = arm
        self.calls = []

    def __call__(self, stage, payload):
        self.calls.append((stage, copy.deepcopy(payload)))
        if stage in ('source_selection', 'self_check'):
            if self.arm == 'A':
                return {'action': 'stop', 'action_id': None,
                        'answers': [{'contract_id': 'contract-opaque', 'label': 'direct',
                                     'citations': ['initial'], 'explanation': 'synthetic'}]}
            return {'action': 'query', 'action_id': 'action-1',
                    'rationale': 'synthetic', 'expectation': 'EXPECTED BEFORE REPLAY'}
        if stage == 'after_query':
            return {'answers': [{'contract_id': 'contract-opaque', 'label': 'direct',
                                 'citations': ['chosen'], 'explanation': 'synthetic'}],
                    'observed_vs_expected': 'synthetic comparison'}
        if stage == 'selection':
            return {'alternatives': [['initial', 'chosen']]}
        if stage == 'inference':
            return {'conclusion': 'contract-opaque has hypothetical direct fit'}
        if stage == 'halter':
            return {'sufficient': True}
        if stage == 'value':
            return {'score': 0.5}
        if stage == 'formatter':
            return {'answers': [{'contract_id': 'contract-opaque', 'label': 'direct'}]}
        raise AssertionError(f'unexpected stage: {stage}')


class FourArmIntegrationTest(unittest.TestCase):
    def test_same_chosen_capture_no_unselected_or_review_leak(self):
        task, replay = fixture()
        original = copy.deepcopy((task, replay))
        generators = {arm: Generator(arm) for arm in ('A', 'B', 'B_self_check', 'C')}
        results = {arm: BaselineEngine(generators[arm]).run(task, replay, arm)
                   for arm in ('A', 'B', 'B_self_check')}
        results['C'] = Engine(generators['C']).run(task, replay)

        # All source-enabled arms receive the same pre-replay task fields.
        # C has an extra instruction and B permits self-directed reflection.
        shared = ('case_id', 'question', 'contract_ids', 'allowed_labels', 'evidence',
                  'available_actions', 'max_model_calls', 'remaining_model_calls',
                  'remaining_source_reads')
        initial_views = {arm: generators[arm].calls[0][1] for arm in generators}
        for arm in ('B_self_check', 'C'):
            self.assertEqual({k: initial_views['B'][k] for k in shared},
                             {k: initial_views[arm][k] for k in shared})
        self.assertEqual(initial_views['A']['available_actions'], [])
        self.assertEqual(initial_views['A']['remaining_source_reads'], 0)

        for arm, gen in generators.items():
            rendered = [json.dumps(payload, sort_keys=True) for _, payload in gen.calls]
            self.assertTrue(all('UNSELECTED SYNTHETIC PAYLOAD' not in text for text in rendered))
            self.assertTrue(all('SECRET REVIEW FIELD' not in text for text in rendered))
            self.assertNotIn('CHOSEN SYNTHETIC PAYLOAD', rendered[0])
            if arm == 'A':
                self.assertTrue(all('CHOSEN SYNTHETIC PAYLOAD' not in text for text in rendered))
            else:
                self.assertTrue(any('CHOSEN SYNTHETIC PAYLOAD' in text for text in rendered[1:]))

        # Inference sees only explicitly selected texts, unlike the baselines'
        # after_query stage, which sees the entire selected evidence projection.
        inference = next(p for stage, p in generators['C'].calls if stage == 'inference')
        self.assertEqual(inference, {'selected_texts': ['INITIAL SYNTHETIC THESIS',
                                                        'CHOSEN SYNTHETIC PAYLOAD']})
        for arm in ('B', 'B_self_check'):
            after = next(p for stage, p in generators[arm].calls if stage == 'after_query')
            self.assertEqual(after['evidence'], task['initial_evidence'] + replay['action-1']['evidence'])
            self.assertEqual(results[arm]['expectation'], 'EXPECTED BEFORE REPLAY')
            self.assertEqual(results[arm]['shadow_source_cost_micro_usd'], 10)

        c_events = results['C']['events']
        c_decision = next(e for e in c_events if e['event'] == 'source_decision')
        c_replay = next(e for e in c_events if e['event'] == 'source_replayed')
        self.assertEqual(c_decision['expectation'], 'EXPECTED BEFORE REPLAY')
        self.assertLess(c_events.index(c_decision), c_events.index(c_replay))
        self.assertEqual(c_replay['evidence'], replay['action-1']['evidence'])
        self.assertEqual(c_replay['quoted_cost_micro_usd'], 10)

        # Results differ by design: C exposes proposal+trace rather than the
        # baseline's citations/explanation. Neither is a semantic adjudication.
        self.assertEqual(results['C']['status'], 'proposal')
        for arm in ('A', 'B', 'B_self_check'):
            self.assertEqual(results[arm]['status'], 'completed')
            self.assertEqual(results[arm]['result']['answers'][0]['label'], 'direct')
        self.assertEqual(results['C']['proposed_answers'][0]['label'], 'direct')
        self.assertEqual((task, replay), original)


if __name__ == '__main__':
    unittest.main()
