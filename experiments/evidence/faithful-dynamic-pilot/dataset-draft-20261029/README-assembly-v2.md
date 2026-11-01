# Case assembly v2 — historical lineage checks

The v2 assembler and output are create-only successors to v1. `assembled-v2/manifest.json` binds the raw hash of `assembled-v1/manifest.json`. The predecessor is preserved; hashes in a single workspace are not an independent external seal.

For both historical development cases, assembly now verifies:

- `packet.source_provenance.normalization_repair_proposal_digest == decision.proposal_digest == draft.proposal_digest`;
- `decision.case_ordinal == draft.case_ordinal == master.original_case_ordinal`;
- the decision run ID, source case identity, exact canonical human approval and exact proposed normalized claim agree across the bound packet, original decision and unique master disposition.

The exact master-disposition JSONL line is retained as a private attachment, as are the packet and human-decision lines. No semantic adjudication, current-session approval or golden promotion follows from this linkage. The six user-approved test-wording strings remain unchanged.

The output remains `blocked_missing_paid_source_capture_and_quote`, with a draft schema rejected by the real runner's preflight. No live effects are authorized by this artifact.

Offline tests:

```
PYTHONDONTWRITEBYTECODE=1 /Users/rk/Desktop/fitcheck-core/.venv/bin/python -m unittest -v test_assemble_v2.py
```

Seven tests include adversarial rebinding of packet digest, decision-plus-draft digest and decision-plus-draft ordinal, even when altered local file and line hashes are updated to match. They do not prove authenticity of previously observed human actions or independently seal the history.
