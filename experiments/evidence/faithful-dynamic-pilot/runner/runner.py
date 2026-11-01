"""Offline four-arm experiment assembly; injected transport only; NOT live-ready.

Review and capture provenance must be independently verified. A digest establishes
byte identity, not that bytes came from the asserted provider or human.
"""
from __future__ import annotations
import copy
import datetime as dt
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parent.parent
for module_dir in (ROOT, ROOT / 'controller', ROOT / 'harness', ROOT / 'budget-v2'):
    sys.path.insert(0, str(module_dir))
import faithful
import harness
import model_protocol
from ledger import Stop

ARMS = ('A', 'B', 'B_self_check', 'C')
GUIDE = Path('/Users/rk/.codex/worktrees/controller-evidence-integration/fitcheck-core/docs/label_guide.md')
PAIR_OUTPUTS = {'direct', 'indirect', 'weak_proxy', 'not_an_expression', 'unknown'}
KALSHI_URL = 'https://external-api.kalshi.com/trade-api/v2/events?limit=30&status=open&with_nested_markets=true'
MANUAL_SOURCE_HASH = '782eb55ee53f316ca97a2e1bbc1b979f0cd9b089a9b7acb0408f120e0cb9586a'
MANUAL_REPORTED_TIME = '2026-10-29T08:52:28Z'
TARGET_SOURCE_HASH = '2f6932c840ecbfc4bc3dac1f52a4f27aeac250f66fe345d0ad371c50be57363b'
TARGET_URL = 'https://external-api.kalshi.com/trade-api/v2/markets?limit=8&tickers=KXFEDDECISION-26DEC-H25%2CKXGDPNOM-US26-32.8%2CKXHIGHINFLATION-26DEC-T4.2%2CKXUSGDPSHARE-27JUL01-T25.7%2CKXIPO-26-ANTHROPIC%2CKXANTHROPICRESCIND-26JUN-27JAN01%2CKXCLAUDE-CLAUDE6-26DEC31%2CKXRSIANNOUNCE-29-27JAN01'
FED_CONTRACT = 'KXFEDDECISION-26DEC-H25'

class PreflightError(ValueError): pass


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _read_bound(root: Path, rel: str, expected: str) -> bytes:
    if not isinstance(rel, str) or not rel or not isinstance(expected, str):
        raise PreflightError('path and hash required')
    p = root / rel
    if p.is_absolute() and not p.resolve().is_relative_to(root):
        raise PreflightError('path outside bound dataset')
    if p.absolute() != p.resolve() or not p.is_file():
        raise PreflightError('missing file, traversal or symlink')
    raw = p.read_bytes()
    if sha(raw) != expected:
        raise PreflightError('artifact byte hash mismatch')
    return raw


def _leaves(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, list):
        for item in value: yield from _leaves(item)
    elif isinstance(value, dict):
        for item in value.values(): yield from _leaves(item)


def _objects(value):
    if isinstance(value, dict):
        yield value
        for child in value.values(): yield from _objects(child)
    elif isinstance(value, list):
        for child in value: yield from _objects(child)


def _evidence_bound(ev, blobs):
    if not isinstance(ev, dict) or ev.get('content_sha256') not in blobs:
        raise PreflightError('evidence lacks bound content bytes')
    raw = blobs[ev['content_sha256']]
    try: text = raw.decode('utf-8')
    except UnicodeDecodeError as exc: raise PreflightError('evidence bytes not UTF-8') from exc
    try: leaves = list(_leaves(json.loads(text)))
    except (ValueError, TypeError): leaves = [text]
    parts = ev.get('verbatim_parts')
    if not isinstance(parts, list) or len(parts) != 1 or not isinstance(parts[0], str) or not parts[0]:
        raise PreflightError('evidence needs exactly one contiguous verbatim span')
    if parts[0] != ev.get('text') or not any(parts[0] == leaf for leaf in leaves):
        raise PreflightError('evidence must equal one complete source value')


