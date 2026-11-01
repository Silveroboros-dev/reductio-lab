"""Single-use, bounded Vertex compatibility check; no model calls at import.

Prepare and independently challenge the frozen contract before dispatch.
The output root is private; do not publish its raw responses or journals.
"""
from __future__ import annotations

import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import signal
import sqlite3
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from reasoning_engine.replay_sources import digest

BASE = ROOT.parent
OUTPUT = BASE / 'vertex-compatibility-private-20261101-v3'
PREDECESSOR = BASE / 'vertex-compatibility-private-20261101-v2/contract.json'
PRIOR = BASE / 'anthropic-s1-pilot-20261029-v1/model-summary.json'
PRIOR_LEDGER = BASE / 'anthropic-s1-pilot-20261029-v1/ledger/ledger.sqlite3'
PRIOR_LEDGER_SHA256 = 'c60dbf70fb2274bca0c09e899c383093b9088c184e218521619c1d445e55d1e8'
PRIOR_CONTRACT = BASE / 'anthropic-s1-pilot-20261029-v1/model-contract.json'
FORBIDDEN_REQUESTS = ['17a148b5aeade7252bf07660e16d3c6ffbb4da639aaf31d2332cd88b2a7e10e4',
                      'cbc14ce21dfdabfb14657e14823f19db22e31a6a63bc9136ec949dd868c6094e',
                      'fd2e5bcb4de52dce98b476e54fc8538f291058ecfbb9f832ab4d2e5113690581']
TRANSPORT = BASE / 'faithful-dynamic-pilot/transport/oneshot.py'
PROJECT_SHA256 = '8a6a45a093d29e5424feb93ea2299e13faf1e8eac56604629ec4af4702e3bef0'

def sha(data):
    return hashlib.sha256(data).hexdigest()

def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode()

def write_new(path, value):
    raw = canonical(value)
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, 'O_NOFOLLOW', 0), 0o600)
    with os.fdopen(fd, 'wb') as out:
        out.write(raw); out.flush(); os.fsync(out.fileno())
    d = os.open(path.parent, os.O_RDONLY)
    try: os.fsync(d)
    finally: os.close(d)

def quarantine_raw(directory, index, endpoint, request, status, body):
    """Durably retain exact provider bytes before any response parsing."""
    base = f'{index:03d}'
    temporary = directory / (base + '.tmp')
    final = directory / (base + '.bin')
    fd = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, 'O_NOFOLLOW', 0), 0o600)
    with os.fdopen(fd, 'wb') as out:
        out.write(body); out.flush(); os.fsync(out.fileno())
    # link refuses overwriting an existing artifact; both names are on one FS.
    os.link(temporary, final, follow_symlinks=False)
    os.unlink(temporary)
    d = os.open(directory, os.O_RDONLY)
    try: os.fsync(d)
    finally: os.close(d)
    write_new(directory / (base + '.json'), {'index': index, 'endpoint': endpoint,
              'request_sha256': sha(request), 'http_status': status,
              'response_sha256': sha(body), 'response_bytes': len(body)})

def with_wall_timeout(fn, seconds=420):
    """Bound one main-thread call; interruption leaves its effect uncertain."""
    previous_handler = signal.getsignal(signal.SIGALRM)
    previous_timer = signal.getitimer(signal.ITIMER_REAL)
    if previous_timer[0] != 0 or previous_timer[1] != 0:
        raise RuntimeError('existing process alarm conflicts with run deadline')
    def timeout(_signum, _frame):
        raise TimeoutError('external operation deadline elapsed')
    signal.signal(signal.SIGALRM, timeout)
    signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        return fn()
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous_handler)

def fixture():
    rule = {'text': 'For batch LARK-7, the target is met only if at least 7 of 10 final checks pass.',
            'provenance': {'captured_at': '2026-10-29T12:00:00Z', 'published_at': '2026-10-29T11:55:00Z', 'source_id': 'synthetic-rule-v1'}}
    tally = {'text': 'Final audit of batch LARK-7: 6 of 10 checks passed; 4 failed.',
             'provenance': {'captured_at': '2026-10-29T12:10:00Z', 'published_at': '2026-10-29T12:05:00Z', 'source_id': 'synthetic-final-tally-v1'}}
    task = {'thesis': 'Batch LARK-7 met its final audit target.',
            'task': 'Assess the thesis using only saved source evidence. Cite the saved source IDs; the thesis is a user claim, not a source fact.',
            'information_cutoff': '2026-10-29T13:00:00Z', 'replay_max_actions': 1, 'replay_max_simulated_micro_usd': 0,
            'tool_catalog': [{'action_id': 'synthetic-final-tally-lark7-v1', 'description': 'Open the saved final audit tally for batch LARK-7. The count is not shown in this action description.', 'quoted_micro_usd': 0, 'capture_ref': 'synthetic-lark7-final-tally-v1'}],
            'initial_evidence': [{'action_id': 'synthetic-rule-lark7-v1', 'response': {'payload': rule, 'response_sha256': digest(rule)}}],
            'preconsumed_action_ids': ['synthetic-rule-lark7-v1']}
    checkpoint = {'case_id': 'synthetic-source-si-lark7-20261029-v1', 'input': task, 'input_version': digest(task)}
    catalog = [{'case_id': checkpoint['case_id'], 'action_id': 'synthetic-final-tally-lark7-v1',
                'capture_ref': 'synthetic-lark7-final-tally-v1', 'saved_response': {'payload': tally, 'response_sha256': digest(tally)}}]
    return checkpoint, catalog

