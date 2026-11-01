"""One successor Vertex case, under the prior run's remaining budget.

Prepare and independently challenge the frozen contract before dispatch.
No network or model calls occur during import or preparation.
"""
from __future__ import annotations

import importlib.metadata
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from research.vertex_compatibility_canary import (BASE, PROJECT_SHA256, TRANSPORT,
    FORBIDDEN_REQUESTS, canonical, quarantine_raw, sha, with_wall_timeout, write_new)
from reasoning_engine.vertex_journal import VertexBudget

PREVIOUS = BASE / 'vertex-compatibility-private-20261101-v3'
OUTPUT = BASE / 'vertex-halter-successor-private-20261101-v1'
CHECKPOINT = PREVIOUS / 'accounting-checkpoint.json'
PREVIOUS_CONTRACT = PREVIOUS / 'contract.json'

def contract():
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    if not revision.startswith('cd96f33'):
        raise ValueError('repository revision differs from previous base')
    previous = json.loads(PREVIOUS_CONTRACT.read_bytes())
    old = json.loads(CHECKPOINT.read_bytes())
    budget = VertexBudget.successor(CHECKPOINT)
    if (old['total_exposure_micro_usd'], old['total_generation_attempts'], old['total_count_attempts']) != (56926158, 1632, 1554):
        raise ValueError('predecessor totals differ')
    code = sorted((ROOT / 'faithful_v3').glob('*.py')) + sorted((ROOT / 'reasoning_engine').glob('*.py'))
    code += [Path(__file__).resolve(), ROOT / 'research/vertex_compatibility_canary.py', TRANSPORT,
             ROOT / 'tests/test_halter_formatter_alignment.py', ROOT / 'tests/test_vertex_successor_budget.py',
             ROOT / 'tests/test_vertex_journal.py']
    return {'schema': 'vertex-halter-successor-v1', 'source_revision': revision,
            'dirty_policy': 'bound source files including uncommitted successor',
            'model': 'gemini-3.8-flash', 'location': 'global', 'observed_model_policy': 'exact',
            'checkpoint': previous['checkpoint'], 'catalog': previous['catalog'],
            'previous_contract_sha256': sha(PREVIOUS_CONTRACT.read_bytes()),
            'previous_accounting_sha256': sha(CHECKPOINT.read_bytes()),
            'previous_ledger_sha256': old['ledger_sha256'],
            'previous_outcome_sha256': old['outcome_sha256'],
            'prior_total_exposure_micro_usd': 56926158, 'prior_generation_attempts': 1632,
            'prior_count_attempts': 1554, 'prior_phase_generation_attempts': 6, 'prior_phase_count_attempts': 6,
            'new_incremental_cap_micro_usd': 2496012, 'original_incremental_cap_micro_usd': 2500000,
            'original_phase_generation_cap': 14, 'original_phase_count_cap': 14,
            'generation_attempt_cap': 8, 'count_attempt_cap': 8,
            'generation_reserve_micro_usd': 520000, 'max_output_tokens': 4096,
            'max_input_tokens': 8192, 'thinking_level': 'LOW', 'max_case_calls': 6,
            'max_depth': 1, 'beam_width': 1, 'max_alternatives': 1,
            'timeout_seconds': 420, 'max_model_attempts_per_operation': 2,
            'retry_policy': 'one retry only on captured HTTP 429 RESOURCE_EXHAUSTED, same request, bounded backoff',
            'uncertain_retry': False, 'forbidden_request_sha256': FORBIDDEN_REQUESTS,
            'source_provider_calls': 0, 'new_canary': False,
            'compatibility_gate': 'proposal; exactly one saved tally retrieval; both synthetic sources selected and cited; no halted accounting; semantic review pending',
            'pricing': previous['pricing'], 'project_id_sha256': PROJECT_SHA256,
            'runtime': {'python': sys.version.split()[0], 'httpx': importlib.metadata.version('httpx'),
                        'google-auth': importlib.metadata.version('google-auth')},
            'code_sha256': {str(p): sha(p.read_bytes()) for p in code},
            'predecessor_budget_binding': budget.as_contract()}

