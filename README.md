# Reductio Lab

Reductio Lab explores how AI can help people examine consequential claims, uncover overlooked assumptions, and form their own judgment.

The project investigates whether structured reasoning and contrary-case analysis make model outputs easier to inspect and challenge. Its early controllers were inspired by [Selection–Inference](https://arxiv.org/abs/2205.09712) and [Faithful Reasoning](https://arxiv.org/abs/2208.14271); they orchestrate model calls and do not reproduce all trained components described in those papers.

## Offline prototype

This repository includes an experimental Python controller and a stricter v3 variant. The included demonstration and tests use scripted callbacks and saved-source fixtures; they make no model or source calls. The code is a research prototype, not a production system or a reproduction of the papers.

The prototype makes several design choices explicit and inspectable:

- **Separated reasoning roles.** Python orchestrates Selection, Inference, Halter, Value and Formatter as distinct callbacks. In the strict v3 controller, Inference receives selected premises rather than the full question or evidence bundle.
- **Recorded evidence and decisions.** Outcomes retain evidence identifiers, input hashes, role events and selected dependency paths. For unstructured saved text, Selection can propose a verbatim quote; the controller derives offsets only when the quote uniquely matches that saved text. These records support inspection; their presence does not establish that an inference is valid or that a model's internal reasoning followed the recorded path.
- **Bounded execution.** The optional local executor records attempts and can apply a pre-authorized, bounded backoff with jitter to confirmed HTTP 429 responses. It records uncertain effects separately and does not automatically retry them. It is a single-runner research component, not a production reliability guarantee.
- **Comparisons and human review.** The repository contains baseline runners and reporting helpers that preserve failed and unknown outcomes. Semantic assessments and human judgments remain separate from model scores and structural checks.

A scripted sensitivity fixture changes a selected premise; there is no general causal-intervention benchmark or automated proof that an explanation is faithful. The Vertex bridge uses caller-supplied single-shot transports and explicit per-run budget and price settings; it is not a ready-to-run live service or production batch pipeline. An earlier, experiment-specific version completed one synthetic end-to-end Vertex run; the generalized public version has been checked offline, not independently live-tested. Untrusted source content remains a prompt-injection risk: structured requests and role boundaries alone do not prove resistance.

```sh
python3 -m reasoning_engine.demo
python3 -m unittest discover -s tests -p test_strict_v3.py -v
```

See the [prototype notes](docs/faithful-engine-prototype-v1.md) for scope and limitations. Live provider use and historical private data are not included.

## Architecture

[Faithful Engine architecture and limitations](docs/architecture.md) (English and Russian).

## Research notes

- [Experiment history: English](research-briefs-20261030/01-experiment-history-en.md) · [Русский](research-briefs-20261030/01-experiment-history-ru.md)
- [Anthropic S-1 FAQ: English](research-briefs-20261030/02-anthropic-s1-faq-en.md) · [Русский](research-briefs-20261030/02-anthropic-s1-faq-ru.md)
- [Source index and availability](research-briefs-20261030/source-index.md)

## Status and limitations

This is exploratory research, not evidence that a controller improves decisions or protects independent judgment. Earlier experiments were small and included technical and methodological limitations. The FAQ is an illustration, not investment advice.

The primary experiment logs and full model answers are retained separately and are not included here. The source index records identifiers and hashes, but does not make those materials independently reproducible.
