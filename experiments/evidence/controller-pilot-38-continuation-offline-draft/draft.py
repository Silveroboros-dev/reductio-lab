"""Offline-only specification and simulation for 14 unstarted slots.

No provider client, credentials, subprocess, network imports or live dispatch.
No simulation state is an authorization or evidence of provider activity.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path('/Users/rk/.codex/visualizations/2026/10/29/01a1865f-6bd2-75a2-abb1-eb14b071bbe0')
PREDECESSOR = ROOT / 'controller-pilot-38-live-run'
PATHS = {
    'summary': PREDECESSOR / 'summary.json', 'events': PREDECESSOR / 'events.jsonl',
    'config': PREDECESSOR / 'run-config.json', 'runner': ROOT / 'controller-pilot-38-live-runner/runner.py',
    'pilot': ROOT / 'controller-pilot-v2-runner/pilot.py', 'cases': ROOT / 'controller-pilot-v2-inputs/cases.json',
}
HASHES = {
    'summary': 'fcdd19c0339e28f66c33622942a75c280acdcd76c064b5d64dade9d2cd162133',
    'events': 'cb35cf770cc513780b4f71fae2adca98f8e6f88738aef17810781340196245ef',
    'config': '2ba77ab611d20ffa6ab152c3936dce8577ab7cb646890d8a80619d66985e8ea2',
    'runner': '86683096cc918d0bd057f689244fb5af7bde4e97e587e4b97c866bf5a8ba7bd2',
    'pilot': '3d2c05db2666e90d7df9855e6ae2f843bbd2eaff566acf1144f8ecba2ded2e8f',
    'cases': '4165954e6d5e9112014d90e027d70e303e5e77292148151c857595c6cd82220b',
}
MODEL = 'gemini-3.8-flash'
ARMS = ('B', 'B_self_check', 'C')
STARTED = ('amazon_visible:B', 'amazon_visible:B_self_check', 'amazon_visible:C', 'amazon_empty:B_self_check')
REMAINING = ('amazon_empty:C', 'amazon_empty:B', 'nvidia_h100:C', 'nvidia_h100:B', 'nvidia_h100:B_self_check',
             'usgs_withdrawal:B', 'usgs_withdrawal:B_self_check', 'usgs_withdrawal:C',
             'usgs_consumptive:B_self_check', 'usgs_consumptive:C', 'usgs_consumptive:B',
             'bea_state_gdp:C', 'bea_state_gdp:B', 'bea_state_gdp:B_self_check')
CARRY_ATTEMPTS, CARRY_COUNTS, CARRY_MICRO = 43, 8, 423627
MAX_ATTEMPTS, MAX_COUNTS, MAX_MICRO = 111, 87, 10000000
RESERVE_MICRO, PROPOSED_TIMEOUT_SECONDS = 43008, 120


def bound_read(label):
    raw = PATHS[label].read_bytes()
    if hashlib.sha256(raw).hexdigest() != HASHES[label]:
        raise ValueError('predecessor binding mismatch: ' + label)
    return raw


def verify_evidence():
    """Validate byte bindings and 012 terminal; never mutate predecessor."""
    for name in PATHS:
        bound_read(name)
    summary = json.loads(bound_read('summary'))
    config = json.loads(bound_read('config'))
    events = [json.loads(line) for line in bound_read('events').splitlines()]
    data = json.loads(bound_read('cases'))
    if (summary.get('status') != 'stopped_boundary' or summary.get('selected_model') != MODEL or
        summary.get('model_version') != MODEL or summary.get('attempts') != CARRY_ATTEMPTS or
        summary.get('countTokens_total') != CARRY_COUNTS or summary.get('estimated_or_reserved_micro_usd') != CARRY_MICRO):
        raise ValueError('summary accounting or model mismatch')
    canaries = summary.get('canaries', [])
    if (len(canaries) != 1 or canaries[0].get('model') != MODEL or canaries[0].get('status') != 'passed' or
        canaries[0].get('result', {}).get('generations') != 4):
        raise ValueError('prior canary evidence mismatch')
    results = summary.get('results', [])
    if tuple(x.get('slot') for x in results) != STARTED or [x.get('status') for x in results] != ['completed'] * 3 + ['technical_failure']:
        raise ValueError('prior slot or status mismatch')
    if (config.get('runner_sha256') != HASHES['runner'] or config.get('pilot_sha256') != HASHES['pilot'] or
        config.get('cases_sha256') != HASHES['cases'] or config.get('max_attempts') != MAX_ATTEMPTS or
        config.get('max_count_tokens') != MAX_COUNTS or config.get('cap_micro_usd') != MAX_MICRO or
        config.get('reserve_micro_usd') != RESERVE_MICRO or config.get('carry_attempts') != 31 or
        config.get('carry_count_tokens') != 7 or config.get('carry_effective_micro_usd') != 359587):
        raise ValueError('prior runtime or carry mismatch')
    if (config.get('automatic_retries') is not False or config.get('resumable') is not False or
        config.get('input_price_usd_per_million') != '0.75' or config.get('output_price_usd_per_million') != '3.75'):
        raise ValueError('prior runtime policy mismatch')
    starts = [x for x in events if x.get('event') == 'started']
    usage = [x for x in events if x.get('event') == 'usage']
    terminal = [x for x in events if x.get('event') == 'terminal' and not str(x.get('operation', '')).startswith('count-')]
    received = [x for x in events if x.get('event') == 'received']
    if ([x.get('operation') for x in starts] != [f'{i:03d}' for i in range(1,13)] or
        [x.get('operation') for x in usage] != [f'{i:03d}' for i in range(1,12)] or
        [x.get('operation') for x in received] != [f'{i:03d}' for i in range(1,12)] or
        [x.get('operation') for x in terminal] != [f'{i:03d}' for i in range(1,13)]):
        raise ValueError('operation identity or terminal mismatch')
    if (any(x.get('model_version') != MODEL for x in usage) or
        any(x.get('effect') != 'succeeded' for x in terminal[:-1]) or
        terminal[-1].get('effect') != 'uncertain' or terminal[-1].get('capture') != 'unavailable' or
        starts[-1].get('slot') != STARTED[-1] or starts[-1].get('role') != 'after_retrieval' or
        starts[-1].get('reserve_micro_usd') != RESERVE_MICRO or
        sum(x.get('estimated_micro_usd', -1) for x in usage) != 21032 or
        359587 + 21032 + RESERVE_MICRO != CARRY_MICRO):
        raise ValueError('unknown operation or accounting mismatch')
    events_012 = [x.get('event') for x in events if x.get('operation') == '012']
    if events_012 != ['started', 'uncertain', 'terminal'] or (PREDECESSOR / 'response-012.bin').exists():
        raise ValueError('012 must remain uncertain and without response')
    for x in received:
        raw = (PREDECESSOR / ('response-' + x['operation'] + '.bin')).read_bytes()
        if hashlib.sha256(raw).hexdigest() != x.get('raw_sha256'):
            raise ValueError('response receipt mismatch')
    count = [x for x in events if x.get('event') == 'count_started']
    count_received = [x for x in events if x.get('event') == 'count_received']
    if len(count) != 1 or len(count_received) != 1 or count[0].get('operation') != 'count-008':
        raise ValueError('countTokens lineage mismatch')
    raw = (PREDECESSOR / 'count-008.bin').read_bytes()
    if hashlib.sha256(raw).hexdigest() != count_received[0].get('raw_sha256'):
        raise ValueError('countTokens response mismatch')
    if data.get('schema') != 'controller-pilot-v2-cases-v1' or len(data.get('cases', [])) != 6:
        raise ValueError('six cases required')
    all_slots = []
    for i, case in enumerate(data['cases']):
        for arm in ARMS[i % 3:] + ARMS[:i % 3]:
            all_slots.append(case['id'] + ':' + arm)
    if (len(set(all_slots)) != 18 or tuple(all_slots[:4]) != STARTED or tuple(all_slots[4:]) != REMAINING or
        set(STARTED).intersection(REMAINING)):
        raise ValueError('remaining slots mismatch')
    ep_starts = [x.get('slot') for x in events if x.get('event') == 'episode_started']
    if ep_starts != ['canary', *STARTED]:
        raise ValueError('not all remaining slots are unstarted')
    return {'status': 'offline_evidence_bound', 'model_version': MODEL, 'prior_012': 'uncertain',
            'started_slots': STARTED, 'remaining_slots': REMAINING,
            'attempts': CARRY_ATTEMPTS, 'counts': CARRY_COUNTS, 'estimated_plus_reserved_micro_usd': CARRY_MICRO,
            'consecutive_technical_failures': 1, 'proposed_transport_timeout_seconds': PROPOSED_TIMEOUT_SECONDS,
            'authorization': 'pending_user_decision', 'live_dispatch': 'not_implemented'}


class Simulation:
    """Pure mock accounting/order model; never performs any effect."""
    def __init__(self):
        self.attempts = CARRY_ATTEMPTS
        self.counts = CARRY_COUNTS
        self.effective_micro = CARRY_MICRO
        self.failure_streak = 1
        self.started_slots = []
        self.active = None
        self.generations_for_slot = 0
        self.source_reads = 0
        self.stopped = False
        self.pending = False

    def start_slot(self, slot, model):
        if self.stopped or self.pending or self.active is not None or model != MODEL:
            raise ValueError('stopped, already active, or model changed')
        if len(self.started_slots) >= len(REMAINING) or slot != REMAINING[len(self.started_slots)]:
            raise ValueError('slot is not the next previously unstarted assignment')
        self.active = slot
        self.started_slots.append(slot)
        self.generations_for_slot = 0
        self.source_reads = 0

    def attempt(self):
        if (self.stopped or self.pending or self.active is None or self.generations_for_slot >= 4 or
            self.attempts >= MAX_ATTEMPTS or self.effective_micro + RESERVE_MICRO > MAX_MICRO):
            raise ValueError('attempt not eligible under proposed limits')
        self.attempts += 1
        self.generations_for_slot += 1
        self.effective_micro += RESERVE_MICRO
        self.pending = True
        return RESERVE_MICRO

    def settle(self, actual_micro):
        if not self.pending or self.active is None or type(actual_micro) is not int or not 0 <= actual_micro <= RESERVE_MICRO:
            self.stopped = True
            raise ValueError('unknown or over-reservation usage stops')
        self.effective_micro -= RESERVE_MICRO - actual_micro
        self.pending = False

    def count(self):
        if self.stopped or self.pending or self.active is None or self.counts >= MAX_COUNTS:
            raise ValueError('countTokens limit')
        self.counts += 1

    def local_read(self):
        if self.stopped or self.pending or self.active is None or self.source_reads >= 2:
            raise ValueError('saved-source read limit')
        self.source_reads += 1

    def finish_slot(self, success):
        if self.stopped or self.pending or self.active is None or type(success) is not bool:
            raise ValueError('no active slot')
        self.failure_streak = 0 if success else self.failure_streak + 1
        self.active = None
        if self.failure_streak >= 2:
            self.stopped = True

    def uncertain(self):
        if self.active is None:
            raise ValueError('no active slot')
        self.stopped = True


if __name__ == '__main__':
    print(json.dumps(verify_evidence(), ensure_ascii=False))
