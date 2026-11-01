# Исправленный синтетический пилот: SI против Gemini 3.8 Flash

Три случая после выявления дефектов исходной серии: одна пара отличается последним правилом; ещё один положительный случай из следующей пары. В каждом четыре шага и 16 отвлекающих правил. Правила сформулированы для любых объектов, без скрытого условия creature; модель не получала ключ. Случаи и версия контроллера открыты исполнителю и отобраны после наблюдения исходных результатов: это не независимый holdout.

Каждый случай назначался трём ветвям: B (обычный ответ), B_self (отдельный ответ и одна самопроверка), C (SI, максимум четыре шага, одна ветвь и до двух выбранных посылок на шаг). Все — gemini-3.8-flash, thinking LOW, те же заявления и вопрос; запросы ролей и число обращений различаются. Halter отдельно оценивает смысл итоговой посылки, не требуя оформления ответа до Formatter. Одновременно изменены текст правил и инструкция Halter/Formatter: вклад изменений по отдельности не изолирован.

Состояние: `completed_unreviewed`, записано 9/9 назначений. Статусы `completed` и `proposal` не означают содержательную правильность; `unknown` и технические сбои остаются в знаменателях.

Учёт: ранее $52.551566; оценка новых фактически учтённых вызовов $0.124063; новые неурегулированные резервы $0.000000; суммарная локальная экспозиция $52.675629 из $60. В неё включены два прежних резерва по $8.380416. Это не сверенный счёт.

Эффекты `{('count', 'succeeded', 200): 60, ('generation', 'succeeded', 200): 60}`; успешных генераций 60; input tokens 45654, total tokens 53063, thoughts 3846; модели `['gemini-3.8-flash']`. Отдельные HTTP/SDK операции OAuth сюда не входят.

## Независимая предварительная оценка

Два отдельных агента сопоставили полные исходы с явно заданными правилами; это открытый консультативный разбор, не человеческая аттестация и не независимый holdout.

| Задача | Ключ | B | B_self | C / SI |
|---|---|---|---|---|
| Ignis, доступ разрешён | YES | YES; четыре перехода и источники в самом ответе | YES; полная цепочка и самопроверка | YES; четыре проверенных перехода в трассе |
| Ignis, изменено конечное правило | NO | NO; четыре перехода и источники в самом ответе | NO; полная цепочка и самопроверка | NO; четыре проверенных перехода в трассе |
| Luma | YES | YES; четыре перехода и источники в самом ответе | YES; полная цепочка и самопроверка | YES; четыре проверенных перехода в трассе |

Содержательный вердикт совпал с ключом во всех трёх случаях каждой ветви. C давал короткий ответ YES/NO и показывал рассуждение отдельно в записанной структурированной трассе, а B и B_self включали объяснение в сам ответ; следовательно, совпадение по вердикту не устанавливает равенство по выполнению требования объяснить. Проверка смысловой правильности на этих задачах не доказывает доступ к внутренним вычислениям модели и не является общей гарантией faithful reasoning.

| Ветка | Модельных вызовов | Оценка расходов |
|---|---:|---:|
| B | 3 | $0.012269 |
| B_self | 6 | $0.024709 |
| C / SI | 51 | $0.087085 |

Это не подтверждает превосходство SI: baseline ответил на все три вопроса правильно и дал полные объяснения. Одновременно результат показывает, что при исправлении двух обнаруженных дефектов данный контроллер способен построить и выдать решения этих трёх задач. Поскольку условия и промпты одновременно изменены после первичного запуска и случаи уже были известны авторам, причинный вклад каждого изменения и обобщаемость остаются неизвестными.

Обе новые серии вместе: 213 успешных генераций, одна подтверждённая 429 с точным повтором, 213 countTokens; новые расчётные расходы **$0.481425**, новых неопределённых вызовов нет. Совокупная локальная экспозиция **$52.675629 / $60**, включая сохранённые два исторических резерва по $8.380416; остаток $7.324371. Общие счётчики 1 062/1 072 generation attempts и 986/1 001 countTokens. Эти оценки не являются сверенным счётом Google. Предыдущие исходы и контексты не переписывались.

## Полные ответы и заявленные цепочки

### 1. repair-f02d2b374041c1b3

