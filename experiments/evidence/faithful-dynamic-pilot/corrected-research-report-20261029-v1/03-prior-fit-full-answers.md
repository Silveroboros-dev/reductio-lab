# Приложение C. Ранний пилот соответствия рынков: полные выходы B, B_self_check, C

Отдельная более ранняя реализация C, не тот же алгоритм, что seed и forecast. 8 кейсов × 3 ветви; прочие A и вся трасса в исходном summary. Выходы без независимой человеческой разметки. News были доступны для выбора, но 24/24 эти ветви выбрали `manual-rules` — дизайн выбирал одно из двух, а не измерял дополнительную ценность новостей. Case-01 имеет нерешённый конфликт источников. JSON воспроизводит полные извлечённые финальные поля и ответ formatter; весь outcome и промежуточные вызовы сохранены в исходном summary. Форматирование может отличаться.

## case-01 / B — slot 1

semantic_status `unassessed_source_conflict`; outcome status `completed`.

Полный сохранённый финальный объект:
```json
{
  "answers": [
    {
      "citations": [
        "thesis",
        "market-id",
        "market-title",
        "primary-rule",
        "secondary-rule",
        "label-guide"
      ],
      "contract_id": "KXFEDDECISION-26DEC-H25",
      "explanation": "The thesis states that the Federal Reserve does not decrease the upper limit of the Federal Funds target rate range at any point prior to January 1, 2028. The market KXFEDDECISION-26DEC-H25 specifically resolves to Yes only if the Fed hikes rates by 25 bps at the December 2026 meeting. The market tests a rate increase of a specific magnitude at a single meeting, whereas the thesis is a multi-year negative thesis regarding the absence of rate cuts across all meetings through 2027. Consequently, the market can resolve No even if the thesis is true (e.g., if rates are held constant, hiked by 50 bps, or cut in 2027), making it a weak proxy or non-equivalent outcome testing a different metric/scope. Under the labeling guide, it represents a weak proxy due to measuring a different event, threshold, and materially different horizon/direction.",
      "label": "weak_proxy"
    }
  ],
  "observed_vs_expected": "The exact rules were retrieved and confirmed that the contract specifically evaluates a single 25 bps hike at the December 2026 FOMC meeting, which differs fundamentally from the thesis covering no rate cuts through 2028.",
  "stop_reason": "completed_evaluation"
}
```
## case-01 / B_self_check — slot 2

semantic_status `unassessed_source_conflict`; outcome status `completed`.

Полный сохранённый финальный объект:
```json
{
  "answers": [
    {
      "citations": [
        "thesis",
        "market-title",
        "primary-rule",
        "secondary-rule",
        "label-guide"
      ],
      "contract_id": "KXFEDDECISION-26DEC-H25",
      "explanation": "The thesis asserts that the Federal Reserve does not decrease the upper limit of the Federal Funds target rate range at any point prior to January 1, 2028. The market specifically resolves to Yes only if the Fed hikes rates by exactly 25 bps at the December 9, 2026 FOMC meeting. A rate hike of 25 bps at a single meeting measures a completely different metric/direction (a hike vs. no decrease across an entire multi-year window), meaning the market can resolve NO while the thesis is true (e.g., rates are held constant or cut prior to 2026/after 2026, or hiked by 50 bps), or resolve YES while the thesis could still be invalidated later before 2028 (if cuts occur in 2027). Under the labeling guide, this mismatch in event, direction, scope, and horizon qualifies it as a weak proxy or not an expression; given the topical relevance to Fed rate decisions but failure to measure the thesis outcome, it is a weak proxy.",
      "label": "weak_proxy"
    }
  ],
  "observed_vs_expected": "Expected to compare the specific resolution conditions of KXFEDDECISION-26DEC-H25 against the thesis on Fed rate cuts before 2028; observed contract rules specifying that the market only resolves to Yes if the Fed hikes rates by 25 bps at the December 2026 FOMC meeting, which differs fundamentally in direction, threshold, and time horizon from the thesis.",
  "stop_reason": "sufficient_evidence"
}
```
## case-01 / C — slot 3

semantic_status `unassessed_source_conflict`; outcome status `proposal`.