def preflight(manifest: dict, dataset_root: Path, ledger, verify_human: Callable | None, verify_capture: Callable | None):
    """Verify all inputs before any model callback; return private case copies.

    `verify_human` is mandatory and must check a separate provenance-bound human
    decision; returning True is a caller assertion, not verification by this code.
    Source effects must already be settled in this exact ledger and bind raw bytes.
    """
    if not callable(verify_human): raise PreflightError('human attestation verifier required')
    if not callable(verify_capture): raise PreflightError('capture provenance verifier required')
    try: harness.validate_manifest(manifest)
    except (harness.ProtocolError, TypeError, KeyError) as exc: raise PreflightError(str(exc)) from exc
    root = Path(dataset_root).resolve()
    if not root.is_dir(): raise PreflightError('dataset root missing')
    guide_raw = GUIDE.read_bytes()
    guide_sha = sha(guide_raw)
    cases = []
    seen_contracts = set()
    for row in manifest['cases']:
        case_raw = _read_bound(root, row.get('input_path'), row['input_sha256'])
        try: case = json.loads(case_raw)
        except (ValueError, TypeError) as exc: raise PreflightError('case JSON invalid') from exc
        confirmation = _read_bound(root, row.get('human_attestation_path'), row.get('human_attestation_sha256'))
        if not verify_human(confirmation, copy.deepcopy(case), copy.deepcopy(row)):
            raise PreflightError('human attestation not independently verified')
        if not verify_capture(copy.deepcopy(case), copy.deepcopy(row)):
            raise PreflightError('capture provenance not independently verified')
        if not isinstance(case, dict) or not isinstance(case.get('task'), dict) or not isinstance(case.get('replay'), dict):
            raise PreflightError('case needs task and replay')
        task, replay = case['task'], case['replay']
        if task.get('case_id') != row['case_id']:
            raise PreflightError('case identity mismatch')
        try: harness.prepare_task(task, replay)
        except (harness.ProtocolError, TypeError, KeyError) as exc: raise PreflightError(str(exc)) from exc
        if set(task['allowed_labels']) != PAIR_OUTPUTS or len(task['allowed_labels']) != len(PAIR_OUTPUTS):
            raise PreflightError('four active classes and exploratory unknown required')
        if seen_contracts & set(task['contract_ids']):
            raise PreflightError('market ID repeats across cases')
        seen_contracts.update(task['contract_ids'])
        attachments = case.get('attachments')
        if not isinstance(attachments, list) or not attachments: raise PreflightError('attachments missing')
        blobs = {}
        for a in attachments:
            if not isinstance(a, dict): raise PreflightError('attachment invalid')
            raw = _read_bound(root, a.get('path'), a.get('sha256'))
            if a['sha256'] in blobs and blobs[a['sha256']] != raw:
                raise PreflightError('attachment hash collision')
            blobs[a['sha256']] = raw
        if guide_sha not in blobs or blobs[guide_sha] != guide_raw:
            raise PreflightError('current active label guide bytes absent')
        if TARGET_SOURCE_HASH in blobs and FED_CONTRACT in task['contract_ids']:
            conflict = {'contract_id': FED_CONTRACT, 'field': 'rules_secondary', 'status': 'unresolved'}
            if conflict not in case.get('source_conflicts', []):
                raise PreflightError('targeted Fed rule conflict must be recorded unresolved')
        market_records = []
        for raw in blobs.values():
            try: market_records.extend(_objects(json.loads(raw)))
            except (ValueError, UnicodeDecodeError): pass
        for contract_id in task['contract_ids']:
            if not any(r.get('ticker') == contract_id and r.get('event_ticker') == row['event_group_id'] for r in market_records):
                raise PreflightError('market and event identity not bound in snapshot')
        initial = task['initial_evidence']
        if not any(e.get('content_sha256') == guide_sha and e.get('text') == guide_raw.decode('utf-8') for e in initial):
            raise PreflightError('active label guide must be selectable whole evidence')
        if not all(any(contract in e.get('text', '') for e in initial) for contract in task['contract_ids']):
            raise PreflightError('each contract id must be in initial selectable text')
        for e in initial: _evidence_bound(e, blobs)
        initial_texts = {e['text'] for e in initial}
        actions = task['actions']
        if not 1 <= len(actions) <= 2: raise PreflightError('one or two captured actions required')
        for action in actions:
            if action.get('capture_kind', 'paid_api') == 'manual_capture':
                receipt_raw = _read_bound(root, action.get('manual_receipt_path'), action.get('manual_receipt_sha256'))
                try: receipt = json.loads(receipt_raw)
                except (ValueError, TypeError) as exc: raise PreflightError('manual receipt invalid') from exc
                if not isinstance(receipt, dict) or action.get('quoted_cost_micro_usd') is not None:
                    raise PreflightError('manual capture report incomplete or incompatible')
                old = (receipt.get('url_reported') == KALSHI_URL and receipt.get('http_status_reported') == 200 and
                       receipt.get('reported_direct_http') is True and receipt.get('report_attribution') == 'user relaying Grok statement' and
                       receipt.get('independent_attestation') is False and receipt.get('source_sha256') == MANUAL_SOURCE_HASH and
                       receipt.get('utc_request_time_reported') == MANUAL_REPORTED_TIME)
                targeted = (receipt.get('source_request_url') == TARGET_URL and receipt.get('reported_http_status') == 200 and
                            receipt.get('reported_direct_http') is True and receipt.get('classification') == 'user-relayed Grok claim; provider transport not independently verified' and
                            receipt.get('content_sha256') == TARGET_SOURCE_HASH and receipt.get('reported_request_start_utc') == '2026-10-29T08:58:06Z' and
                            receipt.get('reported_request_end_utc') == '2026-10-29T08:58:07Z' and receipt.get('reported_http_date') == 'Thu, 29 Oct 2026 08:58:06 GMT')
                if not old and not targeted: raise PreflightError('manual capture report not admitted')
                time_text = receipt['utc_request_time_reported'] if old else receipt['reported_request_start_utc']
                try: timestamp = dt.datetime.fromisoformat(time_text.replace('Z','+00:00'))
                except (KeyError, AttributeError, ValueError) as exc: raise PreflightError('manual report time invalid') from exc
                if timestamp.utcoffset() != dt.timedelta(0): raise PreflightError('manual report requires UTC')
                expected_hash = receipt['source_sha256'] if old else receipt['content_sha256']
                if expected_hash not in blobs: raise PreflightError('manual capture bytes not attached')
            else:
                effect_id = action.get('source_effect_id')
                effect = ledger.db.execute("SELECT state,actual_micro,response_hash,quote_micro,kind,response FROM effects WHERE id=?", (effect_id,)).fetchone()
                if effect is None or effect[0] != 'succeeded' or effect[1] is None or effect[4] != 'source' or not isinstance(effect[5], bytes):
                    raise PreflightError('action lacks settled source effect')
                if sha(effect[5]) != effect[2]: raise PreflightError('stored source response digest mismatch')
                if action['quoted_cost_micro_usd'] != effect[3]: raise PreflightError('action quote differs from capture')
                expected_hash = effect[2]
            for e in replay[action['id']]['evidence']:
                _evidence_bound(e, blobs)
                if e['text'] in initial_texts: raise PreflightError('initial and replay evidence text overlap')
                if e.get('content_sha256') != expected_hash: raise PreflightError('replay differs from captured bytes')
        admitted_row = copy.deepcopy(row)
        admitted_row['unresolved_source_conflicts'] = copy.deepcopy(case.get('source_conflicts', []))
        cases.append((admitted_row, copy.deepcopy(task), copy.deepcopy(replay)))
    return cases


