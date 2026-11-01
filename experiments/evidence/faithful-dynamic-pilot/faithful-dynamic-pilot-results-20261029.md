# FitCheck: Faithful-style и динамические источники — результаты пилота

Серия с исправленным протоколом завершена: 32/32 слота; 22 непроверенных предложения, 5 unknown, 4 результата по случаю с неразрешённым конфликтом источника и 1 техническая ошибка. Это исследовательский прогон после наблюдения части результатов предыдущей серии, а не подтверждающий blind holdout. Предложенные парные оценки не являются независимо проверенными golden.

Важнейший результат для исходной гипотезы: во всех 24 слотах B, B_self_check и C был выбран источник `manual-rules`; `news` через Orthogonal не выбран ни разу. Все восемь новостных ответов были получены заранее за плату, однако ни один не попал в выбранный model replay. Поэтому этот эксперимент не измерил добавочную ценность свежих новостей относительно уже доступных правил рынка. Выбор источника ограничивался одним действием, и правила рынка конкурировали с новостями за единственный выбор.

Формат таблицы: `manual-rules` — точные сохранённые market rules, `—` — запрос источника не выбран; предложения моделей не являются проверенной истинностью. `unknown/no vector` — контроллер не смог выдать полный вектор; техническая ошибка тоже не является семантической оценкой. Число вызовов относится к генерациям в данном слоте.

| Слот | Кейс | Ветвь | Выбранный источник | Предложение | Статус | Вызовы |
|---:|---|---|---|---|---|---:|
| 00 | case-01 | A | — | weak_proxy | unassessed_source_conflict | 2 |
| 01 | case-01 | B | manual-rules | weak_proxy | unassessed_source_conflict | 2 |
| 02 | case-01 | B_self_check | manual-rules | weak_proxy | unassessed_source_conflict | 3 |
| 03 | case-01 | C | manual-rules | unknown | unassessed_source_conflict | 6 |
| 04 | case-02 | B | manual-rules | weak_proxy | proposal_unreviewed | 2 |
| 05 | case-02 | B_self_check | manual-rules | weak_proxy | proposal_unreviewed | 3 |
| 06 | case-02 | C | manual-rules | weak_proxy | proposal_unreviewed | 6 |
| 07 | case-02 | A | — | weak_proxy | proposal_unreviewed | 2 |
| 08 | case-05 | B_self_check | manual-rules | weak_proxy | proposal_unreviewed | 3 |
| 09 | case-05 | C | manual-rules | unknown/no vector | unassessed_unknown | 6 |
| 10 | case-05 | A | — | weak_proxy | proposal_unreviewed | 3 |
| 11 | case-05 | B | manual-rules | weak_proxy | proposal_unreviewed | 2 |
| 12 | case-06 | C | manual-rules | weak_proxy | proposal_unreviewed | 6 |
| 13 | case-06 | A | — | weak_proxy | proposal_unreviewed | 3 |
| 14 | case-06 | B | manual-rules | weak_proxy | proposal_unreviewed | 2 |
| 15 | case-06 | B_self_check | manual-rules | weak_proxy | proposal_unreviewed | 3 |
| 16 | case-07 | A | — | unknown | unassessed_unknown | 2 |
| 17 | case-07 | B | manual-rules | weak_proxy | proposal_unreviewed | 2 |
| 18 | case-07 | B_self_check | manual-rules | weak_proxy | proposal_unreviewed | 3 |
| 19 | case-07 | C | manual-rules | unknown | unassessed_unknown | 6 |
| 20 | case-03 | B | manual-rules | direct | proposal_unreviewed | 2 |
| 21 | case-03 | B_self_check | manual-rules | direct | proposal_unreviewed | 3 |
| 22 | case-03 | C | manual-rules | direct | proposal_unreviewed | 6 |
| 23 | case-03 | A | — | unknown | unassessed_unknown | 2 |
| 24 | case-08 | B_self_check | manual-rules | weak_proxy | proposal_unreviewed | 3 |
| 25 | case-08 | C | manual-rules | weak_proxy | proposal_unreviewed | 6 |
| 26 | case-08 | A | — | — | technical_failure | 1 |
| 27 | case-08 | B | manual-rules | weak_proxy | proposal_unreviewed | 2 |
| 28 | case-04 | C | manual-rules | indirect | proposal_unreviewed | 6 |
| 29 | case-04 | A | — | unknown | unassessed_unknown | 2 |
| 30 | case-04 | B | manual-rules | weak_proxy | proposal_unreviewed | 2 |
| 31 | case-04 | B_self_check | manual-rules | weak_proxy | proposal_unreviewed | 3 |

