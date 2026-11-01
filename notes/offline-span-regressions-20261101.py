"""Run historical offline tests with explicit scripted passage selections.

The prior Selection callbacks returned whole source IDs. This adapter converts
those *fixture outputs* to full saved-passage spans; they are not model outputs
under the new prompt and cannot establish performance or causal improvement.
The predecessor test file and recorded data remain unchanged.
"""
import copy
import json
import unittest

import tests_v3.test_faithful_v3 as historical
from faithful_v3.action_case import run_case as current_run_case


def adapt_run_case(checkpoint, catalog, generate, **kwargs):
    def scripted(stage, payload):
        result = generate(stage, payload)
        if stage != 'selection':
            return result
        statements = {x['id']: x for x in payload['available_statements']}
        converted = copy.deepcopy(result)
        for alternative in converted.get('alternatives', []):
            for index, item in enumerate(alternative):
                if not isinstance(item, str) or item not in statements:
                    continue
                try:
                    source = json.loads(statements[item]['text'])
                except (ValueError, TypeError):
                    continue
                if not isinstance(source, dict) or not isinstance(source.get('passages'), list):
                    continue
                alternative[index] = {'id': item, 'spans': [
                    {'passage_id': p['id'], 'start_char': p['start_char'], 'end_char': p['end_char']}
                    for p in source['passages']
                ]}
        return converted
    return current_run_case(checkpoint, catalog, scripted, **kwargs)


historical.run_case = adapt_run_case
# The predecessor asserted an effect-uncertain label solely from TimeoutError.
# The successor intentionally reports an interrupted callback without claiming
# dispatch. Its replacement is in tests/test_v3_missing_uncertain.py; retain the
# old test source and mark this incompatible expectation explicitly as skipped.
from faithful_v3.engine import VERSION as STRICT_VERSION
if STRICT_VERSION == 'faithful-v3-strict-5':
    old_test = historical.RoleAndControlTests.test_source_callback_failure_is_visible_without_retry
    historical.RoleAndControlTests.test_source_callback_failure_is_visible_without_retry = unittest.skip(
        'predecessor timeout label superseded; see test_v3_missing_uncertain')(old_test)
suite = unittest.defaultTestLoader.loadTestsFromModule(historical)
result = unittest.TextTestRunner(verbosity=1).run(suite)
if not result.wasSuccessful():
    raise SystemExit(1)
