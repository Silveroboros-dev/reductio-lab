import copy
import pytest
from reasoning_engine.replay_sources import ReplayCase, digest


def fixture():
    payload = {'text': 'hidden source result'}
    saved = {'payload': payload, 'response_sha256': digest(payload)}
    inp = {'task': 'Question', 'thesis': 'Thesis', 'initial_evidence': [], 'preconsumed_action_ids': [],
           'replay_max_actions': 1, 'replay_max_simulated_micro_usd': 20,
           'tool_catalog': [{'action_id': 'a', 'description': 'Search', 'quoted_micro_usd': 10, 'capture_ref': 'capture'},
                            {'action_id': 'b', 'description': 'Other', 'quoted_micro_usd': 10, 'capture_ref': 'capture2'}]}
    checkpoint = {'case_id': 'c', 'input': inp, 'input_version': digest(inp)}
    rows = [{'case_id': 'c', 'action_id': aid, 'capture_ref': capture, 'saved_response': saved}
            for aid, capture in [('a', 'capture'), ('b', 'capture2')]]
    return checkpoint, rows


def test_hidden_source_only_visible_after_matching_action_and_cap():
    checkpoint, rows = fixture()
    replay = ReplayCase(checkpoint, rows)
    assert 'hidden source result' not in str(replay.visible())
    assert replay.retrieve('a')['payload']['text'] == 'hidden source result'
    assert 'hidden source result' in str(replay.visible())
    with pytest.raises(ValueError): replay.retrieve('b')
    with pytest.raises(ValueError): replay.retrieve('a')


def test_corrupt_source_and_cross_case_binding_are_rejected():
    checkpoint, rows = fixture()
    rows[0]['saved_response']['payload']['text'] = 'tampered'
    with pytest.raises(ValueError): ReplayCase(checkpoint, rows)
    checkpoint, rows = fixture()
    rows[0]['case_id'] = 'other'
    with pytest.raises(ValueError): ReplayCase(checkpoint, rows)


def test_models_cannot_mutate_internal_snapshots():
    checkpoint, rows = fixture()
    replay = ReplayCase(checkpoint, rows)
    replay.visible()['available_actions'][0]['description'] = 'mutated'
    assert replay.visible()['available_actions'][0]['description'] == 'Search'
    received = replay.retrieve('a')
    received['payload']['text'] = 'mutated'
    assert replay.visible()['observed'][0]['response']['payload']['text'] == 'hidden source result'
