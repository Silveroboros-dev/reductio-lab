# Forecast seed stage — live integration guide

This is the first, model-only part of the approved experiment. It creates
title-free seed proposals in four cases; it does not execute sources, expose
market titles, choose or accept a thesis, create a p0, or perform a forecast.
Source evidence is frozen separately; snippets are attributed to their URLs and
remain unverified claims. There is no automatic retry after an uncertain effect.

## Bindings and order

1. `historical_five.verify()` checks the original four source effects and the
   You.com addendum against exact frozen contracts and separately challenged
   receipts. It validates the source quote at each source effect's original
   start time; it does not grant permission to reuse an expired quote.
2. `launcher.prepare_contract(...)` is offline and create-only. It binds four
   title-free source projections, exact model protocol, user-origin vs operator
   attribution, code, source and global cap; it does not contact a provider.
3. An independent witness reviews exact contract/code/runtime and writes a
   create-only challenge packet plus receipt. A ready challenge does not itself
   grant authority; explicit user authorization remains separate.
4. In a fresh interpreter, the operator verifies the launcher's exact SHA
   against the independent challenge **before importing it**, then calls the
   explicit `launcher.execute(contract, packet, receipt, expected_sha)`. This is
   the live operation and requires the user's authorized budget and no-retry
   limits. ADC is resolved only after all review, source and ledger preflight.
5. The launcher opens the one shared ledger, creates a one-shot stage marker,
   records each started and completed seed as a separate create-only artifact,
   and counts every model call. For each case, C runs first and B receives only
   C's call count; B never receives the C answer. Both are capped at six calls.
   A technical failure, unknown or missing case remains visible.

`historical_seed.verify()` is for the next independently challenged phase,
only after the seed run is finished and the exclusive ledger owner released its
lock. It reconciles exact seed outcomes, source binding, operation IDs and
settled effects to a deterministic receipt summary. It has no network access.
It cannot assert source truth, human acceptance, semantic quality or blind
review. Any further market/source operation needs its own frozen addendum with
current price evidence, and any later model phase needs its own reviewed inputs.

## Verification

```sh
PYTHONDONTWRITEBYTECODE=1 /Users/rk/Desktop/fitcheck-core/.venv/bin/python -m unittest -v test_launcher.py
```

Tests exercise saved source projections and synthetic challenge structures;
they do not issue paid calls or establish live model compatibility. See the
sibling `forecast-orchestrator-v1/README.md` for the proposed prospective
forecast/decision seam and the historical-quote expiry caveat.
