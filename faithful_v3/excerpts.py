"""Validate selections against captured passages, not an unseen original document."""
from __future__ import annotations

import hashlib
import json
from typing import Any

from reasoning_engine.engine import InvalidOutput
from reasoning_engine.replay_sources import digest


def _int(value: Any) -> bool:
    return type(value) is int


def source_registry(evidence: list[dict]) -> dict[str, dict]:
    """Build a per-input registry; a saved response hash binds payload bytes only."""
    registry = {}
    for item in evidence:
        if item.get('kind') == 'derived_claim':
            continue
        if item.get('text_representation') == 'caller_text':
            continue
        if item.get('text_representation') == 'saved_payload_text':
            raw_ref = item.get('raw_ref')
            if raw_ref is not None and raw_ref != 'sha256:' + digest(item['text']):
                raise InvalidOutput('saved response hash mismatch')
            continue
        try:
            payload = json.loads(item['text'])
        except (ValueError, TypeError) as exc:
            if item.get('text_representation') == 'saved_payload_json':
                raise InvalidOutput('invalid saved JSON text representation') from exc
            continue
        if item.get('text_representation') == 'saved_payload_json':
            raw_ref = item.get('raw_ref')
            if raw_ref is not None and raw_ref != 'sha256:' + digest(payload):
                raise InvalidOutput('saved response hash mismatch')
        if not isinstance(payload, dict) or 'passages' not in payload:
            continue
        passages, coverage, size = payload['passages'], payload.get('coverage'), payload.get('source_document_char_count')
        if not isinstance(passages, list) or not isinstance(coverage, dict) or not _int(size) or size < 0:
            raise InvalidOutput('invalid saved passage bundle')
        if coverage.get('range_unit') != 'unicode_code_points':
            raise InvalidOutput('unsupported saved passage offset unit')
        ranges = coverage.get('visible_char_ranges')
        if not isinstance(ranges, list) or any(
            not isinstance(r, list) or len(r) != 2 or not all(_int(v) for v in r)
            or not 0 <= r[0] < r[1] <= size for r in ranges
        ):
            raise InvalidOutput('invalid visible passage ranges')
        sha = digest(payload)
        raw_ref = item.get('raw_ref')
        if raw_ref is not None and raw_ref != 'sha256:' + sha:
            raise InvalidOutput('saved response hash mismatch')
        entries = {}
        for passage in passages:
            if not isinstance(passage, dict):
                raise InvalidOutput('invalid saved passage')
            ident, start, end, text = (passage.get(k) for k in ('id', 'start_char', 'end_char', 'text'))
            if (not isinstance(ident, str) or not ident or ident in entries or not _int(start) or not _int(end)
                    or not isinstance(text, str) or not 0 <= start < end <= size or end - start != len(text)
                    or not any(r[0] <= start and end <= r[1] for r in ranges)):
                raise InvalidOutput('invalid saved passage identity or bounds')
            entries[ident] = {'start_char': start, 'end_char': end, 'text': text}
        ordered = sorted(entries.values(), key=lambda p: (p['start_char'], p['end_char']))
        for index, left in enumerate(ordered):
            for right in ordered[index + 1:]:
                if right['start_char'] >= left['end_char']:
                    break
                start = right['start_char']
                end = min(left['end_char'], right['end_char'])
                left_text = left['text'][start - left['start_char']:end - left['start_char']]
                right_text = right['text'][:end - start]
                if left_text != right_text:
                    raise InvalidOutput('overlapping saved passages disagree')
        registry[item['id']] = {'passages': entries, 'raw_ref': raw_ref,
                                'saved_payload_sha256': sha,
                                'binding': 'caller_supplied_hash_consistency' if raw_ref else 'caller_supplied_payload'}
    return registry


