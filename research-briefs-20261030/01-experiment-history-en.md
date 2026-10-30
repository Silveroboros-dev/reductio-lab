# How We Tested Selection–Inference and Arrived at the Question of Independent Judgment

Working research brief · 30 October 2026 · English version

## The Question We Started With

We wanted to understand whether a system inspired by the work of Antonia Creswell and Murray Shanahan could improve a modern language model's performance: select relevant premises, draw sequential inferences, and show a person what an answer rests on. We then refined the question: perhaps the value lies not only in higher accuracy, but also in enabling a person to notice and challenge an error or someone else's value assumption.

In [Selection–Inference](https://arxiv.org/abs/2205.09712), premise selection and the next inference are separated. [Faithful Reasoning](https://arxiv.org/abs/2208.14271) also uses trained stopping and search components. Our Python controllers coordinated **calls to one modern model in different roles**; this is neither a reproduction of the papers' trained components nor proof of how the model reasons internally.

## Short Answer

**In most of these series, the plain model and the model with self-check more often produced a final answer or matched the key than the controller. But the claim that “self-check always won” is too strong.** In one repaired pilot, all three branches tied; in one difficult example, SI gave a more complete visible justification while the final correct answer was the same. Since the plain model also got the final label right there, we cannot attribute the gain specifically to self-check.

No experiment established that SI is generally worse than modern models, that reasoning models “absorbed” SI during training, or that a trace automatically means sound reasoning. Our sets were small, open, or adjusted after observations; errors in the controller and the methodology itself materially affected the results.

## Chronology

### 1. First Controller on Saved Sources

Across six known situations, we compared a plain answer, an answer with self-check, and a controller with a separate checking role; the model was Gemini 3.8 Flash. There were 18 assignments, 16 received answers, and two technical failures. Paired final answers for C and the plain branch were available for 5 of 6 cases; for C and self-check, 4 of 6. No confirmed improvement from C was found. In all three branches, one BEA answer used numerical data but did not establish the required quarter. An earlier 3.5 series was stopped and is not mixed into this comparison.

This tested a specific controller with a checking role, **not yet a full reproduction of the SI architecture**. [Primary report — source record](source-index.md#source-01).

### 2. Prediction Markets, Rules, and News

The early FitCheck pilot had eight cases × four branches. Across B, B_self, and C, the system selected market rules 24 times and news zero times; therefore, the experiment did not measure the value of news as such. We then corrected the setup: rules determine market resolution, while news can provide evidence about an outcome. These are different functions.

A separate seed stage included four cases and 32 model responses: B and C made four calls each per case; no human semantic gold standard was available for the outputs. P0 contained four C/B pairs: 0.925/0.92 for Anthropic, 0.57/0.57 for CPI, 0.34/0.34 for Astra, and 0.75/0.75 for WTI. All saw the market quote; forecast accuracy was not measured before market resolution. The Anthropic contract concerned IPO confirmation and did not fully match the original valuation thesis.

In the subsequent CPI case, both valid branches with news retained the 0.57 estimate, but C did not include the PCE news in its final answer, even though it appeared in its intermediate branch. One C variant without news could be read only after a post hoc JSON repair and does not count as a strict success. On the other three topics, fresh relevant news after the original forecast was not demonstrably found; those checks remained incomplete. The absence of an effect does not prove that news or Orthogonal is useless.

[Corrected research report — source record](source-index.md#source-02) · [CPI and accounting — source record](source-index.md#source-03).

### 3. Larger Repeat Series on Real Sources

We repeated 18 situations × three branches: B, B_self, and C_v2. All 54 assignments received a status, but these were **not 18 independent questions**: four unique question wordings were used with different source situations.

| Branch | Outcome across 18 assignments |
|---|---|
| B | 18 answers |
| B_self | 18 answers |
| C_v2 | 4 answers, 11 `unknown`, 3 technical failures |

A preliminary model-assisted review rated B and B_self at 12 supported answers and 6 answers with an acceptable, appropriately scoped acknowledgment of uncertainty each; of C's four answers, 3 were supported and 1 unsupported. This was not independent human attestation. A missing answer does not automatically become a substantively wrong answer. C characteristically stopped prematurely without selecting an available source.

In a separate diagnostic series on 12 selected cases, C_v3 obtained sources more often but frequently failed to deliver an answer to the user. On the **nominal GDP** question, it noticed that real GDP data did not answer the question but ended with `unknown` and no explanation for the user. This usefully guards against substituting one metric for another, but it is an unhelpful outcome as an answer.

[Full 18 × 3 report — source record](source-index.md#source-04) · [answer review — source record](source-index.md#source-05) · [C_v3 and nominal GDP — source record](source-index.md#source-06).

### 4. First Synthetic Set: Dragons and Distracting Rules

We prepared eight artificial tasks: four pairs, 16 or 32 distracting statements, and an author-specified four-step path. The plain model and self-check matched the author's key in 8 of 8; C did not produce a final answer matching the author's key. But we then found that **the key itself depended on an unstated condition**: “Ignis is a dragon” did not strictly entail that Ignis belonged to the class of beings to which the rule applied. Under a strict reading, some tasks admitted `unknown`.

This was an important error in our setup, not fair proof of SI's defeat or the baseline's victory. In addition, the Halter sometimes required the final-answer format from an intermediate inference and impeded completion of the chain. [Report with full answers — source record](source-index.md#source-07).

### 5. Three Repaired Synthetic Tasks

We explicitly changed the scope of the rules and corrected the Halter/Formatter behavior. On three open tasks, **B, B_self, and C all matched the key in 3 of 3**. C preserved four transitions per task; B and B_self also provided complete explanations. Across the series, C used 51 model calls, B_self used 6, and B used 3.

This shows that the specific chains were feasible after repair, but not that SI had an advantage. We changed both the rules and the controller and selected cases after viewing earlier results, so the contribution of each change is not isolated. [Repaired pilot — source record](source-index.md#source-08).

### 6. Harder Synthetic Set

The next set contained 12 tasks with an author-specified six-step proof and 64 or 128 distracting rules. On Gemini 3.8, we compared four baselines, including self-check and a variant with a comparable budget, against the SI controller. We recorded 56 of 60 assignments: one baseline assignment in each of four branches was not started.

On the same 11 cases, each baseline branch produced 11 answers matching the key. C had 4 matches, 5 `unknown` stops, one proposal falsely claiming insufficient data, and one result rejected by the Formatter; the twelfth case had an indeterminate network effect. The key and a YES/NO match do not establish proof quality.

There is an important counterexample to a simple ranking. In one case, **all branches gave the correct YES**, but all four baselines omitted the necessary final rule from their visible justifications; C preserved the full six-step chain. In another case, C claimed the connecting rule was absent even though it was in the full set, and the baselines used it. Both examples were checked by an AI reviewer; there was no human attestation. They show why the answer, explanation, premise selection, and abstentions must be evaluated separately.

[Series summary — source record](source-index.md#source-09) · [trace review — source record](source-index.md#source-10).

### 7. Anthropic S-1: Toward Human Judgment

We compared a plain model A, a contrary-case check B, and SI-style C on six questions about saved sources. A and B each produced 6 answers; C produced 5 and had one technical failure. In the five completed C runs, it selected the entire packet and stopped after one step: **this run does not demonstrate full multi-step SI**.

In one participant's review, B's answer about PBC and T-share presented new information, after which the participant reported increased concerns; the plain branch A also mentioned those provisions, so we cannot attribute the change specifically to method B. On several other questions, the participant maintained their view while noting useful details. This is one person's self-report across different questions, not measured proof that independent judgment was preserved.

C incorrectly attributed the entire accounting loss exclusively to revaluation, although the data showed a smaller revaluation amount. B incorrectly restated one supplied excerpt from the market rules. All three branches added categories of compute commitments without evidence that they did not overlap. An inspectable trace does not remove the need to check the answer and the original document.

[Full A/B/C answers — source record](source-index.md#source-11) · participant feedback (retained separately) · [limitations of the initial report — source record](source-index.md#source-12). The last was written **before** your post-answer response and is outdated on this point.

## What We Do Next

The next proposed pilot tests whether a model helps a person find errors in the same piece of educational advice and notice imposed priorities. Twelve development cases have been prepared; for six, two-step reference proofs have been created within a constrained binary setup. The repaired controller and inputs have been checked offline. This is **not a completed experiment**: actual model behavior, the effect on a person, independent human review, and blinding have not been established. The old runtime is tied to v2 and must not be silently used for v3.

[Set and status — source record](source-index.md#source-13) · [protocol — source record](source-index.md#source-14) · [offline audit — source record](source-index.md#source-15).

## Open Research Questions

In our tasks, models often solved logic problems without an external symbolic wrapper. But even with a correct answer, their visible justification sometimes omitted an essential premise; the controller, in turn, could lose a source or produce a false `unknown`. The question is not simply which method produced a good-looking chain.

**Can we build an assistant that lets a person inspect not only a local inference, but also the choice of sources, overlooked alternatives, and the point where a fact becomes a value judgment?** And how should we measure whether a person can challenge advice and adjust their own criteria, without treating an unchanged opinion as an automatic success?

The original raw answers and logs are retained separately and are not included in this collection; the links above identify those records and hashes rather than publishing them. Their cost estimates are calculated local exposure figures with allowances, not a reconciled provider bill. This brief adds no new calls and does not change earlier results.
