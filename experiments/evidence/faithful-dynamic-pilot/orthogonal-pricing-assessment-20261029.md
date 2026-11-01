# Orthogonal pricing and API assessment — 29 October 2026

Scope: public documentation and local historical captures only; no authenticated Orthogonal operations, paid calls, credential reads or model calls performed by this assessment. Public website content is not an account-specific provider quote.

## Short conclusion

The user's estimate of roughly $0.0025 is plausible for some web search services, but it is not a universal price and is not yet a verified price for the exact request or account. Orthogonal's public discovery listing says Serper is **from $0.002 per call**. A third-party, unverified listing attributes **$0.002** specifically to Serper `/news`, and an API directory records `/serper/news` and `/serper/search` at $0.002 on x402/MPP rails. These are separate payment rails and possibly stale publications; they do not establish the exact current direct `/v1/run` credit price for this account or request. [Orthogonal catalog](https://www.orthogonal.com/discover), [Nevermined Serper catalog](https://nevermined.app/catalog/serper), [API directory](https://apis.io/apis/orthogonal/orthogonal-serper-api/).

The official [pricing page](https://docs.orthogonal.com/concepts/pricing) gives Linkup $0.004 as an example, whereas the later public catalog advertises Linkup *from* $0.01. Prices vary by endpoint, provider and potentially request. A fixed price for a particular endpoint must not be inferred from an advertised minimum, historic sample or the $0.25 safety cap.

## Actual retained historical metadata

Three successful local `/v1/details` response captures from 23 October 2026 show Linkup `/search` and `/fetch` with `price: 0.01` as a number, `hasDynamicPricing: false`, and the selected `endpoint` contained in `endpoints[]`. One retained response is [response-d714920a0afb46a4972dbe7f0440a4d5.bin](</Users/rk/.codex/visualizations/2026/10/19/01a152a3-fbde-7cc1-acdd-cb13ff14c2d9/exploration-loop-run-20261023/response-d714920a0afb46a4972dbe7f0440a4d5.bin>). This demonstrates that the local `FixedPriceMetadataPins` parser was compatible with that **specific observed shape**, contrary to any categorical inference from current documentation examples. It does not establish today's price or today's Serper schema.

The old code explicitly called `budget.complete(op, 0)` for metadata after success, so the ledger's zero charge is an operator-supplied accounting assumption, not by itself an independent provider billing receipt.

## Metadata calls and executable contract

The official [details reference](https://docs.orthogonal.com/api-reference/details) specifies authenticated `POST /v1/details` with `{ "api": "serper", "path": "/news" }`. Its example represents `endpoint.price` as a dollar string, or `dynamic` if variable; the retained historic Linkup reply instead used a numeric price with extra fields. Observe the actual response for this exact endpoint; do not assume either shape.

The official docs consulted do not explicitly state whether the direct-account metadata calls themselves cost zero. The separate [Pilot Protocol integration](https://pilotprotocol.co/apps/io_pilot_orthogonal) says that search, details and balance calls are free, with only run billed, for its managed broker. This is useful evidence, not an authoritative quote or guarantee for the user's direct Orthogonal account.

For an eligible endpoint, the official [run reference](https://docs.orthogonal.com/api-reference/run) defines `POST /v1/run` body `{ "api": "serper", "path": "/news", "body": { "q": "..." } }` and returns `priceCents`, data and request ID. A fixed exact direct-account quote should be obtained and bound to exact supported request parameters before any billable source read; reject dynamic or ambiguous pricing. Use a bounded query, one physical capture per selected frozen source, log the provider request ID/response/time and calculate real versus shadow costs separately. The historical Linkup adapter only supports explicitly pinned Linkup and Financial Datasets routes, so a Serper request needs an intentionally reviewed integration and must not bypass its price guard.

## Live unsigned x402 quote (one request)

On 29 October 2026, one authorized anonymous `POST https://x402.orthogonal.com/serper/news` was sent with `{"q":"Federal Reserve interest rate decision","num":3}`. No API key, cookies, wallet, signed payment or payment header was used. The response was HTTP **402 Payment Required**, with an x402 v2 `payment-required` offer of **2,000 base units of USDC on Base (0.002 USDC)**, i.e. an indicative roughly $0.002 price. No paid follow-up was sent and no data call occurred. Orthogonal's [payment documentation](https://docs.orthogonal.com/payments) says payment must be signed and retried and settled before the underlying call runs. This is a live observation for the x402 rail, not a quote or invoice for the account-funded `/v1/run` route.

The attempt was bounded to one, without retry; `prepared`, `started`, and `succeeded` records, request manifest, raw response and payment-offer header with SHA-256 hashes are in [orthogonal-x402-price-check-20261029](orthogonal-x402-price-check-20261029/). Request manifest SHA-256: `d01ee921047401d1cc67962a4e2a7fb7bb19ab453e66db43d1a5e06eeb15aa73`; response body SHA-256: `44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a`. No signing/payment credentials were used, so this price-discovery attempt incurred no Orthogonal account charge.
