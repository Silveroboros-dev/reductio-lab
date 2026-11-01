"""Check previously saved source passages offline; no model or source calls.

Private historical inputs are loaded and verified by the local research loader;
no source text is copied into this diagnostic or printed by it.
"""
import copy
import json
import sys
from pathlib import Path

from faithful_v3.excerpts import resolve_selection, source_registry
from reasoning_engine.engine import InvalidOutput
from reasoning_engine.replay_sources import ReplayCase
from research.live_run import load_inputs

if len(sys.argv) != 2:
    raise SystemExit('usage: python offline-span-provenance-20261101.py PRIVATE_CONTRACT_JSON')
case_ids = json.loads(Path(sys.argv[1]).read_text())['cases']
assert len(case_ids) == 12 and len(set(case_ids)) == 12
_, bundle, _, bindings = load_inputs()
checkpoints = {c['case_id']: c for c in bundle['checkpoints']}
responses = passages = 0
for case_id in case_ids:
    checkpoint = checkpoints[case_id]
    ReplayCase(checkpoint, bundle['replay_catalog'])
    saved_items = [(x['action_id'], x['response']) for x in checkpoint['input']['initial_evidence']]
    saved_items += [(x['action_id'], x['saved_response']) for x in bundle['replay_catalog'] if x['case_id'] == case_id]
    for action_id, saved in saved_items:
        payload = saved['payload']
        entry = {'id': 'source:' + action_id, 'kind': 'observation', 'source': 'captured response',
                 'raw_ref': 'sha256:' + saved['response_sha256'],
                 'text': json.dumps(payload, ensure_ascii=False, sort_keys=True)}
        registry = source_registry([entry])
        assert entry['id'] in registry
        for passage in payload['passages']:
            choose = {'id': entry['id'], 'spans': [{'passage_id': passage['id'],
                       'start_char': passage['start_char'], 'end_char': passage['end_char']}]}
            _, texts, refs = resolve_selection([choose], {entry['id']: entry}, {entry['id']}, registry)
            assert texts[0]['text'] == passage['text']
            assert refs[0]['saved_payload_sha256'] == saved['response_sha256']
            assert refs[0]['document_offsets'] == 'source_reported_not_independently_verified'
            bad = copy.deepcopy(choose)
            bad['spans'][0]['start_char'] = passage['start_char'] - 1
            try:
                resolve_selection([bad], {entry['id']: entry}, {entry['id']}, registry)
            except InvalidOutput:
                pass
            else:
                raise AssertionError('out-of-passage span accepted')
            passages += 1
        changed = copy.deepcopy(entry)
        changed['raw_ref'] = 'sha256:' + '0' * 64
        try:
            source_registry([changed])
        except InvalidOutput:
            pass
        else:
            raise AssertionError('response hash mismatch accepted')
        responses += 1
print(json.dumps({'cases': len(case_ids), 'saved_responses': responses, 'saved_passages': passages,
                  'bundle_canonical_sha256': bindings['bundle_canonical'],
                  'live_model_or_source_calls': 0, 'original_document_offsets_verified': False}))