Все предложенные ответы:
```json
[
  {
    "contract_id": "KXFEDDECISION-26DEC-H25",
    "label": "unknown"
  }
]
```

Выбранная цепочка:
```json
[
  {
    "conclusion": "The provided texts define criteria for market expression quality labeling and provide specific, isolated resolution conditions regarding Federal Reserve interest rate actions and meetings, but do not provide a paired thesis or candidate market pool evaluation linking them.",
    "conclusion_id": "node:0001",
    "selected_ids": [
      "label-guide",
      "primary-rule",
      "secondary-rule",
      "thesis"
    ]
  }
]
```

Полный сохранённый ответ formatter:
```json
{
  "answers": [
    {
      "contract_id": "KXFEDDECISION-26DEC-H25",
      "label": "unknown"
    }
  ]
}
```
## case-02 / B — slot 4

semantic_status `proposal_unreviewed`; outcome status `completed`.

Полный сохранённый финальный объект:
```json
{
  "answers": [
    {
      "citations": [
        "thesis",
        "primary-rule",
        "secondary-rule",
        "label-guide"
      ],
      "contract_id": "KXIPO-26-ANTHROPIC",
      "explanation": "The thesis requires Anthropic to be officially valued at $1,000,000,000,000 ($1 Trillion) or more in a primary funding round or at its IPO by December 31, 2026. However, the market KXIPO-26-ANTHROPIC strictly resolves to YES if Anthropic confirms an IPO before January 1, 2027, regardless of valuation, and does not capture primary funding rounds reaching $1T without an IPO. Because the market tests an IPO occurrence rather than the $1T valuation threshold, it can resolve YES while the thesis is false (an IPO under $1T) or NO while the thesis is true (a $1T private primary round without an IPO), making it a weak proxy under the labeling guide.",
      "label": "weak_proxy"
    }
  ],
  "observed_vs_expected": "As expected, querying the resolution rules confirmed that contract KXIPO-26-ANTHROPIC resolves purely on whether an IPO is confirmed before January 1, 2027, with no valuation threshold requirement.",
  "stop_reason": "completed"
}
```
## case-02 / B_self_check — slot 5

semantic_status `proposal_unreviewed`; outcome status `completed`.

Полный сохранённый финальный объект:
```json
{
  "answers": [
    {
      "citations": [
        "thesis",
        "primary-rule",
        "secondary-rule",
        "label-guide"
      ],
      "contract_id": "KXIPO-26-ANTHROPIC",
      "explanation": "The thesis requires Anthropic to be valued at $1,000,000,000,000 ($1T) or more in a primary funding round or at its IPO by December 31, 2026. The contract KXIPO-26-ANTHROPIC resolves to Yes solely if Anthropic confirms an IPO before Jan 1, 2027 (e.g., Form S-1 effective, IPO priced, or ticker assigned), with no requirement regarding valuation. Thus, the market can resolve Yes if an IPO occurs at any valuation below $1T (thesis false, market Yes), or resolve No if Anthropic achieves a $1T+ valuation in a primary funding round without an IPO (thesis true, market No). Under the labeling guide, this material mismatch in metric/outcome and threshold makes the market a weak proxy.",
      "label": "weak_proxy"
    }
  ],
  "observed_vs_expected": "The retrieved rules confirmed that the contract strictly measures whether Anthropic confirms an IPO before Jan 1, 2027, with no valuation requirement or primary funding round coverage, directly verifying the expected dimensions needed to determine expression fit.",
  "stop_reason": "completed"
}
```
## case-02 / C — slot 6

semantic_status `proposal_unreviewed`; outcome status `proposal`.

Все предложенные ответы:
```json
[
  {
    "contract_id": "KXIPO-26-ANTHROPIC",
    "label": "weak_proxy"
  }
]
```

Выбранная цепочка:
```json
[
  {
    "conclusion": "Under the labeling guide, the market 'KXIPO-26-ANTHROPIC' (which resolves to Yes if Anthropic confirms an IPO before Jan 1, 2027) exhibits a material mismatch in metric/outcome and threshold against the thesis (which specifies Anthropic reaching an official valuation of $1 Trillion or more in a primary funding round or IPO by December 31, 2026), making it a weak proxy rather than a direct expression because an IPO could occur without meeting the $1 Trillion valuation threshold.",
    "conclusion_id": "node:0001",
    "selected_ids": [
      "label-guide",
      "market-id",
      "market-title",
      "primary-rule",
      "secondary-rule",
      "thesis"
    ]
  }
]
```

