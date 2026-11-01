"""Replay recorded B source decisions against C_v3; SI uses explicit fixtures.

No provider is imported or contacted. Input payloads must exactly match the old
recordings, but those decisions were generated with the earlier B prompt, not
with the revised C_v3 source prompt. This is a routing audit, not a model eval.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path

from faithful_v3.action_case import run_case
from reasoning_engine.replay_sources import digest
from research.live_run import load_inputs

BASE = Path('/Users/rk/.codex/visualizations/2026/10/29/01a1865f-6bd2-75a2-abb1-eb14b071bbe0')
AGGREGATE = BASE / 'reasoning-experiment-derived-20261029-v1/combined-54-20261029.json'
OUT_JSON = BASE / 'reasoning-experiment-derived-20261029-v1/faithful-v3-offline-replay-20261029-v2.json'
OUT_NOTE = Path(__file__).resolve().parents[1] / 'notes/faithful-v3-offline-replay-20261029-v2.md'
EXPECTED = {
    'source-choice-v7-8f4f456fc619e25bd4eab2f6', 'source-choice-v7-0745ea0d6c6e5fc5629cab2c',
    'source-choice-v7-5d8e35ecbc6f27e61d005338', 'source-choice-disc-v1-ca855134bb8a9ca2df0db297',
    'source-choice-v7-ff59b8a886ae8b57f6c52647', 'source-choice-disc-v1-fb65b72808abd6bc63c35cc3',
    'source-choice-v7-2a2b9cf07e8702ec8adae441', 'source-choice-disc-v1-6f163022466b0539ac21bb8a',
    'source-choice-v7-5114796919f52673ea9ea0b8', 'source-choice-v7-df3287ee17ba8235b3df3206',
    'eia-candidate-v1-77203da7db5528be804903db',
}
GDP_ID = 'source-choice-v7-f7cd06453b4b01e1b810aff5'


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def saved_decisions(row: dict) -> list[dict]:
    history = row['arms']['B']['full_outcome_packet']['outcome']['history']
    return [x for x in history if x.get('stage') == 'source_decision']


def replay(checkpoint: dict, catalog: list, row: dict, *, nominal_fixture=False) -> dict:
    old = row['arms']['B']['full_outcome_packet']['outcome']
    decisions = saved_decisions(row)
    if not decisions:
        raise ValueError('missing recorded baseline source decisions')
    index = 0
    target = checkpoint['input']['thesis']
    seen = []
    def scripted(stage, payload):
        nonlocal index
        seen.append(stage)
        if stage == 'source_decision':
            if index >= len(decisions) or payload != decisions[index]['input']:
                raise ValueError('historical source decision input differs')
            result = copy.deepcopy(decisions[index]['output'])
            index += 1
            return result
        if stage == 'selection':
            if target not in payload['question']:
                raise ValueError('target lost before Selection')
            ids = [x['id'] for x in payload['available_statements']]
            if not ids:
                return {'alternatives': []}
            return {'alternatives': [[ids[0]]]}
        if stage == 'inference':
            if set(payload) != {'selected_texts'}:
                raise ValueError('inference input boundary failed')
            # This string is explicitly a test fixture, not a model inference.
            return {'conclusion': 'SCRIPTED FIXTURE: no factual model inference was generated.'}
        if stage == 'halter':
            if target not in payload['question']:
                raise ValueError('target lost before Halter')
            return {'sufficient': False,
                    'reason': ('SCRIPTED FIXTURE: real-only data do not settle the nominal target.' if nominal_fixture
                               else 'SCRIPTED FIXTURE: deliberately no model answerability judgment.')}
        if stage == 'value':
            return {'score': 0.5}
        if stage == 'formatter':
            raise AssertionError('formatter must not run when scripted Halter says insufficient')
        raise AssertionError(stage)
    result = run_case(checkpoint, catalog, scripted, max_depth=1)
    if index != len(decisions):
        raise ValueError('not all historical source decisions replayed')
    old_retrievals = [(x['action_id'], x['response_sha256']) for x in old['history'] if x['kind'] == 'replay_retrieval']
    new_retrievals = [(x['action_id'], x['response_sha256']) for x in result['history'] if x['kind'] == 'replay_retrieval']
    if old_retrievals != new_retrievals:
        raise ValueError('replayed response identity mismatch')
    if result['status'] == 'technical_failure' or result['result'] is not None:
        raise ValueError('fixture did not preserve controlled unknown')
    return {'case_id': checkpoint['case_id'], 'input_version': checkpoint['input_version'],
            'prior_C_status': row['arms']['C_v2']['run_status'],
            'recorded_B_decision_inputs_matched': len(decisions),
            'recorded_B_choices': [x['output']['choice'] for x in decisions],
            'saved_retrievals': [{'action_id': x[0], 'response_sha256': x[1]} for x in new_retrievals],
            'source_routing': 'passed', 'fixture_only_SI_outcome': result['status'],
            'fixture_only_SI_reason': result['reason'], 'fixture_only_stages': seen,
            'full_new_outcome': result}


def write_new(path: Path, payload: bytes):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'wb') as f:
        f.write(payload); f.flush(); os.fsync(f.fileno())


def main():
    raw = AGGREGATE.read_bytes(); agg = json.loads(raw)
    ids = {r['case_id'] for r in agg['matrix'] if r['arms']['C_v2']['run_status'] == 'unknown'}
    if ids != EXPECTED:
        raise ValueError('historical 11-case identity mismatch')
    _, bundle, _, hashes = load_inputs()
    by_case = {x['case_id']: x for x in bundle['checkpoints']}
    rows = {x['case_id']: x for x in agg['matrix']}
    records = [replay(by_case[case_id], bundle['replay_catalog'], rows[case_id]) for case_id in sorted(ids)]
    if sum(x['recorded_B_decision_inputs_matched'] for x in records) != 15:
        raise ValueError('unexpected number of recorded baseline decisions')
    nominal = replay(by_case[GDP_ID], bundle['replay_catalog'], rows[GDP_ID], nominal_fixture=True)
    code = Path(__file__).resolve().parent
    envelope = {'schema': 'faithful-v3-offline-check-v1',
        'provider_calls': 0, 'new_model_responses': 0,
        'source_decisions': '15 previously recorded B responses; callback inputs exactly matched',
        'prompt_limitation': 'Previously recorded B decisions were made with the earlier prompt, not C_v3 prompt.',
        'si': 'scripted fixtures deliberately return insufficient; not model output or semantic evaluation',
        'source_aggregate_sha256': hashlib.sha256(raw).hexdigest(), 'source_hashes': hashes,
        'code_sha256': {p.name: sha(p) for p in sorted(code.glob('*.py'))},
        'cases': records, 'nominal_gdp_fixture': nominal}
    content = json.dumps(envelope, ensure_ascii=False, sort_keys=True, indent=2).encode()
    lines = ['# Faithful v3 — локальная проверка 11 случаев и nominal GDP\n',
        '**Нет новых платных, модельных или сетевых вызовов.** Это проверка маршрутизации и границ, не оценка качества новой модели.\n',
        'Все 11 случаев — те, где C_v2 ранее вернул `unknown` до получения источника. Для source-selector воспроизведены 15 *ранее записанных ответов B* при точном совпадении входных объектов. Промпт B и новый промпт C_v3 различаются (новый разрешает `UNKNOWN`); следовательно, это не новые ответы модели C_v3. После каждого выбора сравнивались ID действия и SHA-256 сохранённого фрагмента. SI-роли ниже выполнены заглушками, Halter намеренно возвращал недостаточность: их статусы не являются семантическим результатом.\n',
        '| Случай | Записанные решения B | Получено фрагментов | Входы и хеши совпали |\n|---|---|---:|---|\n']
    for r in records:
        lines.append(f"| {r['case_id']} | {', '.join(r['recorded_B_choices'])} | {len(r['saved_retrievals'])} | да |\n")
    lines += ['\n## Проверка nominal GDP\n',
        'Воспроизведены записанные решения B и источник BEA; исходный nominal-тезис доставлен в Selection и Halter. Inference видит только выбранный фрагмент; после скриптового суждения Halter «недостаточно» Formatter не вызывается, результат `unknown`. Это проверка передачи цели и управления, а не доказательство, что живая модель Halter вынесет такое же суждение. Отдельный негативный тест намеренно заставляет Halter ошибочно согласиться: движок выдаёт непроверенное предложение, что демонстрирует оставшийся семантический риск.\n',
        f'[Подробная машинная запись воспроизведения]({OUT_JSON})\n',
        f'[Сохранённый эксперимент до исправления]({AGGREGATE})\n']
    write_new(OUT_JSON, content)
    write_new(OUT_NOTE, '\n'.join(lines).encode())
    print('11 cases, 15 saved B decisions, exact source hashes; GDP fixture; no live calls')
    print('JSON:', OUT_JSON)
    print('Report:', OUT_NOTE)

if __name__ == '__main__':
    main()
