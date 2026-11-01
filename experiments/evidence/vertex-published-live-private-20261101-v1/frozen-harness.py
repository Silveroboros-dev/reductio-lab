"""Private, single-use published-Vertex repeat. Import and prepare are offline.

The implementer only supplies the harness. An independent reviewer creates
challenge_packet_v0001.json after prepare. Execute is deliberately single-use.
"""
from __future__ import annotations

import contextlib
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import signal
import stat
import subprocess
import sys

HERE = Path(__file__).resolve().parent
BASE = Path('/Users/rk/.codex/visualizations/2026/10/29/01a1865f-6bd2-75a2-abb1-eb14b071bbe0')
REPO = BASE / 'reductio-lab'
PREVIOUS = BASE / 'vertex-span-successor-private-20261101-v2'
TRANSPORT = BASE / 'faithful-dynamic-pilot/transport/oneshot.py'
OUTPUT = BASE / 'vertex-published-live-private-20261101-v1'
HEAD = '47fb68452b2587a7b632d93a43e10c625d84c2fd'
PREVIOUS_CHECKPOINT_SHA256 = 'f0dd846c419d232c6bed97ef93390eff599096bb5f09f8cb87e0a1c05b270873'
PREVIOUS_LEDGER_SHA256 = '9ad273a46044c2b42ce790017c57110b6a3c98e632791ff1db11513f8e0a8533'
PRIOR_EXPOSURE = 56_933_183
PRIOR_GENERATION = 1_640
PRIOR_COUNT = 1_562
FORBIDDEN = frozenset({
    '17a148b5aeade7252bf07660e16d3c6ffbb4da639aaf31d2332cd88b2a7e10e4',
    'cbc14ce21dfdabfb14657e14823f19db22e31a6a63bc9136ec949dd868c6094e',
    'fd2e5bcb4de52dce98b476e54fc8538f291058ecfbb9f832ab4d2e5113690581',
})
SOURCE_IDS = {'source:synthetic-rule-lark7-v1', 'source:synthetic-final-tally-lark7-v1'}
sys.path.insert(0, str(REPO))


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, ensure_ascii=False,
                      separators=(',', ':'), allow_nan=False).encode('utf-8')


def assert_plain_path(path: Path, *, exists: bool = True) -> None:
    """Reject links at every existing ancestor, including private evidence roots."""
    for part in [path, *path.parents]:
        try:
            mode = part.lstat().st_mode
        except FileNotFoundError:
            if part == path and not exists:
                continue
            raise
        if stat.S_ISLNK(mode):
            raise ValueError('symlinked evidence or output path')
    if exists and not path.is_file() and not path.is_dir():
        raise ValueError('non-regular evidence or output path')


def read(path: Path) -> bytes:
    assert_plain_path(path)
    if not path.is_file():
        raise ValueError('expected regular evidence file')
    return path.read_bytes()


def write_new(path: Path, raw: bytes, *, mode: int = 0o600) -> None:
    assert_plain_path(path.parent)
    assert_plain_path(path, exists=False)
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY |
                 getattr(os, 'O_NOFOLLOW', 0), mode)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    os.chmod(path, mode)
    dir_fd = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(dir_fd)
    finally:
        os.close(dir_fd)


def json_new(path: Path, value: object, *, mode: int = 0o600) -> None:
    write_new(path, canonical(value), mode=mode)


def git(*args: str) -> str:
    return subprocess.check_output(['git', *args], cwd=REPO, text=True).strip()


def budget():
    from reasoning_engine.vertex_journal import VertexBudget
    return VertexBudget(
        prior_exposure_micro_usd=PRIOR_EXPOSURE,
        incremental_cap_micro_usd=2_400_000,
        generation_reserve_micro_usd=520_000,
        count_attempt_cap=12, generation_attempt_cap=12,
        max_input_tokens=8192,
        input_rate_micro_usd_per_million=750_000,
        output_rate_micro_usd_per_million=3_750_000,
        count_tokens_are_free=True,
        forbidden_request_sha256=FORBIDDEN,
    )