Полный сохранённый ответ formatter:
```json
{
  "answers": [
    {
      "contract_id": "KXIPO-26-ANTHROPIC",
      "label": "weak_proxy"
    }
  ]
}
```
## case-05 / B_self_check — slot 8

semantic_status `proposal_unreviewed`; outcome status `completed`.

Полный сохранённый финальный объект:
```json
{
  "answers": [
    {
      "citations": [
        "thesis",
        "market-title",
        "primary-rule",
        "label-guide"
      ],
      "contract_id": "KXANTHROPICRESCIND-26JUN-27JAN01",
      "explanation": "The thesis specifically requires that the supply-chain-risk designation will be completely rescinded/cancelled ('полностью отменено') before 2027. In contrast, the market resolves to YES if the DoD or White House merely waives or materially modifies the designation or directive so as to permit federal/DoD use of Anthropic's AI models. Because the market can resolve to YES on a partial waiver or modification while the designation is not completely rescinded, the threshold and scope diverge, making the market a weak proxy under the labeling guide.",
      "label": "weak_proxy"
    }
  ],
  "observed_vs_expected": "As expected, the resolution rule confirms that waiving or materially modifying the designation or directive so as to permit AI model use qualifies for YES, which is broader than complete rescission ('полностью отменено').",
  "stop_reason": "completed"
}
```
## case-05 / C — slot 9

semantic_status `unassessed_unknown`; outcome status `unknown`.

Все предложенные ответы:
```json
[]
```

Выбранная цепочка:
```json
[
  {
    "conclusion": "Under the provided Labeling Guide, evaluating whether the Russian-language statement ('Обозначение Anthropic как риска для цепочки поставок будет полностью отменено до 2027 года') is directly, indirectly, or weakly expressed by the English market rules (which resolve to Yes not only on full cancellation, but also if the designation or directive is merely waived or materially modified to permit use) requires assessing threshold and scope mismatches, where a market that can resolve Yes on a partial waiver or modification while full rescission is false constitutes a potential proxy rather than a clean direct expression.",
    "conclusion_id": "node:0001",
    "selected_ids": [
      "label-guide",
      "market-title",
      "primary-rule",
      "thesis"
    ]
  }
]
```

Полный сохранённый ответ formatter:
```json
{
  "answers": []
}
```
## case-05 / B — slot 11

semantic_status `proposal_unreviewed`; outcome status `completed`.

Полный сохранённый финальный объект:
```json
{
  "answers": [
    {
      "citations": [
        "thesis",
        "primary-rule",
        "market-title",
        "label-guide"
      ],
      "contract_id": "KXANTHROPICRESCIND-26JUN-27JAN01",
      "explanation": "The thesis specifically requires that Anthropic's designation as a supply chain risk be completely rescinded ('полностью отменено') before 2027. However, the market resolves to YES if the Department of Defense or White House merely waives or materially modifies the designation or phaseout directive to permit federal/DoD use. Because a waiver or modification can resolve the market to YES while the designation has not been completely rescinded, the market's resolution conditions are broader/different in threshold and scope, making it a weak proxy under the labeling guide.",
      "label": "weak_proxy"
    }
  ],
  "observed_vs_expected": "The retrieved primary rule clarifies that the market resolves to YES upon waiving or materially modifying the directive/designation, not solely upon full rescission, which directly confirms the scope mismatch with 'полностью отменено'.",
  "stop_reason": "completed"
}
```
## case-06 / C — slot 12

semantic_status `proposal_unreviewed`; outcome status `proposal`.

Все предложенные ответы:
```json
[
  {
    "contract_id": "KXCLAUDE-CLAUDE6-26DEC31",
    "label": "weak_proxy"
  }
]
```

