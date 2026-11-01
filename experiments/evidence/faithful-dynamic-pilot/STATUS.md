# Faithful-style dynamic-evidence pilot — implementation and readiness

Status: **offline implementation and preparation; live experiment not run**. This directory is private working evidence, not a governed FitCheck export or an externally sealed release.

## Objective and comparison

Test whether information acquisition and the Faithful-style inference controller improve assessment of expression fit, at a given cost. Proposed cohort: two development and six diagnostic event groups; for each, A has no newly acquired source, B is an ordinary same-model agent with an optional self-check, B+self-check performs an explicit additional check, and C uses a selection/inference/halter/value beam. An acquisition is a real source response captured once and replayed to any arm selecting the same action. Human-confirmed theses, contract rules, sources and independent review are prerequisites. Forecasting and trading are outside the outcome measured.

C implements a prompt-based adaptation, not the separately fine-tuned 2022 models. Beam width 2, up to 2 alternatives and 2 inference depths; up to 23 model generations per assignment including source choice and formatting. Question-blind local inference and branch-local IDs are structural restrictions, not proof that a conclusion is correct or that internal reasoning is faithful.

## Prior cost and conservative exposure

The earlier two series used 79 generation attempts and 11 countTokens. The predecessor report records $0.356270 usage-based estimate plus $0.184320 retained reserve = $0.540590 exposure; actual provider invoice is not established. Repricing the 3.8 usage and reserves at twice the introductory rates gives a conservative scenario of $0.721593 including 3.5. It is not a confirmed bill. No additional model, Orthogonal, PolyData or Azure API call has been made by this pilot. Public documentation reads and offline tests are not paid provider experiment calls.

Provider reference: https://cloud.google.com/gemini-enterprise-agent-platform/generative-ai/pricing . For global standard 3.8, the page lists $0.75/$3.75 per million input/output tokens through 2026-12-31 and $1.50/$7.50 thereafter; the current promotional price is stated to involve credits. Use of the higher rates here is a conservative scenario, not confirmation of the account bill or taxes. The earlier reserve assumed 8,192 total output/reasoning tokens and is not an independently established provider guarantee.

## Live-readiness blockers

1. An exact eight-event cohort with bound, human-confirmed thesis, complete contract snapshot, freshness/provenance and dev/test separation has not been assembled. A web page or a model-generated thesis is not a human confirmation. Independent semantic review remains needed for claims about correctness.
2. Current Orthogonal whole-request quotes, account pricing, and the cost of catalog discovery itself are not yet established. The public documentation describes endpoint price and dynamic prices, but does not establish a zero price for its own discovery endpoints. No priced request may be substituted using the budget ceiling as a quote. https://docs.orthogonal.com/api-reference/details and https://docs.orthogonal.com/concepts/pricing
3. PolyData local client dependencies are incomplete; historically its maintainer requested queries on an Azure VM near storage to avoid egress. Current VM access, ingestion freshness, the snapshot contract and Azure transaction and egress costs are unverified. See https://github.com/Symbolic-Link/poly-data-client/issues/205#issuecomment-5982965477 and https://learn.microsoft.com/en-us/azure/storage/blobs/map-rest-apis-transaction-categories . Do not run an unbounded or direct Gamma query as a workaround.
4. The modules here are offline components with injected callbacks. The separate runtime is a tested prototype, not a live executor: its model and tariff are not pinned by verified pricing evidence, the 8,192-token output reserve is not established as a Vertex hard maximum, direct internal calls can bypass public pre-counting, and the fixed source reserve is not an atomic ledger of actual source operations. A bound executable run contract, exact prompts, source captures, integrated production effect journal and independent pre-execution challenge are needed before provider calls. No end-to-end live runner is claimed ready solely because unit tests pass.

A public Kalshi page demonstrates a possible market candidate, not a frozen contract snapshot, confirmed thesis, Orthogonal capture, or approved substitution of the planned source: https://kalshi.com/markets/kxfeddecision/fed-meeting .

## Git and data boundary

The source baseline is research revision dccfbb55c7cc4d088e4a82872e72c0cf8a268168. This directory is outside the checkout because the newly created managed worktree was not writable under the active sandbox. Existing dirty checkout and governed data were not altered; no commit, push, GitHub repository or external publication was made.

## Two prior reviewed development candidates

A read-only review of the governed history identified two possible **exposed development** inputs. These are candidates, not current source snapshots, final new labels, or a test cohort:

- Fed thesis about no rate cut before 2028: reviewed packet `pkt_mfta_governance_50_gov_027_eval-v2-013__normrepair_holdout-20260827-v1-exact-approvals-v1`; previously selected market `2923466`, snapshot `ms_immutable_0874ec4d1f8da6659c9d72451a180b441979e0f825d59fdf22e6571f8774189d`, 2026-08-29; previous pair judgment `weak_proxy`.
- Anthropic $1T pre-IPO valuation: reviewed packet `pkt_mfta_governance_50_gov_004_eval-007__normrepair_holdout-20260827-v1-exact-approvals-v1__livefill_holdout-20260827-v1-case03-anthropic-1t-followup-v1`; previously selected market `2299959`, snapshot `ms_immutable_b5c8d64593d89a749e896d6e80e44e37450310ca3804bb0dd9fb8e80caee6639`, 2026-08-29; previous pair judgment `indirect`.

Historical human exact-normalization approvals were scoped to advisory normalization and do not by themselves authorize a new thesis for a new session. Snapshot status and continuing existence are unknown. Any new market rules or other source data need separate provenance and independent evaluation; do not transfer the historical label to altered inputs. No governed file was edited or exported.

## Offline verification

On 29 October, Python unittest passed 19 controller tests, 14 baseline tests, 1 four-arm integration test, and 13 runtime prototype tests. They use synthetic data and injected callbacks; they do not measure model quality, current source accuracy, live compatibility or provider invoices.