def prepare():
    OUTPUT.mkdir(mode=0o700)
    write_new(OUTPUT / 'contract.json', contract())
    print('Frozen successor prepared. No provider operations.')

def execute():
    frozen = json.loads((OUTPUT / 'contract.json').read_bytes())
    if frozen != contract(): raise ValueError('contract, code, predecessor or runtime drift')
    review = json.loads((OUTPUT / 'challenge_packet_v0001.json').read_bytes())
    if review.get('overall_state') != 'ready' or review.get('contract_sha256') != sha((OUTPUT / 'contract.json').read_bytes()):
        raise ValueError('independent challenge missing, blocked or stale')
    os.umask(0o077)
    write_new(OUTPUT / 'dispatch.json', {'contract_sha256': sha((OUTPUT / 'contract.json').read_bytes()),
                                         'one_shot': True, 'uncertain_retry': False})
    raw_root = OUTPUT / 'raw'; raw_root.mkdir(mode=0o700)
    import google.auth
    from google.auth.transport.requests import Request
    from reasoning_engine.executor import EffectExecutor, HttpResponse
    from reasoning_engine.vertex_journal import VertexJournal
    from faithful_v3.action_case import run_case
    import importlib.util
    spec = importlib.util.spec_from_file_location('approved_oneshot', TRANSPORT)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    credentials, project = google.auth.default(scopes=['https://www.googleapis.com/auth/cloud-platform'])
    if not project or sha(project.encode()) != PROJECT_SHA256: raise ValueError('project identity differs from prior run')
    def token(_provider):
        if not credentials.valid: credentials.refresh(Request())
        if not credentials.token: raise ValueError('credentials unavailable')
        return credentials.token
    transport = module.OneShotTransport(project, token)
    counter = 0
    def one(endpoint):
        def perform(raw):
            nonlocal counter
            if sha(raw) in FORBIDDEN_REQUESTS: raise ValueError('historical uncertain request cannot be repeated')
            counter += 1
            status, body = with_wall_timeout(lambda: transport('vertex', endpoint, raw))
            quarantine_raw(raw_root, counter, endpoint, raw, status, body)
            return HttpResponse(status, body)
        return perform
    executor = EffectExecutor(str(OUTPUT / 'effects.sqlite3'), exposure_cap=0, call_cap=16)
    budget = VertexBudget.successor(CHECKPOINT)
    callback = VertexJournal(executor, one('countTokens'), one('gemini-3.8-flash@global'),
                             session_id='vertex-halter-successor-v1',
                             identity={'contract_sha256': sha((OUTPUT / 'contract.json').read_bytes())}, budget=budget)
    outcome, failure = None, None
    try:
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
        path_passed = (len(retrievals) == 1 and retrievals[0].get('action_id') == 'synthetic-final-tally-lark7-v1'
                       and required.issubset(selected) and isinstance(citations, list) and required.issubset(citations))
        gate = ('passed' if failure is None and outcome is not None and outcome.get('status') == 'proposal'
                and path_passed and accounting['halted'] is None else 'not_passed')
        write_new(OUTPUT / 'summary.json', {'gate': gate, 'source_path_passed': path_passed,
                  'semantic_review': 'pending', 'case_status': outcome.get('status') if outcome else 'not_completed',
                  'case_reason': outcome.get('reason') if outcome else None, 'failure_type': failure,
                  'accounting': accounting, 'invoice': 'not reconciled'})
        executor.close()
    print(json.dumps({'gate': gate, 'case_status': outcome.get('status') if outcome else 'not_completed',
                      'failure_type': failure, 'accounting': accounting}, sort_keys=True))
    if gate != 'passed': raise SystemExit(2)

if __name__ == '__main__':
    if len(sys.argv) != 2 or sys.argv[1] not in {'prepare', 'execute'}:
        raise SystemExit('usage: vertex_halter_successor.py prepare|execute')
    (prepare if sys.argv[1] == 'prepare' else execute)()