Выбранная цепочка:
```json
[
  {
    "conclusion": "Under the labeling guide, the market rule resolving to YES upon Claude 6+ release to the public—even if restricted to a high-cost subscription tier—presents a threshold and scope mismatch with the thesis requiring availability specifically to free users ('бесплатным пользователям'), which can cause the market to resolve YES while the thesis is false.",
    "conclusion_id": "node:0001",
    "selected_ids": [
      "label-guide",
      "primary-rule",
      "secondary-rule",
      "thesis"
    ]
  }
]
```

Полный сохранённый ответ formatter:
```json
{
  "answers": [
    {
      "contract_id": "KXCLAUDE-CLAUDE6-26DEC31",
      "label": "weak_proxy"
    }
  ]
}
```
## case-06 / B — slot 14

semantic_status `proposal_unreviewed`; outcome status `completed`.

Полный сохранённый финальный объект:
```json
{
  "answers": [
    {
      "citations": [
        "thesis",
        "primary-rule",
        "secondary-rule",
        "label-guide"
      ],
      "contract_id": "KXCLAUDE-CLAUDE6-26DEC31",
      "explanation": "The thesis explicitly requires Claude 6+ to be publicly available specifically to free users ('бесплатным пользователям'). However, the contract's secondary rule specifies that 'limiting it to a high-cost subscription tier is acceptable'. Therefore, the market can resolve YES (if released solely to high-cost paid subscribers) while the thesis condition is false. Under the labeling guide, this material mismatch in scope and threshold makes the contract a weak_proxy.",
      "label": "weak_proxy"
    }
  ],
  "observed_vs_expected": "As expected, checking the resolution rules clarified the user tier condition: the market explicitly accepts limitation to a high-cost subscription tier, failing to require availability to free users as specified in the thesis.",
  "stop_reason": "stop"
}
```
## case-06 / B_self_check — slot 15

semantic_status `proposal_unreviewed`; outcome status `completed`.

Полный сохранённый финальный объект:
```json
{
  "answers": [
    {
      "citations": [
        "thesis",
        "secondary-rule",
        "primary-rule",
        "label-guide"
      ],
      "contract_id": "KXCLAUDE-CLAUDE6-26DEC31",
      "explanation": "The thesis specifically requires Claude 6+ to become publicly available to free-tier users ('бесплатным пользователям') before December 31, 2026. However, the market's secondary rule explicitly specifies that 'limiting it to a high-cost subscription tier is acceptable' for resolving to Yes. Therefore, the market can resolve to Yes if Anthropic releases Claude 6+ exclusively under a paid/high-cost tier without ever making it accessible to free users, creating a material mismatch in population scope and threshold. Per the labeling guide, this makes the contract a weak proxy.",
      "label": "weak_proxy"
    }
  ],
  "observed_vs_expected": "Observed that the secondary rule explicitly permits limiting the release to a high-cost subscription tier ('limiting it to a high-cost subscription tier is acceptable'), which directly contrasts with the pre-query expectation check regarding whether free-tier availability was required.",
  "stop_reason": "completed_assessment"
}
```
## case-07 / B — slot 17

semantic_status `proposal_unreviewed`; outcome status `completed`.

Полный сохранённый финальный объект:
```json
{
  "answers": [
    {
      "citations": [
        "thesis",
        "primary-rule",
        "secondary-rule"
      ],
      "contract_id": "KXGDPNOM-US26-32.8",
      "explanation": "The thesis specifically requires the BEA's first non-preliminary estimate of US nominal GDP for 2026 to exceed $32.8 trillion. However, the market's resolution rules specify that it resolves using the World Bank's first non-preliminary release of US Nominal GDP for calendar year 2026 (with Trading Economics as backup), rather than the BEA release. While measuring nominal GDP for the same year and threshold, the divergence in the specified authoritative source and vintage constitutes a material difference in resolution evidence/source, making this market a weak_proxy.",
      "label": "weak_proxy"
    }
  ],
  "observed_vs_expected": "The pre-query expectation was to check whether the market aligns with the BEA first non-preliminary estimate. The rules reveal that the market resolves using the World Bank's first non-preliminary release (with Trading Economics as backup), not the BEA.",
  "stop_reason": "completed"
}
```
## case-07 / B_self_check — slot 18

semantic_status `proposal_unreviewed`; outcome status `completed`.

