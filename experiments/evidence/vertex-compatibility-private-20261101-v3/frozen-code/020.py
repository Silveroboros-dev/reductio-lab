"""Blinded-by-field model review packet; never a human adjudication."""
from __future__ import annotations
import copy
from .replay_sources import ReplayCase


def review_packet(checkpoint, catalog, outcome, rubric):
    """Reconstruct only evidence reached by this arm and redact arm identity.

    Blindness is limited to excluded fields; output wording can identify an arm.
    The provided rubric is candidate source/reference evidence, not human review
    of the new answer. Model text is untrusted throughout.
    """
    replay = ReplayCase(checkpoint, catalog)
    decisions = []
    proposed = []
    for event in outcome.get('history', []):
        if event.get('kind') == 'model_decision':
            raw = event.get('output')
            if not isinstance(raw, dict):
                raw = event.get('outcome', {}).get('result')
            if isinstance(raw, dict):
                proposed.append({'choice': raw.get('choice', raw.get('answer')),
                                 'reason': raw.get('reason'), 'expected_result': raw.get('expected_result')})
        if event.get('kind') == 'replay_retrieval':
            replay.retrieve(event['action_id'])
            decisions.append({'action_id': event['action_id']})
        elif event.get('kind') == 'stop':
            decisions.append({'action_id': 'STOP'})
    initial = ReplayCase(checkpoint, catalog).visible()
    observed = replay.visible()['observed']
    return {'question': initial['question'], 'thesis': initial['thesis'],
            'information_cutoff': initial['information_cutoff'],
            'action_descriptions': initial['available_actions'],
            'observed': observed, 'proposed_decisions': proposed, 'actions_taken': decisions,
            'final_result': copy.deepcopy(outcome.get('result')),
            'source_reference_rubric': copy.deepcopy(rubric)}


def validate_review(value):
    """Check shape only; content and reviewer independence remain unverified."""
    if not isinstance(value, dict):
        raise ValueError('review must be an object')
    keys = {'answer_verdict', 'action_verdict', 'alignment_verdict', 'explanation'}
    if set(value) != keys:
        raise ValueError('invalid review keys')
    if value['answer_verdict'] not in ('supported', 'scoped_unknown', 'unsupported', 'unclear'):
        raise ValueError('invalid answer verdict')
    if value['action_verdict'] not in ('reasonable', 'problem', 'unclear'):
        raise ValueError('invalid action verdict')
    if value['alignment_verdict'] not in ('respected', 'concern', 'unclear'):
        raise ValueError('invalid alignment verdict')
    if not isinstance(value['explanation'], str) or not value['explanation'].strip():
        raise ValueError('review needs explanation')
    return {'review': copy.deepcopy(value), 'origin': 'model_advisory',
            'human_review': 'not_performed', 'independence': 'same_model_separate_prompt_not_independent'}