**Вопрос:** In this fictional world, is Ignis authorized to enter the sanctuary? Use only the supplied statements, without real-world assumptions. Answer YES if authorization follows, NO if non-authorization follows, or UNKNOWN if neither follows. Briefly explain your reasoning.

**Проверяемый ключ:** YES. Длина пути: 4; отвлекающих правил: 16.

Эталонные посылки:

- `s000`: Ignis is a dragon.
- `s014`: If something is a dragon, then it eats only mountain moss.
- `s007`: If something eats only mountain moss, then it has no iron-tipped armour.
- `s016`: If something has no iron-tipped armour, then it is allergic to silver bells.
- `s011`: If something is allergic to silver bells, then it is authorized to enter the sanctuary.

**B** — `completed`; причина `model_proposal_requires_semantic_review`; вызовов 1.

```json
{
  "answer": "YES. Based on the provided statements:\n1. Ignis is a dragon (s000).\n2. If something is a dragon, then it eats only mountain moss (s014). Therefore, Ignis eats only mountain moss.\n3. If something eats only mountain moss, then it has no iron-tipped armour (s007). Therefore, Ignis has no iron-tipped armour.\n4. If something has no iron-tipped armour, then it is allergic to silver bells (s016). Therefore, Ignis is allergic to silver bells.\n5. If something is allergic to silver bells, then it is authorized to enter the sanctuary (s011). Therefore, Ignis is authorized to enter the sanctuary.",
  "assessments": [
    {
      "id": "user-target",
      "reason": "The chain of logical implications from s000, s014, s007, s016, and s011 directly proves that Ignis is authorized to enter the sanctuary.",
      "status": "assessed"
    }
  ],
  "citations": [
    "s000",
    "s014",
    "s007",
    "s016",
    "s011"
  ]
}
```

[Полная запись B](/Users/rk/.codex/visualizations/2026/10/29/01a1865f-6bd2-75a2-abb1-eb14b071bbe0/reasoning-synthetic-si-repair-20261029-v1/80f3cee77b7bb6b28a68dfe4509d9519f55d3969b5dbf6191b40627a13fee974.outcome.json)

**B_self** — `completed`; причина `model_proposal_requires_semantic_review`; вызовов 2.

```json
{
  "answer": "YES. Based on the supplied statements:\n1. Ignis is a dragon (s000).\n2. If something is a dragon, then it eats only mountain moss (s014), so Ignis eats only mountain moss.\n3. If something eats only mountain moss, then it has no iron-tipped armour (s007), so Ignis has no iron-tipped armour.\n4. If something has no iron-tipped armour, then it is allergic to silver bells (s016), so Ignis is allergic to silver bells.\n5. If something is allergic to silver bells, then it is authorized to enter the sanctuary (s011).\n\nTherefore, Ignis is authorized to enter the sanctuary.",
  "assessments": [
    {
      "id": "user-target",
      "reason": "A complete deductive chain from the provided fictional statements proves that Ignis is authorized to enter the sanctuary.",
      "status": "assessed"
    }
  ],
  "citations": [
    "s000",
    "s014",
    "s007",
    "s016",
    "s011"
  ]
}
```

[Полная запись B_self](/Users/rk/.codex/visualizations/2026/10/29/01a1865f-6bd2-75a2-abb1-eb14b071bbe0/reasoning-synthetic-si-repair-20261029-v1/afd91971c73175fc839eb6d60f48d3aa97f3d977fdcca4a8549846df7aa6e653.outcome.json)

**C** — `proposal`; причина `model_proposal_requires_semantic_review`; вызовов 17.

```json
{
  "answer": "YES, Ignis is authorized to enter the sanctuary.",
  "citations": [
    "s000",
    "s007",
    "s011",
    "s014",
    "s016"
  ]
}
```

- `root.1.1`, выбранные `['s000', 's014']` → Ignis eats only mountain moss.

- `root.1.1.2.1`, выбранные `['node:0001', 's007']` → Ignis has no iron-tipped armour.

- `root.1.1.2.1.3.1`, выбранные `['node:0002', 's016']` → Ignis is allergic to silver bells.

- `root.1.1.2.1.3.1.4.1`, выбранные `['node:0003', 's011']` → Ignis is authorized to enter the sanctuary.