Полный сохранённый финальный объект:
```json
{
  "answers": [
    {
      "citations": [
        "thesis",
        "primary-rule",
        "secondary-rule"
      ],
      "contract_id": "KXGDPNOM-US26-32.8",
      "explanation": "The thesis specifically requires the first non-preliminary estimate of US nominal GDP for 2026 by the Bureau of Economic Analysis (BEA). In contrast, the market rules specify that resolution relies on the World Bank's first non-preliminary release (with Trading Economics as backup), rather than BEA. Because the market relies on a different authoritative resolution source whose methodology, reporting schedule, and values may diverge from BEA's direct release, it represents a proxy/mismatched resolution source rather than a direct expression, falling under weak_proxy.",
      "label": "weak_proxy"
    }
  ],
  "observed_vs_expected": "Observed the resolution rules which show resolution relies on the World Bank (and Trading Economics backup) rather than the BEA specified in the thesis, contrary to the expected alignment with the BEA.",
  "stop_reason": "completed_assessment"
}
```
## case-07 / C — slot 19

semantic_status `unassessed_unknown`; outcome status `proposal`.

Все предложенные ответы:
```json
[
  {
    "contract_id": "KXGDPNOM-US26-32.8",
    "label": "unknown"
  }
]
```

Выбранная цепочка:
```json
[
  {
    "conclusion": "The market rules specify resolution using the World Bank's first non-preliminary release of 2026 US Nominal GDP in current US dollars (with Trading Economics as a backup), whereas the Russian text refers to the BEA's (Bureau of Economic Analysis) first non-preliminary estimate of 2026 US nominal GDP exceeding $32.8 trillion, representing a difference in the specified authoritative resolution source.",
    "conclusion_id": "node:0001",
    "selected_ids": [
      "label-guide",
      "primary-rule",
      "secondary-rule",
      "thesis"
    ]
  }
]
```

Полный сохранённый ответ formatter:
```json
{
  "answers": [
    {
      "contract_id": "KXGDPNOM-US26-32.8",
      "label": "unknown"
    }
  ]
}
```
## case-03 / B — slot 20

semantic_status `proposal_unreviewed`; outcome status `completed`.

Полный сохранённый финальный объект:
```json
{
  "answers": [
    {
      "citations": [
        "thesis",
        "primary-rule"
      ],
      "contract_id": "KXHIGHINFLATION-26DEC-T4.2",
      "explanation": "The thesis states that in one of the CPI reports for 2026, annual inflation will exceed 4.2% ('В одном из отчётов CPI за 2026 год годовая инфляция превысит 4,2%'). The primary resolution rule specifies that if any Consumer Price Index (CPI YoY) report is above 4.2% for 2026, the market resolves to Yes. The entity, metric (CPI YoY), threshold (4.2%), window (2026), and condition match directly.",
      "label": "direct"
    }
  ],
  "observed_vs_expected": "The manual-rules query returned the primary rule confirming that if any CPI YoY report for 2026 is above 4.2%, the market resolves to Yes, which aligns with the expectation to inspect resolution criteria and threshold.",
  "stop_reason": "completed"
}
```
## case-03 / B_self_check — slot 21

semantic_status `proposal_unreviewed`; outcome status `completed`.

Полный сохранённый финальный объект:
```json
{
  "answers": [
    {
      "citations": [
        "thesis",
        "primary-rule",
        "label-guide"
      ],
      "contract_id": "KXHIGHINFLATION-26DEC-T4.2",
      "explanation": "The thesis states that in at least one 2026 CPI report, annual inflation will exceed 4.2% ('В одном из отчётов CPI за 2026 год годовая инфляция превысит 4,2%'). The primary resolution rule for KXHIGHINFLATION-26DEC-T4.2 states that if any Consumer Price Index (CPI YoY) report is above 4.2% for 2026, the market resolves to Yes. The entity, metric (CPI YoY), threshold (>4.2%), condition (any report in 2026), and time window align materially with the thesis, satisfying the definition of a direct expression under the label guide.",
      "label": "direct"
    }
  ],
  "observed_vs_expected": "The retrieved resolution rule confirmed that the contract resolves to Yes if any CPI YoY report for 2026 is above 4.2%, which exactly matches the threshold, condition, and target year anticipated in the pre-query expectation.",
  "stop_reason": "sufficient_evidence"
}
```
## case-03 / C — slot 22

