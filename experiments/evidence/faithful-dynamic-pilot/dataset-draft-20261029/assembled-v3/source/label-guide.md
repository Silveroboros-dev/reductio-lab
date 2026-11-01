# Labeling Guide: Market Expression Quality

Status: active labeling semantics under
`fitcheck-product-discovery-spec-v3.md`

This guide defines two different decisions that must not be collapsed:

1. the expression quality of one human-approved thesis and one immutable
   market snapshot; and
2. whether the exact, non-empty, fully assessed displayed pool contains a
   clean expression.

False confidence is the critical error: a merely related market must not be
presented as a `direct` or `indirect` expression.

## 1. Pair-Level Fit Classes

Every candidate in a fully labeled top-three evaluation pool receives exactly
one pair-level class.

### `direct`

A market's resolution event is materially equivalent to the thesis event.
The target entity, event stage, measured outcome, time window, threshold, and
resolution evidence align closely enough that resolving the market settles the
market-testable part of the thesis.

Example: the thesis says a Gemini model will rank first on a named leaderboard
by the end of 2026, and the market resolves on that same entity, ranking,
leaderboard, and deadline.

### `indirect`

The market settles the core thesis despite a bounded, explicitly recorded
difference that does not change the event being tested. Typical differences
include a reasonably close horizon or a different but equivalent authoritative
source.

`indirect` is not a bucket for topical similarity. In particular, an event
stage change such as *release* versus *announcement* usually changes the
resolving event and is therefore a `weak_proxy`, unless the contract rules make
the two stages equivalent for that specific case.

### `weak_proxy`

The market is relevant but can resolve YES while the thesis is false, or NO
while the thesis is true, because it measures a different event, stage,
metric, entity, threshold, mechanism, scope, or materially different horizon.
It may be shown as a diagnostic alternative, but never disguised as a clean
expression.

Examples include stock price as a proxy for product adoption, consumer usage
as a proxy for enterprise traction, or an announcement market for a thesis
about an actual release.

### `not_an_expression`

The market is not a meaningful expression of the thesis. It may have appeared
because retrieval found lexical or topical overlap. This is a pair-level
negative, not a statement about the rest of the market catalog.

## 2. Pool-Level Outcome

`no_clean_expression` is an aggregate result, not a pair class. Three scopes
must be recorded separately: the bounded `retrieved_pool`, the terminally
evaluated `assessed_pool`, and the ordered `displayed_pool` of at most three
contracts. The v3 result means that no `direct` or policy-permitted `indirect`
expression was found in the exact, fully assessed displayed pool. The record
must bind all three pool identities, ordered displayed IDs, immutable
snapshot/content identities, retrieval policy, display policy, fit policy, and
observation time.

The phrase must be rendered to users with its scope, for example:

> No clean expression among the checked candidates.

It must not be interpreted as proof that no suitable market exists anywhere.
An empty, failed, or partially assessed displayed pool cannot produce this
outcome. A human-acceptable market outside the displayed pool is a retrieval or
ranking miss, not support for a correct no-clean result.

## 3. Decision Dimensions

Review the dimensions separately before choosing a class:

| Dimension | Strong alignment | Material mismatch |
| --- | --- | --- |
| Entity | Same target or contractually equivalent target | Different actor, asset, product, or population |
| Event stage | Same event: announced, released, adopted, measured, resolved | One stage used as evidence for another |
| Metric/outcome | Same observable outcome and direction | Correlated but different measure |
| Horizon | Same window or a bounded non-material shift | A window that can reverse the answer |
| Threshold/scope | Same threshold, geography, population, and exclusions | Different success condition or coverage |
| Resolution evidence | Same or equivalent authoritative evidence | Subjective, unavailable, or non-equivalent evidence |
| Mechanism | Market tests the asserted mechanism when it is essential | Market tests only an endpoint or proxy |

Deterministic checks may expose mismatches and enforce schemas, but they do not
own the semantic label. A named human review decision supplies the semantic
label under an identified product policy. It becomes a governed golden only
after the required owner disposition and create-only successor export.

## 4. Top-Three Review

For each displayed candidate, preserve:

- `retrieval_rank`: where retrieval placed it;
- `fit_class`: the pair-level decision;
- `display_rank`: where the product showed it; and
- human selection: that market's stable ID or explicit `none`.

Do not pad the list to three. Do not infer labels for unreviewed candidates.
Metrics such as precision at three are valid only when every candidate in the
scored pool has an individual human label. A selected-market label supports
selected-pair scoring; it does not silently label the other candidates.

Market/pool membership identity is content-based and order-independent.
Retrieval order and display order are separately digest-bound observations.
Reordering does not invalidate pair labels, but it creates a new ranking or
presentation observation and may change rank- or choice-dependent metrics.

## 5. Contract Drafting

A draft contract may be generated as a separately labeled product aid after a
weak or no-clean result. Drafting is outside the first v3 critical path and is
never required to make `no_clean_expression` valid. A generated draft is a
proposal, not an existing market and not a verified clean expression.

If enabled in a later policy, a draft must define an unambiguous binary
outcome, observable threshold, precise deadline and timezone, scope, and an
authoritative public resolution source. Its generation and review have their
own provenance and acceptance decision.

## 6. Monitoring and Thesis Revision

A monitoring observation, material-change trigger, revisit packet, or human
revisit decision is not a pair-fit label. Each must bind the exact thesis
revision, old and new market/source evidence, observation time, and applicable
policies. New evidence or a price change may prompt review, but it does not
silently change the fit class, thesis meaning, human confidence, commitment
context, or market choice.
