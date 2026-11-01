# Orthogonal Serper `/news`: one direct-account metadata check

Status: **draft; live dispatch blocked pending evidence and an independent challenge**. This file authorizes nothing by itself and records no execution. No credential, provider, model, payment or network call was made while preparing it.

## User scope

The user requested verification of Orthogonal pricing and authorized the experiment under a **$40 total limit including prior spend**. The approved plan separately requires a confirmed exact whole-request price before a paid `/v1/run` operation. A price estimate, an advertised minimum, the amount of a local reservation or a quote from another payment rail is not that confirmation.

This draft permits analysis of one proposed *discovery metadata* operation, not the underlying source call. It does not expand the previously approved source cohort, `/v1/run` count, model calls, payment permissions, or budget.

## Exact operation and request identity

- Method and URL: `POST https://api.orthogonal.com/v1/details`.
- Body: exact bytes of `request.json`, 31 bytes, SHA-256 `66e53fffad1778784de23bb8ab7ae38defd20100dda5d110ade51997e418949e`. The JSON is `{"api":"serper","path":"/news"}`.
- One direct-account attempt maximum, one HTTP request, no redirect, automatic SDK/client/proxy retry or semantic resampling. No `/v1/search`, `/v1/run`, account/balance/transactions, external notifications, or model generation in this operation. Authentication refresh necessary to obtain the existing direct-account bearer is outside the metered provider-operation count; it must not be mistaken for another Orthogonal call. Any refresh must follow separately applicable access requirements.
- Authentication: bearer supplied through the existing user's credentials; never write or print the value, headers, or environment secrets. Body has no credential. HTTPS certificate checks enabled.
- Request body maximum 31 bytes, raw response maximum 524,288 bytes, HTTPX connect/read/write/pool timeout 420 seconds per phase; this is **not a hard wall-clock deadline**. Any timeout, network error, incomplete or oversized capture after `started` is `uncertain`; stop the run, preserve the entire reservation, and do not retry.

## Price, budget and uncertainty

- Carried exposure for the earlier Gemini 3.5/3.8 series: **$0.721593** conservative scenario, including estimated usage repriced at the non-promotional 3.8 rate and retained uncertain-effect reserves. It is not a confirmed invoice. The earlier promotional-rate accounting was $0.540590. Prior model attempts 79, prior countTokens attempts 11; this metadata attempt does not change either count.
- Requested local metadata reserve: **$0.25**, included in the same shared aggregate ceiling and attributed to the source budget. Before dispatch, scenario exposure including this reserve would be at least **$0.971593**, plus any other committed, reserved or uncertain costs since the stated predecessor. Never assume other operations are zero without checking the shared ledger.
- **$0.25 is only a proposed reservation, not a verified maximum charge or provider quote.** Direct-account `/v1/details` pricing is **unknown**. The Pilot Protocol integration says metadata is free in its own broker context; that does not establish the direct-account fee. No `priceCents` in metadata must not be interpreted as proof of zero charge. No discount, tax treatment, final invoice amount, or freshness guarantee is assumed.
- Stop before dispatch unless current authoritative direct-account evidence establishes a whole-operation maximum no greater than $0.25 (including any applicable gateway fee), or an effective provider-side spending bound makes that ceiling enforceable. Bind the exact price evidence and its scope/time to a successor contract; if no such evidence exists, do not call. A local reserve alone cannot enforce the provider's fee.
- A successful response may quote the **separate** Serper `/news` request; it does not establish the metadata operation's own charge. If the metadata actual cost cannot be obtained from an independently supported receipt/account record, retain $0.25 as an estimate/reserve, mark actual **unknown**, and stop pending reconciliation under a separately authorized operation. If actual exceeds the verified bound, record it truthfully and stop: charges cannot be undone locally.

## Receipt and effect state

A reviewed single-owner executor must journal into the same global accounting authority as every experiment effect. Durable states: `prepared -> started -> succeeded | failed_before_effect | uncertain`. Reserve the verified maximum and persist `started` before any provider transport; prevent reuse of this operation ID or a second attempt. The operation is `succeeded` when an HTTP response completes even if it is non-200, invalid JSON, capture-rejected, or price evidence is missing. Transport outcome and semantic/price-admission gate are separate. No non-200 status implies free or success; retain the reserve and stop unless a verified receipt establishes the charge.

If the call is eventually admitted, write create-only private artifacts with exact request bytes/hash, run and operation identity, UTC start/end, sanitized status and provider request ID if supplied, raw response bytes/hash, operation state and independent actual-cost evidence if available. No auth headers or credential-bearing transport exceptions. Do not edit prior evidence, decisions or goldens. On persistence or bookkeeping failure stop; do not reissue the request.

## Preconditions not currently satisfied

1. Current direct-account price of this `/v1/details` operation and a verified $0.25-or-less whole-request bound are **unknown**.
2. The existing `budget-v2` source API expects an Orthogonal `/v1/run` response with `priceCents`, and the existing `OneShotTransport` allowlists `/v1/run` only. This is not an implementation or approval for `/v1/details`; a separate reviewed metadata operation must bind to the common ledger and endpoint before it could be run.
3. Bind the actual provider project/account identity without exposing credentials, current global ledger state, specific transport/configuration and admitted evidence path. Freeze and independently challenge the exact implementation and contract, including failure semantics. Stop on any mismatch or unresolved predicate.
4. The user's earlier $0.0025 estimate and the observed anonymous x402 402 offer for Serper News (~0.002 USDC) do not quote the direct-account metadata operation and do not establish the direct-account `/v1/run` price.

## Permitted next work

Obtain current authoritative direct-account documentation or a user-provided account-side price statement without issuing this authenticated metadata request. In parallel, develop and independently test a metadata executor with a common journal and no retries, and prepare a read-only contract challenge. These steps do not require new paid provider effects.

After a valid metadata receipt and a verified exact fixed whole-request price for a specific `/v1/run` query, use a separately frozen admission contract before any source query. If `/v1/details` says `dynamic`, has ambiguous units, does not support the intended parameters, exceeds the authorized per-request ceiling, or lacks reliable evidence, do not execute `/v1/run`. Capture candidates remain separate from human review and governed truth.