def schedule(cases):
    ordered = sorted(cases, key=lambda item: (0 if item[0]['split'] == 'dev' else 1, item[0]['event_group_id']))
    return [(row, task, replay, ARMS[(i + j) % 4])
            for i, (row, task, replay) in enumerate(ordered) for j in range(4)]


def _write_once(path: Path, value):
    data = json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2).encode()
    with path.open('xb') as f:
        f.write(data); f.flush(); os.fsync(f.fileno())
    dfd = os.open(path.parent, os.O_RDONLY)
    try: os.fsync(dfd)
    finally: os.close(dfd)


def run(manifest, dataset_root, output_dir, ledger, transport, verify_human=None, verify_capture=None):
    """Execute only through injected transport; a separate reviewed caller owns live authority."""
    cases = preflight(manifest, Path(dataset_root), ledger, verify_human, verify_capture)
    if not callable(transport): raise PreflightError('injected one-shot transport required')
    sequence = schedule(cases)
    out = Path(output_dir)
    out.mkdir(mode=0o700)  # create-only; do not overwrite a prior run
    def persist(path, value):
        try: _write_once(path, value)
        except BaseException:
            try: ledger.stop('runner artifact persistence failed')
            finally: ledger.poisoned = True
            raise
    schedule_data = [{'case_id': row['case_id'], 'split': row['split'], 'arm': arm} for row, _, _, arm in sequence]
    persist(out / 'schedule.json', schedule_data)
    persist(out / 'manifest.json', manifest)
    binding = {'manifest_sha256': sha((out / 'manifest.json').read_bytes()),
               'schedule_sha256': sha((out / 'schedule.json').read_bytes()),
               'protocol_sha256': sha(Path(model_protocol.__file__).read_bytes()),
               'controller_sha256': sha(Path(faithful.__file__).read_bytes()),
               'harness_sha256': sha(Path(harness.__file__).read_bytes()),
               'runner_sha256': sha(Path(__file__).read_bytes()),
               'label_guide_sha256': sha(GUIDE.read_bytes())}
    persist(out / 'binding.json', binding)
    # This durable marker prohibits restarting a previously started runner in a
    # fresh output directory against the same ledger, even before first count.
    try:
        ledger.db.execute('BEGIN IMMEDIATE')
        if ledger.db.execute("SELECT 1 FROM run_events WHERE event='runner_started' LIMIT 1").fetchone():
            raise Stop('runner already started; resume is not permitted')
        if ledger.summary()['stopped']:
            raise Stop('ledger already stopped')
        ledger.db.execute("INSERT INTO run_events(event,reason,at_utc) VALUES ('runner_started',?,?)",
                          (sha((out / 'binding.json').read_bytes()), dt.datetime.now(dt.timezone.utc).isoformat()))
        ledger.db.execute('COMMIT')
    except BaseException:
        if ledger.db.in_transaction: ledger.db.execute('ROLLBACK')
        try: ledger.stop('runner binding failed or duplicate')
        finally: ledger.poisoned = True
        raise
    results = []
    stop = None
    for slot, (row, task, replay, arm) in enumerate(sequence):
        persist(out / f'{slot:02d}-started.json', {'slot':slot,'case_id':row['case_id'],'arm':arm,'state':'started'})
        call_no = 0
        def generate(stage, payload):
            nonlocal call_no
            bound_files = {'protocol_sha256': Path(model_protocol.__file__),
                           'controller_sha256': Path(faithful.__file__),
                           'harness_sha256': Path(harness.__file__),
                           'runner_sha256': Path(__file__), 'label_guide_sha256': GUIDE}
            try:
                unchanged = all(sha(path.read_bytes()) == binding[key] for key, path in bound_files.items())
            except OSError:
                unchanged = False
            if not unchanged:
                ledger.stop('runner code or label guide drifted')
                raise Stop('bound implementation or policy changed')
            call_no += 1
            request = model_protocol.request(stage, payload)
            op = f'{slot:02d}:{call_no:02d}'
            ledger.count('count:' + op, request, transport)
            raw = ledger.generate('generation:' + op, request, 'count:' + op, transport)
            return model_protocol.parse(json.loads(raw))
        engine = None
        try:
            if arm == 'C':
                engine = faithful.Engine(generate)
                outcome = engine.run(task, replay)
            else:
                engine = harness.BaselineEngine(generate)
                outcome = engine.run(task, replay, arm)
            answers = outcome.get('proposed_answers', []) if arm == 'C' else outcome.get('result', {}).get('answers', [])
            if outcome.get('status') == 'technical_failure':
                semantic_status = 'technical_failure'
            elif row.get('unresolved_source_conflicts'):
                semantic_status = 'unassessed_source_conflict'
            elif outcome.get('status') == 'unknown' or any(x.get('label') == 'unknown' for x in answers):
                semantic_status = 'unassessed_unknown'
            else:
                semantic_status = 'proposal_unreviewed'
            result = {'slot': slot, 'case_id': row['case_id'], 'arm': arm, 'outcome': outcome, 'semantic_status': semantic_status,
                      'unresolved_source_conflicts': row.get('unresolved_source_conflicts', [])}
        except Stop as exc:
            result = {'slot': slot, 'case_id': row['case_id'], 'arm': arm,
                      'status': 'stopped', 'error_type': type(exc).__name__,
                      'partial_trace': copy.deepcopy(getattr(engine, 'events', getattr(engine, 'last_trace', [])))}
            stop = slot
        except Exception as exc:
            # Do not reconstruct a semantic answer from a failed model output.
            result = {'slot': slot, 'case_id': row['case_id'], 'arm': arm,
                      'status': 'technical_failure', 'error_type': type(exc).__name__,
                      'partial_trace': copy.deepcopy(getattr(engine, 'events', getattr(engine, 'last_trace', [])))}
            if ledger.summary()['stopped']: stop = slot
        persist(out / f'{slot:02d}.json', result)
        results.append(result)
        if stop is not None: break
    summary = {'requested_slots': len(sequence), 'attempted_slots': len(results),
               'not_attempted_slots': len(sequence) - len(results), 'stop_slot': stop,
               'ledger': ledger.summary(), 'review': 'not adjudicated', 'results': results,
               'manual_capture_external_cost': 'unknown' if any(a.get('capture_kind') == 'manual_capture' for _,task,_ in cases for a in task['actions']) else 'not applicable'}
    persist(out / 'summary.json', summary)
    return summary
