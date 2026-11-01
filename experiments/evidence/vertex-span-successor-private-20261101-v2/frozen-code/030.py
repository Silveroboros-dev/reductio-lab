"""Offline gate checks; no provider calls or model decisions."""
from research.vertex_span_successor import gate_status


def test_uncertain_effect_is_blocked_even_with_proposal():
    assert gate_status({'status': 'proposal'}, {'uncertain_attempts': 1, 'halted': 'uncertain'}, None, True) == 'blocked'
    assert gate_status({'status': 'unknown', 'reason': 'journal_call_journal_error'},
                       {'uncertain_attempts': 0, 'halted': None}, None, False) == 'blocked'
    assert gate_status({'status': 'technical_failure', 'unknown_explanation': {'callback_effect_state': 'not_established'}},
                       {'uncertain_attempts': 0, 'halted': None}, None, False) == 'blocked'


def test_success_requires_proposal_source_path_and_no_halt():
    clean = {'uncertain_attempts': 0, 'halted': None}
    assert gate_status({'status': 'proposal'}, clean, None, True) == 'passed'
    assert gate_status({'status': 'proposal'}, clean, None, False) == 'failed'
    assert gate_status({'status': 'unknown', 'reason': 'reasoning_depth_exhausted'}, clean, None, True) == 'failed'
    assert gate_status({'status': 'proposal'}, {'uncertain_attempts': 0, 'halted': 'error'}, None, True) == 'failed'
    assert gate_status(None, clean, 'RuntimeError', False) == 'blocked'