def predecessor() -> tuple[dict, dict, dict[str, str]]:
    names = ('accounting-checkpoint.json', 'contract.json', 'summary.json',
             'outcome.json', 'effects.sqlite3', 'challenge_packet_v0001.json')
    hashes = {name: sha(read(PREVIOUS / name)) for name in names}
    if (hashes['accounting-checkpoint.json'] != PREVIOUS_CHECKPOINT_SHA256 or
            hashes['effects.sqlite3'] != PREVIOUS_LEDGER_SHA256):
        raise ValueError('independently anchored predecessor hash changed')
    old = json.loads(read(PREVIOUS / 'accounting-checkpoint.json'))
    old_contract = json.loads(read(PREVIOUS / 'contract.json'))
    old_summary = json.loads(read(PREVIOUS / 'summary.json'))
    for name, key in (('contract.json', 'contract_sha256'),
                      ('summary.json', 'summary_sha256'),
                      ('outcome.json', 'outcome_sha256'),
                      ('effects.sqlite3', 'ledger_sha256'),
                      ('challenge_packet_v0001.json', 'challenge_sha256')):
        if hashes[name] != old[key]:
            raise ValueError('predecessor artifact differs from checkpoint: ' + name)
    if (old['total_exposure_micro_usd'], old['total_generation_attempts'],
            old['total_count_attempts']) != (PRIOR_EXPOSURE, PRIOR_GENERATION, PRIOR_COUNT):
        raise ValueError('predecessor cumulative accounting changed')
    if (old['new_generation_attempts'], old['new_count_attempts'],
            old['new_unsettled_reservation_micro_usd']) != (6, 6, 0):
        raise ValueError('predecessor run accounting changed')
    if (old['cumulative_phase_generation_attempts'],
            old['cumulative_phase_count_attempts'],
            old['cumulative_phase_committed_micro_usd']) != (14, 14, 11_013):
        raise ValueError('predecessor phase accounting changed')
    if old_summary['gate'] != 'passed' or old_summary['accounting']['uncertain_attempts'] != 0:
        raise ValueError('predecessor gate or uncertainty changed')
    if (old_summary['accounting']['generation_attempts'],
            old_summary['accounting']['count_attempts']) != (6, 6):
        raise ValueError('predecessor summary counts changed')
    if old_contract['forbidden_request_sha256'] != sorted(FORBIDDEN):
        raise ValueError('historical forbidden request set changed')
    return old, old_contract, hashes


def source_hashes() -> dict[str, str]:
    paths = subprocess.check_output(['git', 'ls-files', '-z', '*.py',
                                     'pyproject.toml'], cwd=REPO).split(b'\0')
    result = {}
    for raw in paths:
        if not raw:
            continue
        relative = os.fsdecode(raw)
        path = REPO / relative
        result[relative] = sha(read(path))
    if not result or 'reasoning_engine/vertex_journal.py' not in result:
        raise ValueError('tracked source inventory missing journal')
    return result


