# Prospective p0 batch: offline integration only

`p0_launcher.py` is an injected, provider-free scaffold. It cannot authorize or
run live calls by itself. `prepare()` reads one to four separate absolute-path
case files, requiring externally reviewed verifiers for create-only human
approval and identity, full market rules against captured exact source bytes,
and provenance, availability and absence of intervention leakage in baseline
evidence. Its four mandatory callbacks have **no default**. A model proposal,
an operator-written approval, an external search excerpt, and `lambda: True`
are not genuine human/venue verification. Test callbacks are mocks.

The input schema is precisely `orchestrator.prepare_case` in the sibling
`forecast-orchestrator-v1/orchestrator.py`. The caller must retain the human
origin, decision evidence and raw market response in separately reviewed,
immutable records. At preparation all cases must share the same as-of UTC,
have unique case, event-group and contract IDs, and pass rules and timestamp
checks. An as-of cutoff is a fixed information boundary; it is not a guarantee
that all forecasts were actually generated before later news. Only an event
published strictly after every relevant p0 is durably saved can be the p1
intervention, and the contract must remain unresolved.

`run()` requires an independent frozen-bundle verifier, rereads file hashes
before generation, writes the full bundle first, and runs C then B with C's
number of calls, at most 23 per arm. B is never given C's answer or trace.
`durable_recorder()` creates a new output directory, uses exclusive file create,
flushes files and fsyncs their parent directory. Failed or uncertain calls must
not be replayed automatically. As in the underlying orchestrator, a saved
receipt proves storage timing only if the caller binds it to the actual ledger.

Before any live integration a separate independently reviewed phase contract
must bind these components, exact file bytes, genuine human decisions, the
sixth source receipt, model/version, fresh timing and inputs, ledger ownership,
count/generation attempts, cap and callback, source denial, deadlines, failure
policy, and the one-shot transport. Neither this folder nor its tests uses
credentials, writes the experiment ledger, connects to a provider, invokes p1,
or grants the model authority over thesis/market choice.

Run offline tests from the artifact root:

```
python3 -m unittest -v forecast-p0-launch-v1/test_p0_launcher.py
```

## Concrete successor and frozen candidate (v1)

The accounting-only successor carries the stopped HTTP-400 effect as unknown
charge with a $0.15 retained reserve. `recovery_adapter.reopen()` reopens that
successor without granting effect authority; `activate()` requires its own
independently reviewed frozen model contract. The model adapter refuses an
unactivated ledger, only admits Vertex count/generation endpoints, and pairs
every exact count request with its generation. It prohibits a second factory
for the same arm and stops on persistence failures. The separately bound
`transport/oneshot.py` has a 420-second timeout, no redirects and no retries.

`approved_inputs.py` and `case_binding.py` reconstruct the four exact case
inputs from the recorded user acceptance, source excerpts and the user-relayed
market JSON. The relayed text is not direct independently verified HTTP bytes.
The four case files are create-only candidate records; their manifest preserves
partial Anthropic fit, unresolved interpretive questions and raw provenance.
Recording time conservatively bounds when the acceptance and relay were known;
it is not claimed to be the user message time. The model-visible rules and
quotes carry the relay limitation.

`dispatch.py` is an explicit reviewed launcher, not an auto-run module. Its
frozen p0 contract binds the account receipt, exact cases, prompts, controller,
source and code hashes and caps. A distinct independent witness must create
matching p0 challenge and receipt before `verify()` can succeed. The common
cutoff precedes dispatch; all generation is conservatively required to finish
before 12:30 UTC. The candidate release time is not a substitute for verifying
actual publication time, market unresolved status, or semantic fit. A dated
news event must still genuinely occur after p0 has been durably saved for the
prospective p1 comparison. Missing or late information remains pending.

Do not execute until the independent challenge is ready and reviewed. The
contract and source records are immutable; any correction needs a separately
reviewed create-only successor. `test_dispatch.py` uses fake files and mocks;
it does not grant authority, exercise credentials or make live calls.
