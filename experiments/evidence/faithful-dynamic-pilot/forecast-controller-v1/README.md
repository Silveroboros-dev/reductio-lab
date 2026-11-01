# Forecast controller: offline research component

This folder contains no live dispatch, credentials, source acquisition, ledger,
human authority, scheduling or outcome adjudication. It is an adaptation of the
prior `controller/faithful.py`; it is **not** the 2022 fine-tuned architecture and
cannot prove factual truth, probabilistic calibration, causal validity or faithful
reasoning. The C formatter deliberately sees the question and only the selected
trace/evidence, so the numeric forecast is a model judgment under assumptions,
not a logically entailed proof. Local inference remains question-blind.

## Callable interface

```python
import forecast
engine = forecast.FaithfulEngine(generate, max_calls=23)
c = engine.run(task)
# The caller gives the ordinary baseline only the number, never C content.
b = forecast.BaselineEngine(generate, matched_calls=c['calls']).run(task)
```

`generate(stage, payload)` makes one generation through a caller-owned journal.
`forecast.build_request(stage, payload)` builds a Vertex-compatible request and
`forecast.parse_response(response_dict)` extracts one valid JSON object. The
callback must make no retry and must propagate provider/transport exceptions so
the caller can persist effect uncertainty and stop. Engine traces are diagnostic
and must not be exposed as human review evidence without separate checks.

An engine is single-use. B retains `first` and final `result`; invalid rechecks
are `technical_failure`, not a silent fallback to `first`. A null probability
is `unknown`. C retains `selected_trace` and final `result` when available;
its width-2/depth-2 beam takes up to 22 model generations without source
selection; a caller cap up to 23 is enforced. An exhausted reasoning cap gives
unknown. Both result forms require a finite probability in `[0,1]` or null,
source citation IDs, explanation, assumptions and counterevidence. A numerical
proposal must cite at least one visible source. C final citations must belong to
selected source leaves; neither intermediate node IDs nor a model prior is a
source citation. These mechanical checks do not verify semantic entailment.

## Exact input schema

```python
task = {
  'case_id': 'case-01',
  'contract_id': 'venue-contract-id',
  'question': 'What is P(the contract resolves YES)?',
  'as_of_utc': '2026-10-29T12:00:00Z',
  'phase': 'p1',                        # p0 or p1
  'condition': 'news',                  # no_news or news
  'evidence': [
    {'id':'rule-1','kind':'rule','text':'Full relevant contract rule...',
     'source':'frozen contract capture','captured_at_utc':'2026-10-29T10:00:00Z'},
    {'id':'context-1','kind':'context','text':'Admissible baseline context...',
     'source':'frozen evidence','available_at_utc':'2026-10-29T10:00:00Z'},
    {'id':'news-1','kind':'news','text':'A newly available disclosure...',
     'source':'primary source','published_at_utc':'2026-10-29T11:00:00Z',
     'available_at_utc':'2026-10-29T11:05:00Z',
     'captured_at_utc':'2026-10-29T11:10:00Z'},
  ],
  'prior_forecast': {
    'probability_yes':0.35, 'explanation':'Fallible prior forecast.',
    'citations':['rule-1'], 'assumptions':['Assumption before the update.'],
    'counterevidence':['A contrary possibility.'],
  },
}
```

For p0 use `phase='p0'`, `condition='no_news'`, `prior_forecast=None`, and
supply only admissible baseline evidence. For p1/no-news use the same p1
`as_of_utc` as p1/news but remove *all new* evidence with kind `news`. A piece
of news already known at p0 may be represented as `context` only if the cohort
builder has established and recorded its p0 availability. For p1/news append
at least one new verified-as-available `news` item. The p1 prior is the same
procedure's frozen p0 result; its citation IDs must occur in initial evidence.
The task accepts no extra keys, evidence IDs must be unique, rule evidence must
be present, and `news` requires availability time at or before `as_of_utc`.
Supplied capture/publication timestamps cannot be in the future or internally
out of order. Missing rule or missing intervention gives `unknown` before model
calls. Content with false `kind`, provider timestamps, retrospective leakage,
historical availability, complete full rules, and semantic relevance cannot be
proved by this module and must be verified by the cohort builder and reviewer.

## Important integration caveats

- The engine validates the shape of `prior_forecast`, not its producer, case,
  contract, p0 timestamp or cryptographic lineage. The runner must verify those
  bindings before creating p1, and must never give B a C prior or vice versa.
- B's first and final p1 estimates in one sequence share a prior. If a simple B
  trajectory uses B-first p0 while matched B uses B-final p0, the two p1 paths
  require separate calls; otherwise B-first measures only the p1 step conditional
  on the shared p0. Do not claim the full simple trajectory was measured.
- Width/depth describes the permitted beam, not evidence that all candidates were
  explored. Model-led halting can end early; record omissions and cap exhaustion.
- Fresh information may be encoded in model weights or an existing snapshot.
  Disabling web access does not itself prove informational isolation.
- Comparable `matched_calls` is not matching by input/output tokens, elapsed
  time or dollars. Report those separately and enforce the global run budget.

Offline verification: `PYTHONDONTWRITEBYTECODE=1 /Users/rk/Desktop/fitcheck-core/.venv/bin/python -m unittest -v test_forecast.py`. The tests use only mock responses and do not establish live compatibility.
