import ast
import hashlib
import unittest
from pathlib import Path
from unittest.mock import patch
import draft


class OfflineDraftTests(unittest.TestCase):
    def setUp(self): self.s = draft.Simulation()
    def test_full_evidence_and_012_remains_uncertain(self):
        result = draft.verify_evidence()
        self.assertEqual(result['prior_012'], 'uncertain')
        self.assertEqual(result['authorization'], 'pending_user_decision')
        self.assertEqual(result['live_dispatch'], 'not_implemented')
        self.assertEqual(len(result['remaining_slots']), 14)
        self.assertFalse((draft.PREDECESSOR / 'response-012.bin').exists())
    def test_predecessor_hash_mismatch_fails_closed(self):
        with patch.dict(draft.HASHES, {'summary': '0' * 64}):
            with self.assertRaises(ValueError): draft.verify_evidence()
    def test_no_network_process_or_live_import(self):
        tree = ast.parse(Path(draft.__file__).read_text())
        names = [n.module for n in ast.walk(tree) if isinstance(n,ast.ImportFrom)]
        names += [a.name for n in ast.walk(tree) if isinstance(n,ast.Import) for a in n.names]
        self.assertTrue(set(names) <= {'__future__','hashlib','json','pathlib'})
    def test_carry_and_proposed_timeout(self):
        self.assertEqual((self.s.attempts,self.s.counts,self.s.effective_micro,self.s.failure_streak),(43,8,423627,1))
        self.assertEqual(draft.PROPOSED_TIMEOUT_SECONDS,120)
    def test_exact_order_no_duplicate_no_prior_slots_or_model_switch(self):
        with self.assertRaises(ValueError): self.s.start_slot(draft.STARTED[-1],draft.MODEL)
        with self.assertRaises(ValueError): self.s.start_slot(draft.REMAINING[1],draft.MODEL)
        with self.assertRaises(ValueError): self.s.start_slot(draft.REMAINING[0],'gemini-3.7-flash')
        self.s.start_slot(draft.REMAINING[0],draft.MODEL); self.s.finish_slot(True)
        with self.assertRaises(ValueError): self.s.start_slot(draft.REMAINING[0],draft.MODEL)
    def test_next_consecutive_failure_stops(self):
        self.s.start_slot(draft.REMAINING[0],draft.MODEL); self.s.finish_slot(False)
        self.assertTrue(self.s.stopped);self.assertEqual(self.s.failure_streak,2)
        with self.assertRaises(ValueError): self.s.start_slot(draft.REMAINING[1],draft.MODEL)
    def test_success_resets_failure_streak(self):
        self.s.start_slot(draft.REMAINING[0],draft.MODEL);self.s.finish_slot(True)
        self.s.start_slot(draft.REMAINING[1],draft.MODEL);self.s.finish_slot(False)
        self.assertFalse(self.s.stopped);self.assertEqual(self.s.failure_streak,1)
    def test_14_slots_four_generations_in_order(self):
        for slot in draft.REMAINING:
            self.s.start_slot(slot,draft.MODEL)
            for _ in range(4):
                self.s.attempt();self.s.settle(0)
            with self.assertRaises(ValueError): self.s.attempt()
            self.s.local_read();self.s.local_read()
            with self.assertRaises(ValueError): self.s.local_read()
            self.s.finish_slot(True)
        self.assertEqual(self.s.attempts,99);self.assertEqual(len(self.s.started_slots),14)
        with self.assertRaises(ValueError): self.s.start_slot(draft.REMAINING[-1],draft.MODEL)
    def test_unknown_cost_halts_and_retains_both_previous_reserves(self):
        self.s.start_slot(draft.REMAINING[0],draft.MODEL);self.s.attempt()
        with self.assertRaises(ValueError): self.s.settle(None)
        self.assertTrue(self.s.stopped);self.assertEqual(self.s.effective_micro,423627+43008)
        with self.assertRaises(ValueError): self.s.attempt()
    def test_no_repeat_settlement_or_overlapping_attempts(self):
        self.s.start_slot(draft.REMAINING[0],draft.MODEL);self.s.attempt()
        with self.assertRaises(ValueError): self.s.attempt()
        self.s.settle(10)
        with self.assertRaises(ValueError): self.s.settle(10)
    def test_uncertain_blocks_future_slots(self):
        self.s.start_slot(draft.REMAINING[0],draft.MODEL);self.s.attempt();self.s.uncertain()
        self.assertEqual(self.s.effective_micro,423627+43008)
        with self.assertRaises(ValueError): self.s.start_slot(draft.REMAINING[1],draft.MODEL)
    def test_global_bounds(self):
        self.s.start_slot(draft.REMAINING[0],draft.MODEL)
        self.s.attempts=111
        with self.assertRaises(ValueError): self.s.attempt()
        self.s.attempts=43;self.s.effective_micro=10000000
        with self.assertRaises(ValueError): self.s.attempt()
        self.s.counts=87
        with self.assertRaises(ValueError): self.s.count()


if __name__ == '__main__': unittest.main()