## Содержание кейсов

- **case-01 (dev):** The Federal Reserve does not decrease the upper limit of the Federal Funds target rate range at any point prior to January 1, 2028, as resolved by official Federal Reserve Board of Governors releases.
- **case-02 (dev):** Anthropic is officially valued at $1,000,000,000,000 ($1 Trillion) or more in a primary funding round or at its initial public offering (IPO) by December 31, 2026, according to SEC filings or major financial press.
- **case-03 (test):** В одном из отчётов CPI за 2026 год годовая инфляция превысит 4,2%.
- **case-04 (test):** Итоговая пересмотренная оценка World Bank доли США в мировом ВВП за 2026 год превысит 25,7%.
- **case-05 (test):** Обозначение Anthropic как риска для цепочки поставок будет полностью отменено до 2027 года.
- **case-06 (test):** Claude 6+ станет публично доступна бесплатным пользователям до 31 декабря 2026 года.
- **case-07 (test):** Первая непредварительная оценка BEA номинального ВВП США за 2026 год превысит $32,8 трлн.
- **case-08 (test):** OpenAI или Anthropic публично продемонстрирует независимо подтверждённое рекурсивное самоулучшение до 2027 года.

## Что видно в trace

- **case-04:** C обнаружил различие между первой публикацией World Bank в правилах рынка и окончательной пересмотренной оценкой в тезисе, но formatter предложил `indirect`. В сохранённом trace нет объяснения, почему различие считается несущественным; это кандидат на проверку возможной ложной уверенности, а не подтверждённая ошибка.
- **case-05:** C зафиксировал, что рынок может разрешиться Yes при waiver или изменении директивы, хотя тезис требует полной отмены. Но formatter вернул пустой вектор; система сохранила `unknown / incomplete_contract_vector`, а не восстановила отсутствующий ответ.
- **case-03:** A предложил `unknown`; B, B_self_check и C после чтения правил предложили `direct`. Это описание различия при предоставлении сохранённых правил, не доказательство точности и не тест новостей Orthogonal.
- **case-01:** во всех четырёх результатах сохранён статус `unassessed_source_conflict`: расхождение в примере rules_secondary для Fed остаётся неразрешённым.
- **case-08/A:** модель выбрала корректный `stop`, но вернула `expectation: null`, тогда как валидатор требовал строку. Возник `ProtocolError`; это проблема совместимости протокола, не установленная семантическая ошибка модели.

## Расходы и учёт

- Предыдущий консервативный перенос до текущего исследования: **$0.721593**; он включает прежние резервы и не равен подтверждённому счёту провайдера.
- Восемь Orthogonal source calls: **$0.016000**, все оплаченные и сохранённые. Затраты или тариф Grok при ручном получении Kalshi неизвестны.
- Остановленная первая модельная серия: **$0.059974** по учтённым usage; 16 генераций и 16 countTokens; 9 слотов начаты, 23 не начаты. Остановлена после повторяющихся ошибок формата выбора источника.
- Исправленный successor: **$0.413023** по учтённым usage; 105 генераций и 105 countTokens. Начисления countTokens в журнале $0. Провайдерский invoice не сверялся.
- Общая консервативная exposure: **$1.210590 из лимита $40**; суммарно 200 генераций, 132 countTokens и 8 source attempts. В завершённой текущей серии неопределённых effects и удержанных резервов нет. В старом переносе ранее учтённые резервы сохраняются.

## Границы интерпретации

Kalshi JSON и время/статус были переданы пользователем со слов Grok; прямой транспорт независимо не подтверждён. UI-цена Orthogonal — наблюдение оператора, а не гарантия провайдера. Первый news response вернул 10 результатов при запросе num=3; после наблюдения дефекта зафиксирована детерминированная проекция первых трёх в порядке провайдера с сохранением полного raw. Это post-hoc поправка, не эквивалент server-side num=3. Относительные даты оставлены как получены.

Два development-кейса используют прежние согласованные формулировки, шесть test-кейсов утверждены пользователем как тезисы, но не имеют независимой pair-label adjudication. Повторная серия запущена после просмотра части предыдущих результатов и исправления prompt, поэтому сравнение является исследовательским. Для теста свежих данных целесообразно обеспечить market rules всем ветвям и отдельно варьировать доступ к неизменённым актуальным новостным данным; при этом отнести результат к исследованию Шанахана через проверяемую декомпозицию и локальную трассу, не приписывая Faithful-style контроллеру доказанной точности.
