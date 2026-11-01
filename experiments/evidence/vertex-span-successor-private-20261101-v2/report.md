# Vertex span-selection successor — 2026-11-01

## Русский

Технический сквозной gate прошёл на том же синтетическом случае. Источник выбран и открыт; Selection выбрал две точные цитаты из сохранённого текста. Код нашёл по единственному буквальному совпадению диапазоны правила [139,218) и фактического итога [146,207), в Unicode code points по сохранённому JSON-представлению, не по исходному документу. Проверка цитаты доказывает совпадение с сохранённым текстом, а не достоверность или entailment.

Inference получил только две цитаты и вывел: “Batch LARK-7 did not meet the target.” Halter ответил sufficient=true: “The inference directly assesses and negates the thesis that Batch LARK-7 met its target.” Formatter вернул этот ответ и обе допустимые ссылки. Value=1.0 — непроверенная модельная оценка. Правило требует как минимум 7 из 10; итог 6 из 10, поэтому ответ согласуется с синтетическими данными. Это один пример, не сравнительное исследование моделей и не доказательство общей надёжности системы.

6 генераций и 6 countTokens, все 12 ответов HTTP 200/STOP, 0 429, 0 uncertain и 0 повторов. Использовано 3 814 входных и 648 выходных токенов, включая 331 thinking. Новая оценка по usage $0.005293. Все три запуска этой проверки: 14/14 генераций, 14/14 countTokens и $0.011013 из $2.50. Общий локальный учёт с прежними резервами $56.933183 (1 640 генераций, 1 562 countTokens); Google invoice не сверён.

Основной offline suite: 196 passed, 51 subtests. Неадаптированный исторический тестовый файл содержит 15 failures/subfailures из-за несовместимости исторических фикстур с текущим протоколом и старой метки timeout; адаптер исторических тестов показывает 17 passed и 1 явный skip.

## English

The technical end-to-end gate passed on the same synthetic case. Source decision retrieved the saved tally; Selection supplied two exact verbatim quotes. The controller derived unique Unicode code-point ranges [139,218) and [146,207) in the saved JSON representation, not the original document. Exact matching establishes consistency with saved text, not truth or entailment.

Inference received only the selected premises and concluded that the batch did not meet the target. Halter marked the inference sufficient and Formatter returned the answer with both allowed source IDs. Value=1.0 is an unverified model assessment. The rule requires at least 7 of 10 checks, while the tally reports 6; the answer is consistent with this synthetic fixture. This is one example, not comparative evidence or proof of general reliability.

Six generation and six countTokens operations completed with HTTP 200 and STOP; no 429, uncertain effects, or retries. Usage: 3,814 input and 648 output tokens including 331 thinking. Local incremental estimate $0.005293. Across all three checks the cap is fully consumed: 14/14 generation and count attempts, $0.011013 of $2.50. Cumulative local exposure with prior reserves: $56.933183; 1,640 generation and 1,562 count attempts. Provider invoice not reconciled.

Offline suite: 196 tests and 51 subtests passed. The unadapted historical test file has 15 failures/subfailures due to legacy fixtures and the superseded timeout label; the compatibility adapter reports 17 passes and one explicit skip.

Artifacts: contract.json, challenge_packet_v0001.json, outcome.json, summary.json, effects.sqlite3, accounting-checkpoint.json, frozen-code/, and raw/. The challenge is agent-authored and not an external seal.
