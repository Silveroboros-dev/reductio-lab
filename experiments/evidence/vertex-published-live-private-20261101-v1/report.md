# Published Vertex bridge: end-to-end check — 2026-11-01

## Русский

Опубликованный commit `47fb684` прошёл один технический сквозной прогон на Gemini 3.8 Flash / Vertex global; результат `proposal`, gate `passed`. Все данные синтетические. Независимая содержательная оценка остаётся pending; это не сравнительный эксперимент и не подтверждение общей надёжности.

Исходный тезис: Batch LARK-7 met its final audit target. Правило: цель достигнута только если прошли не менее 7 из 10 проверок. Сохранённый итог: прошли 6 из 10. Source decision открыл сохранённый итог; Selection выбрал две точные цитаты, границы [139,218) и [146,207) относятся к сохранённому JSON-тексту. Inference получил только эти посылки.

Финальный ответ Formatter: “Batch LARK-7 did not meet the target because only 6 of the 10 final checks passed, which is fewer than the required minimum of 7.” Ссылки: `source:synthetic-final-tally-lark7-v1`, `source:synthetic-rule-lark7-v1`. Halter определил вывод как достаточный; это оценка модели, не независимое подтверждение. Value=1.0 также оценка модели. Глубина зависимости — один шаг Inference.

Шесть генераций и шесть countTokens, все HTTP 200, 0 повторов, 0 429, 0 uncertain, 0 вызовов внешних источников. Токены: вход 3,883, выход 1,149, включая 790 thinking. Оценка по usage: $0.007223; предыдущий локальный учёт с резервами $56.933183, итог $56.940406 из $60; 1,646 генераций и 1,568 countTokens суммарно. Invoice не сверён; резерв не является provider-enforced billing cap.

Офлайн: чистая git-архивная копия публичного коммита 224 passed + 51 subtests; отдельная private harness 9 passed. Independent post-run agent audit сопоставил все 12 raw HTTP bodies, receipts, hashes, usage и SQLite, подтвердил ограничения ролей и данных. Agent review и хеши не являются независимой внешней печатью.

## English

Published commit `47fb684` passed one technical end-to-end check through Vertex using Gemini 3.8 Flash/global: result `proposal`, gate `passed`. All case data are synthetic. Independent semantic review remains pending; this is not a comparative experiment or evidence of general reliability.

The rule requires at least 7 out of 10 final checks; the saved tally reports 6. Source decision retrieved the tally and Selection chose two verbatim quotes. The saved JSON-text ranges are [139,218) and [146,207), not independently verified original-document offsets. Inference received only the selected premises.

Formatter answer: “Batch LARK-7 did not meet the target because only 6 of the 10 final checks passed, which is fewer than the required minimum of 7.” It cited both synthetic source IDs. Halter said sufficient; Value scored 1.0. Both are unverified model outputs. The dependency trace contains one Inference step.

Six generation and six countTokens attempts returned HTTP 200; no retry, 429, uncertain effect, or external source call. Usage: 3,883 input and 1,149 output tokens including 790 thinking. Estimated new cost $0.007223; cumulative local exposure with earlier reserves $56.940406 of $60, 1,646 generation and 1,568 countTokens attempts. Provider invoice not reconciled; local reservations do not enforce provider billing.

Offline: 224 tests and 51 subtests passed from a clean git archive; 9 private harness tests passed. An independent agent checked all 12 raw response/receipt hashes, journal entries, usage and role projections. Agent review and hashes do not constitute an external seal.

Artifacts: contract.json, challenge_packet_v0001.json, frozen-harness.py, case-allowlist.json, dispatch.json, outcome.json, summary.json, effects.sqlite3, accounting-checkpoint.json and raw/.