def contract() -> dict:
    assert_plain_path(HERE)
    assert_plain_path(REPO)
    assert_plain_path(PREVIOUS)
    if git('rev-parse', 'HEAD') != HEAD:
        raise ValueError('published revision differs')
    if git('rev-parse', 'HEAD') != git('rev-parse', 'origin/main'):
        raise ValueError('HEAD differs from published origin/main')
    if git('branch', '--show-current') != 'main':
        raise ValueError('unexpected branch')
    if git('status', '--porcelain=v1', '--untracked-files=no'):
        raise ValueError('tracked source or worktree state differs from published HEAD')
    old, old_contract, old_hashes = predecessor()
    case = {'checkpoint': old_contract['checkpoint'], 'catalog': old_contract['catalog']}
    if len(case['catalog']) != 1 or case['checkpoint']['case_id'] != 'synthetic-source-si-lark7-20261029-v1':
        raise ValueError('frozen case changed')
    if old_contract['pricing']['usd_per_million_input'] != '0.75' or old_contract['pricing']['usd_per_million_output_including_thoughts'] != '3.75':
        raise ValueError('predecessor price basis changed')
    tracked = source_hashes()
    extras = {
        str(TRANSPORT): sha(read(TRANSPORT)),
        str(REPO / 'research/vertex_span_successor.py'):
            sha(read(REPO / 'research/vertex_span_successor.py')),
        str(REPO / 'research/vertex_compatibility_canary.py'):
            sha(read(REPO / 'research/vertex_compatibility_canary.py')),
    }
    pricing_doc = REPO / 'docs/provider-pricing-observation-20261029.md'
    return {
        'schema': 'published-vertex-repeat-v1',
        'published_revision': git('rev-parse', 'HEAD'),
        'published_ref': 'origin/main', 'branch': 'main',
        'dirty_policy': 'tracked paths must be clean against published HEAD; all tracked Python sources and pyproject bound by raw hash; listed untracked helpers bound separately',
        'tracked_source_sha256': tracked, 'extra_code_sha256': extras,
        'harness_code_sha256': sha(read(Path(__file__).resolve())),
        'pricing_evidence': {
            'prior_contract_sha256': old_hashes['contract.json'],
            'coordinator_observed_utc_date': '2026-11-01',
            'provider_pricing_url': 'https://cloud.google.com/model-garden/pricing',
            'provider_count_tokens_url': 'https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/capabilities/get-token-count',
            'provider_observation_scope': 'Gemini 3.8 Flash global standard through 2026-12-31; countTokens no charge',
            'local_document_path': str(pricing_doc),
            'local_document_sha256': sha(read(pricing_doc)),
            'rates_authorized_by_human_micro_usd_per_million': {'input': 750_000, 'output_including_thoughts': 3_750_000},
            'invoice': 'not_reconciled',
            'note': 'older local observation describes a different standard/promotion distinction; this run uses explicit human-authorized rates, prior-contract rates, and the coordinator 2026-11-01 public-doc observation; URLs are not a byte seal',
        },
        'predecessor': {
            'root': str(PREVIOUS), 'raw_sha256': old_hashes,
            'checkpoint_cumulative_exposure_micro_usd': old['total_exposure_micro_usd'],
            'checkpoint_cumulative_generation_attempts': old['total_generation_attempts'],
            'checkpoint_cumulative_count_attempts': old['total_count_attempts'],
        },
        'case_allowlist_sha256': sha(canonical(case)), 'case': case,
        'model': 'gemini-3.8-flash', 'location': 'global',
        'observed_model_policy': 'exact',
        'endpoint_count': 'countTokens', 'endpoint_generate': 'gemini-3.8-flash@global',
        'thinking_level': 'LOW', 'max_output_tokens': 4096,
        'max_case_calls': 6, 'max_depth': 1, 'beam_width': 1, 'max_alternatives': 1,
        'source_provider_calls': 0, 'new_canary': False,
        'timeout_seconds': 420, 'single_worker': True,
        'max_model_attempts_per_operation': 2,
        'retry_policy': 'one exact separate attempt after captured HTTP 429 RESOURCE_EXHAUSTED; 2+jitter[0,1] seconds; never uncertain',
        'executor_call_cap': 24, 'budget': budget().as_contract(),
        'original_total_cap_micro_usd': 60_000_000,
        'project_id_sha256': old_contract['project_id_sha256'],
        'runtime': {'python': sys.version.split()[0],
                    'httpx': importlib.metadata.version('httpx'),
                    'google-auth': importlib.metadata.version('google-auth')},
        'gate': 'blocked for any execution exception, journal_call_* reason, uncertain/cap/halt/capture/accounting failure; failed for structural nonpass including valid technical_failure; passed only for proposal, one tally retrieval, both sources selected and cited',
        'semantic_review': 'pending',
    }


def prepare() -> None:
    frozen = contract()
    os.umask(0o077)
    assert_plain_path(OUTPUT.parent)
    if OUTPUT.exists() or OUTPUT.is_symlink():
        raise ValueError('output root already exists; prepare is create-only')
    OUTPUT.mkdir(mode=0o700)
    case_raw = canonical(frozen['case'])
    write_new(OUTPUT / 'frozen-harness.py', read(Path(__file__).resolve()), mode=0o400)
    write_new(OUTPUT / 'case-allowlist.json', case_raw, mode=0o400)
    json_new(OUTPUT / 'contract.json', frozen, mode=0o400)
    print('Prepared private frozen contract; zero provider operations.')


def quarantine_raw(directory: Path, index: int, endpoint: str,
                   request: bytes, status: int, body: bytes) -> None:
    """Durably save exact body before the caller or journal parses it."""
    assert_plain_path(directory)
    stem = f'{index:03d}'
    temporary = directory / (stem + '.tmp')
    final = directory / (stem + '.bin')
    write_new(temporary, body)
    os.link(temporary, final, follow_symlinks=False)
    os.unlink(temporary)
    dir_fd = os.open(directory, os.O_RDONLY)
    try:
        os.fsync(dir_fd)
    finally:
        os.close(dir_fd)
    json_new(directory / (stem + '.json'), {
        'index': index, 'endpoint': endpoint, 'request_sha256': sha(request),
        'http_status': status, 'response_sha256': sha(body), 'response_bytes': len(body),
    })