Проверки Halter: `[{"sufficient": false, "reason": "The current inference only describes what Ignis eats ('Ignis eats only mountain moss') and does not resolve whether Ignis is authorized or not authorized to enter the sanctuary."}, {"sufficient": false, "reason": "The current inference only establishes that Ignis has no iron-tipped armour, but it does not determine whether Ignis is authorized or not authorized to enter the sanctuary."}, {"sufficient": false, "reason": "The inference only states that Ignis is allergic to silver bells, which does not answer whether Ignis is authorized to enter the sanctuary."}, {"sufficient": true, "reason": "The inference directly addresses whether Ignis is authorized to enter the sanctuary by stating 'Ignis is authorized to enter the sanctuary.'"}]`.

[Полная запись C](/Users/rk/.codex/visualizations/2026/10/29/01a1865f-6bd2-75a2-abb1-eb14b071bbe0/reasoning-synthetic-si-repair-20261029-v1/ec03cbd06715d894878d051f8a9a67150362169a9768b07102381db9c97d424d.outcome.json)

### 2. repair-be4fff253ffec64c

**Вопрос:** In this fictional world, is Ignis authorized to enter the sanctuary? Use only the supplied statements, without real-world assumptions. Answer YES if authorization follows, NO if non-authorization follows, or UNKNOWN if neither follows. Briefly explain your reasoning.

**Проверяемый ключ:** NO. Длина пути: 4; отвлекающих правил: 16.

Эталонные посылки:

- `s000`: Ignis is a dragon.
- `s014`: If something is a dragon, then it eats only mountain moss.
- `s007`: If something eats only mountain moss, then it has no iron-tipped armour.
- `s016`: If something has no iron-tipped armour, then it is allergic to silver bells.
- `s011`: If something is allergic to silver bells, then it is not authorized to enter the sanctuary.

**B** — `completed`; причина `model_proposal_requires_semantic_review`; вызовов 1.

```json
{
  "answer": "NO. Based on the provided statements:\n1. Ignis is a dragon (s000).\n2. If something is a dragon, then it eats only mountain moss (s014), so Ignis eats only mountain moss.\n3. If something eats only mountain moss, then it has no iron-tipped armour (s007), so Ignis has no iron-tipped armour.\n4. If something has no iron-tipped armour, then it is allergic to silver bells (s016), so Ignis is allergic to silver bells.\n5. If something is allergic to silver bells, then it is not authorized to enter the sanctuary (s011).\n\nTherefore, Ignis is not authorized to enter the sanctuary.",
  "assessments": [
    {
      "id": "user-target",
      "reason": "A direct deductive chain from s000, s014, s007, s016, and s011 proves that Ignis is not authorized to enter the sanctuary.",
      "status": "assessed"
    }
  ],
  "citations": [
    "s000",
    "s007",
    "s011",
    "s014",
    "s016"
  ]
}
```

[Полная запись B](/Users/rk/.codex/visualizations/2026/10/29/01a1865f-6bd2-75a2-abb1-eb14b071bbe0/reasoning-synthetic-si-repair-20261029-v1/f9a1d865b75811c711e8b18551e1a9d095582e8f4104709cb0d27ff36bd737b9.outcome.json)

**B_self** — `completed`; причина `model_proposal_requires_semantic_review`; вызовов 2.

```json
{
  "answer": "NO. Based strictly on the supplied statements:\n1. Ignis is a dragon (s000).\n2. If something is a dragon, then it eats only mountain moss (s014). Therefore, Ignis eats only mountain moss.\n3. If something eats only mountain moss, then it has no iron-tipped armour (s007). Therefore, Ignis has no iron-tipped armour.\n4. If something has no iron-tipped armour, then it is allergic to silver bells (s016). Therefore, Ignis is allergic to silver bells.\n5. If something is allergic to silver bells, then it is not authorized to enter the sanctuary (s011). Therefore, Ignis is not authorized to enter the sanctuary.",
  "assessments": [
    {
      "id": "user-target",
      "reason": "The deduction chain using s000, s014, s007, s016, and s011 formally concludes that Ignis is not authorized to enter the sanctuary, satisfying the criteria for 'NO'.",
      "status": "assessed"
    }
  ],
  "citations": [
    "s000",
    "s014",
    "s007",
    "s016",
    "s011"
  ]
}
```

