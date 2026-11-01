# Prospective p1 components — offline, not frozen

This folder contains no credentials, configured news, network on import,
provider calls, background scheduler, ledger creation or mutation. It is a
preparation component, not authority to dispatch. Frozen p0 code and prior
ledgers are untouched. Do not bind a future event until the relevant p0 and
its effect journal are completely settled and independently reviewed.

`p1.prepare()` returns `pending` without model effects when a genuine new
article is absent, own p0 is missing/unusable, or the same market with the
same rules cannot be confirmed active and unresolved. It checks that news
publication follows the durable timestamp of both p0 arms, and the status
observation follows capture of the news, with availability and capture no
later than one common t1. The status must be within the configured freshness
limit, at most 300 seconds. Independent verifiers must tie p0 to the actual
settled ledger and receipt; tie publication time and text to exact source
bytes; evaluate semantic novelty against p0; and bind market status and rules
to an attributable post-news observation. Callbacks that merely return True
are mocks and establish none of these facts.

When ready, `p1.run()` uses the sibling offline orchestrator for four tasks:
C/no-news, B/no-news, C/news, B/news. C and B get their own p0 respectively,
not each other's. Within each condition B receives only the count of C calls,
not its outcome. B-first at p1 remains conditional on B-matched p0. The adapter
requires an independently approved p1-only ledger, verifies the $60 / 835 /
767 / 28 shared limits before each generation, performs one count followed by
one generation, restricts endpoints to Vertex, stops on error, and has no
retry. The ledger itself must reserve worst-case prices, persist every effect
and enforce limits; the precheck is not a substitute for its accounting.

The freshness guard applies before **every** transport invocation. If a run
lasts beyond the reviewed status window, it stops, may preserve partial work,
and cannot be silently retried. The five-minute limit can make the experiment
impractical; a future reviewed protocol may support fresh status checks and a
safe longer-running phase, but status would still be only an observation and
cannot guarantee a contract has not closed a moment later. Do not claim this
component proves unresolved status at the end of the run.

`source.execute()` is a separately scoped source-effect executor. Its exact
future operations, prices, ticket expiration, existing-ledger state and p0
lineage must be frozen and independently challenged **after p0**. It checks
the prior attempt count, exposure/reservations, per-call bound and unique IDs;
only exact allowed payloads reach the injected transport. It saves raw bytes
and the settled receipt through a caller-supplied create-only durable writer.
An ambiguous effect or write failure stops rather than retrying. The present
accounting-only/model-only recovery stages do not provide a source stage:
separately implement and review one after inspecting completed p0. A source
response is not proof of the event's exact publication time or market status.

Before live operation, implement and independently review an authorized p1
source/model activation and durable raw recorder, a no-retry transport and
unresolved/source verification. Bind their code, exact case, current ledger,
all receipts, limits, fresh prices, event proof, four prompts and output paths
into a create-only contract and challenge. New status, news or source evidence
may be unavailable; report pending rather than reconstructing or backdating.
No p1 accounting successor is created by this folder.

Offline checks:

```
python3 -m unittest -v forecast-p1-launch-v1/test_p1.py
```

The tests use synthetic times, fake model/ledger/transport callbacks and do not
validate any actual provider, event, unresolved market, or human adjudication.