semantic_status `proposal_unreviewed`; outcome status `proposal`.

Все предложенные ответы:
```json
[
  {
    "contract_id": "KXHIGHINFLATION-26DEC-T4.2",
    "label": "direct"
  }
]
```

Выбранная цепочка:
```json
[
  {
    "conclusion": "The resolution condition that the market resolves to Yes if any Consumer Price Index (CPI YoY) report for 2026 is above 4.2% materially corresponds to the Russian statement that annual inflation in at least one CPI report for 2026 will exceed 4.2%.",
    "conclusion_id": "node:0001",
    "selected_ids": [
      "label-guide",
      "primary-rule",
      "thesis"
    ]
  }
]
```

Полный сохранённый ответ formatter:
```json
{
  "answers": [
    {
      "contract_id": "KXHIGHINFLATION-26DEC-T4.2",
      "label": "direct"
    }
  ]
}
```
## case-08 / B_self_check — slot 24

semantic_status `proposal_unreviewed`; outcome status `completed`.

Полный сохранённый финальный объект:
```json
{
  "answers": [
    {
      "citations": [
        "thesis",
        "primary-rule",
        "secondary-rule",
        "label-guide"
      ],
      "contract_id": "KXRSIANNOUNCE-29-27JAN01",
      "explanation": "The thesis requires that OpenAI or Anthropic publicly demonstrates independently verified recursive self-improvement before 2027 ('публично продемонстрирует независимо подтверждённое рекурсивное самоулучшение'). In contrast, the market resolves purely on an official announcement or statement by company leadership claiming achieved capability. Furthermore, the market's secondary rule explicitly states: 'A public release, named model, technical demonstration, or independent verification is not required.' Because the market tests an announcement stage rather than a demonstration and explicitly waives independent verification, it can resolve YES while the thesis remains false (or vice versa), making it a weak proxy under the labeling guide.",
      "label": "weak_proxy"
    }
  ],
  "observed_vs_expected": "The retrieved rules explicitly confirmed the pre-query expectation: the market resolves strictly on an official announcement and explicitly specifies that 'A public release, named model, technical demonstration, or independent verification is not required', directly conflicting with the thesis requirements for public demonstration and independent verification.",
  "stop_reason": "completed"
}
```
## case-08 / C — slot 25

semantic_status `proposal_unreviewed`; outcome status `proposal`.

Все предложенные ответы:
```json
[
  {
    "contract_id": "KXRSIANNOUNCE-29-27JAN01",
    "label": "weak_proxy"
  }
]
```

Выбранная цепочка:
```json
[
  {
    "conclusion": "Under the provided labeling guide, the market contract constitutes a weak_proxy for the thesis because there are material mismatches in event stage and required resolution evidence: the thesis demands that OpenAI or Anthropic publicly demonstrate independently verified recursive self-improvement before 2027 ('публично продемонстрирует независимо подтверждённое рекурсивное самоулучшение'), whereas the market resolves purely on an official announcement or statement by an executive/research leader without requiring a public release, technical demonstration, or independent verification ('A public release, named model, technical demonstration, or independent verification is not required').",
    "conclusion_id": "node:0001",
    "selected_ids": [
      "thesis",
      "primary-rule",
      "secondary-rule",
      "label-guide"
    ]
  }
]
```

Полный сохранённый ответ formatter:
```json
{
  "answers": [
    {
      "contract_id": "KXRSIANNOUNCE-29-27JAN01",
      "label": "weak_proxy"
    }
  ]
}
```
## case-08 / B — slot 27

semantic_status `proposal_unreviewed`; outcome status `completed`.

