# Reviewer-only v4 cases and keys — reveals answers

**Do not put this file or `reviewer-key.json` in participant or model inputs.** Candidate agent-authored review only; no independent human attestation, model run, or pilot outcome.

Local original S-1 SHA-256: `2fa24ae7704dbb535d096ee7459b765fe899ac9118762e738183a94473c9905a`. All quoted source cells/phrases below are bound to a period in that local snapshot. Participant evidence is an English paraphrase.

## Exact bounded reference contract

Step 1 selects two separate primary S-1 IDs and performs one binary arithmetic operation. Step 2 selects `node:0001` and the actual unverified `case_id-ADVICE` ID from `make_task`, then performs one binary numerical comparison to yield a boolean memo-support verdict. These selected ID pairs fit `max_depth=2`, `beam_width=1`, and `max_selected_premises=2` as a reference trace. No live SI trace has been observed for these cases. A single LLM call can still do multiple elementary operations.

Source-deletion tests remove the actual model-visible ID; memo-deletion tests remove the actual `-ADVICE` ID. Changed-value witnesses modify only one projected source text or the memo threshold in a hypothetical test world and reverse the expected verdict. They are not corrections to the original S-1. Intermediate and final values are checked against the visible question, source, locator, and memo text.

## C-DC1D56 — RSU vesting conditions

**Class:** clean. **Predecessor mapping (reviewer only):** P12.

**Question:** Does registration effectiveness alone guarantee immediate full vesting of the disclosed RSU grants?

**Unverified prepared memo:** Effectiveness satisfies the performance condition, but does not replace the separate service condition; effectiveness alone does not guarantee immediate full vesting of every grant.

**Participant-side source evidence:**