@contextlib.contextmanager
def wall_deadline(seconds: int):
    if signal.getitimer(signal.ITIMER_REAL) != (0.0, 0.0):
        raise ValueError('existing alarm conflicts with run deadline')
    old_handler = signal.getsignal(signal.SIGALRM)
    def elapsed(_signal, _frame):
        raise TimeoutError('run wall deadline elapsed')
    signal.signal(signal.SIGALRM, elapsed)
    signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, old_handler)


def gate_status(outcome: dict | None, accounting: dict | None,
                failure: str | None, capture_error: bool = False) -> tuple[str, bool]:
    history = outcome.get('history', []) if isinstance(outcome, dict) else []
    if not isinstance(history, list):
        history = []
    retrievals = [x for x in history if isinstance(x, dict) and x.get('kind') == 'replay_retrieval']
    finals = [x.get('outcome', {}) for x in history if isinstance(x, dict) and x.get('kind') == 'final']
    final = finals[-1] if finals else {}
    final = final if isinstance(final, dict) else {}
    selected_rows = final.get('selected_evidence', [])
    selected = ({x.get('id') for x in selected_rows if isinstance(x, dict)}
                if isinstance(selected_rows, list) else set())
    result = outcome.get('result') if isinstance(outcome, dict) else None
    citations = result.get('citations', []) if isinstance(result, dict) else []
    path_passed = (len(retrievals) == 1 and
                   retrievals[0].get('action_id') == 'synthetic-final-tally-lark7-v1' and
                   SOURCE_IDS.issubset(selected) and isinstance(citations, list) and
                   SOURCE_IDS.issubset(citations))
    explanation = outcome.get('unknown_explanation', {}) if isinstance(outcome, dict) else {}
    reason = outcome.get('reason') if isinstance(outcome, dict) else None
    if (capture_error or failure is not None or not isinstance(outcome, dict) or
            not isinstance(accounting, dict) or
            type(accounting.get('uncertain_attempts')) is not int or
            accounting['uncertain_attempts'] != 0 or
            accounting.get('cap_exceeded') is not False or
            'halted' not in accounting or accounting['halted'] is not None or
            (isinstance(reason, str) and reason.startswith('journal_call_')) or
            (isinstance(explanation, dict) and explanation.get('callback_effect_state') == 'not_established')):
        return 'blocked', path_passed
    if outcome.get('status') == 'proposal' and path_passed:
        return 'passed', path_passed
    return 'failed', path_passed


