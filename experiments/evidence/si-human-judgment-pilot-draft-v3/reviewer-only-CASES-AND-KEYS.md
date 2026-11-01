# Reviewer-only v3 cases and keys — reveals answers

**Keep this file and `reviewer-key.json` out of participant and model inputs.** Agent-authored candidate only. No independent human attestation, no run, no model outputs, and no pilot outcome.

Original local S-1 SHA-256: `2fa24ae7704dbb535d096ee7459b765fe899ac9118762e738183a94473c9905a`. Source locators below refer to that snapshot and preserve original filing text; the participant evidence is an English paraphrase.

## Measurement grammar and limit

For the six DAG cases, one local inference may apply exactly one typed binary operation (`add`, `subtract`, or `divide`) to at most two existing premise IDs. Two sequential steps are allowed. Step 1 consumes two distinct original evidence IDs; step 2 consumes `n1` plus the third original evidence ID. No model-visible evidence contains the computed final target. This path is shape-compatible with depth 2, beam width 1, and two premise IDs per inference. This is **not** a claim that an LLM cannot compute the result in one call or that the actual SI runtime will produce the path.

The offline validator binds each source atom to a period-specific prose phrase or table cell, removes each actual model-visible evidence ID, and checks that the target becomes unbuildable. It also changes one visible atomic fact in a hypothetical test world and checks that the memo classification flips. These counterfactuals are not observations or corrections to the S-1. A forged final value is rejected unless both named inferences are built.

## C-DC1D56 — RSU vesting conditions

**Class:** clean. **Predecessor ID (reviewer only):** P12. **Two-step status:** not claimed as necessary two-step.

**Question:** Does registration effectiveness alone guarantee immediate full vesting of the disclosed RSU grants?

**Prepared memo:** Effectiveness satisfies the performance condition, but does not replace the separate service condition; effectiveness alone does not guarantee immediate full vesting of every grant.

**Projected source evidence:**

