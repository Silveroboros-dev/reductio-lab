# Bounded public Kalshi accessibility preflight

Authority: user request 2026-10-29 in this session explicitly permits public Kalshi API; parent delegated ≤2 bounded read-only requests. This is source feasibility only, not an experiment or evidence adjudication.

Operations, in order:
1. GET `https://external-api.kalshi.com/trade-api/v2/events?limit=30&status=open&with_nested_markets=true`
2. Only if #1 succeeds with 200 and parseable expected schema, GET `https://external-api.kalshi.com/trade-api/v2/events/KXFEDDECISION-26DEC?with_nested_markets=true`

Unauthenticated, no credentials, orders or account operations; no redirects; timeout 20 seconds each; response cap 10,000,000 bytes; no automatic retry; stop after any HTTP error, transport failure or invalid response. Record actual attempt, UTC timestamp, HTTP status, raw bytes and SHA-256. JSON and request metadata are public, but stored as private local research artifacts; no publication. No live model, Orthogonal, PolyData, or Gamma operations. Maximum 2 requests, intended charge $0: Kalshi's public, unauthenticated documentation at https://docs.kalshi.com/api-reference/events/get-events has no account/payment parameters, and the provider listing on https://www.orthogonal.com/discover describes Kalshi's upstream public reads as free. This is not an independently established Kalshi billing contract; no account or payment instrument is supplied to these calls.
