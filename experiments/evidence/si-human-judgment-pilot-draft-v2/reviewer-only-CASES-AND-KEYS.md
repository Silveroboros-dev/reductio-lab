# Reviewer-only cases and keys — reveals answers

**Do not put this file or `reviewer-key.json` in participant/model context.** Candidate development material only. Source: local original Anthropic S-1 HTML, SHA-256 `2fa24ae7704dbb535d096ee7459b765fe899ac9118762e738183a94473c9905a`, as recorded in `draft-manifest.json`. No independent human source/semantic review, no model run, no pilot outcome.

## Formal scope

Six cases below carry a typed reference DAG. Primitive operations are one `add`, `subtract`, `divide`, `less_than`, `greater_than`, or typed `attach_right` on at most two already available inputs; output of a prior operation is a separately named node. The only built-in numeric constant is 100% for complement calculations. No step may read a derived value from raw source or perform two arithmetic operations internally. In this grammar, the target needs a path through at least two linked local operations. This is a property of the bounded graph representation, not a computational lower bound on one LLM call, and does not imply the actual SI engine will use it. Source facts can be directly co-located in the full S-1; the grammar applies to the stated evidence projection.

The check removes each declared critical source input and each precursor node, then requires the target to be unbuildable. It also perturbs each critical input and requires a changed or unbuildable target. A separate forged-target control refuses to count a supplied final value as a derivation when its declared nodes were skipped. These tests catch graph-level false positives, not semantic errors in a model or a human answer.

## P01 — Credit amendment: two increases

**Class:** error; **two-step status:** bounded_formal_DAG_checked_offline; actual SI behavior untested.

**Question:** How do the September 2026 changes in revolving commitments and the minimum-liquidity covenant compare in dollar terms?

**Prepared memo:** The September amendment raised the minimum-liquidity covenant by a larger dollar amount than it raised the revolving commitment. This comparison alone does not measure cash available.

**Source evidence (paraphrases):**

