import ast
import hashlib
import unittest
from decimal import Decimal
from pathlib import Path

import draft


class OfflineDraftTests(unittest.TestCase):
    def test_source_and_prompts_bound_to_predecessor_without_modifying_it(self):
        before = hashlib.sha256(draft.SOURCE.read_bytes()).hexdigest()
        self.assertEqual(before, draft.SOURCE_SHA256)
        self.assertEqual(len(draft.prompt_binding()), 64)
        self.assertEqual(before, hashlib.sha256(draft.SOURCE.read_bytes()).hexdigest())
        self.assertEqual(draft.MODEL_38_PROPOSED.model, 'gemini-3.8-flash')
        self.assertNotEqual(draft.MODEL_38_PROPOSED.model, 'gemini-3.5-flash')

    def test_fixed_full_eighteen_slots_same_as_frozen_cases(self):
        slots = draft.frozen_assignments()
        self.assertEqual(len(slots), 18)
        self.assertEqual(len(set(slots)), 18)
        self.assertEqual(slots[:3], ('amazon_visible:B', 'amazon_visible:B_self_check', 'amazon_visible:C'))
        self.assertEqual(slots[-3:], ('bea_state_gdp:C', 'bea_state_gdp:B', 'bea_state_gdp:B_self_check'))

    def test_prior_usage_and_reserved_429_never_disappear(self):
        draft.verify_carried_summary()
        sim = draft.Simulation()
        self.assertEqual((sim.attempts, sim.count_requests, sim.effective_micro_usd), (31, 7, 359587))
        reserve = sim.attempt('gemini-3.8-flash', 'canary')
        self.assertEqual(reserve, 43008)
        sim.settle_success(reserve, 1)
        self.assertEqual(sim.effective_micro_usd, 359588)

    def test_full_model_38_series_with_one_canary_fits_107(self):
        sim = draft.Simulation()
        for _ in range(4): sim.attempt('gemini-3.8-flash', 'canary')
        sim.pass_canary()
        for slot in sim.slots:
            sim.start_slot(slot)
            for _ in range(4): sim.attempt('gemini-3.8-flash', 'main')
        self.assertEqual(sim.attempts, 107)
        self.assertEqual(len(sim.started_slots), 18)
        self.assertEqual(sim.effective_micro_usd, 359587 + 76 * 43008)
        with self.assertRaises(ValueError): sim.attempt('gemini-3.8-flash', 'main')

    def test_fallback_two_canaries_and_full_main_fit_111(self):
        sim = draft.Simulation()
        for _ in range(4): sim.attempt('gemini-3.8-flash', 'canary')
        fallback = draft.Profile('gemini-3.7-flash', Decimal('.75'), Decimal('3.75'), 'mock-only rates')
        sim.choose_fallback(fallback)
        self.assertFalse(sim.canary_passed)
        for _ in range(4): sim.attempt('gemini-3.7-flash', 'canary')
        sim.pass_canary()
        for slot in sim.slots:
            sim.start_slot(slot)
            for _ in range(4): sim.attempt('gemini-3.7-flash', 'main')
        self.assertEqual(sim.attempts, 111)
        with self.assertRaises(ValueError): sim.attempt('gemini-3.7-flash', 'main')
        with self.assertRaises(ValueError): sim.choose_fallback(fallback)

    def test_no_model_mixing_and_no_late_fallback(self):
        sim = draft.Simulation()
        with self.assertRaises(ValueError): sim.attempt('gemini-3.5-flash', 'canary')
        sim.attempt('gemini-3.8-flash', 'canary')
        sim.pass_canary()
        sim.start_slot(sim.slots[0])
        fallback = draft.Profile('gemini-3.7-flash', Decimal('1'), Decimal('5'), 'mock-only rates')
        with self.assertRaises(ValueError): sim.choose_fallback(fallback)
        with self.assertRaises(ValueError): sim.attempt('gemini-3.7-flash', 'main')
        with self.assertRaises(ValueError): sim.start_slot(sim.slots[0])

    def test_count_cap_87_counts_prior_seven(self):
        sim = draft.Simulation()
        for _ in range(80): sim.count()
        self.assertEqual(sim.count_requests, 87)
        with self.assertRaises(ValueError): sim.count()

    def test_absent_37_pricing_is_not_invented(self):
        sim = draft.Simulation()
        with self.assertRaises(ValueError):
            sim.choose_fallback(draft.Profile('gemini-3.7-flash', Decimal('0'), Decimal('0'), ''))

    def test_module_has_no_external_provider_or_network_imports(self):
        source = Path(draft.__file__).read_text()
        tree = ast.parse(source)
        imports = {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
        imports |= {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
        self.assertTrue(imports.isdisjoint({'httpx', 'requests', 'google', 'urllib', 'subprocess', 'socket'}))
        self.assertFalse(hasattr(draft, 'VertexProvider'))
        self.assertFalse(hasattr(draft, 'run_live'))


if __name__ == '__main__': unittest.main()
