"""Offline regression tests; all model responses and sources are fixtures."""
import copy
import json
import unittest

from faithful_v3.action_case import run_case
from faithful_v3.engine import StrictEngine
from faithful_v3.prompts import bind_model, build_request
from reasoning_engine.engine import EngineConfig
from reasoning_engine.renderer import render_outcome
from test_strict_v3 import checkpoint_fixture, engine_task


class FeedbackAndUnknownTests(unittest.TestCase):
    def test_feedback_is_branch_local_and_never_reaches_inference(self):
        calls = []
        first = [True]

        def requester(request):
            stage, payload = request['stage'], request['input']
            calls.append((stage, copy.deepcopy(payload)))
            if stage == 'selection':
                feedback = payload['halter_feedback']
                if first[0]:
                    first[0] = False
                    self.assertIsNone(feedback)
                    return {'alternatives': [['s1'], ['s2']]}
                self.assertEqual(feedback['origin'], 'model_unverified')
                source = 's1' if feedback['reason'] == 'feedback A' else 's2'
                self.assertEqual(feedback['reason'], 'feedback A' if source == 's1' else 'feedback B')
                self.assertNotIn(feedback['reason'], json.dumps(payload['available_statements']))
                return {'alternatives': [[source]]}
            if stage == 'inference':
                self.assertEqual(set(payload), {'selected_texts'})
                self.assertNotIn('feedback', json.dumps(payload))
                return {'conclusion': payload['selected_texts'][0]['text']}
            if stage == 'halter':
                return {'sufficient': False, 'reason': 'feedback A' if payload['current_inference'] == 'premise A' else 'feedback B'}
            if stage == 'value':
                return {'score': 0.1 if payload['trace'][-1]['conclusion'] == 'premise A' else 0.9}
            raise AssertionError(stage)

        out = StrictEngine(bind_model(requester), EngineConfig(max_calls=16, max_depth=2, beam_width=2)).run(engine_task())
        selections = [p for s, p in calls if s == 'selection']
        self.assertEqual([p['halter_feedback']['reason'] for p in selections[1:]], ['feedback B', 'feedback A'])
        self.assertEqual(len({p['halter_feedback']['branch_id'] for p in selections[1:]}), 2)
        self.assertEqual((out['status'], out['reason']), ('unknown', 'reasoning_depth_exhausted'))
        explanation = out['unknown_explanation']
        self.assertEqual(explanation['stop_reason'], 'reasoning_depth_exhausted')
        self.assertEqual(explanation['unresolved_questions'][0]['question'], engine_task()['required_questions'][0]['question'])
        self.assertEqual(len(explanation['model_assessments']), 4)
        for item in explanation['model_assessments']:
            self.assertEqual(item['origin'], 'model_unverified')
            self.assertEqual([r['id'] for r in item['selected_source_refs']], ['s1' if item['reason'] == 'feedback A' else 's2'])
        rendered = render_outcome(out)
        self.assertIn('Unverified Halter assessment', rendered)
        self.assertIn('feedback A', rendered)

    def test_budget_and_uncertain_call_do_not_claim_insufficient_evidence(self):
        def model(stage, payload):
            if stage == 'selection': return {'alternatives': [['s1']]}
            if stage == 'inference': return {'conclusion': 'some inference'}
            if stage == 'halter': return {'sufficient': False, 'reason': 'unverified prior feedback'}
            if stage == 'value': return {'score': 0.5}
            raise AssertionError(stage)
        out = StrictEngine(model, EngineConfig(max_calls=5, max_depth=2)).run(engine_task())
        self.assertEqual(out['reason'], 'generation_cap_exhausted')
        self.assertEqual(out['unknown_explanation']['stop_kind'], 'execution_limit')
        self.assertEqual(out['unknown_explanation']['model_assessments'][0]['origin'], 'model_unverified')
        timed = StrictEngine(lambda s, p: (_ for _ in ()).throw(TimeoutError())).run(engine_task())
        self.assertEqual(timed['reason'], 'callback_effect_uncertain:TimeoutError')
        self.assertEqual(timed['unknown_explanation']['stop_kind'], 'effect_uncertain')
        self.assertEqual(timed['unknown_explanation']['model_assessments'], [])

    def test_source_unknown_and_nested_unknown_are_exposed(self):
        checkpoint, catalog = checkpoint_fixture(with_initial=True)
        source_unknown = run_case(checkpoint, catalog, lambda s, p: {
            'choice': 'UNKNOWN', 'reason': 'Cannot choose a source responsibly', 'expected_result': 'none'})
        x = source_unknown['unknown_explanation']
        self.assertEqual(x['stop_reason'], 'source_decision_uncertain')
        self.assertEqual(x['stop_kind'], 'model_decision')
        self.assertEqual(x['source_decision']['origin'], 'model_unverified')
        self.assertEqual(x['available_saved_sources'][0]['id'], 'source:initial')
        self.assertNotIn('DATA_A', json.dumps(x))
        self.assertIn('Unverified source-decision assessment', render_outcome(source_unknown))
        self.assertIn('Saved responses available in this run: source:initial', render_outcome(source_unknown))

        def callback(stage, payload):
            if stage == 'source_decision': return {'choice': 'STOP', 'reason': 'stop acquiring', 'expected_result': 'none'}
            if stage == 'selection': return {'alternatives': [['source:initial']]}
            if stage == 'inference': return {'conclusion': 'only saved observation'}
            if stage == 'halter': return {'sufficient': False, 'reason': 'requested metric is missing'}
            if stage == 'value': return {'score': 0.4}
            raise AssertionError(stage)
        out = run_case(checkpoint, catalog, callback, max_depth=1)
        nested = out['history'][-1]['outcome']['unknown_explanation']
        outer = out['unknown_explanation']
        self.assertEqual(outer['model_assessments'], nested['model_assessments'])
        self.assertEqual(outer['model_assessments'][0]['reason'], 'requested metric is missing')
        self.assertEqual(outer['model_assessments'][0]['selected_source_refs'][0]['id'], 'source:initial')
        self.assertEqual(out['status'], 'unknown')
        self.assertIsNone(out['result'])
        rendered = render_outcome(out)
        self.assertIn('requested metric is missing', rendered)
        self.assertNotIn('No coverage records were saved', rendered)

    def test_late_failure_and_timeout_do_not_relabel_prior_halt(self):
        for failure in (TimeoutError, ValueError):
            calls = {'selection': 0}
            def callback(stage, payload):
                if stage == 'selection':
                    calls['selection'] += 1
                    if calls['selection'] == 2:
                        raise failure('fixture')
                    return {'alternatives': [['s1']]}
                if stage == 'inference': return {'conclusion': 'x'}
                if stage == 'halter': return {'sufficient': False, 'reason': 'unverified missing fact'}
                if stage == 'value': return {'score': 0.5}
                raise AssertionError(stage)
            out = StrictEngine(callback, EngineConfig(max_calls=10, max_depth=2)).run(engine_task())
            self.assertEqual(out['unknown_explanation']['model_assessments'], [])
            self.assertEqual(out['unknown_explanation']['stop_kind'],
                             'effect_uncertain' if failure is TimeoutError else 'technical_failure')
            self.assertEqual(len([e for e in out['events'] if e.get('event') == 'step_proposed']), 1)

    def test_invalid_halter_is_technical_failure_and_inputs_are_strict(self):
        def bad(stage, payload):
            if stage == 'selection': return {'alternatives': [['s1']]}
            if stage == 'inference': return {'conclusion': 'x'}
            if stage == 'halter': return {'sufficient': False, 'reason': ''}
            raise AssertionError(stage)
        out = StrictEngine(bad).run(engine_task())
        self.assertEqual(out['status'], 'technical_failure')
        self.assertEqual(out['unknown_explanation']['model_assessments'], [])
        with self.assertRaises(ValueError):
            build_request('inference', {'selected_texts': [], 'halter_feedback': {'reason': 'x'}})
        with self.assertRaises(ValueError):
            build_request('formatter', {'final_inference': 'x', 'allowed_citation_ids': [], 'halter_feedback': 'x'})


if __name__ == '__main__':
    unittest.main()
