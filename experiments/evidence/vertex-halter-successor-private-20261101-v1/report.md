# Halter–Formatter successor — 2026-11-01

## Русский

Halter prompt версии `faithful-v3-prompts-5` поручает оценивать содержательный ответ и сохранять ограничения задачи, но не требовать цитаты до Formatter. Это изменение проверено офлайн; решения в фикстурах заданы сценарием и не доказывают поведения реальной модели.

Повтор на том же замороженном синтетическом случае завершился `technical_failure / unstructured text span is duplicate or out of bounds`. Source decision выбрал сохранённый tally. Selection предложил для правила `[147,226)` при длине текста 220, и для tally `[154,217)` при длине 209. Контроллер отверг оба неверных диапазона; Inference, Halter, Value и Formatter в этом прогоне не вызывались. Поэтому реальное влияние исправления Halter пока не проверено. Предыдущий `unknown` остаётся отдельным результатом.

Обе генерации и оба countTokens дали HTTP 200; не было 429, повторов или неопределённых исходов. Новый расход по usage $0.001732; первая проверка $0.003988, вместе $0.005720. Общий локальный учёт с прежними резервами $56.927890, 1 634 генерации и 1 556 countTokens. Проверка счёта провайдера не выполнена.

## English

The `faithful-v3-prompts-5` Halter instruction assesses substantive sufficiency and retains factual constraints while leaving citations to Formatter. Offline scripted tests verify routing, not the live model’s semantics.

The repeat on the same frozen synthetic case ended `technical_failure / unstructured text span is duplicate or out of bounds`. Source decision retrieved the saved tally. Selection proposed `[147,226)` against rule text length 220 and `[154,217)` against tally text length 209. The controller rejected the invalid spans; Inference, Halter, Value and Formatter did not run. The live effect of the Halter fix therefore remains untested. The prior `unknown` remains a separate result.

Two generation and two countTokens attempts all returned HTTP 200; no 429, retries or uncertain effects. Incremental usage estimate: $0.001732; the first check cost $0.003988, combined $0.005720. Cumulative local exposure including earlier reserves is $56.927890, with 1,634 generation and 1,556 countTokens attempts. Provider billing is not reconciled.

Artifacts: `contract.json`, `challenge_packet_v0001.json`, `outcome.json`, `summary.json`, `effects.sqlite3`, `accounting-checkpoint.json`, `raw/`. The challenge is agent-authored and not an external seal.