def selection_payload():
    return {'question': 'Does the saved observation say the light is green?', 'task_type': 'exploration',
            'as_of_utc': None, 'required_questions': [{'id': 'q', 'question': 'Does the saved observation say the light is green?', 'evidence_ids': []}],
            'available_statements': [{'id': 's1', 'kind': 'observation', 'source': 'synthetic', 'text': 'The light is green.'}],
            'candidate_findings': [], 'halter_feedback': None}

def contract():
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    if not revision.startswith('cd96f33'):
        raise ValueError('repository revision differs from approved base')
    prior = json.loads(PRIOR.read_bytes())['ledger']
    if (prior['exposure_micro'], prior['generation_attempts'], prior['count_attempts']) != (56922170, 1626, 1548):
        raise ValueError('prior accounting mismatch')
    if sha(PRIOR_LEDGER.read_bytes()) != PRIOR_LEDGER_SHA256:
        raise ValueError('prior ledger bytes changed')
    old = sqlite3.connect('file:' + str(PRIOR_LEDGER) + '?mode=ro&immutable=1', uri=True)
    try:
        totals = old.execute('select stopped,exposure_micro,generation_attempts,count_attempts,source_attempts from run').fetchone()
    finally:
        old.close()
    if totals != (0, 56922170, 1626, 1548, 1):
        raise ValueError('prior ledger counters changed')
    if sorted(json.loads(PRIOR_CONTRACT.read_bytes())['predecessor']['forbidden_request_hashes']) != sorted(FORBIDDEN_REQUESTS):
        raise ValueError('historical uncertain request bindings changed')
    checkpoint, catalog = fixture()
    code = sorted((ROOT / 'faithful_v3').glob('*.py')) + sorted((ROOT / 'reasoning_engine').glob('*.py'))
    code += [Path(__file__).resolve(), TRANSPORT, ROOT / 'tests/test_vertex_journal.py']
    return {'schema': 'vertex-compatibility-canary-v1', 'model': 'gemini-3.8-flash', 'location': 'global',
            'source_revision': revision, 'dirty_policy': 'bound source files including uncommitted successor',
            'checkpoint': checkpoint, 'catalog': catalog, 'canary_payload': selection_payload(),
            'expected_review': 'Target not met: 6 of 10 passed, below required 7; semantic review pending.',
            'compatibility_gate': 'canary valid; case proposal; exactly one saved tally retrieval; both synthetic sources selected and cited; no halted accounting; semantic review pending',
            'logical_generation_cap': 7, 'generation_attempt_cap': 14, 'count_attempt_cap': 14,
            'max_case_calls': 6, 'max_depth': 1, 'beam_width': 1, 'max_alternatives': 1,
            'max_output_tokens': 4096, 'max_input_tokens': 8192, 'thinking_level': 'LOW',
            'observed_model_policy': 'exact gemini-3.8-flash',
            'incremental_cap_micro_usd': 2500000, 'prior_exposure_micro_usd': 56922170,
            'generation_reserve_micro_usd': 520000, 'max_model_attempts_per_operation': 2,
            'retry_policy': 'one retry only on captured HTTP 429 RESOURCE_EXHAUSTED, same request, bounded backoff',
            'uncertain_retry': False, 'source_provider_calls': 0, 'timeout_seconds': 420,
            'pricing': {'usd_per_million_input': '0.75', 'usd_per_million_output_including_thoughts': '3.75',
                        'url': 'https://cloud.google.com/model-garden/pricing', 'observed': '2026-11-01'},
            'prior_summary_sha256': sha(PRIOR.read_bytes()), 'prior_ledger_sha256': PRIOR_LEDGER_SHA256,
            'prior_contract_sha256': sha(PRIOR_CONTRACT.read_bytes()),
            'predecessor_contract_sha256': sha(PREDECESSOR.read_bytes()) if PREDECESSOR.exists() else None,
            'forbidden_request_sha256': FORBIDDEN_REQUESTS,
            'project_id_sha256': PROJECT_SHA256,
            'runtime': {'python': sys.version.split()[0], 'httpx': importlib.metadata.version('httpx'),
                        'google-auth': importlib.metadata.version('google-auth')},
            'code_sha256': {str(p): sha(p.read_bytes()) for p in code}}

def prepare():
    # Refuse a reused or symlinked output root; it owns one run only.
    OUTPUT.mkdir(mode=0o700)
    write_new(OUTPUT / 'contract.json', contract())
    print('Frozen contract prepared. No model calls.')

