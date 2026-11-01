# Offline Serper News price/admission adapter

This module has no network, credentials or retries. It accepts a previously captured, direct-account Orthogonal `/v1/details` response, constructs one bounded Serper `/news` request, binds a price quote to its exact request bytes and delegates the effect to the injected `budget-v2` ledger. Its output is candidate source evidence; it is not a human review or frozen market snapshot.

## Contract

- Metadata capture: `provider='orthogonal'`, `endpoint='/v1/details'`, exact request bytes from `details_request()`, HTTP 200, raw JSON bytes/hash, UTC started/completed timestamps. Reject stale, future, wrong-response, wrong-identity and malformed evidence. A digest verifies consistency, not where the bytes came from.
- Direct price: `success=true`, `api.slug='serper'`, endpoint `/news`, POST, payable true. Accept a numeric USD price only with `hasDynamicPricing=false`, matching a real historic Linkup response shape. Also accept the official documentation's `"$0.03"` style fixed-per-call string without a dynamic flag; reject explicit dynamic, unknown types/units, non-USD, zero, or more than $0.25. Validate `endpoints` membership if present. Metadata is assumed to be per whole request under the documented `endpoint.price` contract; its current accuracy and exact account-specific semantics require live evidence.
- Source: exact canonical JSON envelope only; fixed `serper` `/news`, one text query of 1–500 non-control characters, `num` 1–3, no pagination or extra fields. The exact `/v1/run` bytes, price and evidence hash are pinned in a 15-minute local quote. This local expiry is a conservative policy choice, not a provider price guarantee.
- Ledger records the real provider effect and raw response before parsing, accounts priceCents, returns a receipt and enforces its budget. Adapter validates response success, request ID, bound hashes, receipt and timestamp; a post-effect admission failure calls `ledger.stop()` without rewriting the successful physical effect. A transport exception propagates with ledger uncertainty and stop.

`/v1/details` capture is not implemented or billed by this module or ledger. A separate, bounded metadata operation and verified capture/price contract are required before live dispatch. The source ledger's mere `evidence_sha256` does not establish trusted origin or whole-request price. The injected transport must independently enforce no automatic retries, endpoint/TLS/credential binding and capture limits. No network/model calls were made for these tests. Do not substitute the anonymous x402 quote for a direct-account details result.

## Offline verification

```
PYTHONDONTWRITEBYTECODE=1 /Users/rk/Desktop/fitcheck-core/.venv/bin/python -m unittest -v test_serper.py
```

The tests use synthetic metadata and fake responses, plus the actual local `budget-v2` ledger. The old real Linkup metadata is used solely as a negative identity test. They do not establish the live Serper shape, endpoint price, billing, source freshness, retrieval quality, or current account access.