def execute() -> None:
    assert_plain_path(OUTPUT)
    raw_contract = read(OUTPUT / 'contract.json')
    frozen = json.loads(raw_contract)
    if frozen != contract() or raw_contract != canonical(frozen):
        raise ValueError('contract, code, predecessor, Git or runtime drift')
    if read(OUTPUT / 'case-allowlist.json') != canonical(frozen['case']):
        raise ValueError('private case snapshot changed')
    if sha(read(OUTPUT / 'frozen-harness.py')) != frozen['harness_code_sha256']:
        raise ValueError('durable harness snapshot changed')
    packet = json.loads(read(OUTPUT / 'challenge_packet_v0001.json'))
    if (packet.get('schema_version') != 'eval_contract_challenge_packet_v1' or
            packet.get('packet_sequence') != 1 or
            packet.get('overall_state') != 'ready' or
            packet.get('contract_sha256') != sha(raw_contract) or
            packet.get('challenged_contract', {}).get('raw_sha256') != sha(raw_contract) or
            packet.get('challenged_contract', {}).get('byte_count') != len(raw_contract) or
            packet.get('authority_assessment', {}).get('authority_present') is not True or
            packet.get('authority_assessment', {}).get('live_authority_granted_by_packet') is not False):
        raise ValueError('independent challenge is missing, blocked, or bound to another contract')
    if packet.get('context_binding', {}).get('source_revision') != frozen['published_revision']:
        raise ValueError('challenge context differs from published revision')
    os.umask(0o077)
    json_new(OUTPUT / 'dispatch.json', {'contract_sha256': sha(raw_contract),
             'challenge_packet_sha256': sha(read(OUTPUT / 'challenge_packet_v0001.json')),
             'one_shot': True, 'uncertain_retry': False})
    raw_root = OUTPUT / 'raw'
    raw_root.mkdir(mode=0o700)
    outcome = None
    failure = None
    capture_error = False
    callback = None
    executor = None
    try:
        import google.auth
        from google.auth.transport.requests import Request
        from reasoning_engine.executor import EffectExecutor, HttpResponse
        from reasoning_engine.vertex_journal import VertexJournal
        from faithful_v3.action_case import run_case
        import importlib.util
        spec = importlib.util.spec_from_file_location('published_oneshot', TRANSPORT)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        credentials, project = google.auth.default(
            scopes=['https://www.googleapis.com/auth/cloud-platform'])
        if not project or sha(project.encode()) != frozen['project_id_sha256']:
            raise ValueError('project identity differs from predecessor')
        def token(_provider):
            if not credentials.valid:
                credentials.refresh(Request())
            if not credentials.token:
                raise ValueError('credentials unavailable')
            return credentials.token
        transport = module.OneShotTransport(project, token)
        counter = 0
        def one(endpoint):
            def perform(raw):
                nonlocal counter, capture_error
                if sha(raw) in FORBIDDEN:
                    raise ValueError('historical uncertain request cannot be repeated')
                counter += 1
                with wall_deadline(420):
                    status, body = transport('vertex', endpoint, raw)
                try:
                    quarantine_raw(raw_root, counter, endpoint, raw, status, body)
                except Exception:
                    capture_error = True
                    raise
                return HttpResponse(status, body)
            return perform
        executor = EffectExecutor(str(OUTPUT / 'effects.sqlite3'),
                                  exposure_cap=0, call_cap=24)
        callback = VertexJournal(
            executor, one('countTokens'), one('gemini-3.8-flash@global'),
            session_id='published-vertex-repeat-v1',
            identity={'contract_sha256': sha(raw_contract),
                      'case_allowlist_sha256': frozen['case_allowlist_sha256']},
            budget=budget(), retry_confirmed_429=True)
        outcome = run_case(frozen['case']['checkpoint'], frozen['case']['catalog'],
                           callback, max_calls=6, max_depth=1,
                           beam_width=1, max_alternatives=1)
        json_new(OUTPUT / 'outcome.json', outcome)
    except Exception as exc:
        failure = type(exc).__name__
    finally:
        accounting = None
        try:
            if callback is not None:
                accounting = callback.accounting()
        except Exception:
            capture_error = True
        gate, path_passed = gate_status(outcome, accounting, failure, capture_error)
        summary = {
            'gate': gate, 'source_path_passed': path_passed,
            'semantic_review': 'pending',
            'case_status': outcome.get('status') if outcome else 'not_completed',
            'case_reason': outcome.get('reason') if outcome else None,
            'failure_type': failure, 'capture_or_accounting_error': capture_error,
            'accounting': accounting, 'invoice': 'not_reconciled',
            'prior_exposure_micro_usd': PRIOR_EXPOSURE,
            'prior_generation_attempts': PRIOR_GENERATION,
            'prior_count_attempts': PRIOR_COUNT,
            'total_exposure_estimated_or_reserved_micro_usd':
                (PRIOR_EXPOSURE + accounting['committed_micro_usd'] if accounting else None),
            'total_generation_attempts':
                (PRIOR_GENERATION + accounting['generation_attempts'] if accounting else None),
            'total_count_attempts':
                (PRIOR_COUNT + accounting['count_attempts'] if accounting else None),
        }
        json_new(OUTPUT / 'summary.json', summary)
        if executor is not None:
            executor.close()
    print(json.dumps({'gate': gate, 'case_status': summary['case_status'],
                      'failure_type': failure, 'accounting': accounting}, sort_keys=True))
    if gate != 'passed':
        raise SystemExit(3 if gate == 'blocked' else 2)


if __name__ == '__main__':
    if len(sys.argv) != 2 or sys.argv[1] not in {'prepare', 'execute'}:
        raise SystemExit('usage: harness.py prepare|execute')
    (prepare if sys.argv[1] == 'prepare' else execute)()