def execute():
    frozen = json.loads((OUTPUT / 'contract.json').read_bytes())
    if frozen != contract():
        raise ValueError('contract, code, prior or runtime drift')
    review = json.loads((OUTPUT / 'challenge_packet_v0001.json').read_bytes())
    if review.get('overall_state') != 'ready' or review.get('contract_sha256') != sha((OUTPUT / 'contract.json').read_bytes()):
        raise ValueError('independent preflight missing, blocked or stale')
    os.umask(0o077)
    write_new(OUTPUT / 'dispatch.json', {'contract_sha256': sha((OUTPUT / 'contract.json').read_bytes()),
                                         'one_shot': True, 'uncertain_retry': False})
    raw_root = OUTPUT / 'raw'
    raw_root.mkdir(mode=0o700)
    counter = 0
    import google.auth
    from google.auth.transport.requests import Request
    from reasoning_engine.executor import EffectExecutor, HttpResponse
    from reasoning_engine.vertex_journal import VertexJournal
    from faithful_v3.excerpts import resolve_selection, source_registry
    from faithful_v3.action_case import run_case
    import importlib.util
    spec = importlib.util.spec_from_file_location('approved_oneshot', TRANSPORT)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    credentials, project = google.auth.default(scopes=['https://www.googleapis.com/auth/cloud-platform'])
    if not project or sha(project.encode()) != PROJECT_SHA256:
        raise ValueError('project identity differs from prior run')
    def token(_provider):
        if not credentials.valid: credentials.refresh(Request())
        if not credentials.token: raise ValueError('credentials unavailable')
        return credentials.token
    transport = module.OneShotTransport(project, token)
    def one(endpoint):
        def perform(raw):
            nonlocal counter
            if sha(raw) in FORBIDDEN_REQUESTS:
                raise ValueError('historical uncertain request cannot be repeated')
            counter += 1
            status, body = with_wall_timeout(lambda: transport('vertex', endpoint, raw))
            quarantine_raw(raw_root, counter, endpoint, raw, status, body)
            return HttpResponse(status, body)
        return perform
    executor = EffectExecutor(str(OUTPUT / 'effects.sqlite3'), exposure_cap=0, call_cap=28)
    callback = VertexJournal(executor, one('countTokens'), one('gemini-3.8-flash@global'),
                             session_id='vertex-compatibility-v1', identity={'contract_sha256': sha((OUTPUT / 'contract.json').read_bytes())})
    canary, outcome, failure = None, None, None
    try:
        canary = callback('selection', frozen['canary_payload'])
        alternatives = canary.get('alternatives')
        if not isinstance(alternatives, list) or not alternatives or len(alternatives) > 1:
            raise ValueError('canary selection alternatives invalid')
        statements = frozen['canary_payload']['available_statements']
        resolve_selection(alternatives[0], {x['id']: x for x in statements}, {'s1'}, source_registry(statements))
        write_new(OUTPUT / 'canary.json', {'result': canary, 'receipt': callback.last_receipt, 'gate': 'passed'})
        outcome = run_case(frozen['checkpoint'], frozen['catalog'], callback,
                           max_calls=6, max_depth=1, beam_width=1, max_alternatives=1)
        write_new(OUTPUT / 'outcome.json', outcome)
    except Exception as exc:
        failure = type(exc).__name__
    finally:
        accounting = callback.accounting()
        history = outcome.get('history', []) if outcome else []
        retrievals = [x for x in history if x.get('kind') == 'replay_retrieval']
        final = next((x.get('outcome', {}) for x in reversed(history) if x.get('kind') == 'final'), {})
        selected = {x.get('id') for x in final.get('selected_evidence', []) if isinstance(x, dict)}
        citations = (outcome.get('result') or {}).get('citations', []) if outcome else []
        required = {'source:synthetic-rule-lark7-v1', 'source:synthetic-final-tally-lark7-v1'}
        source_path_passed = (len(retrievals) == 1
                              and retrievals[0].get('action_id') == 'synthetic-final-tally-lark7-v1'
                              and required.issubset(selected)
                              and isinstance(citations, list) and required.issubset(citations))
        gate = ('passed' if failure is None and (OUTPUT / 'canary.json').exists()
                and outcome is not None and outcome.get('status') == 'proposal'
                and source_path_passed and accounting['halted'] is None else 'not_passed')
        write_new(OUTPUT / 'summary.json', {'gate': gate, 'canary_passed': (OUTPUT / 'canary.json').exists(),
                  'source_path_passed': source_path_passed, 'semantic_review': 'pending',
                  'case_status': outcome.get('status') if outcome else 'not_completed',
                  'case_reason': outcome.get('reason') if outcome else None,
                  'failure_type': failure, 'accounting': accounting, 'invoice': 'not reconciled'})
        executor.close()
    print(json.dumps({'canary_passed': (OUTPUT / 'canary.json').exists(),
                      'case_status': outcome.get('status') if outcome else 'not_completed',
                      'failure_type': failure, 'gate': gate, 'accounting': accounting}, sort_keys=True))
    if gate != 'passed':
        raise SystemExit(2)

if __name__ == '__main__':
    if len(sys.argv) != 2 or sys.argv[1] not in {'prepare', 'execute'}:
        raise SystemExit('usage: vertex_compatibility_canary.py prepare|execute')
    (prepare if sys.argv[1] == 'prepare' else execute)()
