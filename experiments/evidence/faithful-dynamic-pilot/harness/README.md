# Offline baseline and replay harness

This is local draft infrastructure, not an authorized live experiment. It imports
only Python's standard library and contains no network client, credentials,
provider dispatch, filesystem writes, or semantic adjudicator. `generate` is an
injected callback; the caller must enforce actual provider effects, pricing,
request identity, retries, durable started/terminal journaling, and raw-response
capture. One callback invocation is not proof of one HTTP request inside an
untrusted or retrying adapter.

`BaselineEngine(generate, max_calls=23).run(task, replay, arm)` supports `A`,
`B`, and `B_self_check`. The task shape matches the sibling Faithful controller:
`case_id`, `question`, `contract_ids`, `allowed_labels`, `initial_evidence`,
`actions`. `replay` is a separate action-id → `{evidence: [...]}` mapping. Every
offered action needs a verified `quoted_cost_micro_usd` integer; 0 means a
documented free action, not an unknown price. Evidence IDs must be nonempty and
unique in each visible set. Source collection and its price verification are
outside this harness.

Before any callback, all action replays are checked, including those not selected:
each has a valid evidence list, no duplicate evidence ID within it or overlap
with initial evidence, no reserved `node:` evidence ID, and any declared
`content_sha256` is 64 lowercase hexadecimal characters. The digest's bytes and
scope are not verified here. The aggregate `no_clean_expression` is forbidden as
a pair label. Different alternative replays may reuse an ID because at most one
alternative enters a run. All branches require this same preflight even for A.

The callback receives `generate(stage, payload)`. Stages are `source_selection`,
optional `reflect` (the ordinary agent is free to check itself), `self_check`
(the explicit baseline, before query/stop), `after_query`, and `answer`. The
payload includes only the question, contract identities, allowed labels,
visible evidence, eligible action descriptions/prices, and remaining budgets;
owner review/reference fields and unselected results are never projected. The
callback must treat source contents as data, not instructions.

`source_selection`, `reflect` and `self_check` return a decision object:
`action` (`query`, `stop`, or `reflect` where allowed), `action_id` (only for
query), `rationale`, optional `expectation` recorded before a query, and
optionally `answers` plus `stop_reason` if stopping. After a query, callback
`after_query` returns `answers` (one row per contract, each with `contract_id`,
`label`, optional visible-only `citations`, optional `explanation`), plus optional
`stop_reason` and `observed_vs_expected`. Missing or empty expectations remain
`None` in the result; an unsolicited retrospective comparison is preserved in
the raw trace but is not promoted into an expectation.

At most one source action is replayed. `shadow_source_cost_micro_usd` records the
chosen action's pinned hypothetical policy cost, while `live_provider_calls_during_replay`
is zero. This does not mean the earlier physical source collection was free; its
actual cash expense and receipt must be maintained separately. A malformed or
unpriced selection fails closed. Exceptions are propagated; diagnostic
`last_trace` and `last_calls` are in-memory only and do not establish a durable
external-effect state or semantic success.

`validate_manifest` checks shape for exactly eight distinct event groups and
case/input identifiers: two dev, six test. The supplied input SHA is a declared
identity, not an automatically verified digest of source bytes. This validator
cannot prove event novelty, model exposure, independently adjudicated truth,
human confirmation, verified timestamps, or a blind holdout. The collector and
review pipeline must establish those properties before a live run.

Local verification (no paid calls):

```
PYTHONDONTWRITEBYTECODE=1 /Users/rk/Desktop/fitcheck-core/.venv/bin/python -m unittest -v test_harness.py
```

A tagged `manual_capture` can carry explicit `quoted_cost_micro_usd: null`; its shadow cost stays unknown. Untagged/paid actions still require a nonnegative quote. Null does not mean zero or authorize an unpriced paid API call.
