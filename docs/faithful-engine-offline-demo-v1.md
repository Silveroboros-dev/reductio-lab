OFFLINE SCRIPTED DEMONSTRATION: no real model or source calls; not experimental results.

# Faithful Engine outcome — synthetic-cpi-coverage

## Proposed answer
No further release needs assessment.

**Status:** Incomplete
**Outcome reason:** model\_proposal\_requires\_semantic\_review
**Semantic status:** unreviewed

## Required-question coverage
- **pce-impact:** not assessed — Assess the PCE report's impact on YES.; required evidence not supplied to selected formatter context; not supplied to selected formatter context: pce

## Sources used by the selected path
- **rule:** A published monthly CPI figure above 0.2% resolves YES. — synthetic contract (contract\_rule)

## Evidence outside the selected path
- **input:thesis:** A synthetic inflation thesis — demo only
- **pce:** A hypothetical PCE report was released. — synthetic news

## Semantic verification
The engine records semantic status as unreviewed. This view cannot establish whether the selected claims are semantically consistent; possible contradiction or its absence remains unknown.
Model value scores are ranking signals, not probabilities of truth or measures of human value.

## Selected trace (allowlisted summary)
- Step 1: depth 1; verification: unreviewed; selected IDs: rule; conclusion ID: node:0001; conclusion: An illustrative and unverified inference.

## Saved event summary
- Selection calls: 1 started, 1 returned.
- Inference calls: 2 started, 2 returned.
- Halter calls: 2 started, 2 returned.
- Value calls: 2 started, 2 returned.
- Formatter calls: 1 started, 1 returned.
- Step proposed: branch root.1.1; selected: rule; conclusion ID: node:0001; halter sufficient: yes; value score: 0.9; Selection reason: reason not recorded; Halter reason: reason not recorded; Value reason: reason not recorded
- Step proposed: branch root.1.2; selected: rule, pce; conclusion ID: node:0002; halter sufficient: yes; value score: 0.8; Selection reason: reason not recorded; Halter reason: reason not recorded; Value reason: reason not recorded
- Beam selected: root.1.1, root.1.2

## Saved trace artifact
This page is an allowlisted summary, not the complete trace. The full recorded trace and model-call evidence remain in the saved outcome artifact; arbitrary call payloads and model results are not reproduced here.

## Other recorded branches
- **root.1.2** (included in recorded beam): last conclusion: An illustrative and unverified inference.; score 0.8; halted: yes.

Costs: $0; scripted callbacks: 8
For the complete synthetic packet run: python -m reasoning_engine.demo --json
