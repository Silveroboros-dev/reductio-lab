# Prospective forecast orchestration — offline component

This component has no network, credentials, scheduling, autonomous resume or
human authority. It adapts the sibling `forecast-controller-v1` module to the
four-event pilot. It is a proposed execution component, not a frozen or reviewed
live protocol. No source/model operations occur on import or in its unit tests.

## Boundary

### Offline journey: seed -> post-market -> human decision

`journey.prepare_exploration(task, verify_thought=..., verify_sources=...,
verify_leads=...)` requires independently attributable original thought and
captured sources/market leads; each evidence item needs availability and capture
time at or before the frozen cutoff. `exploration.prepare_task` rejects known
market-title or ID leakage into seed, but not paraphrases or model memory.

`journey.run_exploration(prepared, generator_factory=..., record=..., clock=...)`
stores both seeds before generating any post-market proposal. C then B receive
identical source inputs, while seed prompts never receive the titles or IDs.
B receives only C's seed call count, not C output. Each arm's post-market step
uses only its own seed and shares the same six-generation cap with it. Every
post-market result retains an exact seed parent digest; no proposal is an
acceptance. A strict post-market lineage and source verifier is still needed
before supplying any lead to the user or a forecasting stage.

`journey.bind_human_decision(prepared, result, case, decision,
verify_decision=...)` checks that a real decision occurred after the exploration
packet was durably saved and before the p0 cutoff, and binds exact case, thesis,
market, result digest and origin. It neither solicits nor manufactures an
acceptance. The human can author or revise their own thesis; attributable
verification is the caller's responsibility. Persist the returned binding as a
separate create-only record; a model suggestion is not a human decision.
`journey.blindable_seed_cards(...)` creates same-shape seed cards without market
titles and a separate private identity map; it does not establish actual blindness
or a review decision.

### Prospective forecast phase

`prepare_case(case, verify_human=..., verify_rules=...)` requires an exact
human-approved thesis, a specific contract, primary and secondary rules, an
immutable source-capture digest, capture and close times, and baseline evidence
whose availability and capture precede p0. The human and rule verifiers must
check actual attributable approval and matching exact raw venue bytes; a dummy
callback is not such evidence. The model-visible p0 gets only the resulting
rules and baseline evidence. It cannot see a news intervention at this point.

`run_p0(prepared, generator_factory=..., record=..., clock=...)` runs C first,
then ordinary B with the exact number of C's generator calls. B receives no C
answer, trace, premise IDs or forecast. The callback factory is called separately
for `(phase, condition, arm)` to let a real ledger assign unique effect IDs. The
factory's callback must implement the one-shot, count-and-generate protocol with
the separately governed ledger; no generator, ledger or provider is supplied.

The recorder must implement create-only, durable persistence, not an in-memory
function: it must flush/fsync each exact record and its directory before
returning, fail on duplicates, and retain an independent effect journal. p0 is
considered available for prospective comparison only **after** the p0-frozen
record has been durably written; the helper reads a UTC clock immediately after
the write and returns a receipt binding those frozen bytes. The caller must
independently bind that receipt to settled calls and saved source captures.

`prepare_p1(prepared, p0, intervention, t1=..., verify_p0=...,`
`verify_intervention=..., verify_unresolved=...)` verifies same-case/contract
lineage and requires each intervention to have publication strictly after both
p0 results were saved, availability no earlier than publication, capture no
earlier than availability, and all before t1 and market close. A caller must
verify the market actually remains unresolved at t1, source origin and exact
evidence bytes, and that the genuinely new information is not already present
in p0 in another form. Empty/undated or unverifiable news remains pending or
unknown. Synthetic verifier callbacks in tests establish no such facts.

`run_p1(bundle, expected_bundle_sha256=..., verify_bundle=...,`
`generator_factory=..., record=...)` rechecks the externally frozen bundle and
runs C then B for no-news and news. C receives only its own frozen p0, and B only
its own. Every pair sees identical timestamps and evidence; p1/no-news excludes
the intervention. Inference calls, task state, source acquisition and results
must be independently tied to the same case, exact binding and ledger effect IDs
by the reviewed live caller. There is no automatic retry, and an exception must
stop if a provider effect is uncertain.

`review_cards(prepared, bundle, p1)` gives equal-field opaque cards and a
separate identity map; the caller must protect and segregate the mapping, save
both, check if model text itself discloses identity, and organize real review.
They are blindable candidates, not verified blind human adjudication. The three
card variants per condition are B first, B matched and C final. **B-first p1
is conditional on B-matched p0**, not a full cheap B-first trajectory.

## Reopening the ledger for later phases

The initial source challenge only authorized the four exact requests in the
source-phase contract, under its then-current quote. After those requests
settle, preserve the source contract and review it **historically**: validate
the exact challenge/receipt/code bindings and each source receipt against its
own `started_at_utc < ticket.expires_utc`. Do not call the original
`seed_phase.verify()` as a generic later-phase verifier: it checks quote expiry
against the current clock and will correctly reject an old quote for a new
source dispatch, even when the completed historical source call was timely.
Conversely, an old timely source quote does not authorize another source call.

`forecast_ledger.reopen_successor` expects a verifier for the original frozen
contract. Provide a separately reviewed historical verifier that revalidates
its exact challenge and receipts without converting expired historical quotes
into current permission. If a later phase needs additional source effects,
first freeze and independently challenge an exact phase addendum with current
quotes, new unique operation IDs, remaining global source attempts and limits;
its ticket callback must reject any operation absent from that new allowlist.
The budget ledger's own source method also checks current quote expiration.
Separately review and bind model run inputs and prompts. Do not amend or replace
the original source contract, erase its started/succeeded/uncertain records, or
retry an ambiguous operation.

## Remaining constraints before any live use

- Read-only independently challenge and freeze the full integration, including
  honest operator-written verifiers, account and budget lineage, control-flow
  journal, mode settings, code, dataset and runtime. A source hash alone is not
  a source-authenticity or human-approval proof.
- The helper does not implement the source-acquisition executor or detect
  semantic news duplication, model-internal historical knowledge, leaked
  last-minute market prices, changed contract terms, or news after early market
  resolution. The specified checkers and prospective timestamps are necessary.
- The helper orchestrates injected seed/post-market engines but does not itself
  create a blind holdout, assess causal edges, check logic,
  or adjudicate the appropriateness of a numeric forecast.
- The prospective design inherently requires a real later information event.
  A missing later event cannot be replaced with a pre-p0 news item, and an API
  key, model, blocked source or unavailable verified price is not a reason to
  invent a response. Do not silently backdate the baseline.
- `matched_calls` is only a call-count comparison, not equal tokens, elapsed time
  or monetary spend. An invalid model response, no p0 result, early market close,
  unknown timestamps, missing approval or unresolved provider error remain
  visible as failures or pending.

## Offline verification

```sh
PYTHONDONTWRITEBYTECODE=1 /Users/rk/Desktop/fitcheck-core/.venv/bin/python -m unittest -v test_journey.py test_orchestrator.py
```

Tests use synthetic case/rules, fake evidence, in-memory recorder and fake model
responses. They check isolation and temporal boundary handling, not production
persistence, provider compatibility, reviewer independence, or causality.
