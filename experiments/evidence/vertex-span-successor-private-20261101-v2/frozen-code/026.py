"""Offline role-wiring regressions; scripted decisions are not semantic validation."""
from __future__ import annotations

import json
import unittest

from faithful_v3.action_case import run_case
from faithful_v3.engine import StrictEngine
from faithful_v3.prompts import bind_model
from reasoning_engine.engine import EngineConfig
from reasoning_engine.replay_sources import digest


def lark_case():
    """The synthetic rule, tally, thesis, and citation request from the v3 canary."""
    rule = {'text': 'For batch LARK-7, the target is met only if at least 7 of 10 final checks pass.'}
    tally = {'text': 'Final audit of batch LARK-7: 6 of 10 checks passed; 4 failed.'}
    task = {
        'thesis': 'Batch LARK-7 met its final audit target.',
        'task': 'Assess the thesis using only saved source evidence. Cite the saved source IDs; the thesis is a user claim, not a source fact.',
        'information_cutoff': '2026-10-29T13:00:00Z',
        'replay_max_actions': 1, 'replay_max_simulated_micro_usd': 0,
        'tool_catalog': [{'action_id': 'tally', 'description': 'Open the saved final tally.',
                          'quoted_micro_usd': 0, 'capture_ref': 'tally-capture'}],
        'initial_evidence': [{'action_id': 'rule', 'response': {'payload': rule, 'response_sha256': digest(rule)}}],
        'preconsumed_action_ids': ['rule'],
    }
    checkpoint = {'case_id': 'lark-7', 'input': task, 'input_version': digest(task)}
    catalog = [{'case_id': 'lark-7', 'action_id': 'tally', 'capture_ref': 'tally-capture',
                'saved_response': {'payload': tally, 'response_sha256': digest(tally)}}]
    return checkpoint, catalog


class HalterFormatterAlignmentTests(unittest.TestCase):
    def test_canary_factual_negation_reaches_formatter_with_citations(self):
        checkpoint, catalog = lark_case()
        stages = []
        conclusion = ('For batch LARK-7, the target was not met because only 6 of the 10 '
                      'final checks passed, which is fewer than the required minimum of 7.')

        def requester(request):
            stage, payload = request['stage'], request['input']
            stages.append(stage)
            if stage == 'source_decision':
                return {'choice': 'tally', 'reason': 'retrieve the tally', 'expected_result': 'final count'}
            if stage == 'selection':
                self.assertIn('Cite the saved source IDs', payload['question'])
                return {'alternatives': [['source:rule', 'source:tally']]}
            if stage == 'inference':
                self.assertEqual(set(payload), {'selected_texts'})
                self.assertNotIn('source:rule', json.dumps(payload))
                self.assertNotIn('source:tally', json.dumps(payload))
                self.assertNotIn('Batch LARK-7 met its final audit target.', json.dumps(payload))
                return {'conclusion': conclusion}
            if stage == 'halter':
                self.assertIn('Cite the saved source IDs', payload['question'])
                self.assertIn('2026-10-29T13:00:00Z', payload['question'])
                self.assertEqual(payload['current_inference'], conclusion)
                instruction = request['instruction']
                self.assertIn('negative answer', instruction)
                self.assertIn('information boundary', instruction)
                self.assertIn('source restrictions', instruction)
                self.assertIn('citation IDs', instruction)
                self.assertIn('Formatter', instruction)
                return {'sufficient': True, 'reason': 'scripted judgment: 6 is below 7, so thesis is negated'}
            if stage == 'value':
                return {'score': 0.8}
            if stage == 'formatter':
                self.assertEqual(set(payload), {'final_inference', 'allowed_citation_ids'})
                self.assertEqual(payload['final_inference'], conclusion)
                self.assertEqual(payload['allowed_citation_ids'], ['source:rule', 'source:tally'])
                self.assertNotIn('Batch LARK-7 met its final audit target.', json.dumps(payload))
                return {'answer': conclusion, 'citations': payload['allowed_citation_ids']}
            self.fail(stage)

        out = run_case(checkpoint, catalog, bind_model(requester), max_calls=6,
                       max_depth=1, beam_width=1, max_alternatives=1)
        self.assertEqual(out['status'], 'proposal')
        self.assertEqual(stages, ['source_decision', 'selection', 'inference', 'halter', 'value', 'formatter'])
        self.assertEqual(out['result']['citations'], ['source:rule', 'source:tally'])
        final = out['history'][-1]['outcome']
        self.assertEqual(final['coverage'][0]['assessment_origin'], 'model_unverified')
        self.assertEqual(final['semantic_status'], 'unreviewed')

    def test_substantive_metric_gap_remains_insufficient(self):
        target = 'What was nominal GDP growth in 2025?'
        task = {'case_id': 'metric-gap', 'question': target + '\nTask instructions: Cite the source IDs.',
                'task_type': 'exploration', 'evidence': [
                    {'id': 'real-gdp', 'kind': 'observation', 'source': 'fixture', 'text': 'Real GDP growth was 2.2% in 2025.'}],
                'required_questions': [{'id': 'target', 'question': target, 'evidence_ids': []}]}
        stages = []

        def requester(request):
            stage, payload = request['stage'], request['input']
            stages.append(stage)
            if stage == 'selection':
                return {'alternatives': [['real-gdp']]}
            if stage == 'inference':
                self.assertEqual(set(payload), {'selected_texts'})
                return {'conclusion': 'Real GDP growth was 2.2% in 2025.'}
            if stage == 'halter':
                self.assertIn('metric', request['instruction'])
                return {'sufficient': False, 'reason': 'real GDP does not answer nominal GDP',
                        'evidence_assessment': 'insufficient'}
            if stage == 'value':
                return {'score': 0.2}
            self.fail(stage)

        out = StrictEngine(bind_model(requester), EngineConfig(max_calls=5, max_depth=1)).run(task)
        self.assertEqual((out['status'], out['reason']), ('unknown', 'reasoning_depth_exhausted'))
        self.assertEqual(stages, ['selection', 'inference', 'halter', 'value'])
        self.assertIsNone(out['result'])
        self.assertEqual(out['unknown_explanation']['model_assessments'][0]['origin'], 'model_unverified')

    def test_formatter_still_cannot_cite_outside_selected_ancestry(self):
        checkpoint, catalog = lark_case()

        def requester(request):
            stage = request['stage']
            if stage == 'source_decision':
                return {'choice': 'tally', 'reason': 'retrieve tally', 'expected_result': 'final count'}
            if stage == 'selection':
                return {'alternatives': [['source:rule', 'source:tally']]}
            if stage == 'inference':
                return {'conclusion': 'The target was not met: 6 is below 7.'}
            if stage == 'halter':
                return {'sufficient': True, 'reason': 'scripted sufficient'}
            if stage == 'value':
                return {'score': 0.8}
            if stage == 'formatter':
                return {'answer': request['input']['final_inference'], 'citations': ['source:invented']}
            self.fail(stage)

        out = run_case(checkpoint, catalog, bind_model(requester), max_calls=6,
                       max_depth=1, beam_width=1, max_alternatives=1)
        self.assertEqual(out['status'], 'technical_failure')
        self.assertIsNone(out['result'])
        self.assertIn('citations', out['history'][-1]['outcome']['reason'])


if __name__ == '__main__':
    unittest.main()
