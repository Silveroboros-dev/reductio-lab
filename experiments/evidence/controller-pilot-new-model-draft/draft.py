"""OFFLINE DRAFT: model selection, bound inputs, and budget simulation only.

NO provider client, credentials, live runner, network access, or execution entry
point exists in this module. The proposed numerical ceilings are NOT approved.
Mock state changes here do not authorise or dispatch a provider request.
"""
from __future__ import annotations

import ast
import hashlib
import json
from dataclasses import dataclass
from decimal import Decimal, ROUND_CEILING
from pathlib import Path

BASE = Path('/Users/rk/.codex/visualizations/2026/10/29/01a1865f-6bd2-75a2-abb1-eb14b071bbe0')
SOURCE = BASE / 'controller-pilot-v2-runner/pilot.py'
CASE_FILE = BASE / 'controller-pilot-v2-inputs/cases.json'
PREDECESSOR_SUMMARY = BASE / 'controller-pilot-v2-successor-live-run/summary.json'
PREDECESSOR_EVENTS = BASE / 'controller-pilot-v2-successor-live-run/events.jsonl'
ACCESS = BASE / 'controller-pilot-38-access-check'
SOURCE_SHA256 = '3d2c05db2666e90d7df9855e6ae2f843bbd2eaff566acf1144f8ecba2ded2e8f'
CASES_SHA256 = '4165954e6d5e9112014d90e027d70e303e5e77292148151c857595c6cd82220b'
SUMMARY_SHA256 = 'b5cb309d8e9a4987b9d83e1e8fab5271d785748c4c1ccfba444f7afe61c92648'
EVENTS_SHA256 = '96b3561aff08d7478993201b50d34ea443c64e6a13db16b726ffd08b37ef2b4c'
ACCESS_SHA256 = {
    'prepared.json': '6cb01a897deb974eab60adb57cff3555ad311a7d88960a44468c3b04c170be77',
    'started.json': 'e9cb040aa011fb6199c20e37d57cb28a9af37c3cecac509481ab9f53b6db8db2',
    'terminal.json': '2e38b9c3d812cb9a64f5d1afda836fa0cf22fe54d83c7fe818e8e830e6e943c3',
    'response.bin': '5f2169e6395de034a558e3bb1b37f5ba5b7a5e987b66fa7dc5dc8fa0df7299a9',
}
ARMS = ('B', 'B_self_check', 'C')
CARRIED_ATTEMPTS = 31
CARRIED_COUNT_REQUESTS = 7  # six prior plus one 3.8 count preflight
CARRIED_EFFECTIVE_MICRO_USD = 359587  # includes a 98304 reserve for unknown 429 cost
PROPOSED_ATTEMPTS = 111  # 31 carried + up to 4 for EACH canary + 18*4 main
PROPOSED_COUNT_REQUESTS = 87  # 7 carried + up to 80 new count requests
PROPOSED_CAP_MICRO_USD = 10_000_000
MAX_INPUT = 16384
OUTPUT_RESERVE = 8192
OUTPUT_REQUEST = 4096


def checked_read(path: Path, expected: str) -> bytes:
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected:
        raise ValueError('source binding mismatch: ' + path.name)
    return raw


def prompt_binding() -> str:
    """Pin the exact schema and orchestration prompt code without executing it."""
    raw = checked_read(SOURCE, SOURCE_SHA256)
    module = ast.parse(raw, filename=str(SOURCE))
    schema = [n for n in module.body if isinstance(n, ast.Assign) and
              any(isinstance(t, ast.Name) and t.id == 'DECISION_SCHEMA' for t in n.targets)]
    cls = next(n for n in module.body if isinstance(n, ast.ClassDef) and n.name == 'Pilot')
    members = [n for n in cls.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and
               n.name in ('episode', '_validate_decision')]
    if len(schema) != 1 or len(members) != 2:
        raise ValueError('prompt structure drift')
    value = '\n'.join(ast.dump(n, include_attributes=False) for n in (schema + members))
    return hashlib.sha256(value.encode()).hexdigest()


def frozen_assignments() -> tuple[str, ...]:
    data = json.loads(checked_read(CASE_FILE, CASES_SHA256))
    cases = data.get('cases')
    if data.get('schema') != 'controller-pilot-v2-cases-v1' or not isinstance(cases, list) or len(cases) != 6:
        raise ValueError('invalid cases')
    slots = []
    for i, case in enumerate(cases):
        arms = ARMS[i % 3:] + ARMS[:i % 3]
        slots.extend(case['id'] + ':' + arm for arm in arms)
    if len(slots) != 18 or len(set(slots)) != 18:
        raise ValueError('assignments not unique')
    return tuple(slots)


def verify_carried_summary() -> None:
    data = json.loads(checked_read(PREDECESSOR_SUMMARY, SUMMARY_SHA256))
    if data.get('attempts') != CARRIED_ATTEMPTS or data.get('estimated_or_reserved_micro_usd') != CARRIED_EFFECTIVE_MICRO_USD:
        raise ValueError('previous expenditure differs from evidence')
    events = [json.loads(line) for line in checked_read(PREDECESSOR_EVENTS, EVENTS_SHA256).splitlines()]
    if sum(e.get('event') == 'count_started' for e in events) != 6:
        raise ValueError('previous countTokens evidence mismatch')
    prepared, started, terminal = [json.loads(checked_read(ACCESS / name, ACCESS_SHA256[name]))
                                   for name in ('prepared.json', 'started.json', 'terminal.json')]
    checked_read(ACCESS / 'response.bin', ACCESS_SHA256['response.bin'])
    if (prepared.get('model') != 'gemini-3.8-flash' or prepared.get('region') != 'global' or
        prepared.get('operation') != 'countTokens' or prepared.get('generation_calls') != 0 or
        started.get('operation') != 'countTokens' or started.get('effect') != 'started' or
        started.get('request_body_sha256') != prepared.get('request_body_sha256') or
        terminal.get('effect') != 'succeeded' or terminal.get('http_status') != 200 or
        terminal.get('response_sha256') != ACCESS_SHA256['response.bin']):
        raise ValueError('3.8 access-check evidence mismatch')


