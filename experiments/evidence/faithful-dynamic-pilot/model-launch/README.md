# Bounded model phase handoff

These are offline preparation steps. The live action is explicitly identified
below. Do not use a synthetic `verify_challenge` callback in the live path. Local
reviewer identity is an attributed process, not a cryptographic signature.
The eight cases are unreviewed proposals; human thesis approval does not imply
pair-label adjudication or promotion to a golden dataset.

The source phase must be complete with all seven successor receipts durably
settled and a `source_continuation_complete` event bound to its summary. Open it
through the successor bridge's read-only completed-phase reader, or use the
still-open shared `PhaseLedger`. Never clear a stopped ledger or repeat case 01.

## Offline cohort and contract

All paths below are absolute, in the pilot artifact directory. Use distinct,
non-existent create-only paths for `cohort`, `source_manifest`, `contract`, and
`model_out`. Import from `model-launch`, `source-successor` and
`cohort-successor-v2` after checking code hashes. `phase` is the verified,
completed successor ledger, `old_ui` and `new_ui` are the bound dashboard
observations, `source_v4` the exact frozen source contract, and `summary` the
exact source continuation `summary.json`.

```python
manifest = admission.build_cohort(predecessor, cohort, phase, old_ui, new_ui)
prepared = prepare.prepare(
    phase=phase,
    source_contract_path=source_v4,
    source_summary_path=summary,
    source_manifest_path=source_manifest,
    dataset_root=cohort,
    output_dir=model_out,
    model_contract_path=contract,
)
```

`prepare` rechecks all eight input rows via trusted provenance callbacks and
`runner_v2.preflight`, checks the seven source-stage markers, uses the same
source ledger and writes only the source receipt manifest and model contract.
It is create-only; a partial failure leaves evidence in place. The returned
SHA values bind exact bytes. UI observations are local operator observations,
not provider price guarantees; Kalshi transport provenance is user-relayed.

## Independent challenge

An independent reviewer inspects the exact frozen contract, every code binding,
the source and dataset byte bindings, the original user authority and limits,
source deviation/projection amendment, role separation and side-effect guards.
The reviewed challenge packet must state `overall_state: ready`, witness
`identity: audit_go`, witness `mode: read_only_offline`, and
`challenged_contract.raw_sha256` equal to `prepared.model_contract_sha256`.
Its `context_binding` has:

- `code_bindings_at_inspection`: every contract `component_bindings` path mapped
  to `{"sha256": exact_hash, "size": exact_byte_count}`.
- `execution_context`: exact contract context, including actual ledger, cohort,
  output directory and working directory.
- `dataset_manifest_sha256`: exact dataset manifest hash.
- `source_binding`: exact contract `source_binding` including all 8 receipts.

`internal_digest` is SHA-256 over canonical UTF-8 JSON of the whole packet with
that property omitted, using sorted keys and compact separators. A separate
receipt must contain `packet_raw_sha256`, `packet_byte_count`,
`packet_internal_digest`, and `state: ready`, matching exact packet bytes.
These are integrity bindings and do not prove the witness's identity by
cryptographic signature. The reviewer owns the packet; the operator must not
fabricate their ready determination.

## Activation and live dispatch

Use a fresh Python process. In that same process, before importing any pilot
module, independently compare the exact `trusted_launcher.py` SHA with the
reviewed challenge. Only then load it with `importlib.util.spec_from_file_location`.
The launcher checks the exact frozen contract and challenge, every component
hash including `reopen.py`, and rejects pre-imported pilot modules. Import is
read-only. The explicitly invoked `execute_reviewed` is the live action:

```python
result = launcher.execute_reviewed(
    contract, challenge, receipt,
    expected_contract_sha256=prepared_model_contract_sha256,
    expected_launcher_sha256=reviewed_launcher_sha256,
    source_summary_path=summary,
    source_manifest_path=source_manifest,
)
```

It opens the completed source ledger exclusively and rechecks it, activates the
one-shot model-stage marker with a meaningful challenge verifier, then performs
the 32-slot preflight before resolving ADC. It permits Vertex Gemini 3.8 Flash
only, uses a 420-second timeout and no retries, and rechecks bindings before
each call. A post-start uncertain effect stops with its reserve retained.
Inspect ledger and `summary.json` for measured counts and costs; separately
identify unreviewed, unknown, source-conflict and technical-failure outcomes.
A successful run is not independent human semantic evaluation.
