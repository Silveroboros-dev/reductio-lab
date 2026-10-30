"""Bounded offline replay of previously captured source actions.

This component makes no network calls. Source content is exposed only after an
allowed action; hashes identify local artifacts but are not external attestations.
"""
from __future__ import annotations

import copy
import hashlib
import json
from typing import Any


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode()


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


class ReplayCase:
    def __init__(self, checkpoint: dict, replay_catalog: list[dict]):
        self._task = copy.deepcopy(checkpoint['input'])
        self._id = checkpoint['case_id']
        if digest(self._task) != checkpoint['input_version']:
            raise ValueError('input version mismatch')
        self._cap = self._task['replay_max_actions']
        self._money = self._task['replay_max_simulated_micro_usd']
        if type(self._cap) is not int or self._cap < 0 or type(self._money) is not int or self._money < 0:
            raise ValueError('invalid replay caps')
        self._catalog = {}
        for x in self._task['tool_catalog']:
            aid, price = x['action_id'], x['quoted_micro_usd']
            if not isinstance(aid, str) or not aid or aid in self._catalog or type(price) is not int or price < 0:
                raise ValueError('invalid action catalog')
            if not isinstance(x['description'], str):
                raise ValueError('invalid action description')
            self._catalog[aid] = copy.deepcopy(x)
        initial = self._task['initial_evidence']
        self._observed = {}
        for x in initial:
            aid, saved = x['action_id'], x['response']
            if aid in self._observed or digest(saved['payload']) != saved['response_sha256']:
                raise ValueError('invalid initial evidence binding')
            self._observed[aid] = copy.deepcopy(saved)
        consumed = self._task['preconsumed_action_ids']
        if len(consumed) != len(set(consumed)) or set(consumed) != set(self._observed) or set(consumed) & set(self._catalog):
            raise ValueError('initial evidence binding mismatch')
        self._sources = {}
        for item in replay_catalog:
            if item.get('case_id') != self._id:
                continue
            aid = item['action_id']
            if aid in self._sources or aid not in self._catalog or item['capture_ref'] != self._catalog[aid]['capture_ref']:
                raise ValueError('action source binding mismatch')
            saved = item['saved_response']
            if digest(saved['payload']) != saved['response_sha256']:
                raise ValueError('saved response hash mismatch')
            self._sources[aid] = copy.deepcopy(saved)
        if set(self._sources) != set(self._catalog):
            raise ValueError('incomplete replay catalog')
        self._used: set[str] = set()
        self._spent = 0

    def visible(self) -> dict:
        """Return only current evidence and actionable descriptions, never unchosen content."""
        available = [{'action_id': aid, 'description': item['description'],
                      'quoted_micro_usd': item['quoted_micro_usd']}
                     for aid, item in self._catalog.items()
                     if aid not in self._used and len(self._used) < self._cap
                     and self._spent + item['quoted_micro_usd'] <= self._money]
        return {'question': self._task['task'], 'thesis': self._task['thesis'],
                'information_cutoff': self._task.get('information_cutoff'),
                'observed': [{'action_id': aid, 'response': copy.deepcopy(saved)}
                             for aid, saved in self._observed.items()],
                'available_actions': available, 'remaining_actions': self._cap - len(self._used),
                'simulated_spent_micro_usd': self._spent}

    def retrieve(self, action_id: str) -> dict:
        """Replay a single allowed saved action and return only its observed data."""
        allowed = {x['action_id'] for x in self.visible()['available_actions']}
        if action_id not in allowed:
            raise ValueError('action unavailable, repeated or over cap')
        self._used.add(action_id)
        self._spent += self._catalog[action_id]['quoted_micro_usd']
        self._observed[action_id] = copy.deepcopy(self._sources[action_id])
        return copy.deepcopy(self._sources[action_id])
