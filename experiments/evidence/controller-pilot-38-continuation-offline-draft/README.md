# Gemini 3.8 continuation: offline proposal only

Status: draft for a possible human decision. No live client, credentials, external calls, repeat canary or retry exists here. The original run has stopped on an uncertain effect; the user-approved plan required stopping on that condition. This draft does not authorize any continuation.

The saved predecessor remains untouched: 3 main slots completed, `amazon_empty:B_self_check` is a technical failure because operation 012 timed out, and 14 slots remain unstarted. Operation 012 must remain `uncertain` even if the continuation is approved; no repetition or reconstructed response is permitted. Keep the previously passed 3.8 canary, without another canary. Preserve both unknown cost reserves: $0.098304 on the prior 3.5 HTTP 429, and $0.043008 on 3.8 operation 012.

Any future operator implementation must bind the existing cases, source bytes, prior runner, prompts and returned model version (`gemini-3.8-flash`); preserve the exact 14-slot order emitted by `draft.verify_evidence`; use the same model for every remaining slot; and preserve the prior terminal state and raw receipts. Carry 43 of 111 generation attempts, 8 of 87 countTokens and $0.423627 estimated-plus-reserved of $10. An existing technical failure gives an initial consecutive-failure count of 1: if the first continued slot is also a technical failure, stop; a successful slot resets the count. Maximum four model generations and two saved-source reads per slot; no retry of a previous operation, no semantic resampling, no new live source reads, and no hidden SDK retries.

Proposed changed transport timeout: 120 seconds for newly started operations only, instead of 60. This cannot prove a timed-out operation was unexecuted, and it does not guarantee future timeouts will be avoided. Another ambiguous operation must stop and retain its reserve. Any actual successor requires separately approved authority, a frozen executable contract, a read-only challenge, consistent effect/capture state, a single dispatch fence, and distinct output artifacts.

`draft.py` is exclusively an offline evidence verifier and simulated accounting/order model. The simulator is not a live runner and has no way to send or schedule requests. Its mock inputs and outputs cannot establish real provider behaviour, semantics, a confirmed invoice, user approval, or an independent external seal.

Offline checks:

```
PYTHONDONTWRITEBYTECODE=1 /Users/rk/Desktop/fitcheck-core/.venv/bin/python draft.py
PYTHONDONTWRITEBYTECODE=1 /Users/rk/Desktop/fitcheck-core/.venv/bin/python -m unittest -v test_draft.py
```
