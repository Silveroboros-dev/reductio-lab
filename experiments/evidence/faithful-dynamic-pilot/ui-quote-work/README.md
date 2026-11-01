# UI-priced Serper News adapter — offline preparation

This artifact binds an **attributed UI observation** to a bounded `/v1/run` request. It does not synthesize or claim an authenticated `/v1/details` response. No provider is called on import, construction or during tests.

The current evidence file, `../ui-serper-price-20261029.json`, records the coordinator's direct observation of the authenticated Orthogonal dashboard card for Serper `POST /news`: **$0.002 per call**, first page, `q` and `num`. It is an operator-authored record of what the UI displayed, not a raw provider response, signed quotation, bill or independently sealed attestation. The separate `../ui-serper-card-visible-text-20261029.txt` is a visible-text transcription, not raw HTTP. The token/account suffix binding was reported as checked in memory; independent review must determine whether it is adequate before any live use.

`ui_quote.bind_quote(request, observation_bytes, expected_sha256=..., verify_provenance=..., now=...)` checks the exact known card URL, endpoint, first-page rate, account binding, required parameter descriptions, age (15 minutes maximum), digest and a caller-supplied independent verifier. It accepts only canonical Serper News requests built by `serper.build_request(q, num)` with `1 <= num <= 3`, no pagination, continuation or other parameters. A frozen hash and verifier are necessary bindings but **do not prove the claim, guarantee future pricing or authorize a call**.

The returned ledger `max_micro=250000` is a **local $0.25 risk reservation** per request, not a price or provider-enforced cap. The displayed first-page price is **2000 microUSD ($0.002)** and must remain the model-visible action price. It is a separate variable from the reservation. If a response's accounted actual cost is greater than 2000 microUSD, `execute` stops the run after preserving `succeeded` and actual cost; if it exceeds 250000, the ledger stops after accounting it. A lower charge is accepted as a possible credit, not treated as evidence of another call price. A provider could charge more than the reserve before the client sees the response, so the $40 bill cannot be guaranteed from this UI observation alone.

`ui_quote.execute(ledger, op_id, request, observation, expected_sha256=..., verify_provenance=..., transport=...)` delegates exactly once to `ledger.source`. The raw returned bytes and charged `priceCents` are preserved/settled by the shared ledger; a valid root `requestId` or `billing.requestId` is required (if both are present they must match). Failure after provider completion causes a durable stop without rewriting effect truth. Timeout is propagated as uncertain with its reservation retained. Use `source:<case_id>:serper` as the operation ID and the separately frozen exact query. The returned projection contains only diagnostic metadata; a source intake must use the ledger's exact raw bytes for evidence.

Before any real dispatch: independently bind the exact price capture and model/API configuration in an approved run contract, verify credentials/account association and the no-retry transport, verify the cohort/request bytes, ensure **all** calls pass one shared ledger, perform an independent read-only contract challenge, and pre-register the stop if prices, effect state or costs drift. Integrate runner so it compares the model-visible price to `PRICE_MICRO` rather than `receipt.quote_micro`; the latter is just the reserve. Capture physical source responses once, then replay to each eligible arm. Responses remain untrusted data and human semantic review remains separate.

Test (synthetic injected transport, no network):

```
PYTHONDONTWRITEBYTECODE=1 /Users/rk/Desktop/fitcheck-core/.venv/bin/python -m unittest -v test_ui_quote.py
```