- `E-743176CE`: The described RSUs have both service-based and performance-based vesting conditions. Locator: Note 17 Subsequent Events, F-65; find: The RSUs are subject to both service-based and performance-based vesting conditions. [Original S-1](https://www.sec.gov/Archives/edgar/data/2130357/000162828026067168/anthropicpbc-sx1.htm).
- `E-3F0C147A`: Registration effectiveness satisfies the performance condition; the service condition generally runs quarterly over four years, with a new-hire cliff and continuous-service requirement. Locator: Note 17 Subsequent Events, F-65; find: The performance-based vesting condition of the RSUs will be satisfied upon the effectiveness. [Original S-1](https://www.sec.gov/Archives/edgar/data/2130357/000162828026067168/anthropicpbc-sx1.htm).
- `E-D102983D`: The S-1 also describes a separate hypothetical June 30, 2026 offering-completion scenario with $2.9 billion cumulative RSU expense. Locator: Risk Factors, p. 65; find: If this offering had been completed on June 30, 2026. [Original S-1](https://www.sec.gov/Archives/edgar/data/2130357/000162828026067168/anthropicpbc-sx1.htm).

**Expected review (candidate):** Оба условия применяются совместно; одного события effectiveness недостаточно для гарантии полного vesting всех грантов. Некоторые service-порции могут уже быть выполнены; никаких фактических продаж из этого не следует.

**Authority:** Source and semantic status need independent human review.

**Reference trace:** None claimed; this adapted control case does not establish necessary two-step behavior.

## C-F75743 — Two current-asset balances

**Class:** clean. **Predecessor mapping (reviewer only):** P11.

**Question:** What is the combined H1 2026 balance-sheet amount of short-term investments and net accounts receivable?

**Unverified prepared memo:** Short-term investments and net accounts receivable together exceeded $25 billion at June 30, 2026. This is not a claim that both lines are immediately spendable.

**Participant-side source evidence:**

- `E-80FE3ED0`: Short-term investments at June 30, 2026 were $19.262 billion. Locator: Consolidated Balance Sheets, F-6; June 30 2026 column; short-term investments. [Original S-1](https://www.sec.gov/Archives/edgar/data/2130357/000162828026067168/anthropicpbc-sx1.htm).
- `E-2CBAD120`: Net accounts receivable at June 30, 2026 were $5.833 billion. Locator: Consolidated Balance Sheets, F-6; June 30 2026 column; accounts receivable, net. [Original S-1](https://www.sec.gov/Archives/edgar/data/2130357/000162828026067168/anthropicpbc-sx1.htm).

**Expected review (candidate):** The arithmetic source subtotal is 25.095 billion; the memo threshold comparison is supported. This is a candidate reviewer interpretation, not human-adjudicated.

**Authority:** Source and semantic status need independent human review.

**Reference trace:**

- Primary `E-80FE3ED0` = `19.262`; source atom `19,262` within `As of December 31, As of June 30, 2024 2025 2026 (unaudited)`.
- Primary `E-2CBAD120` = `5.833`; source atom `5,833` within `As of December 31, As of June 30, 2024 2025 2026 (unaudited)`.
- Unverified memo `C-F75743-ADVICE` = threshold `25.0`; exact adapter text prefix: `Simulated advisory claim, unverified:`.
- `node:0001` = `add(E-80FE3ED0, E-2CBAD120)` → `25.095`.
- `node:0002` = `greater_than(node:0001, C-F75743-ADVICE)` → `True`.

**Semantic use:** Add two distinct current-asset balance-sheet lines at June 30; then test the unverified memo threshold. Accounting value is not free cash.

**Critical removals and counterexamples:**

- Delete `E-80FE3ED0` from the model-visible task: `node:0001` and the verdict become unbuildable. Replace only that source amount with `18.262` in a hypothetical input: the verdict reverses.
- Delete `E-2CBAD120` from the model-visible task: `node:0001` and the verdict become unbuildable. Replace only that source amount with `4.833` in a hypothetical input: the verdict reverses.
- Delete `C-F75743-ADVICE`: the arithmetic node remains, but the verdict becomes unbuildable. Change only the memo threshold to `26.0`: the verdict reverses.

- Delete `node:0001`: the comparison cannot execute; a supplied final boolean without both declared nodes is rejected as an unsupported derivation.

**Limit:** This establishes a bounded two-inference reference trace under the actual adapter ID projection, not that one LLM call cannot do both operations or that the runtime will select or semantically validate this trace.

## C-BF6785 — Infrastructure financing notes

**Class:** error. **Predecessor mapping (reviewer only):** P05.

**Question:** How should the disclosed infrastructure financing instrument be interpreted?

**Unverified prepared memo:** As of June 30, the company already held $42 billion of unrestricted cash available for any expense.

**Participant-side source evidence:**

- `E-F77F3878`: A March 2026 agreement permits, subject to conditions, up to $42.0 billion of convertible notes solely to finance rent obligations under a compute/infrastructure agreement. Locator: Note 9 Other Note Purchase Agreements 2026, F-43; find: up to $42.0 billion of convertible promissory notes solely to finance rent obligations. [Original S-1](https://www.sec.gov/Archives/edgar/data/2130357/000162828026067168/anthropicpbc-sx1.htm).
- `E-2B8C8F63`: As of June 30, 2026, the draw period had not yet begun and no amount was outstanding under that agreement. Locator: Note 9 Other Note Purchase Agreements 2026, F-43; find: As of June 30, 2026 , no amounts were outstanding under the note purchase agreement. [Original S-1](https://www.sec.gov/Archives/edgar/data/2130357/000162828026067168/anthropicpbc-sx1.htm).
- `E-6FF4FA8D`: In September 2026, revolving commitments increased from $3.3 billion to $15.0 billion. Locator: Note 17 Subsequent Events, F-65; find: increasing the revolving commitments from $3.3 billion to $15.0 billion. [Original S-1](https://www.sec.gov/Archives/edgar/data/2130357/000162828026067168/anthropicpbc-sx1.htm).

**Expected review (candidate):** Это условная возможность финансирования целевого назначения, а не уже имеющиеся свободные деньги; на дату по конкретному соглашению нот не было.

**Authority:** Source and semantic status need independent human review.

**Reference trace:** None claimed; this adapted control case does not establish necessary two-step behavior.

## C-86837B — Customer concentration across periods

**Class:** error. **Predecessor mapping (reviewer only):** P06.

**Question:** What does the disclosed nine-month customer concentration establish about Q3?

**Unverified prepared memo:** Because no individual customer exceeded 10% of nine-month revenue, no individual customer exceeded 10% in Q3.

**Participant-side source evidence:**

- `E-3DEF1799`: No individual customer exceeded 10% of revenue for the nine months ended September 30, 2026. Locator: Customer Base, p. 144; find: No single customer represented more than 10% of our revenue for the nine months ended September 30, 2026. [Original S-1](https://www.sec.gov/Archives/edgar/data/2130357/000162828026067168/anthropicpbc-sx1.htm).
- `E-4FAD6A0C`: Approximately 79% of Q3 2026 revenue came from customers outside the top five. Locator: Customer Base, p. 144; find: Approximately 79% of our revenue came from customers outside of our top five customers. [Original S-1](https://www.sec.gov/Archives/edgar/data/2130357/000162828026067168/anthropicpbc-sx1.htm).
- `E-07055694`: Approximately 64% of Q1 2026 revenue came from customers outside the top five. Locator: Customer Base, p. 144; find: approximately 64% for the three months ended March 31, 2026. [Original S-1](https://www.sec.gov/Archives/edgar/data/2130357/000162828026067168/anthropicpbc-sx1.htm).

**Expected review (candidate):** The nine-month threshold does not establish the same threshold separately for Q3. The Q3 claim is unsupported by this evidence, not proven historically false.

**Authority:** Source and semantic status need independent human review.

**Reference trace:** None claimed; this adapted control case does not establish necessary two-step behavior.

## C-F015DA — Dividend policy

**Class:** clean. **Predecessor mapping (reviewer only):** P07.

**Question:** How should the dividend policy affect an assessment of possible shareholder returns?

**Unverified prepared memo:** The prospectus does not expect dividends in the foreseeable future, but does not rule them out forever. The policy alone cannot establish total share return, which also depends on an unknown future share price.

**Participant-side source evidence:**

- `E-99CD51A6`: As of the prospectus, the company had never declared or paid cash dividends on its capital stock. Locator: Dividend Policy, p. 126; find: We have never declared or paid any cash dividends on our capital stock. [Original S-1](https://www.sec.gov/Archives/edgar/data/2130357/000162828026067168/anthropicpbc-sx1.htm).
- `E-55D5F747`: The company does not expect dividends in the foreseeable future; future declarations are at board discretion subject to applicable law and other factors. Locator: Dividend Policy, p. 126; find: do not expect to pay any dividends in the foreseeable future. [Original S-1](https://www.sec.gov/Archives/edgar/data/2130357/000162828026067168/anthropicpbc-sx1.htm).
- `E-CBD90C82`: H1 2026 operating cash flow was positive $3.929 billion and investing cash flow negative $17.181 billion. Locator: Consolidated Statements of Cash Flows, F-13; find: Net cash provided by (used in) operating activities. [Original S-1](https://www.sec.gov/Archives/edgar/data/2130357/000162828026067168/anthropicpbc-sx1.htm).

**Expected review (candidate):** Совет допустим в пределах данных: ближайшее ожидание не является бессрочным запретом; отсутствие ожидаемых дивидендов не устанавливает общую доходность. Не интерпретировать его как прогноз роста.

**Authority:** Source and semantic status need independent human review.

**Reference trace:** None claimed; this adapted control case does not establish necessary two-step behavior.

## C-355345 — Credit amendment: increase versus covenant

**Class:** error. **Predecessor mapping (reviewer only):** P01.

**Question:** How much did the September 2026 amendment increase revolving commitments?

**Unverified prepared memo:** The increase in revolving commitments was less than $10 billion. This numerical comparison does not establish available cash.

**Participant-side source evidence:**

- `E-766176DD`: Before the September 2026 amendment, revolving commitments were $3.3 billion. Locator: Note 17 Subsequent Events, F-65; September 2026 credit amendment; prior revolving commitments. [Original S-1](https://www.sec.gov/Archives/edgar/data/2130357/000162828026067168/anthropicpbc-sx1.htm).
- `E-217F182B`: The amendment raised revolving commitments to $15.0 billion. Locator: Note 17 Subsequent Events, F-65; September 2026 credit amendment; amended revolving commitments. [Original S-1](https://www.sec.gov/Archives/edgar/data/2130357/000162828026067168/anthropicpbc-sx1.htm).

**Expected review (candidate):** The arithmetic source subtotal is 11.7 billion; the memo threshold comparison is false. This is a candidate reviewer interpretation, not human-adjudicated.

**Authority:** Source and semantic status need independent human review.

**Reference trace:**

- Primary `E-766176DD` = `3.3`; source atom `from $3.3 billion` within `In September 2026`.
- Primary `E-217F182B` = `15.0`; source atom `to $15.0 billion` within `In September 2026`.
- Unverified memo `C-355345-ADVICE` = threshold `10.0`; exact adapter text prefix: `Simulated advisory claim, unverified:`.
- `node:0001` = `subtract(E-217F182B, E-766176DD)` → `11.7`.
- `node:0002` = `less_than(node:0001, C-355345-ADVICE)` → `False`.

**Semantic use:** Subtract the earlier commitment from the amended commitment; then test the unverified memo threshold. No liquidity balance is inferred.

**Critical removals and counterexamples:**

- Delete `E-766176DD` from the model-visible task: `node:0001` and the verdict become unbuildable. Replace only that source amount with `6.0` in a hypothetical input: the verdict reverses.
- Delete `E-217F182B` from the model-visible task: `node:0001` and the verdict become unbuildable. Replace only that source amount with `12.0` in a hypothetical input: the verdict reverses.
- Delete `C-355345-ADVICE`: the arithmetic node remains, but the verdict becomes unbuildable. Change only the memo threshold to `12.0`: the verdict reverses.

- Delete `node:0001`: the comparison cannot execute; a supplied final boolean without both declared nodes is rejected as an unsupported derivation.

**Limit:** This establishes a bounded two-inference reference trace under the actual adapter ID projection, not that one LLM call cannot do both operations or that the runtime will select or semantically validate this trace.

## C-3ED506 — Class F voting fallback

**Class:** clean. **Predecessor mapping (reviewer only):** P08.

**Question:** Under what conditions does the Class F voting fallback apply?

**Unverified prepared memo:** For an applicable general matter, if a majority of Continuing Founders gives no instruction and the required Class A quorum is present, Class F votes track the Class A votes proportionally; this need not hold for special matters.

**Participant-side source evidence:**

- `E-92424CBE`: For specified general matters, absent a majority Continuing Founder instruction, Class F votes proportionally with Class A votes cast, subject to a quorum of a majority of outstanding Class A shares. Locator: Class F Common Stock Voting Mechanics; find: our Class F common stock will be voted proportionately with the votes of Class A common stock cast. [Original S-1](https://www.sec.gov/Archives/edgar/data/2130357/000162828026067168/anthropicpbc-sx1.htm).
- `E-BDADAA49`: Other matters carry distinct special voting thresholds. Locator: Class F Common Stock Voting Mechanics; find: If a proposal requires both a Supermajority and a Trust Amendment Supermajority. [Original S-1](https://www.sec.gov/Archives/edgar/data/2130357/000162828026067168/anthropicpbc-sx1.htm).
- `E-C56DEB2E`: The proposed board has seven authorized seats; the LTBT as Class T holder generally elects four, subject to described procedures. Locator: Board of Directors; find: seven authorized directors. [Original S-1](https://www.sec.gov/Archives/edgar/data/2130357/000162828026067168/anthropicpbc-sx1.htm).

**Expected review (candidate):** Совет верен для указанных условий. Нельзя переносить fallback на все специальные вопросы или опускать условие кворума.

**Authority:** Source and semantic status need independent human review.

**Reference trace:** None claimed; this adapted control case does not establish necessary two-step behavior.

## C-6AE3F7 — Compute commitments

**Class:** error. **Predecessor mapping (reviewer only):** P04.

**Question:** How should future compute payments under the disclosed agreements be interpreted?

**Unverified prepared memo:** All future compute payments are already included in the $265.6 billion figure; payments under other agreements will be zero.

**Participant-side source evidence:**

- `E-73D0FC3C`: As of June 30, 2026, expected future fixed or minimum guaranteed commitments under specified agreements were approximately $265.6 billion. Locator: Note 13 Purchase Commitments, F-59; find: expected future fixed or minimum guaranteed commitments under these agreements were approximately $265.6 billion. [Original S-1](https://www.sec.gov/Archives/edgar/data/2130357/000162828026067168/anthropicpbc-sx1.htm).
- `E-C4E81143`: Other compute and infrastructure agreements have no fixed or minimum dollar commitment; their payments are not determinable and were excluded from the $265.6 billion amount, though expected to be significant. Locator: Note 13 Purchase Commitments, F-59; find: The Company does not include any estimated obligation for these agreements in the amount above. [Original S-1](https://www.sec.gov/Archives/edgar/data/2130357/000162828026067168/anthropicpbc-sx1.htm).
- `E-896A44DB`: H1 2026 revenue was $16.286 billion and compute/infrastructure expense $8.945 billion. Locator: Results of Operations, pp. 148–150; find: Compute and infrastructure 433 2,522 7,326 2,334 8,945. [Original S-1](https://www.sec.gov/Archives/edgar/data/2130357/000162828026067168/anthropicpbc-sx1.htm).

**Expected review (candidate):** Из суммы исключены договоры без фиксированного минимума. Исключение из оценки не означает нулевые расходы; величина оставшихся платежей неизвестна.

**Authority:** Source and semantic status need independent human review.

**Reference trace:** None claimed; this adapted control case does not establish necessary two-step behavior.

## C-E698ED — Operating expense remainder

**Class:** error. **Predecessor mapping (reviewer only):** P03.

**Question:** What is the combined H1 2026 expense in the sales/marketing/partnerships and other operating/administrative categories?

**Unverified prepared memo:** The two named H1 operating-expense categories together exceed $5 billion. This is not a measure of total operating expense.

**Participant-side source evidence:**

- `E-78E21B3C`: H1 2026 sales, marketing, and partnerships expense was $3.168 billion. Locator: Results of Operations, p. 148; 2026 six months ended June 30; sales/marketing/partnerships expense. [Original S-1](https://www.sec.gov/Archives/edgar/data/2130357/000162828026067168/anthropicpbc-sx1.htm).
- `E-704998D6`: H1 2026 other operating and administrative expense was $1.714 billion. Locator: Results of Operations, p. 148; 2026 six months ended June 30; other operating and administrative expense. [Original S-1](https://www.sec.gov/Archives/edgar/data/2130357/000162828026067168/anthropicpbc-sx1.htm).

**Expected review (candidate):** The arithmetic source subtotal is 4.882 billion; the memo threshold comparison is false. This is a candidate reviewer interpretation, not human-adjudicated.

**Authority:** Source and semantic status need independent human review.

**Reference trace:**

- Primary `E-78E21B3C` = `3.168`; source atom `3,168` within `Six Months Ended June 30, (in millions) 2023 2024 2025 2025 2026`.
- Primary `E-704998D6` = `1.714`; source atom `1,714` within `Six Months Ended June 30, (in millions) 2023 2024 2025 2025 2026`.
- Unverified memo `C-E698ED-ADVICE` = threshold `5.0`; exact adapter text prefix: `Simulated advisory claim, unverified:`.
- `node:0001` = `add(E-78E21B3C, E-704998D6)` → `4.882`.
- `node:0002` = `greater_than(node:0001, C-E698ED-ADVICE)` → `False`.

**Semantic use:** Add two distinct operating-expense rows of the same H1 period; then test the unverified memo threshold. The computed subtotal does not equal total expenses.

**Critical removals and counterexamples:**

- Delete `E-78E21B3C` from the model-visible task: `node:0001` and the verdict become unbuildable. Replace only that source amount with `3.468` in a hypothetical input: the verdict reverses.
- Delete `E-704998D6` from the model-visible task: `node:0001` and the verdict become unbuildable. Replace only that source amount with `2.014` in a hypothetical input: the verdict reverses.
- Delete `C-E698ED-ADVICE`: the arithmetic node remains, but the verdict becomes unbuildable. Change only the memo threshold to `4.5`: the verdict reverses.

- Delete `node:0001`: the comparison cannot execute; a supplied final boolean without both declared nodes is rejected as an unsupported derivation.

**Limit:** This establishes a bounded two-inference reference trace under the actual adapter ID projection, not that one LLM call cannot do both operations or that the runtime will select or semantically validate this trace.

## C-D7DC65 — Investing cash-flow gap

**Class:** clean. **Predecessor mapping (reviewer only):** P09.

**Question:** What were net purchases of short-term investments in H1 2026?

**Unverified prepared memo:** Net purchases of short-term investments were less than $17 billion in H1 2026. This does not allocate the rest of investing cash flow.

**Participant-side source evidence:**

- `E-4A4334C7`: H1 2026 purchases of short-term investments were $18.972 billion. Locator: Consolidated Statements of Cash Flows, F-13; 2026 six months ended June 30; purchases of short-term investments. [Original S-1](https://www.sec.gov/Archives/edgar/data/2130357/000162828026067168/anthropicpbc-sx1.htm).
- `E-7F25A9BE`: H1 2026 sales and maturities of short-term investments provided $2.610 billion. Locator: Consolidated Statements of Cash Flows, F-13; 2026 six months ended June 30; sales and maturities of short-term investments. [Original S-1](https://www.sec.gov/Archives/edgar/data/2130357/000162828026067168/anthropicpbc-sx1.htm).

**Expected review (candidate):** The arithmetic source subtotal is 16.362 billion; the memo threshold comparison is supported. This is a candidate reviewer interpretation, not human-adjudicated.

**Authority:** Source and semantic status need independent human review.

**Reference trace:**

- Primary `E-4A4334C7` = `18.972`; source atom `(18,972)` within `Six Months Ended June 30, 2023 2024 2025 2025 2026 (unaudited)`.
- Primary `E-7F25A9BE` = `2.61`; source atom `2,610` within `Six Months Ended June 30, 2023 2024 2025 2025 2026 (unaudited)`.
- Unverified memo `C-D7DC65-ADVICE` = threshold `17.0`; exact adapter text prefix: `Simulated advisory claim, unverified:`.
- `node:0001` = `subtract(E-4A4334C7, E-7F25A9BE)` → `16.362`.
- `node:0002` = `less_than(node:0001, C-D7DC65-ADVICE)` → `True`.

**Semantic use:** Subtract sale/maturity proceeds from purchases in the H1 cash-flow table; then test the unverified memo threshold. Do not equate this net amount with capex.

**Critical removals and counterexamples:**

- Delete `E-4A4334C7` from the model-visible task: `node:0001` and the verdict become unbuildable. Replace only that source amount with `19.972` in a hypothetical input: the verdict reverses.
- Delete `E-7F25A9BE` from the model-visible task: `node:0001` and the verdict become unbuildable. Replace only that source amount with `1.61` in a hypothetical input: the verdict reverses.
- Delete `C-D7DC65-ADVICE`: the arithmetic node remains, but the verdict becomes unbuildable. Change only the memo threshold to `16.0`: the verdict reverses.

- Delete `node:0001`: the comparison cannot execute; a supplied final boolean without both declared nodes is rejected as an unsupported derivation.

**Limit:** This establishes a bounded two-inference reference trace under the actual adapter ID projection, not that one LLM call cannot do both operations or that the runtime will select or semantically validate this trace.

## C-63BC31 — RSU versus other equity awards

**Class:** error. **Predecessor mapping (reviewer only):** P02.

**Question:** What combined RSU amount does the June 30, 2026 hypothetical offering illustration describe?

**Unverified prepared memo:** The two illustrated RSU expense components total less than $25 billion. They have different recognition timing.

**Participant-side source evidence:**

- `E-EB1FF671`: If the offering had completed on June 30, 2026, $2.9 billion cumulative RSU expense would have been recorded on that date. Locator: Risk Factors, p. 65; June 30 hypothetical offering; cumulative RSU expense. [Original S-1](https://www.sec.gov/Archives/edgar/data/2130357/000162828026067168/anthropicpbc-sx1.htm).
- `E-9789E114`: In the June 30, 2026 hypothetical offering illustration, an additional $23.7 billion RSU expense would be recognized later. Locator: Risk Factors, p. 65; June 30 hypothetical offering; later RSU expense. [Original S-1](https://www.sec.gov/Archives/edgar/data/2130357/000162828026067168/anthropicpbc-sx1.htm).

**Expected review (candidate):** The arithmetic source subtotal is 26.6 billion; the memo threshold comparison is false. This is a candidate reviewer interpretation, not human-adjudicated.

**Authority:** Source and semantic status need independent human review.

**Reference trace:**

- Primary `E-EB1FF671` = `2.9`; source atom `$2.9 billion of cumulative stock-based compensation expense` within `June 30, 2026`.
- Primary `E-9789E114` = `23.7`; source atom `$23.7 billion of unrecognized stock-based compensation expense` within `June 30, 2026`.
- Unverified memo `C-63BC31-ADVICE` = threshold `25.0`; exact adapter text prefix: `Simulated advisory claim, unverified:`.
- `node:0001` = `add(E-EB1FF671, E-9789E114)` → `26.6`.
- `node:0002` = `less_than(node:0001, C-63BC31-ADVICE)` → `False`.

**Semantic use:** Add only the two RSU components in the stated hypothetical; then compare their combined nominal amount with the unverified memo threshold. This is not one-period expense.

**Critical removals and counterexamples:**

- Delete `E-EB1FF671` from the model-visible task: `node:0001` and the verdict become unbuildable. Replace only that source amount with `0.9` in a hypothetical input: the verdict reverses.
- Delete `E-9789E114` from the model-visible task: `node:0001` and the verdict become unbuildable. Replace only that source amount with `21.7` in a hypothetical input: the verdict reverses.
- Delete `C-63BC31-ADVICE`: the arithmetic node remains, but the verdict becomes unbuildable. Change only the memo threshold to `28.0`: the verdict reverses.

- Delete `node:0001`: the comparison cannot execute; a supplied final boolean without both declared nodes is rejected as an unsupported derivation.

**Limit:** This establishes a bounded two-inference reference trace under the actual adapter ID projection, not that one LLM call cannot do both operations or that the runtime will select or semantically validate this trace.

## C-D6998A — Revenue after two expense categories

**Class:** clean. **Predecessor mapping (reviewer only):** P10.

**Question:** How much H1 2026 revenue remained after compute/infrastructure expense, before other expenses?

**Unverified prepared memo:** More than $7 billion of H1 revenue remained after compute/infrastructure expense, before other expenses. This is not operating profit.

**Participant-side source evidence:**

- `E-7CEAD064`: H1 2026 revenue was $16.286 billion. Locator: Results of Operations, p. 148; 2026 six months ended June 30; revenue. [Original S-1](https://www.sec.gov/Archives/edgar/data/2130357/000162828026067168/anthropicpbc-sx1.htm).
- `E-3488BC71`: H1 2026 compute/infrastructure expense was $8.945 billion. Locator: Results of Operations, p. 148; 2026 six months ended June 30; compute and infrastructure expense. [Original S-1](https://www.sec.gov/Archives/edgar/data/2130357/000162828026067168/anthropicpbc-sx1.htm).

**Expected review (candidate):** The arithmetic source subtotal is 7.341 billion; the memo threshold comparison is supported. This is a candidate reviewer interpretation, not human-adjudicated.

**Authority:** Source and semantic status need independent human review.

**Reference trace:**

- Primary `E-7CEAD064` = `16.286`; source atom `16,286` within `Six Months Ended June 30, (in millions) 2023 2024 2025 2025 2026`.
- Primary `E-3488BC71` = `8.945`; source atom `8,945` within `Six Months Ended June 30, (in millions) 2023 2024 2025 2025 2026`.
- Unverified memo `C-D6998A-ADVICE` = threshold `7.0`; exact adapter text prefix: `Simulated advisory claim, unverified:`.
- `node:0001` = `subtract(E-7CEAD064, E-3488BC71)` → `7.341`.
- `node:0002` = `greater_than(node:0001, C-D6998A-ADVICE)` → `True`.

**Semantic use:** Subtract compute/infrastructure expense from H1 revenue; then test the unverified memo threshold. Other expenses still apply.

**Critical removals and counterexamples:**

- Delete `E-7CEAD064` from the model-visible task: `node:0001` and the verdict become unbuildable. Replace only that source amount with `15.286` in a hypothetical input: the verdict reverses.
- Delete `E-3488BC71` from the model-visible task: `node:0001` and the verdict become unbuildable. Replace only that source amount with `9.945` in a hypothetical input: the verdict reverses.
- Delete `C-D6998A-ADVICE`: the arithmetic node remains, but the verdict becomes unbuildable. Change only the memo threshold to `8.0`: the verdict reverses.

- Delete `node:0001`: the comparison cannot execute; a supplied final boolean without both declared nodes is rejected as an unsupported derivation.

**Limit:** This establishes a bounded two-inference reference trace under the actual adapter ID projection, not that one LLM call cannot do both operations or that the runtime will select or semantically validate this trace.

## Before any pilot

1. Obtain independent human source and semantic review of each original excerpt, date, unit, numeric claim, intended label, alternative reasonable answer, and materiality. Record review bytes and disagreements.
2. Verify the participant projection and staged display. Advice is an unverified claim and is selectable only under its adapter ID; reviewer key and this packet remain withheld.
3. Freeze a successor packet, exposure registry, assignment, and exact runtime/prompts before any model operation. Same-folder hashes are not an external seal.
4. Treat earlier S-1 and draft exposures as development exposure. A blind holdout for the same viewer is not established.
5. The previous controller review found five completed C branches stopping after one step and one Selection schema failure. This offline graph challenge neither repairs prompts nor proves live multi-step execution.
