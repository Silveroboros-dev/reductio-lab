# Hard SI 56/60 review — attributed model-assisted assessment

Status: draft review of the 56 recorded assignments only. The 4 absent
assignments remain missing, not failures. No model or network calls were made.

## Review procedure and limits

The recorded assignments were first reviewed from shuffled pseudonymous
reviewer packets. At that stage I did not inspect the custodian key or baseline
outcomes. C was inferable from the branch/event traces, so this was not fully
blinded. The initial assessment below is an AI-agent review, not human
adjudication. Later key and baseline comparisons are identified separately.

The rubric checks whether each selected premise locally supports its inference,
whether the chain reaches the requested proposition, and whether an answer
introduces unsupported conditions. A structurally recorded edge is not itself
proof; each conclusion still needs a semantic check.

## Primary review before key or baseline comparison

| Pseudonymous case | Packet outcome | Primary review |
|---|---|---|
| `case-964d8ff5a5ef` | Proposal: YES | Six-step path is locally coherent: the initial fact matches the first rule; each later label matches the next rule antecedent; the final rule entails authorization. A distractor alternative was explored, then not used in the final ancestry. No unsupported step observed in the selected path. |
| `case-3f956f52abe3` | Unknown: `reasoning_depth_exhausted` | No halted final candidate and no selected ancestry. Recorded branches end in intermediate labels or general rules. The model Halter repeatedly rejects them as not answering the specific authorization question. This is an engine-exhaustion outcome, not a model-authored justified UNKNOWN. |
| `case-25cdf0051505` | Proposal: YES | Six locally coherent forward-chaining steps from the initial fact through matching rule antecedents to authorization. No unsupported step observed in the selected path. |
| `case-0b4273f00043` | Unknown: `reasoning_depth_exhausted` | No halted final candidate. The last recorded inferences remain intermediate labels or a general conditional; Halter does not accept a specific authorization conclusion. This is an exhausted controller result, not a reasoned UNKNOWN answer. |
| `case-7cc56b821436` | Unknown: `reasoning_depth_exhausted` | No halted final candidate. The final candidates remain an intermediate label and a general conditional rather than an entity-specific conclusion. No final answer to semantically score. |
| `case-0f51c93116c1` | Unknown: `reasoning_depth_exhausted` | No halted final candidate. The last candidate is a general rule and another is an intermediate label. Halter rejection explains the engine status; it does not establish that the task itself is unanswerable. |
| `case-20ef998df54f` | Unknown: `reasoning_depth_exhausted` | No halted final candidate. The final selected ancestry is empty; recent branches contain a conditional and intermediate label, with Halter rejecting both as non-answering. |
| `case-ec8f5fdf8047` | Proposal: YES | Six-step path is locally valid, including two conditional-composition steps: `A→B` with `B→C` yields `A→C`; the next composed rule and final fact-to-authorization application are valid. The selected path reaches the requested conclusion. |
| `case-f56e1597ff0d` | Technical failure: formatter citation validation | The saved six-step reasoning path reaches non-authorization through matching antecedents. The run produced no accepted final response because the formatter citations failed the nonempty/unique/selected-ID check. Treat as technical failure, not a correct NO outcome. |
| `case-af9beb45aa3f` | Proposal: bounded UNKNOWN explanation | The recorded path derives a chain from the entity's initial label to `SZOLE`, and separately composes a detached rule chain from `RLIQK` to authorization. It then notes no supplied link from `SZOLE` to `RLIQK`. The explanation is appropriately bounded; full task-level correctness awaits the separately held key. |
| `case-ab1fc66345ca` | Proposal: NO | Six-step path is locally coherent from initial fact through matching rule antecedents to non-authorization. No unsupported step observed in the selected path. |
| `case-a4a56dd53100` | Technical failure: `callback_failed:UnknownEffect` | The callback stopped during inference after partial branch evidence. This is an uncertain provider effect, not a semantic unknown and not evidence that the proposed partial conclusion is false. |

### Primary interpretation

Recorded inference quality among the proposals is mixed only in the limited
sense that most final paths appear locally supported on their own premises;
that does not establish controller reliability. Five C outcomes are
`reasoning_depth_exhausted`, one failed formatter validation after a seemingly
valid trace, and one uncertain callback effect. The repeated depth-exhausted
reason is consistent with the Halter requiring an entity-specific terminal
conclusion; it is not evidence that the underlying questions were unanswerable.

## Separate key check after the primary review

After recording the blind review above, I checked the custodian-held synthetic
answer key. This is a program-generated task key, not independent human gold.
All 12 planned C assignments are recorded. Five are proposals: four final
answers match the key; one proposal gives UNKNOWN when the key is YES. Five
assignments are `reasoning_depth_exhausted` with no final answer. Two are
technical failures. These counts describe this 12-case synthetic set only.

