# Offline exploration block

`exploration.py` is an injected-callback prototype, no provider effects or human
acceptance. Both seed branches see the same `thought` and evidence but never see market
lead IDs or titles. A separate post-market step may inspect retained leads.
Market leads are suggestions, not verified venue/rule fit, absence or trade
recommendations. A model proposal or a curation status cannot activate a
thesis or write a human decision. The caller must verify source identity, content,
cutoff, eligible venue, case binding, privacy and the user's selection.

```python
import exploration
engine = exploration.FaithfulEngine(generate, max_calls=6)
c = engine.run(task)
b = exploration.BaselineEngine(generate, matched_calls=c['calls']).run(task)
```

`generate(stage,payload)` returns a JSON-like object. Use
`exploration.build_request(stage,payload)` and `exploration.parse_response` for
the frozen Vertex request/response shape; the injected callback owns the effect
journal, budget, transport, retries and JSON decoding. `BaselineEngine` returns
`first` and `result` on valid completion. B sees no C content or selections, only
its assigned call count. `FaithfulEngine` separates selection, question-blind
inference and halter. This preliminary block uses one path and a limit of six;
it **does not** implement or claim beam search. It can run two local steps but
if six calls are exhausted before the formatter it returns `unknown` rather than
inventing the final proposal. A non-halting two-step path also returns `unknown`.
Failures from the callback propagate to the caller's effect journal.

```python
task = {
  'case_id':'case-01',
  'thought':'A proposed initial thought.',
  'thought_origin':'assistant_proposal_unaccepted',
  'as_of_utc':'2026-10-29T12:00:00Z',
  'evidence':[{'id':'src-1','text':'Exact retained context.',
               'source':'frozen source name',
               'published_at_utc':'2026-10-29T10:00:00Z',
               'available_at_utc':'2026-10-29T10:01:00Z',
               'captured_at_utc':'2026-10-29T10:02:00Z'}],
  'market_leads':[{'market_id':'MARKET-1','title':'Verbatim proposed market title',
                   'source':'dated catalog','captured_at_utc':'2026-10-29T11:00:00Z'}],
}
```

Evidence and leads may be empty arrays. IDs and timestamps are checked; missing
provenance knowledge must remain unknown in the caller's source records, not
be synthesized. The synthetic evidence ID `input:thought` represents the original user input.
Seed proposals have empty `suggested_market_ids`; post-market proposals may
reference only market IDs in the retained lead set.

`thought_origin` is required and is one of `user_exact`,
`assistant_proposal_accepted`, `assistant_proposal_unaccepted`, or
`prior_user_approved`. The caller must supply provenance evidence; a label by
itself does not establish human authorship or acceptance. The C inference step
receives only selected texts with their selected source attribution, without
the hidden question or unselected context.

A response has `directions` and `unknown_reason`; each nonempty direction binds
`candidate`, `connection`, `mechanism`, `observable`, `horizon`, `falsifier`,
`alternatives`, `counterevidence`, `suggested_market_ids` and `citations`.
Nullable unknowns are permitted for mechanism/observable/horizon/falsifier.
At most three proposed directions are allowed; no market ID is required. When
empty, `unknown_reason` must be an explicit nonempty string. Citation ID checks
and structural validation establish neither entailment nor causal validity.

Seed tasks carry market leads for a later stage, but neither seed generator
receives them. If an exact known market ID or title already appears in the
original thought or evidence, the seed stops before any generation without
rewriting the original input. Matching is case-insensitive; semantic paraphrases,
unknown market identities and facts learned through model weights require a
separate review. The separate `PostMarketEngine(generate, seed_outcome,
max_total_calls=6).run(task)` admits saved leads only if a proposed same-arm
seed exists and the combined seed + post-market call cap permits one more call.
It deep-copies the seed, binds each new direction to an exact seed-direction
SHA-256, returns `stage: post_market`, and emits at most two new directions.
It never alters or upgrades the stored seed. The caller must verify the seed
outcome came from that case and arm, that its call count matches the ledger,
and that the evidence and market snapshots were genuinely available at the
recorded time. The single-path C has no beam search in this preliminary block.

Offline tests from this folder:
`PYTHONDONTWRITEBYTECODE=1 /Users/rk/Desktop/fitcheck-core/.venv/bin/python -m unittest -v test_forecast.py test_exploration.py`