- `E-743176CE` — The described RSUs have both service-based and performance-based vesting conditions. Locator: Note 17 Subsequent Events, F-65; find: The RSUs are subject to both service-based and performance-based vesting conditions. [Original S-1](https://www.sec.gov/Archives/edgar/data/2130357/000162828026067168/anthropicpbc-sx1.htm).
- `E-3F0C147A` — Registration effectiveness satisfies the performance condition; the service condition generally runs quarterly over four years, with a new-hire cliff and continuous-service requirement. Locator: Note 17 Subsequent Events, F-65; find: The performance-based vesting condition of the RSUs will be satisfied upon the effectiveness. [Original S-1](https://www.sec.gov/Archives/edgar/data/2130357/000162828026067168/anthropicpbc-sx1.htm).
- `E-D102983D` — The S-1 also describes a separate hypothetical June 30, 2026 offering-completion scenario with $2.9 billion cumulative RSU expense. Locator: Risk Factors, p. 65; find: If this offering had been completed on June 30, 2026. [Original S-1](https://www.sec.gov/Archives/edgar/data/2130357/000162828026067168/anthropicpbc-sx1.htm).

**Expected review:** Оба условия применяются совместно; одного события effectiveness недостаточно для гарантии полного vesting всех грантов. Некоторые service-порции могут уже быть выполнены; никаких фактических продаж из этого не следует.

**Authority:** Candidate agent-authored interpretation; independent human review is pending.

**Reference DAG:** None claimed for this adapted control case.

## C-F75743 — Cash and short-term investments as asset share

**Class:** clean. **Predecessor ID (reviewer only):** P11. **Two-step status:** exact_two_step_three_source_leaf_reference_DAG_checked_offline.

**Question:** At June 30, 2026, approximately what fraction of reported total assets was cash and cash equivalents plus short-term investments?

**Prepared memo:** At June 30, 2026, cash and short-term investments together exceeded 85% of reported total assets. This accounting ratio does not establish unrestricted spendable cash.

**Projected source evidence:**

- `E-80FE3ED0` — Cash and cash equivalents at June 30, 2026 were $112.389 billion. Locator: Consolidated Balance Sheets, F-6; June 30 2026 column; cash and cash equivalents. [Original S-1](https://www.sec.gov/Archives/edgar/data/2130357/000162828026067168/anthropicpbc-sx1.htm).
- `E-2CBAD120` — Short-term investments at June 30, 2026 were $19.262 billion. Locator: Consolidated Balance Sheets, F-6; June 30 2026 column; short-term investments. [Original S-1](https://www.sec.gov/Archives/edgar/data/2130357/000162828026067168/anthropicpbc-sx1.htm).
- `E-EF027A63` — Total assets at June 30, 2026 were $147.358 billion. Locator: Consolidated Balance Sheets, F-6; June 30 2026 column; total assets. [Original S-1](https://www.sec.gov/Archives/edgar/data/2130357/000162828026067168/anthropicpbc-sx1.htm).

**Expected review:** $112.389bn plus $19.262bn is $131.651bn; divided by $147.358bn total assets is about 89.34%. This is a balance-sheet share, not unrestricted cash.

**Authority:** Candidate agent-authored interpretation; independent human review is pending.

**Exact reference ancestry:**

- `a` ← `E-80FE3ED0` = `112.389`. Original source atom: `112,389`; period marker: `As of December 31, As of June 30, 2024 2025 2026 (unaudited)`.
- `b` ← `E-2CBAD120` = `19.262`. Original source atom: `19,262`; period marker: `As of December 31, As of June 30, 2024 2025 2026 (unaudited)`.
- `c` ← `E-EF027A63` = `147.358`. Original source atom: `147,358`; period marker: `As of December 31, As of June 30, 2024 2025 2026 (unaudited)`.
- `n1` = `add(a, b)` → `131.651`.
- `n2` = `divide(n1, c)` → `0.8934092482254102`.

**Why it matters:** The first step combines two balance-sheet lines; the second divides by total assets of the same date. It is an accounting share, not a claim about unrestricted spendability. The prepared memo is checked by `greater_than(target, 0.85)`.

**Evidence deletion and hypothetical counterexample:**

- Removing `E-80FE3ED0` from the model-visible projection makes the final target unbuildable. If only its numeric fact were hypothetically `90.389`, the memo classification would flip; this is not source evidence.
- Removing `E-2CBAD120` from the model-visible projection makes the final target unbuildable. If only its numeric fact were hypothetically `5.262`, the memo classification would flip; this is not source evidence.
- Removing `E-EF027A63` from the model-visible projection makes the final target unbuildable. If only its numeric fact were hypothetically `160.358`, the memo classification would flip; this is not source evidence.

Removing `n1` blocks the second inference. Supplying a final number without both declared nodes is a false-positive derivation.

**Scope:** This is a lower bound only for the declared binary operation/evidence-projection grammar. One LLM call may perform both elementary operations. No actual SI model trace or semantic correctness is inferred.

## C-BF6785 — Infrastructure financing notes

**Class:** error. **Predecessor ID (reviewer only):** P05. **Two-step status:** not claimed as necessary two-step.

**Question:** How should the disclosed infrastructure financing instrument be interpreted?

**Prepared memo:** As of June 30, the company already held $42 billion of unrestricted cash available for any expense.

**Projected source evidence:**

- `E-F77F3878` — A March 2026 agreement permits, subject to conditions, up to $42.0 billion of convertible notes solely to finance rent obligations under a compute/infrastructure agreement. Locator: Note 9 Other Note Purchase Agreements 2026, F-43; find: up to $42.0 billion of convertible promissory notes solely to finance rent obligations. [Original S-1](https://www.sec.gov/Archives/edgar/data/2130357/000162828026067168/anthropicpbc-sx1.htm).
- `E-2B8C8F63` — As of June 30, 2026, the draw period had not yet begun and no amount was outstanding under that agreement. Locator: Note 9 Other Note Purchase Agreements 2026, F-43; find: As of June 30, 2026 , no amounts were outstanding under the note purchase agreement. [Original S-1](https://www.sec.gov/Archives/edgar/data/2130357/000162828026067168/anthropicpbc-sx1.htm).
- `E-6FF4FA8D` — In September 2026, revolving commitments increased from $3.3 billion to $15.0 billion. Locator: Note 17 Subsequent Events, F-65; find: increasing the revolving commitments from $3.3 billion to $15.0 billion. [Original S-1](https://www.sec.gov/Archives/edgar/data/2130357/000162828026067168/anthropicpbc-sx1.htm).

**Expected review:** Это условная возможность финансирования целевого назначения, а не уже имеющиеся свободные деньги; на дату по конкретному соглашению нот не было.

**Authority:** Candidate agent-authored interpretation; independent human review is pending.

**Reference DAG:** None claimed for this adapted control case.

## C-86837B — Customer concentration across periods

**Class:** error. **Predecessor ID (reviewer only):** P06. **Two-step status:** not claimed as necessary two-step.

**Question:** What does the disclosed nine-month customer concentration establish about Q3?

**Prepared memo:** Because no individual customer exceeded 10% of nine-month revenue, no individual customer exceeded 10% in Q3.

**Projected source evidence:**

- `E-3DEF1799` — No individual customer exceeded 10% of revenue for the nine months ended September 30, 2026. Locator: Customer Base, p. 144; find: No single customer represented more than 10% of our revenue for the nine months ended September 30, 2026. [Original S-1](https://www.sec.gov/Archives/edgar/data/2130357/000162828026067168/anthropicpbc-sx1.htm).
- `E-4FAD6A0C` — Approximately 79% of Q3 2026 revenue came from customers outside the top five. Locator: Customer Base, p. 144; find: Approximately 79% of our revenue came from customers outside of our top five customers. [Original S-1](https://www.sec.gov/Archives/edgar/data/2130357/000162828026067168/anthropicpbc-sx1.htm).
- `E-07055694` — Approximately 64% of Q1 2026 revenue came from customers outside the top five. Locator: Customer Base, p. 144; find: approximately 64% for the three months ended March 31, 2026. [Original S-1](https://www.sec.gov/Archives/edgar/data/2130357/000162828026067168/anthropicpbc-sx1.htm).

**Expected review:** The nine-month threshold does not establish the same threshold separately for Q3. The Q3 claim is unsupported by this evidence, not proven historically false.

**Authority:** Candidate agent-authored interpretation; independent human review is pending.

**Reference DAG:** None claimed for this adapted control case.

## C-F015DA — Dividend policy

**Class:** clean. **Predecessor ID (reviewer only):** P07. **Two-step status:** not claimed as necessary two-step.

**Question:** How should the dividend policy affect an assessment of possible shareholder returns?

**Prepared memo:** The prospectus does not expect dividends in the foreseeable future, but does not rule them out forever. The policy alone cannot establish total share return, which also depends on an unknown future share price.

**Projected source evidence:**

- `E-99CD51A6` — As of the prospectus, the company had never declared or paid cash dividends on its capital stock. Locator: Dividend Policy, p. 126; find: We have never declared or paid any cash dividends on our capital stock. [Original S-1](https://www.sec.gov/Archives/edgar/data/2130357/000162828026067168/anthropicpbc-sx1.htm).
- `E-55D5F747` — The company does not expect dividends in the foreseeable future; future declarations are at board discretion subject to applicable law and other factors. Locator: Dividend Policy, p. 126; find: do not expect to pay any dividends in the foreseeable future. [Original S-1](https://www.sec.gov/Archives/edgar/data/2130357/000162828026067168/anthropicpbc-sx1.htm).
- `E-CBD90C82` — H1 2026 operating cash flow was positive $3.929 billion and investing cash flow negative $17.181 billion. Locator: Consolidated Statements of Cash Flows, F-13; find: Net cash provided by (used in) operating activities. [Original S-1](https://www.sec.gov/Archives/edgar/data/2130357/000162828026067168/anthropicpbc-sx1.htm).

**Expected review:** Совет допустим в пределах данных: ближайшее ожидание не является бессрочным запретом; отсутствие ожидаемых дивидендов не устанавливает общую доходность. Не интерпретировать его как прогноз роста.

**Authority:** Candidate agent-authored interpretation; independent human review is pending.

**Reference DAG:** None claimed for this adapted control case.

## C-355345 — Credit amendment: increase versus covenant

**Class:** error. **Predecessor ID (reviewer only):** P01. **Two-step status:** exact_two_step_three_source_leaf_reference_DAG_checked_offline.

**Question:** How does the September 2026 increase in revolving commitments compare in dollars with the amended minimum-liquidity covenant?

**Prepared memo:** The increase in revolving commitments is smaller than the amended minimum-liquidity covenant. This numerical comparison alone does not determine cash available.

**Projected source evidence:**

- `E-766176DD` — Before the September 2026 amendment, revolving commitments were $3.3 billion. Locator: Note 17 Subsequent Events, F-65; September 2026 credit amendment; prior revolving commitments. [Original S-1](https://www.sec.gov/Archives/edgar/data/2130357/000162828026067168/anthropicpbc-sx1.htm).
- `E-217F182B` — The amendment raised revolving commitments to $15.0 billion. Locator: Note 17 Subsequent Events, F-65; September 2026 credit amendment; amended revolving commitments. [Original S-1](https://www.sec.gov/Archives/edgar/data/2130357/000162828026067168/anthropicpbc-sx1.htm).
- `E-6AF0ADF6` — The amended minimum-liquidity covenant is $5.0 billion. Locator: Note 17 Subsequent Events, F-65; September 2026 credit amendment; amended minimum-liquidity covenant. [Original S-1](https://www.sec.gov/Archives/edgar/data/2130357/000162828026067168/anthropicpbc-sx1.htm).

**Expected review:** The commitment increase exceeds the amended covenant level by $6.7bn in a numerical comparison. The memo reverses the ordering; neither figure alone establishes available cash.

**Authority:** Candidate agent-authored interpretation; independent human review is pending.

**Exact reference ancestry:**

- `a` ← `E-217F182B` = `15.0`. Original source atom: `to $15.0 billion`; period marker: `In September 2026`.
- `b` ← `E-766176DD` = `3.3`. Original source atom: `from $3.3 billion`; period marker: `In September 2026`.
- `c` ← `E-6AF0ADF6` = `5.0`. Original source atom: `to $5.0 billion`; period marker: `In September 2026`.
- `n1` = `subtract(a, b)` → `11.7`.
- `n2` = `subtract(n1, c)` → `6.7`.

**Why it matters:** The first subtraction yields the disclosed commitment increase; the second finds its dollar excess over the amended liquidity covenant. This compares figures, not spendable cash. The prepared memo is checked by `less_than(target, 0.0)`.

**Evidence deletion and hypothetical counterexample:**

- Removing `E-217F182B` from the model-visible projection makes the final target unbuildable. If only its numeric fact were hypothetically `7.0`, the memo classification would flip; this is not source evidence.
- Removing `E-766176DD` from the model-visible projection makes the final target unbuildable. If only its numeric fact were hypothetically `12.0`, the memo classification would flip; this is not source evidence.
- Removing `E-6AF0ADF6` from the model-visible projection makes the final target unbuildable. If only its numeric fact were hypothetically `13.0`, the memo classification would flip; this is not source evidence.

Removing `n1` blocks the second inference. Supplying a final number without both declared nodes is a false-positive derivation.

**Scope:** This is a lower bound only for the declared binary operation/evidence-projection grammar. One LLM call may perform both elementary operations. No actual SI model trace or semantic correctness is inferred.

## C-3ED506 — Class F voting fallback

**Class:** clean. **Predecessor ID (reviewer only):** P08. **Two-step status:** not claimed as necessary two-step.

**Question:** Under what conditions does the Class F voting fallback apply?

**Prepared memo:** For an applicable general matter, if a majority of Continuing Founders gives no instruction and the required Class A quorum is present, Class F votes track the Class A votes proportionally; this need not hold for special matters.

**Projected source evidence:**

- `E-92424CBE` — For specified general matters, absent a majority Continuing Founder instruction, Class F votes proportionally with Class A votes cast, subject to a quorum of a majority of outstanding Class A shares. Locator: Class F Common Stock Voting Mechanics; find: our Class F common stock will be voted proportionately with the votes of Class A common stock cast. [Original S-1](https://www.sec.gov/Archives/edgar/data/2130357/000162828026067168/anthropicpbc-sx1.htm).
- `E-BDADAA49` — Other matters carry distinct special voting thresholds. Locator: Class F Common Stock Voting Mechanics; find: If a proposal requires both a Supermajority and a Trust Amendment Supermajority. [Original S-1](https://www.sec.gov/Archives/edgar/data/2130357/000162828026067168/anthropicpbc-sx1.htm).
- `E-C56DEB2E` — The proposed board has seven authorized seats; the LTBT as Class T holder generally elects four, subject to described procedures. Locator: Board of Directors; find: seven authorized directors. [Original S-1](https://www.sec.gov/Archives/edgar/data/2130357/000162828026067168/anthropicpbc-sx1.htm).

**Expected review:** Совет верен для указанных условий. Нельзя переносить fallback на все специальные вопросы или опускать условие кворума.

**Authority:** Candidate agent-authored interpretation; independent human review is pending.

**Reference DAG:** None claimed for this adapted control case.

## C-6AE3F7 — Compute commitments

**Class:** error. **Predecessor ID (reviewer only):** P04. **Two-step status:** not claimed as necessary two-step.

**Question:** How should future compute payments under the disclosed agreements be interpreted?

**Prepared memo:** All future compute payments are already included in the $265.6 billion figure; payments under other agreements will be zero.

**Projected source evidence:**

- `E-73D0FC3C` — As of June 30, 2026, expected future fixed or minimum guaranteed commitments under specified agreements were approximately $265.6 billion. Locator: Note 13 Purchase Commitments, F-59; find: expected future fixed or minimum guaranteed commitments under these agreements were approximately $265.6 billion. [Original S-1](https://www.sec.gov/Archives/edgar/data/2130357/000162828026067168/anthropicpbc-sx1.htm).
- `E-C4E81143` — Other compute and infrastructure agreements have no fixed or minimum dollar commitment; their payments are not determinable and were excluded from the $265.6 billion amount, though expected to be significant. Locator: Note 13 Purchase Commitments, F-59; find: The Company does not include any estimated obligation for these agreements in the amount above. [Original S-1](https://www.sec.gov/Archives/edgar/data/2130357/000162828026067168/anthropicpbc-sx1.htm).
- `E-896A44DB` — H1 2026 revenue was $16.286 billion and compute/infrastructure expense $8.945 billion. Locator: Results of Operations, pp. 148–150; find: Compute and infrastructure 433 2,522 7,326 2,334 8,945. [Original S-1](https://www.sec.gov/Archives/edgar/data/2130357/000162828026067168/anthropicpbc-sx1.htm).

**Expected review:** Из суммы исключены договоры без фиксированного минимума. Исключение из оценки не означает нулевые расходы; величина оставшихся платежей неизвестна.

**Authority:** Candidate agent-authored interpretation; independent human review is pending.

**Reference DAG:** None claimed for this adapted control case.

## C-E698ED — Board seat arithmetic

**Class:** error. **Predecessor ID (reviewer only):** P03. **Two-step status:** exact_two_step_three_source_leaf_reference_DAG_checked_offline.

**Question:** Do the disclosed Class T and remaining Class F/A seat counts reconcile with the proposed total authorized board seats?

**Prepared memo:** The two seat allocations exceed the proposed total authorized seats; the disclosed counts do not reconcile. This refers to proposed authority, not currently occupied seats.

**Projected source evidence:**

- `E-78E21B3C` — After the offering, the board is proposed to have 7 authorized directors. Locator: Board of Directors; after-offering proposed total seats. [Original S-1](https://www.sec.gov/Archives/edgar/data/2130357/000162828026067168/anthropicpbc-sx1.htm).
- `E-704998D6` — The LTBT as Class T holder generally has authority to elect 4 Class T directors, subject to stated procedures. Locator: Board of Directors; after-offering Class T allocation. [Original S-1](https://www.sec.gov/Archives/edgar/data/2130357/000162828026067168/anthropicpbc-sx1.htm).
- `E-AA87C188` — Class F and Class A holders together elect and remove the remaining 3 directors. Locator: Board of Directors; after-offering remaining F/A allocation. [Original S-1](https://www.sec.gov/Archives/edgar/data/2130357/000162828026067168/anthropicpbc-sx1.htm).

**Expected review:** The proposed Class T and remaining F/A allocations sum to seven, matching seven authorized seats; the difference is zero, so the memo’s exceedance claim is false.

**Authority:** Candidate agent-authored interpretation; independent human review is pending.

**Exact reference ancestry:**

- `a` ← `E-704998D6` = `4`. Original source atom: `four Class T directors`; period marker: `Upon the completion of this offering`.
- `b` ← `E-AA87C188` = `3`. Original source atom: `remaining three directors`; period marker: `Upon the completion of this offering`.
- `c` ← `E-78E21B3C` = `7`. Original source atom: `seven authorized directors`; period marker: `Upon the completion of this offering`.
- `n1` = `add(a, b)` → `7`.
- `n2` = `subtract(n1, c)` → `0`.

**Why it matters:** First add the two proposed allocation counts; then subtract the disclosed authorized total. The result is zero, so the memo’s exceedance claim is false. This does not establish occupied seats. The prepared memo is checked by `greater_than(target, 0)`.

**Evidence deletion and hypothetical counterexample:**

- Removing `E-704998D6` from the model-visible projection makes the final target unbuildable. If only its numeric fact were hypothetically `5`, the memo classification would flip; this is not source evidence.
- Removing `E-AA87C188` from the model-visible projection makes the final target unbuildable. If only its numeric fact were hypothetically `4`, the memo classification would flip; this is not source evidence.
- Removing `E-78E21B3C` from the model-visible projection makes the final target unbuildable. If only its numeric fact were hypothetically `6`, the memo classification would flip; this is not source evidence.

Removing `n1` blocks the second inference. Supplying a final number without both declared nodes is a false-positive derivation.

**Scope:** This is a lower bound only for the declared binary operation/evidence-projection grammar. One LLM call may perform both elementary operations. No actual SI model trace or semantic correctness is inferred.

## C-D7DC65 — Investing cash-flow gap

**Class:** clean. **Predecessor ID (reviewer only):** P09. **Two-step status:** exact_two_step_three_source_leaf_reference_DAG_checked_offline.

**Question:** For H1 2026, what is the dollar gap between net purchases of short-term investments and net cash used in investing activities?

**Prepared memo:** The gap between net short-term investment purchases and total net investing cash used in H1 2026 is less than $1 billion; the gap cannot simply be assigned to property and equipment.

**Projected source evidence:**

- `E-4A4334C7` — H1 2026 purchases of short-term investments were $18.972 billion. Locator: Consolidated Statements of Cash Flows, F-13; 2026 six months ended June 30; purchases of short-term investments. [Original S-1](https://www.sec.gov/Archives/edgar/data/2130357/000162828026067168/anthropicpbc-sx1.htm).
- `E-7F25A9BE` — H1 2026 sales and maturities of short-term investments provided $2.610 billion. Locator: Consolidated Statements of Cash Flows, F-13; 2026 six months ended June 30; sales and maturities of short-term investments. [Original S-1](https://www.sec.gov/Archives/edgar/data/2130357/000162828026067168/anthropicpbc-sx1.htm).
- `E-8383474E` — H1 2026 net cash used in investing activities was $17.181 billion. Locator: Consolidated Statements of Cash Flows, F-13; 2026 six months ended June 30; net cash used in investing activities. [Original S-1](https://www.sec.gov/Archives/edgar/data/2130357/000162828026067168/anthropicpbc-sx1.htm).

**Expected review:** Net short-term investment purchases are $16.362bn and the gap to $17.181bn net investing cash used is $0.819bn. The gap cannot be assigned to one line without the rest of the cash-flow statement.

**Authority:** Candidate agent-authored interpretation; independent human review is pending.

**Exact reference ancestry:**

- `a` ← `E-4A4334C7` = `18.972`. Original source atom: `(18,972)`; period marker: `Six Months Ended June 30, 2023 2024 2025 2025 2026 (unaudited)`.
- `b` ← `E-7F25A9BE` = `2.61`. Original source atom: `2,610`; period marker: `Six Months Ended June 30, 2023 2024 2025 2025 2026 (unaudited)`.
- `c` ← `E-8383474E` = `17.181`. Original source atom: `(17,181)`; period marker: `Six Months Ended June 30, 2023 2024 2025 2025 2026 (unaudited)`.
- `n1` = `subtract(a, b)` → `16.362`.
- `n2` = `subtract(c, n1)` → `0.819`.

**Why it matters:** The first step nets investment purchases against sale/maturity proceeds; the second finds the magnitude gap to total investing cash used. It does not allocate that gap to a specific line. The prepared memo is checked by `less_than(target, 1.0)`.

**Evidence deletion and hypothetical counterexample:**

- Removing `E-4A4334C7` from the model-visible projection makes the final target unbuildable. If only its numeric fact were hypothetically `17.972`, the memo classification would flip; this is not source evidence.
- Removing `E-7F25A9BE` from the model-visible projection makes the final target unbuildable. If only its numeric fact were hypothetically `3.61`, the memo classification would flip; this is not source evidence.
- Removing `E-8383474E` from the model-visible projection makes the final target unbuildable. If only its numeric fact were hypothetically `18.181`, the memo classification would flip; this is not source evidence.

Removing `n1` blocks the second inference. Supplying a final number without both declared nodes is a false-positive derivation.

**Scope:** This is a lower bound only for the declared binary operation/evidence-projection grammar. One LLM call may perform both elementary operations. No actual SI model trace or semantic correctness is inferred.

## C-63BC31 — RSU versus other equity awards

**Class:** error. **Predecessor ID (reviewer only):** P02. **Two-step status:** exact_two_step_three_source_leaf_reference_DAG_checked_offline.

**Question:** In the June 30, 2026 hypothetical offering illustration, what is the ratio of the combined RSU expense amount to the separate unrecognized other-award amount?

**Prepared memo:** The combined illustrative RSU amount was less than eight times the separately disclosed other-award amount. The amounts have different recognition timing.

**Projected source evidence:**

- `E-EB1FF671` — If the offering had completed on June 30, 2026, $2.9 billion cumulative RSU expense would have been recorded on that date. Locator: Risk Factors, p. 65; June 30 hypothetical offering; cumulative RSU expense. [Original S-1](https://www.sec.gov/Archives/edgar/data/2130357/000162828026067168/anthropicpbc-sx1.htm).
- `E-9789E114` — In the June 30, 2026 hypothetical offering illustration, an additional $23.7 billion RSU expense would be recognized later. Locator: Risk Factors, p. 65; June 30 hypothetical offering; later RSU expense. [Original S-1](https://www.sec.gov/Archives/edgar/data/2130357/000162828026067168/anthropicpbc-sx1.htm).
- `E-0EE2F3DD` — As of June 30, 2026, about $3.1 billion unrecognized stock-based compensation expense related to other outstanding equity awards was disclosed separately. Locator: Risk Factors, p. 65; June 30 disclosed other-award expense. [Original S-1](https://www.sec.gov/Archives/edgar/data/2130357/000162828026067168/anthropicpbc-sx1.htm).

**Expected review:** The two illustrative RSU components total $26.6bn. Relative to the separately disclosed $3.1bn other-award figure, that is about 8.58 times, not less than eight times; recognition timing differs.

**Authority:** Candidate agent-authored interpretation; independent human review is pending.

**Exact reference ancestry:**

- `a` ← `E-EB1FF671` = `2.9`. Original source atom: `$2.9 billion of cumulative stock-based compensation expense`; period marker: `June 30, 2026`.
- `b` ← `E-9789E114` = `23.7`. Original source atom: `$23.7 billion of unrecognized stock-based compensation expense`; period marker: `June 30, 2026`.
- `c` ← `E-0EE2F3DD` = `3.1`. Original source atom: `approximately $3.1 billion related to other outstanding equity awards`; period marker: `June 30, 2026`.
- `n1` = `add(a, b)` → `26.6`.
- `n2` = `divide(n1, c)` → `8.580645161290322`.

**Why it matters:** The first step totals the two illustrated RSU components; the second divides by the separate other-award figure. The ratio is a comparison of disclosed nominal amounts, not equal recognition periods. The prepared memo is checked by `less_than(target, 8.0)`.

**Evidence deletion and hypothetical counterexample:**

- Removing `E-EB1FF671` from the model-visible projection makes the final target unbuildable. If only its numeric fact were hypothetically `0.9`, the memo classification would flip; this is not source evidence.
- Removing `E-9789E114` from the model-visible projection makes the final target unbuildable. If only its numeric fact were hypothetically `21.7`, the memo classification would flip; this is not source evidence.
- Removing `E-0EE2F3DD` from the model-visible projection makes the final target unbuildable. If only its numeric fact were hypothetically `3.5`, the memo classification would flip; this is not source evidence.

Removing `n1` blocks the second inference. Supplying a final number without both declared nodes is a false-positive derivation.

**Scope:** This is a lower bound only for the declared binary operation/evidence-projection grammar. One LLM call may perform both elementary operations. No actual SI model trace or semantic correctness is inferred.

## C-D6998A — Revenue after two expense categories

**Class:** clean. **Predecessor ID (reviewer only):** P10. **Two-step status:** exact_two_step_three_source_leaf_reference_DAG_checked_offline.

**Question:** For H1 2026, how much revenue remains after compute/infrastructure and personnel expenses, before other operating expenses?

**Prepared memo:** More than $4 billion remains after compute/infrastructure and personnel expenses, before other operating expenses. That remainder is not operating profit.

**Projected source evidence:**

- `E-7CEAD064` — H1 2026 revenue was $16.286 billion. Locator: Results of Operations, p. 148; 2026 six months ended June 30; revenue. [Original S-1](https://www.sec.gov/Archives/edgar/data/2130357/000162828026067168/anthropicpbc-sx1.htm).
- `E-3488BC71` — H1 2026 compute/infrastructure expense was $8.945 billion. Locator: Results of Operations, p. 148; 2026 six months ended June 30; compute and infrastructure expense. [Original S-1](https://www.sec.gov/Archives/edgar/data/2130357/000162828026067168/anthropicpbc-sx1.htm).
- `E-DB13187E` — H1 2026 personnel expense was $3.152 billion. Locator: Results of Operations, p. 148; 2026 six months ended June 30; personnel expense. [Original S-1](https://www.sec.gov/Archives/edgar/data/2130357/000162828026067168/anthropicpbc-sx1.htm).

**Expected review:** $16.286bn less $8.945bn less $3.152bn is $4.189bn before other expenses, not operating profit.

**Authority:** Candidate agent-authored interpretation; independent human review is pending.

**Exact reference ancestry:**

- `a` ← `E-7CEAD064` = `16.286`. Original source atom: `16,286`; period marker: `Six Months Ended June 30, (in millions) 2023 2024 2025 2025 2026`.
- `b` ← `E-3488BC71` = `8.945`. Original source atom: `8,945`; period marker: `Six Months Ended June 30, (in millions) 2023 2024 2025 2025 2026`.
- `c` ← `E-DB13187E` = `3.152`. Original source atom: `3,152`; period marker: `Six Months Ended June 30, (in millions) 2023 2024 2025 2025 2026`.
- `n1` = `subtract(a, b)` → `7.341`.
- `n2` = `subtract(n1, c)` → `4.189`.

**Why it matters:** This is the remainder after only two expense categories. Other expenses make it distinct from operating profit. The prepared memo is checked by `greater_than(target, 4.0)`.

**Evidence deletion and hypothetical counterexample:**

- Removing `E-7CEAD064` from the model-visible projection makes the final target unbuildable. If only its numeric fact were hypothetically `15.286`, the memo classification would flip; this is not source evidence.
- Removing `E-3488BC71` from the model-visible projection makes the final target unbuildable. If only its numeric fact were hypothetically `9.945`, the memo classification would flip; this is not source evidence.
- Removing `E-DB13187E` from the model-visible projection makes the final target unbuildable. If only its numeric fact were hypothetically `4.152`, the memo classification would flip; this is not source evidence.

Removing `n1` blocks the second inference. Supplying a final number without both declared nodes is a false-positive derivation.

**Scope:** This is a lower bound only for the declared binary operation/evidence-projection grammar. One LLM call may perform both elementary operations. No actual SI model trace or semantic correctness is inferred.

## Required review before a pilot

1. Independent human source review: inspect the exact local S-1 excerpt, original period, arithmetic, translation, nuance, and whether each intended error is material; sign review bytes and record disagreements.
2. Verify participant-side projection and staged display of prepared memo. Neither `reviewer-key.json` nor this document may be given to the participant or models.
3. Freeze a successor packet, exposure registry, randomized A/B/C assignment, and exact runtime/prompts before any model operation. A same-folder hash is not an external seal.
4. Treat prior S-1 and draft exposure as development exposure. Do not claim a blind holdout for the same viewer.
5. The previous controller review reported five completed C branches stopping after one step and one Selection schema failure. This v3 graph challenge does not fix or validate runtime behavior.
