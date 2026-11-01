# Vertex compatibility canary — 2026-11-01

## Русский

Canary прошёл; полный сквозной критерий не выполнен: после Source decision, Selection, Inference, Halter и Value контроллер вернул `unknown / reasoning_depth_exhausted`, не вызвав Formatter. Все входы синтетические. Семантическая оценка требует отдельной проверки.

Сохранённое правило: цель LARK-7 достигнута только при успешных как минимум 7 из 10 проверок. Сохранённый итог: успешно 6 из 10. Source decision выбрал сохранённый итог; Selection выбрал оба источника. Inference: “For batch LARK-7, the target was not met because only 6 of the 10 final checks passed, which is fewer than the required minimum of 7.”

Halter ответил `sufficient=false`: “The inference provides a factual conclusion assessing whether batch LARK-7 met its final audit target, but it fails to cite any saved source IDs as explicitly required by the task instructions.” Проблема согласования: в вопрос Halter включено требование сослаться на источники, хотя Inference получает только выбранные посылки без ID, а ссылки предназначены Formatter. Отсутствие ссылок в Inference не означает отсутствие источников в журнале. Value дал 1.0; это оценка модели, не независимое подтверждение.

6 генераций и 6 countTokens, 12 ответов HTTP 200, 0 повторов, 0 uncertain, 0 внешних источников. Usage: 3 589 входных токенов и 345 выходных, включая 98 thinking. Локальная оценка новых расходов $0.003988; общий локальный учёт с прежними резервами $56.926158, 1 632 генерации и 1 554 countTokens. Счёт провайдера не сверён.

## English

The canary passed, but the end-to-end gate did not: after source decision, Selection, Inference, Halter and Value, the controller returned `unknown / reasoning_depth_exhausted`; Formatter was not called. All case data are synthetic. Semantic review remains pending.

The saved rule requires at least 7 of 10 checks; the saved tally reports 6 of 10. The source decision retrieved the tally and Selection selected both sources. Inference concluded that the target was not met. Halter nevertheless returned `sufficient=false` because the inference did not cite source IDs. That requirement was present in Halter’s question although Inference sees selected premises without IDs and Formatter is responsible for citations. Value scored the branch 1.0; this is an unverified model assessment.

Six generation and six countTokens attempts returned HTTP 200. There were no retries, uncertain effects, or external source calls. Usage: 3,589 input and 345 output tokens including 98 thinking tokens. Local incremental estimate: $0.003988; cumulative local exposure including prior reserves: $56.926158, with 1,632 generation and 1,554 count attempts. Provider billing has not been reconciled.

Artifacts: `contract.json`, `challenge_packet_v0001.json`, `canary.json`, `outcome.json`, `summary.json`, `effects.sqlite3`, `accounting-checkpoint.json`, and raw response quarantine `raw/`. The challenge is an agent review, not an external seal.
