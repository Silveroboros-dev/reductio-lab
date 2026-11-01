"""Isolated 3.8 pilot with bounded optional 3.7 fallback; no network at import.

No retries, no cross-model main series, no restart. Operator must freeze this
module's hash and obtain an independent read-only challenge before invoking.
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
PILOT = ROOT / 'controller-pilot-v2-runner/pilot.py'
DRAFT = ROOT / 'controller-pilot-new-model-draft/draft.py'
CASES = ROOT / 'controller-pilot-v2-inputs/cases.json'
PILOT_SHA = '3d2c05db2666e90d7df9855e6ae2f843bbd2eaff566acf1144f8ecba2ded2e8f'
DRAFT_SHA = 'c8d047dc495a0be90d26e5dd4af3bdd2cdda8b70aa6096a2fbfff08328781734'
CASES_SHA = '4165954e6d5e9112014d90e027d70e303e5e77292148151c857595c6cd82220b'
LOCK = ROOT / 'controller-pilot-38-dispatch-once-v1.lock'


def bound(path: Path, digest: str) -> bytes:
    value = path.read_bytes()
    if hashlib.sha256(value).hexdigest() != digest:
        raise ValueError('bound file drift: ' + path.name)
    return value


def load_module(path: Path, raw: bytes, name: str):
    m = types.ModuleType(name)
    m.__file__ = str(path)
    sys.modules[name] = m
    exec(compile(raw, str(path), 'exec'), m.__dict__)
    return m


def load_frozen():
    """Adapt only transport model selection, limits, and 429 handling.

    Pilot.episode and all scientific prompts remain byte-for-byte unchanged.
    Assertions fail closed if the frozen source does not have the expected form.
    """
    raw = bound(PILOT, PILOT_SHA)
    src = raw.decode('utf-8')
    replacements = [
        ('MAX_ATTEMPTS = 80\n', 'MAX_ATTEMPTS = 111\n'),
        ('self.token_count_attempts >= 80:', 'self.token_count_attempts >= 87:'),
        ('raise TechnicalFailure("token-count request failed; no generation dispatched") from None',
         'raise StopRun("token-count effect uncertain; no generation dispatched") from None'),
        ('effect="succeeded" if status == 200 else "uncertain", capture="saved")\n        if status != 200:\n            # Conservatively retain a full attempt reservation; never retry.\n            raise StopRun(f"provider returned HTTP {status}; effect uncertain and cost reserved")',
         '''effect="succeeded", capture="saved")
        if status != 200:
            # A complete HTTP response is a completed transport operation. Its
            # billing is unknown; retain the reservation and never retry.
            if status == 429:
                raise TechnicalFailure("HTTP 429; complete response; cost reserved")
            if status in (403, 404):
                try:
                    error_status = json.loads(raw).get("error", {}).get("status")
                except (ValueError, UnicodeError, AttributeError):
                    error_status = None
                if (status, error_status) in ((403, "PERMISSION_DENIED"), (404, "NOT_FOUND")):
                    raise ModelUnavailable("model access unavailable; complete response; cost reserved")
            raise StopRun(f"HTTP {status}; unknown effect or billing; cost reserved")'''),
    ]
    for before, after in replacements:
        if src.count(before) != 1:
            raise ValueError('expected frozen adaptation point missing or ambiguous')
        src = src.replace(before, after, 1)
    # ModelUnavailable is an exception type injected before executing the module.
    m = types.ModuleType('_pilot38_adapted')
    m.__file__ = str(PILOT)
    sys.modules[m.__name__] = m
    # The name resolves when call() is executed; base class needed first.
    exec(compile(src, str(PILOT), 'exec'), m.__dict__)
    m.ModelUnavailable = type('ModelUnavailable', (m.TechnicalFailure,), {})
    return m, hashlib.sha256(src.encode()).hexdigest()


class Transport:
    def __init__(self, pilot, model: str):
        if model not in ('gemini-3.8-flash', 'gemini-3.7-flash'):
            raise ValueError('model is not permitted')
        import google.auth
        import httpx
        self.pilot, self.model = pilot, model
        self.credentials, self.project = google.auth.default(scopes=['https://www.googleapis.com/auth/cloud-platform'])
        if not self.project:
            raise RuntimeError('ADC project unavailable')
        self.client = httpx.Client(timeout=60, follow_redirects=False, transport=httpx.HTTPTransport(retries=0))

    def request(self, prompt: str, *, count: bool = False):
        from google.auth.transport.requests import Request
        url = ('https://aiplatform.googleapis.com/v1/projects/' + self.project + '/locations/global/publishers/google/models/' + self.model + ':' + ('countTokens' if count else 'generateContent'))
        headers = {'Content-Type': 'application/json', 'Accept-Encoding': 'identity'}
        self.credentials.before_request(Request(), 'POST', url, headers)
        body = {'contents': [{'role': 'user', 'parts': [{'text': prompt}]}],
                'generationConfig': {'maxOutputTokens': 4096, 'responseMimeType': 'application/json',
                                     'thinkingConfig': {'thinkingLevel': 'LOW'}}}
        start = time.monotonic()
        with self.client.stream('POST', url, headers=headers, content=self.pilot.encoded(body)) as response:
            raw = bytearray()
            for part in response.iter_raw():
                if len(raw) + len(part) > 524288:
                    raise RuntimeError('provider response exceeds local capture limit')
                raw.extend(part)
            return response.status_code, bytes(raw), time.monotonic() - start


def canary_ok(out: dict) -> bool:
    return (out.get('status') == 'completed' and out.get('generations') == 4 and
            out.get('source_reads') == 1 and out.get('critique', {}).get('issue') is True and
            len(out.get('retrievals', [])) == 1 and out.get('chosen_final', {}).get('action') == 'stop')


def run_series(pilot, runner, cases, transport_factory):
    """Operate one canary for each model at most, then 18 main assignments."""
    canaries = []
    selected = None
    for model in ('gemini-3.8-flash', 'gemini-3.7-flash'):
        runner.provider = transport_factory(pilot, model)
        runner.version = None
        try:
            canary = runner.episode(pilot.synthetic_case(), 'C', canary=True)
        except pilot.ModelUnavailable as exc:
            canaries.append({'model': model, 'status': 'unavailable', 'detail': str(exc)})
            runner.log(event='canary_unavailable', model=model, reason=str(exc))
            if model == 'gemini-3.8-flash':
                continue
            return finish('stopped_unavailable', runner, canaries, [])
        except (pilot.StopRun, pilot.TechnicalFailure) as exc:
            # A 429 or an invalid canary is not proof model unavailable. No
            # semantic resampling or fallback based on that observation.
            runner.log(event='run_stopped', reason='canary_failed', detail=str(exc), model=model)
            return finish('stopped_canary', runner, canaries, [])
        if not canary_ok(canary):
            runner.log(event='run_stopped', reason='canary_did_not_exercise_full_path', model=model)
            canaries.append({'model': model, 'status': 'incomplete_canary', 'result': canary})
            return finish('stopped_canary', runner, canaries, [])
        if not isinstance(runner.version, str) or not (runner.version == model or runner.version.startswith(model + '-')):
            runner.log(event='run_stopped', reason='unexpected_model_version', model=model)
            return finish('stopped_model_version', runner, canaries, [])
        canaries.append({'model': model, 'status': 'passed', 'result': canary})
        selected = model
        break
    if selected is None:
        return finish('stopped_unavailable', runner, canaries, [])
    results = []
    failures = 0
    for index, case in enumerate(cases):
        arms = pilot.ARMS[index % 3:] + pilot.ARMS[:index % 3]
        for arm in arms:
            started = time.monotonic()
            try:
                outcome = runner.episode(case, arm)
                failures = 0
            except pilot.ModelUnavailable as exc:
                # Mid-main model switch would invalidate the paired study.
                outcome = {'slot': case['id'] + ':' + arm, 'status': 'technical_failure', 'detail': str(exc)}
                results.append(outcome)
                runner.log(event='run_stopped', reason='model_unavailable_during_main', detail=str(exc))
                return finish('stopped_boundary', runner, canaries, results, selected)
            except pilot.StopRun as exc:
                outcome = {'slot': case['id'] + ':' + arm, 'status': 'technical_failure', 'detail': str(exc)}
                results.append(outcome)
                runner.log(event='run_stopped', reason='global_boundary', detail=str(exc))
                return finish('stopped_boundary', runner, canaries, results, selected)
            except pilot.TechnicalFailure as exc:
                failures += 1
                outcome = {'slot': case['id'] + ':' + arm, 'status': 'technical_failure', 'detail': str(exc)}
                runner.log(event='episode_failure', **outcome)
                if str(exc).startswith('HTTP 429;') and failures < 2:
                    # Delay a different slot, never repeat the failed request.
                    runner.log(event='rate_limit_cooldown', seconds=5)
                    time.sleep(5)
            outcome['elapsed_seconds'] = round(time.monotonic() - started, 3)
            results.append(outcome)
            if failures >= 2:
                runner.log(event='run_stopped', reason='two_consecutive_technical_failures')
                return finish('stopped_consecutive_failures', runner, canaries, results, selected)
    return finish('completed', runner, canaries, results, selected)


def finish(status, runner, canaries, results, selected=None):
    return {'status': status, 'selected_model': selected, 'model_version': runner.version,
            'canaries': canaries, 'results': results, 'attempts': runner.guard.attempts,
            'countTokens_total': runner.token_count_attempts,
            'estimated_or_reserved_micro_usd': runner.guard.used}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True, help='new nonexistent directory')
    parser.add_argument('--execute-live', action='store_true', required=True)
    args = parser.parse_args()
    pilot, adapted_sha = load_frozen()
    draft = load_module(DRAFT, bound(DRAFT, DRAFT_SHA), '_pilot38_draft')
    draft.verify_carried_summary()
    cases = pilot.validate_cases(json.loads(bound(CASES, CASES_SHA)))
    guard = pilot.CostGuard('0.75', '3.75')
    guard.apply_carry({'attempts': 31, 'estimated_or_reserved_micro_usd': 359587})
    versions = {name: importlib.metadata.version(name) for name in ('httpx', 'google-auth')}
    output = Path(args.output)
    if output.exists():
        raise ValueError('output must not exist')
    # Global create-only fence covers both possible model choices and output
    # roots. Once created this run is not resumed or dispatched again.
    pilot.write_new(LOCK, pilot.encoded({'kind':'one_live_dispatch', 'runner_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), 'cases_sha256': CASES_SHA}))
    output.mkdir(mode=0o700, parents=False, exist_ok=False)
    pilot.write_new(output / 'run-config.json', pilot.encoded({
        'model_preference': ['gemini-3.8-flash', 'gemini-3.7-flash'],
        'fallback_rule': 'before main, only explicit model unavailable 403/PERMISSION_DENIED or 404/NOT_FOUND',
        'pilot_sha256': PILOT_SHA, 'adapted_pilot_sha256': adapted_sha, 'cases_sha256': CASES_SHA,
        'draft_sha256': DRAFT_SHA, 'runner_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'input_price_usd_per_million': '0.75', 'output_price_usd_per_million': '3.75',
        'price_checked': '2026-10-29', 'price_source': 'https://cloud.google.com/gemini-enterprise-agent-platform/generative-ai/pricing',
        'carry_attempts': 31, 'carry_count_tokens': 7, 'carry_effective_micro_usd': 359587,
        'reserve_micro_usd': guard.reserve, 'max_attempts': 111, 'max_count_tokens': 87,
        'max_generations_per_slot': 4, 'max_source_reads_per_slot': 2, 'max_output_tokens_requested': 4096,
        'output_token_reserve': 8192, 'cap_micro_usd': 10000000, 'model_settings': {'thinking_level': 'LOW', 'response_mime_type': 'application/json'},
        'automatic_retries': False, 'retry_429': False, 'resumable': False, 'runtime_versions': versions,
    }))
    # No credentials or network before explicit --execute-live, binding checks,
    # the fence, and persistent run config.
    runner = pilot.Pilot(None, output, guard, carried_count_attempts=7)
    result = run_series(pilot, runner, cases, Transport)
    pilot.write_new(output / 'summary.json', pilot.encoded(result))
    print(json.dumps({'status': result['status'], 'selected_model': result['selected_model'],
                      'attempts': result['attempts'], 'countTokens_total': result['countTokens_total'],
                      'estimated_or_reserved_micro_usd': result['estimated_or_reserved_micro_usd']}))


if __name__ == '__main__':
    main()
