# Faithful-style controller — offline component

`faithful.py` contains no network access, credentials, provider client or semantic judge. It implements a prompt-based structural adaptation, not the trained original 2022 models. The sole entry point is `Engine(generate, max_calls=23).run(task, replay)` with an injected synchronous callback. Each instance is single-use.

`task` is a dict with `case_id`, non-empty `question`, `contract_ids` (1–3 unique IDs), `allowed_labels` (non-empty unique pair labels; `no_clean_expression` is not a pair label), `initial_evidence` (list) and `actions` (list). Each evidence item has `id`, `text`, and optional textual provenance fields `source`, `captured_at`, `published_at`, `as_of`, `content_sha256`; arbitrary extra metadata is not projected. `content_sha256` is preserved unverified: the source capture/manifest must define and validate its hash scope. Each action has `id`, `description`, and mandatory `quoted_cost_micro_usd` as a non-negative integer; `captured_at` and `coverage` are optional strings. Unknown prices must fail source preflight rather than be represented as zero. The human-approved thesis is an initial evidence item.

`replay` is a separate dict mapping exactly the action IDs to objects shaped `{ "evidence": [evidence items] }`. It remains hidden until the model chooses one action; at most one action is replayed. The external capture and permission layer must itself verify exact snapshot bytes, source provenance, cost, timestamp and authority. The controller does not issue actual tool calls.

Callback stages and return objects:

- `source_selection`: `{action: "query" | "stop", action_id: string | null, rationale?: string, expectation?: string}`. Model sees case_id, question, contract_ids, allowed_labels, initial visible evidence, projected action descriptions/prices, max/remaining generations and remaining source reads, never `replay` or human references. The optional rationale and expectation are validated and recorded in `source_decision` before replay; a missing expectation stays empty.
- `selection`: `{alternatives: [[visible_id, ...], ...]}` with at most two distinct sets. Model sees the question and visible statements including only the current branch's own nodes. Duplicate alternatives are discarded, not resampled.
- `inference`: `{conclusion: string}`. Payload is **only** `{selected_texts: [string, ...]}`. The adapter must supply a generic, question-free inference instruction; it must not add question, remaining context, owner references, other branches or unavailable source text.
- `halter`: `{sufficient: boolean}`. Model sees the question and current inference, not the source context.
- `value`: `{score: number}` between 0 and 1; model sees question, visible evidence and current branch's proposed trace. The score ranks candidates and is not an independently established probability of truth.
- `formatter`: `{answers: [{contract_id: string, label: string}, ...]}`. It sees only the final inference, permitted contract IDs and output labels; no question, source catalog, raw evidence or other branches. All requested contract IDs must be present exactly once or the result is `unknown`; syntactically complete output remains only a **proposal pending semantic review**.

The beam keeps at most two branches for two depths, at most two alternatives per active parent; maximum `1 source + 3 selection + 6 inference + 6 halter + 6 value + 1 formatter = 23` calls. Exhausted budget or depth yields scoped `unknown`, not a proof of impossibility. Invalid or inaccessible IDs and malformed returned schemas yield `technical_failure`. Callback exceptions propagate with `callback_raised` recorded in the in-memory trace: external provider/ledger code must distinguish ambiguous effects and stop the run as required. This component does not retry, interpret such failures or persist a durable journal.

Outcome fields are `status`, `reason`, `calls`, `events`, and for a selected answer `selected_trace`/`proposed_answers`. Event records include stage projections, result, branch IDs, selected IDs, scores and any selected source. They are private experiment artifacts and must not be projected back to models except as explicitly defined. The semantic correctness of inference, the truth of a `direct` label and source completeness are **not** validated by schemas or reference IDs.

Offline test:

```
PYTHONDONTWRITEBYTECODE=1 /Users/rk/Desktop/fitcheck-core/.venv/bin/python -m unittest -v test_faithful.py
```

A tagged `manual_capture` can carry explicit `quoted_cost_micro_usd: null` to represent unknown external cost. Untagged/paid actions still require a nonnegative quote. Null does not mean zero. Admission of the user-reported source and byte provenance occurs in the runner, not this engine.
