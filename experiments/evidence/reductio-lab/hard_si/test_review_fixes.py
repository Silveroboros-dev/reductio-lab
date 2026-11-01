"""Offline regression tests for intervention selection and run status."""
from __future__ import annotations

from hard_si.run import _intervention_payload, _summary_status


def _matching_step(key, ordinal):
    return {
        'selected_ids': [key['terminal_rule_id'], 'node:prior'],
        'inference_call_ordinal': ordinal,
    }


def _payload(key):
    return {
        'selected_texts': [
            {'text': key['terminal_text'], 'source': 'source', 'kind': 'observation'},
            {'text': f"Derived label {key['terminal_condition']}.",
             'source': 'model', 'kind': 'derived_claim'},
        ]
    }


def test_intervention_finds_earliest_matching_ancestor_once():
    key = {
        'terminal_rule_id': 's007',
        'terminal_text': 'If something has label ABCDE, then it is authorized to enter the sanctuary.',
        'terminal_condition': 'ABCDE',
    }
    first_payload = _payload(key)
    later_payload = _payload(key)
    # The common ordinal-2 ancestor appears in two branches; a later matching
    # leaf must not replace it, and branch traversal order must not decide.
    outcome = {
        'branches': [
            {'steps': [_matching_step(key, 2), {'selected_ids': ['x'], 'inference_call_ordinal': 8}]},
            {'steps': [_matching_step(key, 2), _matching_step(key, 5)]},
        ],
        'events': [
            {'event': 'model_started', 'stage': 'inference', 'ordinal': 2, 'payload': first_payload},
            {'event': 'model_started', 'stage': 'inference', 'ordinal': 5, 'payload': later_payload},
            {'event': 'model_started', 'stage': 'inference', 'ordinal': 8, 'payload': later_payload},
        ],
    }

    sample = _intervention_payload(outcome, key)

    assert sample is not None
    assert sample['inference_ordinal'] == 2
    assert sample['control'] == first_payload
    assert sample['edited']['selected_texts'][1] == first_payload['selected_texts'][1]
    assert sample['edited']['selected_texts'][0]['text'] == key['terminal_text'].replace(
        'then it is authorized', 'then it is not authorized', 1)


def test_summary_status_requires_complete_assignments_and_probes():
    completed = [{'status': 'completed'}, {'status': 'completed'}]
    unavailable = [{'status': 'completed'}, {'status': 'unavailable'}]
    incomplete = [{'status': 'completed'}, {'status': 'incomplete'}]

    assert _summary_status(59, completed) == 'incomplete'
    assert _summary_status(60, []) == 'incomplete_interventions'
    assert _summary_status(60, completed[:1]) == 'incomplete_interventions'
    assert _summary_status(60, incomplete) == 'incomplete_interventions'
    assert _summary_status(60, unavailable) == 'completed_with_unavailable_interventions'
    assert _summary_status(60, completed) == 'completed_unreviewed'