Полный сохранённый финальный объект:
```json
{
  "answers": [
    {
      "citations": [
        "thesis",
        "market-title",
        "primary-rule",
        "secondary-rule",
        "label-guide"
      ],
      "contract_id": "KXRSIANNOUNCE-29-27JAN01",
      "explanation": "The thesis requires that OpenAI or Anthropic publicly demonstrates independently verified recursive self-improvement ('публично продемонстрирует независимо подтверждённое рекурсивное самоулучшение'). However, the market resolves based solely on an announcement ('If OpenAI or Anthropic announces it has achieved recursive self-improvement...'). Crucially, the secondary rule explicitly states: 'A public release, named model, technical demonstration, or independent verification is not required.' Under the label guide, an announcement vs demonstration/verification discrepancy constitutes a material mismatch in event stage, threshold, and resolution evidence, meaning the market can resolve YES (on a mere corporate statement) while the thesis remains false. Thus, it is classified as a weak_proxy.",
      "label": "weak_proxy"
    }
  ],
  "observed_vs_expected": "The retrieved rules confirmed the pre-query expectation: the contract resolves on an official announcement and explicitly excludes requiring a technical demonstration or independent verification, directly diverging from the thesis's core requirement.",
  "stop_reason": "completed"
}
```
## case-04 / C — slot 28

semantic_status `proposal_unreviewed`; outcome status `proposal`.

Все предложенные ответы:
```json
[
  {
    "contract_id": "KXUSGDPSHARE-27JUL01-T25.7",
    "label": "indirect"
  }
]
```

Выбранная цепочка:
```json
[
  {
    "conclusion": "The resolution rules base the market outcome on values from the first World Development Indicators release reporting 2026 data for both economies, whereas the thesis specifies the World Bank's final revised estimate ('Итоговая пересмотренная оценка') of the U.S. share of global GDP for 2026.",
    "conclusion_id": "node:0001",
    "selected_ids": [
      "label-guide",
      "primary-rule",
      "secondary-rule",
      "thesis"
    ]
  }
]
```

Полный сохранённый ответ formatter:
```json
{
  "answers": [
    {
      "contract_id": "KXUSGDPSHARE-27JUL01-T25.7",
      "label": "indirect"
    }
  ]
}
```
## case-04 / B — slot 30

semantic_status `proposal_unreviewed`; outcome status `completed`.

Полный сохранённый финальный объект:
```json
{
  "answers": [
    {
      "citations": [
        "thesis",
        "secondary-rule",
        "primary-rule"
      ],
      "contract_id": "KXUSGDPSHARE-27JUL01-T25.7",
      "explanation": "The human thesis specifically specifies the final revised estimate by the World Bank ('Итоговая пересмотренная оценка World Bank доли США в мировом ВВП за 2026 год превысит 25,7%'). However, the contract's resolution rules state: 'Both inputs must be taken from the first World Development Indicators database release in which values attributed to 2026 are available for both the United States and World.' Because the market resolves strictly on the first release rather than the revised/final estimate, it measures an earlier data vintage/stage which can diverge from the final revised figures, making it a weak proxy under the labeling guide.",
      "label": "weak_proxy"
    }
  ],
  "observed_vs_expected": "The retrieved rules revealed the exact source and calculation method, but showed that the contract resolves on the first WDI release for 2026 rather than the final revised estimate specified in the thesis.",
  "stop_reason": "Evaluation complete with all necessary contract rules and thesis details assessed."
}
```
## case-04 / B_self_check — slot 31

semantic_status `proposal_unreviewed`; outcome status `completed`.

Полный сохранённый финальный объект:
```json
{
  "answers": [
    {
      "citations": [
        "thesis",
        "primary-rule",
        "secondary-rule",
        "label-guide"
      ],
      "contract_id": "KXUSGDPSHARE-27JUL01-T25.7",
      "explanation": "The thesis specifically specifies the final revised estimate by the World Bank ('Итоговая пересмотренная оценка World Bank доли США в мировом ВВП за 2026 год превысит 25,7%'). However, the contract resolution rules explicitly mandate that 'Both inputs must be taken from the first World Development Indicators database release in which values attributed to 2026 are available for both the United States and World.' Because the market resolves strictly on the initial release rather than subsequent revisions, the market can resolve YES while the revised figure is NO, or vice versa. Under the label guide, measuring an initial/different stage or metric revision that can diverge creates a weak proxy.",
      "label": "weak_proxy"
    }
  ],
  "observed_vs_expected": "Expected to check whether the resolution source is the World Bank and how revisions are handled. Observed that while the source is indeed the World Bank's World Development Indicators, the contract resolves on the first release rather than the final revised estimate specified in the thesis.",
  "stop_reason": "completed"
}
```