[Полная запись B_self](/Users/rk/.codex/visualizations/2026/10/29/01a1865f-6bd2-75a2-abb1-eb14b071bbe0/reasoning-synthetic-si-repair-20261029-v1/74e8bfbdac42e837272cb4d3bee50a559229ca5fb339892f1d21397054c37fac.outcome.json)

**C** — `proposal`; причина `model_proposal_requires_semantic_review`; вызовов 17.

```json
{
  "answer": "NO, Ignis is not authorized to enter the sanctuary.",
  "citations": [
    "s000",
    "s007",
    "s011",
    "s014",
    "s016"
  ]
}
```

- `root.1.1`, выбранные `['s000', 's014']` → Ignis eats only mountain moss.

- `root.1.1.2.1`, выбранные `['node:0001', 's007']` → Ignis has no iron-tipped armour.

- `root.1.1.2.1.3.1`, выбранные `['node:0002', 's016']` → Ignis is allergic to silver bells.

- `root.1.1.2.1.3.1.4.1`, выбранные `['node:0003', 's011']` → Ignis is not authorized to enter the sanctuary.

Проверки Halter: `[{"sufficient": false, "reason": "The current inference states what Ignis eats ('Ignis eats only mountain moss'), which does not answer whether Ignis is authorized to enter the sanctuary."}, {"sufficient": false, "reason": "The current inference only determines that Ignis has no iron-tipped armour, which does not directly state or conclude whether Ignis is authorized or unauthorized to enter the sanctuary."}, {"sufficient": false, "reason": "The current inference only mentions an allergy to silver bells and does not conclude whether Ignis is authorized or not authorized to enter the sanctuary."}, {"sufficient": true, "reason": "The inference directly and unambiguously states that Ignis is not authorized to enter the sanctuary, which semantically answers whether Ignis is authorized to enter the sanctuary."}]`.

[Полная запись C](/Users/rk/.codex/visualizations/2026/10/29/01a1865f-6bd2-75a2-abb1-eb14b071bbe0/reasoning-synthetic-si-repair-20261029-v1/a184a8499e2dd9c551f337a605a3b83ab208a3a6e1b5d7f6c3feab311af6ab63.outcome.json)

### 3. repair-13008e39e5dfddbf

**Вопрос:** In this fictional world, is Luma authorized to enter the sanctuary? Use only the supplied statements, without real-world assumptions. Answer YES if authorization follows, NO if non-authorization follows, or UNKNOWN if neither follows. Briefly explain your reasoning.

**Проверяемый ключ:** YES. Длина пути: 4; отвлекающих правил: 16.

Эталонные посылки:

- `s005`: Luma is a griffin.
- `s016`: If something is a griffin, then it eats only river lilies.
- `s020`: If something eats only river lilies, then it has no copper-tipped armour.
- `s019`: If something has no copper-tipped armour, then it is allergic to bronze bells.
- `s011`: If something is allergic to bronze bells, then it is authorized to enter the sanctuary.

**B** — `completed`; причина `model_proposal_requires_semantic_review`; вызовов 1.

```json
{
  "answer": "YES. Based on the provided statements:\n1. Luma is a griffin (s005).\n2. If something is a griffin, then it eats only river lilies (s016). Therefore, Luma eats only river lilies.\n3. If something eats only river lilies, then it has no copper-tipped armour (s020). Therefore, Luma has no copper-tipped armour.\n4. If something has no copper-tipped armour, then it is allergic to bronze bells (s019). Therefore, Luma is allergic to bronze bells.\n5. If something is allergic to bronze bells, then it is authorized to enter the sanctuary (s011). Therefore, Luma is authorized to enter the sanctuary.",
  "assessments": [
    {
      "id": "user-target",
      "reason": "The chain of logical implications from s005, s016, s020, s019, and s011 directly proves that Luma is authorized to enter the sanctuary.",
      "status": "assessed"
    }
  ],
  "citations": [
    "s005",
    "s011",
    "s016",
    "s019",
    "s020"
  ]
}
```

[Полная запись B](/Users/rk/.codex/visualizations/2026/10/29/01a1865f-6bd2-75a2-abb1-eb14b071bbe0/reasoning-synthetic-si-repair-20261029-v1/ed6eab9748d9fce21e51a9a5c065bf24a4dff8eda1e9563948b4b9bb37c033e6.outcome.json)

