"""Separate, explicitly authorised continuation of seven unstarted pilot slots.

Imports only SHA-bound bytes of the pilot runner; never mutates previous runs.
No network or credentials at import. No 429 retry and no repeated canary.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import sys
import time
import types
from pathlib import Path

ROOT = Path('/Users/rk/.codex/visualizations/2026/10/29/01a1865f-6bd2-75a2-abb1-eb14b071bbe0')
PREDECESSOR = ROOT / 'controller-pilot-v2-successor-live-run'
CASES = ROOT / 'controller-pilot-v2-inputs/cases.json'
PILOT = ROOT / 'controller-pilot-v2-runner/pilot.py'
SHA = {
    'summary.json': 'b5cb309d8e9a4987b9d83e1e8fab5271d785748c4c1ccfba444f7afe61c92648',
    'events.jsonl': '96b3561aff08d7478993201b50d34ea443c64e6a13db16b726ffd08b37ef2b4c',
    'run-config.json': '882aaecb543084633f920e8b6a763494671593effc3cd88b1927cb65483c574a',
    'cases': '4165954e6d5e9112014d90e027d70e303e5e77292148151c857595c6cd82220b',
    'pilot': '3d2c05db2666e90d7df9855e6ae2f843bbd2eaff566acf1144f8ecba2ded2e8f',
}
MODEL_VERSION = 'gemini-3.5-flash'
EXPECTED_STARTED = (
    'amazon_visible:B', 'amazon_visible:B_self_check', 'amazon_visible:C',
    'amazon_empty:B_self_check', 'amazon_empty:C', 'amazon_empty:B',
    'nvidia_h100:C', 'nvidia_h100:B', 'nvidia_h100:B_self_check',
    'usgs_withdrawal:B', 'usgs_withdrawal:B_self_check',
)
EXPECTED_REMAINING = (
    'usgs_withdrawal:C', 'usgs_consumptive:B_self_check', 'usgs_consumptive:C',
    'usgs_consumptive:B', 'bea_state_gdp:C', 'bea_state_gdp:B', 'bea_state_gdp:B_self_check',
)


def read_bound(path: Path, digest: str) -> bytes:
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != digest:
        raise ValueError('bound input hash mismatch: ' + path.name)
    return data


def load_pilot():
    raw = read_bound(PILOT, SHA['pilot'])
    module = types.ModuleType('_pilot_v2_frozen')
    module.__file__ = str(PILOT)
    sys.modules[module.__name__] = module
    exec(compile(raw, str(PILOT), 'exec'), module.__dict__)
    return module


def verify_predecessor(pilot):
    config = json.loads(read_bound(PREDECESSOR / 'run-config.json', SHA['run-config.json']))
    summary = json.loads(read_bound(PREDECESSOR / 'summary.json', SHA['summary.json']))
    events = [json.loads(line) for line in read_bound(PREDECESSOR / 'events.jsonl', SHA['events.jsonl']).splitlines()]
    cases = pilot.validate_cases(json.loads(read_bound(CASES, SHA['cases'])))
    if (summary.get('status') != 'stopped_boundary' or summary.get('attempts') != 31 or
        summary.get('estimated_or_reserved_micro_usd') != 359587 or
        config.get('cases_sha256') != SHA['cases'] or config.get('runner_sha256') != SHA['pilot'] or
        config.get('model') != MODEL_VERSION or config.get('input_price_usd_per_million') != '1.50' or
        config.get('output_price_usd_per_million') != '9.00' or config.get('automatic_retries') is not False or
        config.get('resumable') is not False or config.get('reserve_micro_usd') != 98304):
        raise ValueError('predecessor profile mismatch')
    prior = config.get('carried_predecessor', {})
    if prior.get('attempts') != 3 or prior.get('estimated_or_reserved_micro_usd') != 12845 or prior.get('count_attempts') != 0:
        raise ValueError('earlier canary carry mismatch')
    rows = summary.get('results', [])
    if (tuple(x.get('slot') for x in rows) != EXPECTED_STARTED or
        [x.get('status') for x in rows] != ['completed'] * 10 + ['technical_failure']):
        raise ValueError('predecessor assigned slots mismatch')
    canary = summary.get('canary', {})
    if (canary.get('slot') != 'canary' or canary.get('status') != 'completed' or
        canary.get('generations') != 4 or canary.get('critique', {}).get('issue') is not True):
        raise ValueError('canary evidence insufficient')
    episode_starts = [e.get('slot') for e in events if e.get('event') == 'episode_started']
    if episode_starts != ['canary', *EXPECTED_STARTED] or len(episode_starts) != len(set(episode_starts)):
        raise ValueError('episode start history mismatch')
    starts = [e for e in events if e.get('event') == 'started']
    received = [e for e in events if e.get('event') == 'received']
    usage = [e for e in events if e.get('event') == 'usage']
    terminals = [e for e in events if e.get('event') == 'terminal' and not str(e.get('operation', '')).startswith('count-')]
    counts = [e for e in events if e.get('event') == 'count_started']
    if (len(starts) != 28 or len(received) != 28 or len(usage) != 27 or len(terminals) != 28 or len(counts) != 6 or
        any(e.get('model_version') != MODEL_VERSION for e in usage) or
        sum(e.get('estimated_micro_usd', -1) for e in usage) != 248438 or
        12845 + 248438 + 98304 != 359587):
        raise ValueError('predecessor operation, usage or carry mismatch')
    expected_ops = [f'{n:03d}' for n in range(1, 29)]
    if ([e.get('operation') for e in starts] != expected_ops or
        [e.get('operation') for e in received] != expected_ops or
        [e.get('operation') for e in terminals] != expected_ops or
        [e.get('operation') for e in usage] != expected_ops[:-1] or
        any(e.get('effect') != 'succeeded' for e in terminals[:-1]) or
        terminals[-1].get('effect') != 'uncertain' or received[-1].get('http_status') != 429 or
        starts[-1].get('slot') != 'usgs_withdrawal:B_self_check' or starts[-1].get('role') != 'proposal'):
        raise ValueError('429 or operation order evidence mismatch')
    for receipt in received:
        read_bound(PREDECESSOR / ('response-' + receipt['operation'] + '.bin'), receipt['raw_sha256'])
    count_receipts = [e for e in events if e.get('event') == 'count_received']
    if len(count_receipts) != 6 or [e.get('operation') for e in count_receipts] != [f'count-{n:03d}' for n in range(1, 7)]:
        raise ValueError('countTokens receipts mismatch')
    for receipt in count_receipts:
        read_bound(PREDECESSOR / (receipt['operation'] + '.bin'), receipt['raw_sha256'])
    by_id = {c['id']: c for c in cases}
    order = []
    for i, case in enumerate(cases):
        arms = pilot.ARMS[i % 3:] + pilot.ARMS[:i % 3]
        order.extend(case['id'] + ':' + arm for arm in arms)
    if tuple(order[:len(EXPECTED_STARTED)]) != EXPECTED_STARTED or tuple(order[len(EXPECTED_STARTED):]) != EXPECTED_REMAINING:
        raise ValueError('remaining assignment order mismatch')
    slots = [(by_id[slot.rsplit(':', 1)[0]], slot.rsplit(':', 1)[1]) for slot in EXPECTED_REMAINING]
    return slots


def run_continuation(pilot, runner, slots):
    results = []
    consecutive = 1  # the predecessor's 429 episode remains a technical failure
    for case, arm in slots:
        start = time.monotonic()
        try:
            outcome = runner.episode(case, arm)
            consecutive = 0
        except pilot.StopRun as exc:
            outcome = {'slot': case['id'] + ':' + arm, 'status': 'technical_failure', 'detail': str(exc)}
            results.append(outcome)
            runner.log(event='run_stopped', reason='global boundary', detail=str(exc))
            return {'status': 'stopped_boundary', 'results': results,
                    'attempts': runner.guard.attempts, 'estimated_or_reserved_micro_usd': runner.guard.used}
        except pilot.TechnicalFailure as exc:
            consecutive += 1
            outcome = {'slot': case['id'] + ':' + arm, 'status': 'technical_failure', 'detail': str(exc)}
            runner.log(event='episode_failure', **outcome)
        outcome['elapsed_seconds'] = round(time.monotonic() - start, 3)
        results.append(outcome)
        if consecutive >= 2:
            runner.log(event='run_stopped', reason='two consecutive technical episode failures')
            return {'status': 'stopped_consecutive_failures', 'results': results,
                    'attempts': runner.guard.attempts, 'estimated_or_reserved_micro_usd': runner.guard.used}
    return {'status': 'completed', 'results': results, 'attempts': runner.guard.attempts,
            'estimated_or_reserved_micro_usd': runner.guard.used, 'model_version': runner.version}


def claim_dispatch(pilot, fence, output):
    """One create-only global fence for this frozen continuation; no resumption."""
    pilot.write_new(fence, pilot.encoded({'kind': 'single-dispatch-fence',
        'predecessor_summary_sha256': SHA['summary.json'], 'output': str(output.resolve()),
        'remaining_slots': EXPECTED_REMAINING}))


def main():
    parser = argparse.ArgumentParser(description='One explicitly authorised separate continuation, never a retry.')
    parser.add_argument('--output', required=True, help='new non-existent private directory')
    parser.add_argument('--execute-live', action='store_true', required=True)
    args = parser.parse_args()
    pilot = load_pilot()
    slots = verify_predecessor(pilot)
    guard = pilot.CostGuard('1.50', '9.00')
    guard.attempts, guard.used = 31, 359587
    versions = {name: importlib.metadata.version(name) for name in ('httpx', 'google-auth')}
    previous_config = json.loads(read_bound(PREDECESSOR / 'run-config.json', SHA['run-config.json']))
    if versions != previous_config['runtime_versions']:
        raise ValueError('provider runtime dependency versions changed')
    output = Path(args.output)
    output.mkdir(mode=0o700, parents=False, exist_ok=False)
    pilot.write_new(output / 'run-config.json', pilot.encoded({
        'kind': 'seven-unstarted-slots-separate-continuation', 'binding_sha256': SHA,
        'continuation_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'model': MODEL_VERSION, 'pinned_returned_model_version': MODEL_VERSION,
        'carried_attempts': 31, 'carried_effective_micro_usd': 359587,
        'carried_countTokens_attempts': 6, 'initial_consecutive_technical_failures': 1,
        'remaining_slots': EXPECTED_REMAINING, 'canary_reused_not_repeated': True,
        'retry_429': False, 'cap_micro_usd': 10000000, 'max_attempts': 80,
        'max_countTokens': 80, 'automatic_retries': False, 'resumable': False,
        'input_price_usd_per_million': '1.50', 'output_price_usd_per_million': '9.00',
        'runtime_versions': versions,
    }))
    claim_dispatch(pilot, ROOT / 'controller-pilot-v2-continuation-dispatch-fence-v1.json', output)
    runner = pilot.Pilot(pilot.VertexProvider(), output, guard, carried_count_attempts=6)
    runner.version = MODEL_VERSION
    result = run_continuation(pilot, runner, slots)
    pilot.write_new(output / 'summary.json', pilot.encoded(result))
    print(json.dumps({'status': result['status'], 'attempts': result['attempts'],
                      'estimated_or_reserved_micro_usd': result['estimated_or_reserved_micro_usd']}))


if __name__ == '__main__':
    main()
