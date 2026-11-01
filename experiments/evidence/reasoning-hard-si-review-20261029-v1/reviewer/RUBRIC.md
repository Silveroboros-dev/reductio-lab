# Independent review rubric

Review each packet on its own. A proposal is not automatically correct because
its answer matches the synthetic answer key. Do not treat unknowns or technical
failures as incorrect answers.

For a substantive proposal, record:

1. **Conclusion correctness** — Does the answer follow from the supplied task
   and evidence? Check polarity, entity, and requested condition.
2. **Premise sufficiency** — Do the cited/selected premises support every
   inference step needed for the conclusion? For these logical tasks, check the
   stated rule antecedents and whether the initial fact reaches them. This is
   logical sufficiency, not a claim about real-world causation.
3. **Unsupported inference** — Mark any invented premise, skipped condition,
   invalid substitution, polarity flip, contradiction, or outside knowledge.
4. **Evidence use** — Are explanations and citations faithful to the supplied
   statements? A citation ID alone does not establish entailment.

Use `supported`, `partly_supported`, `unsupported`, or `unclear` for the first
two criteria. For unsupported inference, record `none_observed`, `present`, or
`unclear`, with a short explanation.

For `unknown_no_answer`, judge whether UNKNOWN is warranted because neither
answer follows, or whether the supplied evidence supports YES/NO. Keep this
separate from answer correctness. For `technical_failure_no_answer` or
`no_final_proposal`, do not assign semantic correctness; record the item in the
failure denominator and note the visible failure category only.

The C trace can reveal the method through its role names and branch structure.
Blinding is therefore limited. Do not infer that traceability proves truth,
causal influence, or semantic validity. An automated synthetic key may be
provided separately by the custodian after blinded review; it is not a human
gold standard.

Suggested review fields: conclusion_correctness, premise_sufficiency,
unsupported_inference, evidence_use, unknown_warranted (when applicable), and
reviewer_explanation.
