"""One independently authorised continuation, 14 previously unstarted slots.

Network is not used on import; live dispatch requires --execute-live. Prior
responses, prompts, and the unknown effect are never modified or replayed.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import sys
import time
import types
from pathlib import Path

ROOT = Path('/Users/rk/.codex/visualizations/2026/10/29/01a1865f-6bd2-75a2-abb1-eb14b071bbe0')
ORIGINAL = ROOT / 'controller-pilot-38-live-runner/runner.py'
DRAFT = ROOT / 'controller-pilot-38-continuation-offline-draft/draft.py'
LOCK = ROOT / 'controller-pilot-38-continuation-dispatch-v1.lock'
ORIGINAL_SHA = '86683096cc918d0bd057f689244fb5af7bde4e97e587e4b97c866bf5a8ba7bd2'
DRAFT_SHA = '7bcf897b2901ec91cbca98a2ecf3aa173f3ccfbd2ede67f8755dcda9f7ec491d'
MODEL = 'gemini-3.8-flash'
TIMEOUT_SECONDS = 420


def load_bound(path, expected, name):
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected:
        raise ValueError('input binding mismatch: ' + path.name)
    module = types.ModuleType(name)
    module.__file__ = str(path)
    sys.modules[name] = module
    exec(compile(raw, str(path), 'exec'), module.__dict__)
    return module


def prepare():
    original = load_bound(ORIGINAL, ORIGINAL_SHA, '_continuation_original')
    draft = load_bound(DRAFT, DRAFT_SHA, '_continuation_draft')
    evidence = draft.verify_evidence()
    if evidence['model_version'] != MODEL or evidence['prior_012'] != 'uncertain':
        raise ValueError('prior effect or model mismatch')
    pilot, adapted_sha = original.load_frozen()
    config = json.loads(draft.bound_read('config'))
    if config.get('adapted_pilot_sha256') != adapted_sha:
        raise ValueError('adapted policy drift')
    versions = {name: importlib.metadata.version(name) for name in ('httpx', 'google-auth')}
    if versions != config['runtime_versions']:
        raise ValueError('runtime dependency drift')
    data = json.loads(draft.bound_read('cases'))
    cases = pilot.validate_cases(data)
    by_id = {case['id']: case for case in cases}
    slots = [(by_id[slot.rsplit(':', 1)[0]], slot.rsplit(':', 1)[1]) for slot in evidence['remaining_slots']]
    return original, draft, pilot, slots, evidence, config, versions, adapted_sha


def transport_420(original, pilot):
    """Construct only for the live call; never imported credentials in tests."""
    import httpx
    transport = original.Transport(pilot, MODEL)
    transport.client.timeout = httpx.Timeout(TIMEOUT_SECONDS)
    # before_request may refresh credentials via google-auth's requests
    # transport, separately from httpx. Bind that timeout too; a timeout in
    # either phase remains uncertain because the predecessor did not record
    # the exact phase when an exception occurred.
    inner_credentials = transport.credentials

    class CredentialsWithTimeout:
        def before_request(self, request, method, url, headers):
            def request_with_timeout(*args, **kwargs):
                kwargs['timeout'] = TIMEOUT_SECONDS
                return request(*args, **kwargs)
            return inner_credentials.before_request(request_with_timeout, method, url, headers)

    transport.credentials = CredentialsWithTimeout()
    return transport


def run_remaining(pilot, runner, slots):
    results = []
    consecutive = 1  # the prior ambiguous attempt is a technical failure
    for case, arm in slots:
        start = time.monotonic()
        try:
            outcome = runner.episode(case, arm)
            consecutive = 0
        except pilot.ModelUnavailable as exc:
            outcome = {'slot': case['id'] + ':' + arm, 'status': 'technical_failure', 'detail': str(exc)}
            results.append(outcome)
            runner.log(event='run_stopped', reason='model_unavailable_during_main', detail=str(exc))
            return finish('stopped_boundary', runner, results)
        except pilot.StopRun as exc:
            outcome = {'slot': case['id'] + ':' + arm, 'status': 'technical_failure', 'detail': str(exc)}
            results.append(outcome)
            runner.log(event='run_stopped', reason='global_boundary', detail=str(exc))
            return finish('stopped_boundary', runner, results)
        except pilot.TechnicalFailure as exc:
            consecutive += 1
            outcome = {'slot': case['id'] + ':' + arm, 'status': 'technical_failure', 'detail': str(exc)}
            runner.log(event='episode_failure', **outcome)
            if str(exc).startswith('HTTP 429;') and consecutive < 2:
                runner.log(event='rate_limit_cooldown', seconds=5)
                time.sleep(5)
        outcome['elapsed_seconds'] = round(time.monotonic() - start, 3)
        results.append(outcome)
        if consecutive >= 2:
            runner.log(event='run_stopped', reason='two_consecutive_technical_failures')
            return finish('stopped_consecutive_failures', runner, results)
    return finish('completed', runner, results)


def finish(status, runner, results):
    return {'status': status, 'selected_model': MODEL, 'model_version': runner.version,
            'results': results, 'attempts': runner.guard.attempts,
            'countTokens_total': runner.token_count_attempts,
            'estimated_or_reserved_micro_usd': runner.guard.used}


def main():
    parser = argparse.ArgumentParser(description='Single authorized continuation; no retry or canary.')
    parser.add_argument('--output', required=True, help='new non-existent output directory')
    parser.add_argument('--execute-live', action='store_true', required=True)
    args = parser.parse_args()
    original, draft, pilot, slots, evidence, config, versions, adapted_sha = prepare()
    output = Path(args.output)
    if output.exists():
        raise ValueError('output must not exist')
    guard = pilot.CostGuard('0.75', '3.75')
    guard.apply_carry({'attempts': evidence['attempts'], 'estimated_or_reserved_micro_usd': evidence['estimated_plus_reserved_micro_usd']})
    if guard.reserve != draft.RESERVE_MICRO:
        raise ValueError('reservation drift')
    pilot.write_new(LOCK, pilot.encoded({'kind': 'one_continuation_dispatch',
        'continuation_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'predecessor_events_sha256': draft.HASHES['events']}))
    output.mkdir(mode=0o700, parents=False, exist_ok=False)
    fd = os.open(output.parent, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)
    pilot.write_new(output / 'run-config.json', pilot.encoded({
        'kind': 'fourteen-unstarted-slots', 'model': MODEL, 'predecessor_hashes': draft.HASHES,
        'original_runner_sha256': ORIGINAL_SHA, 'offline_draft_sha256': DRAFT_SHA,
        'continuation_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'adapted_pilot_sha256': adapted_sha, 'remaining_slots': evidence['remaining_slots'],
        'runtime_versions': versions, 'transport_timeout_seconds': TIMEOUT_SECONDS,
        'carry_attempts': evidence['attempts'], 'carry_count_tokens': evidence['counts'],
        'carry_effective_micro_usd': evidence['estimated_plus_reserved_micro_usd'],
        'initial_consecutive_technical_failures': 1, 'previous_012': 'uncertain',
        'max_attempts': 111, 'max_count_tokens': 87, 'max_micro_usd': 10000000,
        'reserve_micro_usd': guard.reserve, 'max_output_tokens_requested': 4096,
        'thinking_level': 'LOW', 'retry': False, 'repeat_canary': False,
        'resumable': False, 'price_input_usd_million': '0.75', 'price_output_usd_million': '3.75',
    }))
    runner = pilot.Pilot(transport_420(original, pilot), output, guard, carried_count_attempts=evidence['counts'])
    runner.version = MODEL
    # Unique operation ordinals across predecessor and successor. Source data
    # remains in its original namespace; the prior op 012 is never replayed.
    runner.raw_count = 12
    result = run_remaining(pilot, runner, slots)
    pilot.write_new(output / 'summary.json', pilot.encoded(result))
    print(json.dumps({k: result[k] for k in ('status', 'selected_model', 'attempts', 'countTokens_total', 'estimated_or_reserved_micro_usd')}))


if __name__ == '__main__':
    main()
