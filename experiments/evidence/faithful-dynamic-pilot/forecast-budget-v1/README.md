# Forecast-pilot accounting successor

Offline preparation only; importing, inspecting or testing performs no provider call.

`inspect_parent()` reads the previous stopped predecessor and completed successor
under read-only locks, verifies their hashes, complete settled effects, usage
accounting, state transitions, output summary and previous source lineage. It
returns the carry: $1.210590, 200 generations, 132 countTokens and 8 sources.
This is conservative usage and reserve accounting, not a reconciled invoice.

`ledger_contract.json` sets the new total $60 cap and previous model ceilings
835/767. Its 20 new source allowance plus eight existing attempts is 28 total.
The proposed source spending sub-cap is $3 and each new source operation reserves
at most $0.15. Both paid requests and source metadata consume the source attempt
allowance. A metadata call whose actual charge is unknown retains its reserve and
stops. Exact method-specific quoted prices and actual provider effects must be
verified; a local reserve does not compel a provider to honor a price ceiling.

`create_successor(...)` requires the parent, exact new accounting contract and a
frozen run contract, as well as an independently implemented challenge verifier
and source ticket verifier. It makes one exclusive claim and one new ledger,
without modifying predecessors. This function by itself does not authorize a
model or external request; a trusted dispatcher must bind and recheck complete
implementation, execution context, inputs, runtime, reviewer packet, endpoints,
privacy, source ticket authority and price evidence. An arbitrary callback
returning `True` is not evidence.

`reopen_successor(...)` takes the same arguments and permits a later prospective
phase only for an existing matching claim/run, with all effects settled and
counters, model usage, source charges and event transitions reconciled. It obtains
a read-only lock, then an exclusive lock and repeats the checks. Any pending,
uncertain, stopped, unaccounted or inconsistent ledger is not resumable by this
function. It never authorizes repeating an uncertain effect or erasing a stop.

`ledger.count(op, request_dict, transport)` and
`ledger.generate(op, request_dict, matching_count_id, transport)` reuse the
previous ledger's no-retry accounting. Every transport has the signature
`transport(provider, endpoint, raw_request_bytes) -> (http_status, raw_bytes)`.
A trusted live adapter must enforce single-shot delivery, caller-owned credential
handling, supported methods, response capture limits and timeout. Callbacks must
not log or serialize credentials.

`ledger.source(op, provider, endpoint, request_bytes, ticket, transport)` accepts
exactly a ticket with `id, provider, endpoint, request_sha256, max_micro,
evidence_sha256, expires_utc, category, settlement`. The reviewed ticket verifier
must bind it to a permitted case, actual operation, scope, user-approved purpose,
request digest, current quote evidence and expiry before provider use. An
operation ticket is an attributable local record, not independently authenticated
pricing or an irrevocable quote. Source responses are preserved in the ledger;
Orthogonal `/v1/run` is settled from its `priceCents`. Public Kalshi endpoints use
zero settlement only where independently established. `/v1/search` and
`/v1/details` metadata with unknown actual charges stop and retain reservation.
Only allowlisted provider/endpoint/settlement combinations are accepted. The
operator must extend the separately reviewed contract and transport rather than
bypassing this wrapper for any other provider.

`ledger.receipt()` returns exact original source receipts for the previous eight
source IDs and current receipts for successor IDs; old source identities cannot
be reused. `summary()` combines previous source attempts with current ones.
Raw response and request contents are private artifacts, not public telemetry.

Offline tests: run `PYTHONDONTWRITEBYTECODE=1 /Users/rk/Desktop/fitcheck-core/.venv/bin/python -m unittest -v test_forecast_ledger.py` from this folder. Fifteen tests include predecessor integrity, carry, exclusive claim, price/counter bounds, settled reopen, unknown and uncertain stops, and single-use count receipts. Synthetic transports never access a provider.
