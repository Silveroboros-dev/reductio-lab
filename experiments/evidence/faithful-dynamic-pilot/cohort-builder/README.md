# Cohort successor builder (offline)

`builder.py` prepares a create-only successor of `assembled-v2` only **after** eight settled, separately captured Orthogonal responses exist in the same experiment ledger. It performs no provider calls and does not invent source responses. A passing builder or checksum is not independent proof of source origin, human identity, semantic truth, novelty, or a provider-imposed budget ceiling.

Inputs per case: the original exact predeclared Serper `q` and `num=3`; a matching settled `Ledger.receipt` with operation ID `source:case-NN:serper`, actual raw response bytes and SHA-256, exact request bytes and digest, provider request ID, timestamps, actual `priceCents`, and quote metadata bound to `ui-serper-price-20261029.json`. The quote is checked against the separately observed UI rate **$0.002**, whereas the ledger reserves **$0.25** before each call. A larger source charge stops admission. Each raw JSON text leaf is independently extracted; absent `news` is a failure and a real empty `news` array remains empty, with no fabricated content. Selected source text remains unavailable until replay; `manual-rules` and `news` are available equally to B, B_self_check and C.

The caller must supply externally reviewed `verify_quote`, `verify_human`, and `verify_capture` callbacks; a callback that always returns true is only a mock, not review or authorization. The builder preserves the eight cases, six exact user-approved thesis wordings, the two historical source lineages, and the unresolved Fed source conflict. It retains raw files privately and creates a new manifest binding its predecessor. Model labels remain proposals awaiting human review; `unknown` is an exploratory abstention, not a governed fit class. Each case covers one market only.

The builder invokes `runner-ui/runner_ui.py`, whose separate preflight accounts for the different **displayed rate** and **reserved bound** and the Fed conflict's descriptive provenance. The UI observation is a price signal, not an independently sealed quote or provider guarantee; exact billing identity, capture origin, current time, one-shot transport, active price and all runtime hashes must be checked before the live series.

Offline test command:

```sh
PYTHONDONTWRITEBYTECODE=1 /Users/rk/Desktop/fitcheck-core/.venv/bin/python -m unittest -v test_builder.py
```

Tests use synthetic data and `Ledger.source` with a fake transport. They do not assert that real Orthogonal responses were obtained.