def resolve_selection(items: list, nodes: dict, source_ids: set[str], registry: dict) -> tuple[list[str], list[dict], list[dict]]:
    """Resolve model selection to exact saved substrings and explicit source refs."""
    ids, selected, refs = [], [], []
    for item in items:
        if isinstance(item, str):
            ident = item
            if ident in registry:
                raise InvalidOutput('structured source requires explicit passage spans')
            spans = None
        elif isinstance(item, dict) and set(item) == {'id', 'spans'}:
            ident, spans = item['id'], item['spans']
            if not isinstance(ident, str) or ident not in source_ids:
                raise InvalidOutput('span selection requires a source')
            if not isinstance(spans, list) or not spans:
                raise InvalidOutput('source spans must be nonempty')
        else:
            raise InvalidOutput('invalid selection item')
        if not isinstance(ident, str) or not ident or ident not in nodes or ident in ids:
            raise InvalidOutput('selection has unknown, duplicate or empty IDs')
        ids.append(ident)
        node = nodes[ident]
        if spans is None:
            selected.append({'text': node['text'], 'source': node.get('source', 'model inference, not source fact'),
                             'kind': node.get('kind', 'derived_claim')})
            if ident in source_ids:
                refs.append({'id': ident, 'source': node.get('source'), 'raw_ref': node.get('raw_ref'),
                             'scope': 'whole_saved_response', 'excerpt_offsets': None})
            continue
        seen = set()
        for span in spans:
            if ident not in registry:
                if not isinstance(span, dict) or set(span) != {'start_char', 'end_char'}:
                    raise InvalidOutput('invalid unstructured text span')
                start, end = span['start_char'], span['end_char']
                if not _int(start) or not _int(end) or not 0 <= start < end <= len(node['text']) or (start, end) in seen:
                    raise InvalidOutput('unstructured text span is duplicate or out of bounds')
                seen.add((start, end))
                representation = node.get('text_representation', 'caller_text')
                raw_ref = node.get('raw_ref')
                payload_sha = None
                try:
                    surface_hash = hashlib.sha256(node['text'].encode('utf-8')).hexdigest()
                    if representation == 'saved_payload_text':
                        payload_sha = digest(node['text'])
                    elif representation == 'saved_payload_json':
                        payload_sha = digest(json.loads(node['text']))
                    if payload_sha is not None and raw_ref is not None and raw_ref != 'sha256:' + payload_sha:
                        raise InvalidOutput('saved response hash mismatch')
                    text = node['text'][start:end]
                    excerpt_hash = hashlib.sha256(text.encode('utf-8')).hexdigest()
                except InvalidOutput:
                    raise
                except (UnicodeError, ValueError, TypeError) as exc:
                    raise InvalidOutput('invalid saved text encoding or representation') from exc
                selected.append({'text': text, 'source': node.get('source'), 'kind': node.get('kind')})
                refs.append({'id': ident, 'source': node.get('source'), 'raw_ref': raw_ref,
                             'scope': 'saved_response_text_span', 'text_representation': representation,
                             'start_char': start, 'end_char': end, 'offset_unit': 'unicode_code_points',
                             'offset_basis': 'saved_evidence_text_not_original_document',
                             'evidence_text_sha256': surface_hash, 'excerpt_sha256': excerpt_hash,
                             'saved_payload_sha256': payload_sha,
                             'binding': 'caller_supplied_hash_consistency' if payload_sha and raw_ref else 'caller_supplied_text'})
                continue
            if not isinstance(span, dict) or set(span) != {'passage_id', 'start_char', 'end_char'}:
                raise InvalidOutput('invalid source span')
            passage_id, start, end = span['passage_id'], span['start_char'], span['end_char']
            if not isinstance(passage_id, str) or not _int(start) or not _int(end):
                raise InvalidOutput('invalid source span types')
            key = (passage_id, start, end)
            passage = registry[ident]['passages'].get(passage_id)
            if key in seen or passage is None or not passage['start_char'] <= start < end <= passage['end_char']:
                raise InvalidOutput('source span is duplicate or outside saved passage')
            seen.add(key)
            text = passage['text'][start - passage['start_char']:end - passage['start_char']]
            selected.append({'text': text, 'source': node.get('source'), 'kind': node.get('kind')})
            refs.append({'id': ident, 'source': node.get('source'), 'raw_ref': registry[ident]['raw_ref'],
                         'saved_payload_sha256': registry[ident]['saved_payload_sha256'],
                         'binding': registry[ident]['binding'], 'scope': 'saved_passage_span',
                         'passage_id': passage_id, 'start_char': start, 'end_char': end,
                         'offset_unit': 'unicode_code_points', 'document_offsets': 'source_reported_not_independently_verified',
                         'excerpt_sha256': hashlib.sha256(text.encode('utf-8')).hexdigest()})
    return ids, selected, refs