- P01-E1: Before the September 2026 amendment, revolving commitments were $3.3 billion. [Note 17 Subsequent Events, F-65; find: increasing the revolving commitments from $3.3 billion to $15.0 billion](https://www.sec.gov/Archives/edgar/data/2130357/000162828026067168/anthropicpbc-sx1.htm)
- P01-E2: The September 2026 amendment raised revolving commitments to $15.0 billion. [Note 17 Subsequent Events, F-65; find: increasing the revolving commitments from $3.3 billion to $15.0 billion](https://www.sec.gov/Archives/edgar/data/2130357/000162828026067168/anthropicpbc-sx1.htm)
- P01-E3: Before the same amendment, the minimum-liquidity covenant was $0.5 billion. [Note 17 Subsequent Events, F-65; find: increases the minimum liquidity covenant from $500 million to $5.0 billion](https://www.sec.gov/Archives/edgar/data/2130357/000162828026067168/anthropicpbc-sx1.htm)
- P01-E4: The amendment raised the minimum-liquidity covenant to $5.0 billion. [Note 17 Subsequent Events, F-65; find: increases the minimum liquidity covenant from $500 million to $5.0 billion](https://www.sec.gov/Archives/edgar/data/2130357/000162828026067168/anthropicpbc-sx1.htm)

**Expected review:** The disclosed dollar increases are $11.7bn and $4.5bn respectively, so the memo reverses their order. It makes no justified cash-availability conclusion.

**Authority:** Candidate agent-authored key; an independent reviewer has not signed it.

**Bounded reference DAG:**

- Input `a` = `3.3` (P01-E1).
- Input `b` = `15.0` (P01-E2).
- Input `c` = `0.5` (P01-E3).
- Input `d` = `5.0` (P01-E4).
- `n1` = `subtract(b, a)` → `11.7`.
- `n2` = `subtract(d, c)` → `4.5`.
- `n3` = `subtract(n1, n2)` → `7.2`.

**Why the links are needed here:** Both increases need their two endpoints; comparing the derived increases is a downstream step. The memo reverses their ordering. The graph says nothing about cash availability.

**Critical removal / modification:**

- Remove `a` → target cannot be built; replace its value with `11.0` → target changes or becomes unbuildable.
- Remove `b` → target cannot be built; replace its value with `3.3` → target changes or becomes unbuildable.
- Remove `c` → target cannot be built; replace its value with `1.0` → target changes or becomes unbuildable.
- Remove `d` → target cannot be built; replace its value with `20.0` → target changes or becomes unbuildable.
- Remove `n1` → downstream target cannot be built. Counterexample to accepting an uncomputed final value: with source input `a` set to `11.0`, the complete graph gives a different or unbuildable target.
- Remove `n2` → downstream target cannot be built. Counterexample to accepting an uncomputed final value: with source input `c` set to `1.0`, the complete graph gives a different or unbuildable target.

**Limit:** A minimal reference trace inside this operation grammar, not a proof that an LLM needs multiple calls or that the actual SI engine will form this graph.

## P02 — RSU illustrative expense split

**Class:** error; **two-step status:** bounded_formal_DAG_checked_offline; actual SI behavior untested.

**Question:** In the June 30, 2026 hypothetical IPO illustration, what proportion of the combined RSU expense remains to be recognized later?

**Prepared memo:** In the June 30 hypothetical offering illustration, the later-recognized $23.7 billion RSU amount is about 11% of the combined immediate and later RSU amounts.

**Source evidence (paraphrases):**

- P02-E1: If the offering had completed on June 30, 2026, $2.9 billion cumulative RSU expense would have been recorded on that date. [Risk Factors, p. 65; find: recorded $2.9 billion of cumulative stock-based compensation expense](https://www.sec.gov/Archives/edgar/data/2130357/000162828026067168/anthropicpbc-sx1.htm)
- P02-E2: Another $23.7 billion of unrecognized RSU expense would be recognized over a weighted-average period of about 2.1 years. [Risk Factors, p. 65; find: additional $23.7 billion of unrecognized stock-based compensation expense](https://www.sec.gov/Archives/edgar/data/2130357/000162828026067168/anthropicpbc-sx1.htm)

**Expected review:** The later $23.7bn is about 89% of the $26.6bn illustrative combination, not about 11%; the amounts are a June 30 hypothetical.

**Authority:** Candidate agent-authored key; an independent reviewer has not signed it.

**Bounded reference DAG:**

- Input `a` = `2.9` (P02-E1).
- Input `b` = `23.7` (P02-E2).
- `n1` = `add(a, b)` → `26.6`.
- `n2` = `divide(b, n1)` → `0.8909774436090225`.

**Why the links are needed here:** The reference target is the later-recognized fraction of this historical hypothetical total. The memo assigns the complementary fraction to the later amount. No forecast of actual IPO expense is made.

**Critical removal / modification:**

- Remove `a` → target cannot be built; replace its value with `213.3` → target changes or becomes unbuildable.
- Remove `b` → target cannot be built; replace its value with `0.33` → target changes or becomes unbuildable.
- Remove `n1` → downstream target cannot be built. Counterexample to accepting an uncomputed final value: with source input `a` set to `213.3`, the complete graph gives a different or unbuildable target.

**Limit:** A minimal reference trace inside this operation grammar, not a proof that an LLM needs multiple calls or that the actual SI engine will form this graph.

## P03 — Board seat majority

**Class:** error; **two-step status:** bounded_formal_DAG_checked_offline; actual SI behavior untested.

**Question:** For the proposed seven-seat board, do the seats elected by the Class F and Class A holders form a majority?

**Prepared memo:** The Class F and Class A holders elect the seats outside Class T; these seats form a majority of the proposed seven-seat board.

**Source evidence (paraphrases):**

- P03-E1: After the offering, the board is proposed to have seven authorized directors. [Board of Directors; find: seven authorized directors](https://www.sec.gov/Archives/edgar/data/2130357/000162828026067168/anthropicpbc-sx1.htm)
- P03-E2: The Long-Term Benefit Trust, as Class T holder, generally has authority to elect and remove four Class T directors, subject to stated procedures. [Board of Directors; find: elect and remove the four Class T directors](https://www.sec.gov/Archives/edgar/data/2130357/000162828026067168/anthropicpbc-sx1.htm)
- P03-E3: Class F and Class A holders together elect and remove the remaining directors. [Board of Directors; find: elect and remove the remaining three directors](https://www.sec.gov/Archives/edgar/data/2130357/000162828026067168/anthropicpbc-sx1.htm)

**Expected review:** The residual Class F/A seats are three of seven; the four Class T seats are the majority, subject to the disclosed procedures.

**Authority:** Candidate agent-authored key; an independent reviewer has not signed it.

**Bounded reference DAG:**

- Input `a` = `7` (P03-E1).
- Input `b` = `4` (P03-E2).
- Input `c` = `F/A elect remaining` (P03-E3).
- `n1` = `subtract(a, b)` → `3`.
- `n2` = `attach_right(n1, c)` → `{'holder': 'F/A', 'count': 3}`.
- `n3` = `greater_than(b, n2)` → `True`.

**Why the links are needed here:** Under the disclosed proposed board, four Class T seats exceed the three residual F/A seats. The allocation condition is needed to identify the residual seats; procedures and vacancies still matter.

**Critical removal / modification:**

- Remove `a` → target cannot be built; replace its value with `9` → target changes or becomes unbuildable.
- Remove `b` → target cannot be built; replace its value with `2` → target changes or becomes unbuildable.
- Remove `c` → target cannot be built; replace its value with `T elect remaining` → target changes or becomes unbuildable.
- Remove `n1` → downstream target cannot be built. Counterexample to accepting an uncomputed final value: with source input `a` set to `9`, the complete graph gives a different or unbuildable target.
- Remove `n2` → downstream target cannot be built. Counterexample to accepting an uncomputed final value: with source input `a` set to `9`, the complete graph gives a different or unbuildable target.

**Limit:** A minimal reference trace inside this operation grammar, not a proof that an LLM needs multiple calls or that the actual SI engine will form this graph.

## P04 — Compute commitments

**Class:** error; **two-step status:** not claimed as necessary two-step.

**Question:** How should future compute payments under the disclosed agreements be interpreted?

**Prepared memo:** All future compute payments are already included in the $265.6 billion figure; payments under other agreements will be zero.

**Source evidence (paraphrases):**

- P04-E1: As of June 30, 2026, expected future fixed or minimum guaranteed commitments under specified agreements were approximately $265.6 billion. [Note 13 Purchase Commitments, F-59; find: expected future fixed or minimum guaranteed commitments under these agreements were approximately $265.6 billion](https://www.sec.gov/Archives/edgar/data/2130357/000162828026067168/anthropicpbc-sx1.htm)
- P04-E2: Other compute and infrastructure agreements have no fixed or minimum dollar commitment; their payments are not determinable and were excluded from the $265.6 billion amount, though expected to be significant. [Note 13 Purchase Commitments, F-59; find: The Company does not include any estimated obligation for these agreements in the amount above](https://www.sec.gov/Archives/edgar/data/2130357/000162828026067168/anthropicpbc-sx1.htm)
- P04-E3: H1 2026 revenue was $16.286 billion and compute/infrastructure expense $8.945 billion. [Results of Operations, pp. 148–150; find: Compute and infrastructure 433 2,522 7,326 2,334 8,945](https://www.sec.gov/Archives/edgar/data/2130357/000162828026067168/anthropicpbc-sx1.htm)

**Expected review:** Из суммы исключены договоры без фиксированного минимума. Исключение из оценки не означает нулевые расходы; величина оставшихся платежей неизвестна.

**Authority:** Candidate agent-authored key; an independent reviewer has not signed it.

**Reference graph:** None claimed. The inherited source-grounded case is a control/adaptation, not evidence of necessary multi-step SI.

## P05 — Infrastructure financing notes

**Class:** error; **two-step status:** not claimed as necessary two-step.

**Question:** How should the disclosed infrastructure financing instrument be interpreted?

**Prepared memo:** As of June 30, the company already held $42 billion of unrestricted cash available for any expense.

**Source evidence (paraphrases):**

- P05-E1: A March 2026 agreement permits, subject to conditions, up to $42.0 billion of convertible notes solely to finance rent obligations under a compute/infrastructure agreement. [Note 9 Other Note Purchase Agreements 2026, F-43; find: up to $42.0 billion of convertible promissory notes solely to finance rent obligations](https://www.sec.gov/Archives/edgar/data/2130357/000162828026067168/anthropicpbc-sx1.htm)
- P05-E2: As of June 30, 2026, the draw period had not yet begun and no amount was outstanding under that agreement. [Note 9 Other Note Purchase Agreements 2026, F-43; find: As of June 30, 2026 , no amounts were outstanding under the note purchase agreement](https://www.sec.gov/Archives/edgar/data/2130357/000162828026067168/anthropicpbc-sx1.htm)
- P05-E3: In September 2026, revolving commitments increased from $3.3 billion to $15.0 billion. [Note 17 Subsequent Events, F-65; find: increasing the revolving commitments from $3.3 billion to $15.0 billion](https://www.sec.gov/Archives/edgar/data/2130357/000162828026067168/anthropicpbc-sx1.htm)

**Expected review:** Это условная возможность финансирования целевого назначения, а не уже имеющиеся свободные деньги; на дату по конкретному соглашению нот не было.

**Authority:** Candidate agent-authored key; an independent reviewer has not signed it.

**Reference graph:** None claimed. The inherited source-grounded case is a control/adaptation, not evidence of necessary multi-step SI.

## P06 — Customer concentration across periods

**Class:** error; **two-step status:** not claimed as necessary two-step.

**Question:** What does the disclosed nine-month customer concentration establish about Q3?

**Prepared memo:** Because no individual customer exceeded 10% of nine-month revenue, no individual customer exceeded 10% in Q3.

**Source evidence (paraphrases):**

- P06-E1: No individual customer exceeded 10% of revenue for the nine months ended September 30, 2026. [Customer Base, p. 144; find: No single customer represented more than 10% of our revenue for the nine months ended September 30, 2026](https://www.sec.gov/Archives/edgar/data/2130357/000162828026067168/anthropicpbc-sx1.htm)
- P06-E2: Approximately 79% of Q3 2026 revenue came from customers outside the top five. [Customer Base, p. 144; find: Approximately 79% of our revenue came from customers outside of our top five customers](https://www.sec.gov/Archives/edgar/data/2130357/000162828026067168/anthropicpbc-sx1.htm)
- P06-E3: Approximately 64% of Q1 2026 revenue came from customers outside the top five. [Customer Base, p. 144; find: approximately 64% for the three months ended March 31, 2026](https://www.sec.gov/Archives/edgar/data/2130357/000162828026067168/anthropicpbc-sx1.htm)

**Expected review:** The nine-month threshold does not establish the same threshold separately for Q3. The Q3 claim is unsupported by this evidence, not proven historically false.

**Authority:** Candidate agent-authored key; an independent reviewer has not signed it.

**Reference graph:** None claimed. The inherited source-grounded case is a control/adaptation, not evidence of necessary multi-step SI.

## P07 — Dividend policy

**Class:** clean; **two-step status:** not claimed as necessary two-step.

**Question:** How should the dividend policy affect an assessment of possible shareholder returns?

**Prepared memo:** The prospectus does not expect dividends in the foreseeable future, but does not rule them out forever. The policy alone cannot establish total share return, which also depends on an unknown future share price.

**Source evidence (paraphrases):**

- P07-E1: As of the prospectus, the company had never declared or paid cash dividends on its capital stock. [Dividend Policy, p. 126; find: We have never declared or paid any cash dividends on our capital stock](https://www.sec.gov/Archives/edgar/data/2130357/000162828026067168/anthropicpbc-sx1.htm)
- P07-E2: The company does not expect dividends in the foreseeable future; future declarations are at board discretion subject to applicable law and other factors. [Dividend Policy, p. 126; find: do not expect to pay any dividends in the foreseeable future](https://www.sec.gov/Archives/edgar/data/2130357/000162828026067168/anthropicpbc-sx1.htm)
- P07-E3: H1 2026 operating cash flow was positive $3.929 billion and investing cash flow negative $17.181 billion. [Consolidated Statements of Cash Flows, F-13; find: Net cash provided by (used in) operating activities](https://www.sec.gov/Archives/edgar/data/2130357/000162828026067168/anthropicpbc-sx1.htm)

**Expected review:** Совет допустим в пределах данных: ближайшее ожидание не является бессрочным запретом; отсутствие ожидаемых дивидендов не устанавливает общую доходность. Не интерпретировать его как прогноз роста.

**Authority:** Candidate agent-authored key; an independent reviewer has not signed it.

**Reference graph:** None claimed. The inherited source-grounded case is a control/adaptation, not evidence of necessary multi-step SI.

## P08 — Class F voting fallback

**Class:** clean; **two-step status:** not claimed as necessary two-step.

**Question:** Under what conditions does the Class F voting fallback apply?

**Prepared memo:** For an applicable general matter, if a majority of Continuing Founders gives no instruction and the required Class A quorum is present, Class F votes track the Class A votes proportionally; this need not hold for special matters.

**Source evidence (paraphrases):**

- P08-E1: For specified general matters, absent a majority Continuing Founder instruction, Class F votes proportionally with Class A votes cast, subject to a quorum of a majority of outstanding Class A shares. [Class F Common Stock Voting Mechanics; find: our Class F common stock will be voted proportionately with the votes of Class A common stock cast](https://www.sec.gov/Archives/edgar/data/2130357/000162828026067168/anthropicpbc-sx1.htm)
- P08-E2: Other matters carry distinct special voting thresholds. [Class F Common Stock Voting Mechanics; find: If a proposal requires both a Supermajority and a Trust Amendment Supermajority](https://www.sec.gov/Archives/edgar/data/2130357/000162828026067168/anthropicpbc-sx1.htm)
- P08-E3: The proposed board has seven authorized seats; the LTBT as Class T holder generally elects four, subject to described procedures. [Board of Directors; find: seven authorized directors](https://www.sec.gov/Archives/edgar/data/2130357/000162828026067168/anthropicpbc-sx1.htm)

**Expected review:** Совет верен для указанных условий. Нельзя переносить fallback на все специальные вопросы или опускать условие кворума.

**Authority:** Candidate agent-authored key; an independent reviewer has not signed it.

**Reference graph:** None claimed. The inherited source-grounded case is a control/adaptation, not evidence of necessary multi-step SI.

## P09 — Net short-term investment purchases

**Class:** clean; **two-step status:** bounded_formal_DAG_checked_offline; actual SI behavior untested.

**Question:** How do net purchases of short-term investments compare with net cash used in investing activities for H1 2026?

**Prepared memo:** For H1 2026, net short-term investment purchases were $16.362 billion, smaller in magnitude than the $17.181 billion net investing cash outflow. This does not identify the whole remainder as capital spending.

**Source evidence (paraphrases):**

- P09-E1: H1 2026 purchases of short-term investments were $18.972 billion. [Consolidated Statements of Cash Flows, F-13; find: Purchases of short-term investments](https://www.sec.gov/Archives/edgar/data/2130357/000162828026067168/anthropicpbc-sx1.htm)
- P09-E2: H1 2026 sales and maturities of short-term investments provided $2.610 billion. [Consolidated Statements of Cash Flows, F-13; find: Sales and maturities of short-term investments](https://www.sec.gov/Archives/edgar/data/2130357/000162828026067168/anthropicpbc-sx1.htm)
- P09-E3: H1 2026 net cash used in investing activities was $17.181 billion. [Consolidated Statements of Cash Flows, F-13; find: Net cash used in investing activities](https://www.sec.gov/Archives/edgar/data/2130357/000162828026067168/anthropicpbc-sx1.htm)

**Expected review:** $18.972bn less $2.610bn is $16.362bn, below the $17.181bn net investing outflow magnitude. The memo does not assign the remainder to capex.

**Authority:** Candidate agent-authored key; an independent reviewer has not signed it.

**Bounded reference DAG:**

- Input `a` = `18.972` (P09-E1).
- Input `b` = `2.61` (P09-E2).
- Input `c` = `17.181` (P09-E3).
- `n1` = `subtract(a, b)` → `16.362`.
- `n2` = `less_than(n1, c)` → `True`.

**Why the links are needed here:** Compare net purchases with the magnitude of the net investing cash outflow, both H1 2026. This comparison does not allocate every other investing line.

**Critical removal / modification:**

- Remove `a` → target cannot be built; replace its value with `28.972` → target changes or becomes unbuildable.
- Remove `b` → target cannot be built; replace its value with `0.61` → target changes or becomes unbuildable.
- Remove `c` → target cannot be built; replace its value with `10.0` → target changes or becomes unbuildable.
- Remove `n1` → downstream target cannot be built. Counterexample to accepting an uncomputed final value: with source input `a` set to `28.972`, the complete graph gives a different or unbuildable target.

**Limit:** A minimal reference trace inside this operation grammar, not a proof that an LLM needs multiple calls or that the actual SI engine will form this graph.

## P10 — Revenue remaining after two expense categories

**Class:** clean; **two-step status:** bounded_formal_DAG_checked_offline; actual SI behavior untested.

**Question:** For H1 2026, how much revenue remains after compute/infrastructure and personnel expenses, before other operating expenses?

**Prepared memo:** From $16.286 billion of H1 revenue, $4.189 billion remains after the $8.945 billion compute/infrastructure and $3.152 billion personnel expense categories; other expenses still apply.

**Source evidence (paraphrases):**

- P10-E1: H1 2026 revenue was $16.286 billion. [Results of Operations, p. 148; Statements of Operations, F-7; find: Revenue $ 41 $ 386 $ 4,585 $ 1,163 $ 16,286](https://www.sec.gov/Archives/edgar/data/2130357/000162828026067168/anthropicpbc-sx1.htm)
- P10-E2: H1 2026 compute/infrastructure expense was $8.945 billion. [Results of Operations, pp. 148–150; Statements of Operations, F-7; find: Compute and infrastructure 433 2,522 7,326 2,334 8,945](https://www.sec.gov/Archives/edgar/data/2130357/000162828026067168/anthropicpbc-sx1.htm)
- P10-E3: H1 2026 personnel expense was $3.152 billion; other operating expense categories were also reported. [Results of Operations, pp. 148–150; Statements of Operations, F-7; find: Personnel 95 454 1,839 538 3,152](https://www.sec.gov/Archives/edgar/data/2130357/000162828026067168/anthropicpbc-sx1.htm)

**Expected review:** $16.286bn minus $8.945bn minus $3.152bn is $4.189bn before other operating expenses. The memo does not label this profit.

**Authority:** Candidate agent-authored key; an independent reviewer has not signed it.

**Bounded reference DAG:**

- Input `a` = `16.286` (P10-E1).
- Input `b` = `8.945` (P10-E2).
- Input `c` = `3.152` (P10-E3).
- `n1` = `subtract(a, b)` → `7.341`.
- `n2` = `subtract(n1, c)` → `4.189`.

**Why the links are needed here:** This is a two-category arithmetic remainder, not operating profit; S-1 lists other expenses.

**Critical removal / modification:**

- Remove `a` → target cannot be built; replace its value with `17.286` → target changes or becomes unbuildable.
- Remove `b` → target cannot be built; replace its value with `7.945` → target changes or becomes unbuildable.
- Remove `c` → target cannot be built; replace its value with `4.152` → target changes or becomes unbuildable.
- Remove `n1` → downstream target cannot be built. Counterexample to accepting an uncomputed final value: with source input `a` set to `17.286`, the complete graph gives a different or unbuildable target.

**Limit:** A minimal reference trace inside this operation grammar, not a proof that an LLM needs multiple calls or that the actual SI engine will form this graph.

## P11 — Top-five revenue share change

**Class:** clean; **two-step status:** bounded_formal_DAG_checked_offline; actual SI behavior untested.

**Question:** How did the approximate top-five customer share change between Q1 and Q3 2026?

**Prepared memo:** The approximate top-five share fell from 36% in Q1 to 21% in Q3, a decline of about 15 percentage points; this does not establish future diversification.

**Source evidence (paraphrases):**

- P11-E1: Approximately 64% of Q1 2026 revenue came from customers outside the top five. [Customer Usage Patterns, p. 144; find: approximately 64% for the three months ended March 31, 2026](https://www.sec.gov/Archives/edgar/data/2130357/000162828026067168/anthropicpbc-sx1.htm)
- P11-E2: Approximately 79% of Q3 2026 revenue came from customers outside the top five. [Customer Usage Patterns, p. 144; find: Approximately 79% of our revenue came from customers outside of our top five customers](https://www.sec.gov/Archives/edgar/data/2130357/000162828026067168/anthropicpbc-sx1.htm)

**Expected review:** The complements of approximately 64% and 79% are approximately 36% and 21%, a decline of about 15 percentage points. Future composition is unknown.

**Authority:** Candidate agent-authored key; an independent reviewer has not signed it.

**Bounded reference DAG:**

- Input `a` = `64` (P11-E1).
- Input `b` = `79` (P11-E2).
- Input `hundred` = `100` (100% definition).
- `n1` = `subtract(hundred, a)` → `36`.
- `n2` = `subtract(hundred, b)` → `21`.
- `n3` = `subtract(n1, n2)` → `15`.

**Why the links are needed here:** Approximate outside-top-five shares become approximate inside-top-five shares, then a percentage-point difference. It does not identify customers or predict future concentration.

**Critical removal / modification:**

- Remove `a` → target cannot be built; replace its value with `70` → target changes or becomes unbuildable.
- Remove `b` → target cannot be built; replace its value with `75` → target changes or becomes unbuildable.
- Remove `n1` → downstream target cannot be built. Counterexample to accepting an uncomputed final value: with source input `a` set to `70`, the complete graph gives a different or unbuildable target.
- Remove `n2` → downstream target cannot be built. Counterexample to accepting an uncomputed final value: with source input `b` set to `75`, the complete graph gives a different or unbuildable target.

**Limit:** A minimal reference trace inside this operation grammar, not a proof that an LLM needs multiple calls or that the actual SI engine will form this graph.

## P12 — RSU vesting conditions

**Class:** clean; **two-step status:** not claimed as necessary two-step.

**Question:** Does registration effectiveness alone guarantee immediate full vesting of the disclosed RSU grants?

**Prepared memo:** Effectiveness satisfies the performance condition, but does not replace the separate service condition; effectiveness alone does not guarantee immediate full vesting of every grant.

**Source evidence (paraphrases):**

- P12-E1: The described RSUs have both service-based and performance-based vesting conditions. [Note 17 Subsequent Events, F-65; find: The RSUs are subject to both service-based and performance-based vesting conditions](https://www.sec.gov/Archives/edgar/data/2130357/000162828026067168/anthropicpbc-sx1.htm)
- P12-E2: Registration effectiveness satisfies the performance condition; the service condition generally runs quarterly over four years, with a new-hire cliff and continuous-service requirement. [Note 17 Subsequent Events, F-65; find: The performance-based vesting condition of the RSUs will be satisfied upon the effectiveness](https://www.sec.gov/Archives/edgar/data/2130357/000162828026067168/anthropicpbc-sx1.htm)
- P12-E3: The S-1 also describes a separate hypothetical June 30, 2026 offering-completion scenario with $2.9 billion cumulative RSU expense. [Risk Factors, p. 65; find: If this offering had been completed on June 30, 2026](https://www.sec.gov/Archives/edgar/data/2130357/000162828026067168/anthropicpbc-sx1.htm)

**Expected review:** Оба условия применяются совместно; одного события effectiveness недостаточно для гарантии полного vesting всех грантов. Некоторые service-порции могут уже быть выполнены; никаких фактических продаж из этого не следует.

**Authority:** Candidate agent-authored key; an independent reviewer has not signed it.

**Reference graph:** None claimed. The inherited source-grounded case is a control/adaptation, not evidence of necessary multi-step SI.

## Pre-use review and exposure

1. Have an independent human compare every paraphrase and date against the original S-1 and adjudicate the intended error/clean status; record alternatives and ambiguous source scope. This did not occur here.
2. Inspect the participant projection so status, expected review, and graph fields never enter prompts. Prepared advice should appear only after the participant pre-position is recorded. This has not been tested.
3. Freeze a successor reviewed package and separately bind exact corpus/exposure/assignment hashes before any run. Same-folder hashes alone are not an external seal.
4. The prior S-1 and draft-v1 material have been exposed or may have been available. Treat this package as development, not a blind holdout for the same viewer.
5. The previous controller review found completed C branches taking one step; this package does not repair runtime Selection prompts, prove two-step SI execution, or authorize model/provider calls.