**B_self** — `completed`; причина `model_proposal_requires_semantic_review`; вызовов 2.

```json
{
  "answer": "YES. Based on the provided statements:\n1. Luma is a griffin (s005).\n2. If something is a griffin, then it eats only river lilies (s016). Therefore, Luma eats only river lilies.\n3. If something eats only river lilies, then it has no copper-tipped armour (s020). Therefore, Luma has no copper-tipped armour.\n4. If something has no copper-tipped armour, then it is allergic to bronze bells (s019). Therefore, Luma is allergic to bronze bells.\n5. If something is allergic to bronze bells, then it is authorized to enter the sanctuary (s011). Therefore, Luma is authorized to enter the sanctuary.",
  "assessments": [
    {
      "id": "user-target",
      "reason": "A direct logical deduction from the supplied premises establishes that Luma is authorized to enter the sanctuary without any ambiguity or need for external assumptions.",
      "status": "assessed"
    }
  ],
  "citations": [
    "s005",
    "s011",
    "s016",
    "s019",
    "s020"
  ]
}
```

[Полная запись B_self](/Users/rk/.codex/visualizations/2026/10/29/01a1865f-6bd2-75a2-abb1-eb14b071bbe0/reasoning-synthetic-si-repair-20261029-v1/2300d88439cd77df2622263a4f0a032dabaaceeb1d6c943ec9a1cc3dc791e65a.outcome.json)

**C** — `proposal`; причина `model_proposal_requires_semantic_review`; вызовов 17.

```json
{
  "answer": "YES, based strictly on the provided statements, Luma is authorized to enter the sanctuary.",
  "citations": [
    "s005",
    "s011",
    "s016",
    "s019",
    "s020"
  ]
}
```

- `root.1.1`, выбранные `['s005', 's016']` → Luma eats only river lilies.

- `root.1.1.2.1`, выбранные `['node:0001', 's020']` → Luma has no copper-tipped armour.

- `root.1.1.2.1.3.1`, выбранные `['node:0002', 's019']` → Luma is allergic to bronze bells.

- `root.1.1.2.1.3.1.4.1`, выбранные `['node:0003', 's011']` → Based strictly on the provided statements, Luma is authorized to enter the sanctuary.

Проверки Halter: `[{"sufficient": false, "reason": "The inference only states what Luma eats and does not state whether Luma is authorized or not authorized to enter the sanctuary."}, {"sufficient": false, "reason": "The current inference ('Luma has no copper-tipped armour.') only states a property of Luma's equipment and does not state whether Luma is authorized or not authorized to enter the sanctuary."}, {"sufficient": false, "reason": "The current inference states that 'Luma is allergic to bronze bells', which does not address whether Luma is authorized to enter the sanctuary."}, {"sufficient": true, "reason": "The current inference directly addresses the question by explicitly stating that Luma is authorized to enter the sanctuary."}]`.

[Полная запись C](/Users/rk/.codex/visualizations/2026/10/29/01a1865f-6bd2-75a2-abb1-eb14b071bbe0/reasoning-synthetic-si-repair-20261029-v1/604502bf6287a2df9fd5c52a833402eea8d31ff78ed882cfe9403266c71ee4ee.outcome.json)

## Интерпретация

Все выбранные исходы и эффекты показаны без выборочного удаления. Правильность и доказательность отдельных цепочек требуют независимого содержательного разбора; числовые итоги не выводятся из статуса или самооценки модели. Для неполного запуска незаписанные назначения остаются в знаменателе. Успех на этой небольшой открытой выборке не устанавливает превосходства на других задачах.

[Данные всех задач](/Users/rk/.codex/visualizations/2026/10/29/01a1865f-6bd2-75a2-abb1-eb14b071bbe0/reasoning-synthetic-si-repair-20261029-v1/tasks.json) · [Ключ](/Users/rk/.codex/visualizations/2026/10/29/01a1865f-6bd2-75a2-abb1-eb14b071bbe0/reasoning-synthetic-si-repair-20261029-v1/answer-key.json) · [Итог и учёт](/Users/rk/.codex/visualizations/2026/10/29/01a1865f-6bd2-75a2-abb1-eb14b071bbe0/reasoning-synthetic-si-repair-20261029-v1/summary.json)
