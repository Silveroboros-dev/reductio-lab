"""Offline diagnostic: saved outputs are fixtures, not new model responses."""
import copy, hashlib, json, sys
from pathlib import Path
from faithful_v3.engine import StrictEngine
from reasoning_engine.engine import EngineConfig

if len(sys.argv) != 2:
    raise SystemExit('usage: python offline-feedback-replay-20261101.py PRIVATE_RUN_DIR')
root = Path(sys.argv[1])
files = sorted(root.glob('*.outcome.json'))
assert len(files) == 12
summary = json.loads((root / 'summary.json').read_text())
assert summary['recorded'] == 12
assert {hashlib.sha256(p.read_bytes()).hexdigest() for p in files} == {r['outcome_sha256'] for r in summary['records']}
results = []
for path in files:
    outer = json.loads(path.read_text())['outcome']
    historical = next(x['outcome'] for x in outer['history'] if x.get('kind') == 'final')
    events = historical['events']
    starts = [x for x in events if x['event'] == 'model_started']
    returned = {x['ordinal']: x for x in events if x['event'] == 'model_returned'}
    first = next(x['payload'] for x in starts if x['stage'] == 'selection')
    task = {'case_id': historical['case_id'], 'question': first['question'],
            'task_type': first['task_type'], 'as_of_utc': first['as_of_utc'],
            'evidence': copy.deepcopy(historical['evidence']),
            'required_questions': copy.deepcopy(first['required_questions'])}
    if historical.get('user_target') is not None:
        task['thesis'] = copy.deepcopy(historical['user_target'])
    recorded_halts = {e['branch_id']: e for e in events
                      if e.get('event') == 'step_proposed' and e.get('sufficient') is False}
    state = {'index': 0, 'stop': False, 'mismatch': None, 'first_feedback': None}

    def fixture(stage, payload):
        # Older outputs are deterministic fixtures even at the initial step,
        # since the current prompt version has changed. Never treat them as a
        # response by the model to the revised request.
        if state['index'] >= len(starts):
            state['mismatch'] = 'extra_callback'
            raise RuntimeError('stop replay')
        entry = starts[state['index']]
        if stage != entry['stage']:
            state['mismatch'] = 'different_stage'
            raise RuntimeError('stop replay')
        compare = copy.deepcopy(payload)
        if stage == 'selection':
            feedback = compare.pop('halter_feedback')
            if feedback is not None:
                expected = recorded_halts.get(feedback['branch_id'])
                assert expected is not None
                assert feedback['branch_id'] == entry['branch_id']
                assert feedback['reason'] == expected['halter_reason']
                assert feedback['conclusion_id'] == expected['conclusion_id']
                assert feedback['halter_call_ordinal'] == expected['halter_call_ordinal']
                assert feedback['origin'] == 'model_unverified'
                assert compare == entry['payload']
                state['first_feedback'] = feedback['branch_id']
                state['stop'] = True
                raise RuntimeError('stopped at changed selection; no response reused')
        if compare != entry['payload']:
            state['mismatch'] = 'different_input'
            raise RuntimeError('stop replay')
        state['index'] += 1
        if entry['ordinal'] not in returned:
            state['mismatch'] = 'historical_response_missing'
            raise RuntimeError('stop replay')
        return copy.deepcopy(returned[entry['ordinal']]['result'])

    source_calls = outer['calls'] - historical['calls']
    eng = StrictEngine(fixture, EngineConfig(max_calls=26-source_calls, max_depth=2, beam_width=2, max_alternatives=2),
                       candidate_findings=historical['candidate_findings'])
    outcome = eng.run(task)
    assert state['mismatch'] is None, (path.name[:6], state['mismatch'])
    if state['stop']:
        assert state['first_feedback'] is not None
    else:
        assert state['index'] == len(starts), (path.name[:6], state['index'], len(starts))
        assert outcome['status'] == historical['status']
    # Exercise deterministic explanation against the original recorded events,
    # without claiming that these are successor model results.
    if historical['status'] == 'unknown':
        report_engine = StrictEngine(lambda *_: (_ for _ in ()).throw(AssertionError('no model call')))
        report_engine.events = copy.deepcopy(events)
        report_engine._branches = copy.deepcopy(historical['branches'])
        explanation = report_engine._explain_stop(task, historical['status'], historical['reason'])
        assert explanation['stop_reason'] == historical['reason']
        assert len(explanation['model_assessments']) == len(recorded_halts)
        source_ids = {item['id'] for item in historical['evidence']}
        for assessment in explanation['model_assessments']:
            original = recorded_halts[assessment['branch_id']]
            assert assessment['reason'] == original['halter_reason']
            assert assessment['origin'] == 'model_unverified'
            assert {x['id'] for x in assessment['selected_source_refs']} <= source_ids
    results.append({'case_prefix': path.name[:6], 'old_status': historical['status'],
                    'old_negative_halts': len(recorded_halts),
                    'stopped_at_new_feedback': state['stop'],
                    'saved_calls_used_as_fixtures': state['index']})
print(json.dumps({'cases': len(results), 'unknown_explanations_checked': sum(x['old_status']=='unknown' for x in results),
                  'feedback_boundaries_checked': sum(x['stopped_at_new_feedback'] for x in results),
                  'unchanged_fixture_sequences': sum(not x['stopped_at_new_feedback'] for x in results),
                  'details': results}, indent=2))