| Pseudonymous case | Key | C result | Key comparison |
|---|---:|---|---|
| `case-964d8ff5a5ef` | YES | YES proposal | Matches |
| `case-3f956f52abe3` | YES | `reasoning_depth_exhausted` | No final answer |
| `case-25cdf0051505` | YES | YES proposal | Matches |
| `case-0b4273f00043` | NO | `reasoning_depth_exhausted` | No final answer |
| `case-7cc56b821436` | YES | `reasoning_depth_exhausted` | No final answer |
| `case-0f51c93116c1` | NO | `reasoning_depth_exhausted` | No final answer |
| `case-20ef998df54f` | NO | `reasoning_depth_exhausted` | No final answer |
| `case-ec8f5fdf8047` | YES | YES proposal | Matches |
| `case-f56e1597ff0d` | NO | formatter technical failure | No accepted final answer |
| `case-af9beb45aa3f` | YES | UNKNOWN proposal | Does not match; trace omits a supplied connecting rule |
| `case-ab1fc66345ca` | NO | NO proposal | Matches |
| `case-a4a56dd53100` | NO | uncertain-effect technical failure | No accepted final answer |

## Two case comparisons, performed after primary C review

### `case-3f956f52abe3`: answerable YES versus depth exhaustion

The key is YES. B_low, B_medium, B_self, and B_budget all produced YES; their
assessments marked the target `assessed`. C produced no final response because
no Halter candidate was sufficient. The trace follows the correct label chain
through `Entity-3 has label CTVRW`. At depth 5, however, it spends one inference
turn paraphrasing the rule `CTVRW → FMNFB` as a general conditional. At depth 6
it applies that rule and reaches `Entity-3 has label FMNFB`; the supplied final
rule `FMNFB → authorized` is not applied. The Halter rejects the intermediate
label and the depth limit ends the episode. This is direct evidence of a
per-case depth/selection interaction; it does not establish that depth limits
generally cause the observed outcome.

### `case-af9beb45aa3f`: false UNKNOWN despite a supplied connecting rule

The key is YES. All four recorded B variants answered YES and gave a coherent
chain, including rule `s030` from `SZOLE` to `RLIQK`. C returned a prose UNKNOWN
proposal claiming that no relationship between those labels was specified.
The task does include that relationship. The selected C ancestry reaches
`SZOLE`, then explores a detached rule chain from `RLIQK` to authorization, but
does not select `s030` to connect the entity to it. The final UNKNOWN claim is
therefore unsupported by the full task input; this is a selection miss plus an
incorrect absence claim, not a justified abstention. C's formatter response
has citations but no `assessments` array; its structural coverage is only
`model_says_answerable` with model origin. The B assessment field saying
`assessed` is itself not proof, though these B explanations do cite the
connecting rule.

## Additional requested pair: `hard-b3f0…`

This case's key is YES with proof depth 6. C's six selected steps are all
locally valid modus-ponens applications:

1. `UOPMB` fact + `UOPMB → LCRTC` yields `LCRTC`.
2. `LCRTC` + `LCRTC → AXYQQ` yields `AXYQQ`.
3. `AXYQQ` + `AXYQQ → EIEGE` yields `EIEGE`.
4. `EIEGE` + `EIEGE → IYLER` yields `IYLER`.
5. `IYLER` + `IYLER → WYTNS` yields `WYTNS`.
6. `WYTNS` + `WYTNS → authorized` yields the YES conclusion.

C's final answer is YES and its citations include the complete proof path.
Each B variant also answers YES and marks the obligation `assessed`, but each
written explanation omits the last intermediate edge: it incorrectly describes
`s095` (`IYLER → WYTNS`) as if it directly established authorization, omitting
`s033` (`WYTNS → authorized`). Thus their answer labels match the key while
their explanations are incomplete or unsupported at the terminal step. C has
no assessment object; its coverage is `model_says_answerable`, not a verified
assessment. This comparison shows why answer labels and explanation validity
must be reviewed separately.

## Denominators and limits

The frozen schedule has 60 assignments; 56 are recorded. All 12 C assignments
are present. The four missing assignments are B_low, B_medium, B_self, and
B_budget for one case; the B denominator is therefore 44/48. The two
interventions are 0/2 because the interrupted main schedule did not reach the
probe phase. Missing assignments and interventions are not scored failures.

This is a small, synthetic, six-pair study, with only 12 C cases and incomplete
baseline coverage. The answer key is deterministic task evidence, not human
adjudication. C's trace structure reveals the method, so the packet review had
limited blindness. Method, prompts, and budgets differ by arm; the individual
comparisons above are descriptive and do not prove a causal effect or a general
advantage for either method.