@dataclass(frozen=True)
class Profile:
    model: str
    input_usd_million: Decimal
    output_usd_million: Decimal
    price_evidence: str

    def reserve_micro_usd(self) -> int:
        if self.model not in ('gemini-3.8-flash', 'gemini-3.7-flash'):
            raise ValueError('model outside proposed scope')
        if not self.price_evidence or not self.input_usd_million.is_finite() or not self.output_usd_million.is_finite() or min(self.input_usd_million, self.output_usd_million) <= 0:
            raise ValueError('price evidence and positive rates required')
        return int((self.input_usd_million * MAX_INPUT + self.output_usd_million * OUTPUT_RESERVE).to_integral_value(rounding=ROUND_CEILING))


MODEL_38_PROPOSED = Profile('gemini-3.8-flash', Decimal('0.75'), Decimal('3.75'),
                             'proposed Vertex global standard pricing, through 2026-12-31; verify before any future run')


class Simulation:
    """Pure simulated accounting; deliberately incapable of provider effects."""
    def __init__(self, profile: Profile = MODEL_38_PROPOSED):
        if profile.model != 'gemini-3.8-flash':
            raise ValueError('3.8 is the initial proposed model')
        self.profile = profile
        self.profile.reserve_micro_usd()
        self.attempts = CARRIED_ATTEMPTS
        self.count_requests = CARRIED_COUNT_REQUESTS
        self.effective_micro_usd = CARRIED_EFFECTIVE_MICRO_USD
        self.canary_attempts = 0
        self.canary_passed = False
        self.main_started = False
        self.slots = frozen_assignments()
        self.started_slots: list[str] = []
        self.current_slot: str | None = None
        self.current_slot_attempts = 0
        self.fallback_used = False

    def choose_fallback(self, profile: Profile) -> None:
        if self.main_started or self.fallback_used or profile.model != 'gemini-3.7-flash':
            raise ValueError('fallback only once before any main slot, and only 3.7')
        profile.reserve_micro_usd()  # 3.7 pricing is deliberately not invented
        self.profile = profile
        self.fallback_used = True
        self.canary_attempts = 0
        self.canary_passed = False  # a 3.8 canary never passes 3.7

    def start_slot(self, slot: str) -> None:
        if not self.canary_passed or slot in self.started_slots:
            raise ValueError('canary missing or duplicate slot')
        if len(self.started_slots) >= len(self.slots) or slot != self.slots[len(self.started_slots)]:
            raise ValueError('slot is not next frozen assignment')
        self.main_started = True
        self.current_slot = slot
        self.current_slot_attempts = 0
        self.started_slots.append(slot)

    def count(self) -> None:
        if self.count_requests >= PROPOSED_COUNT_REQUESTS:
            raise ValueError('proposed count ceiling exhausted')
        self.count_requests += 1

    def attempt(self, model: str, phase: str) -> int:
        if model != self.profile.model:
            raise ValueError('mixed-model series is forbidden')
        if phase == 'canary':
            if self.main_started or self.canary_passed or self.canary_attempts >= 4:
                raise ValueError('invalid canary attempt')
        elif phase == 'main':
            if not self.main_started or not self.canary_passed or self.current_slot is None or self.current_slot_attempts >= 4:
                raise ValueError('main slot generation bound')
        else:
            raise ValueError('invalid phase')
        reserve = self.profile.reserve_micro_usd()
        if self.attempts >= PROPOSED_ATTEMPTS or self.effective_micro_usd + reserve > PROPOSED_CAP_MICRO_USD:
            raise ValueError('proposed attempt or budget cap exhausted')
        self.attempts += 1
        self.effective_micro_usd += reserve
        if phase == 'canary': self.canary_attempts += 1
        else: self.current_slot_attempts += 1
        return reserve

    def settle_success(self, reserve: int, actual_micro_usd: int) -> None:
        if type(actual_micro_usd) is not int or not 0 <= actual_micro_usd <= reserve:
            raise ValueError('missing or over-reserve usage must stop')
        self.effective_micro_usd -= reserve - actual_micro_usd

    def pass_canary(self) -> None:
        if not 1 <= self.canary_attempts <= 4 or self.main_started:
            raise ValueError('no canary evidence in simulated series')
        self.canary_passed = True


if __name__ == '__main__':
    verify_carried_summary()
    print(json.dumps({'status': 'offline_draft_only_no_provider_calls', 'prompt_binding': prompt_binding(),
                      'cases_sha256': CASES_SHA256, 'slots': frozen_assignments(),
                      'proposed_attempt_cap_not_approved': PROPOSED_ATTEMPTS,
                      'proposed_count_cap_not_approved': PROPOSED_COUNT_REQUESTS,
                      'carried_attempts': CARRIED_ATTEMPTS, 'carried_count_requests': CARRIED_COUNT_REQUESTS,
                      'carried_effective_micro_usd': CARRIED_EFFECTIVE_MICRO_USD,
                      '3_8_reserve_micro_usd': MODEL_38_PROPOSED.reserve_micro_usd()}))
