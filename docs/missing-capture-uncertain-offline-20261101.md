# Missing captures and uncertain callbacks / Отсутствующие ответы и неопределённые вызовы

## English

The successor returns a scoped `unknown` if a validated replay catalog lacks a required saved capture, before any model callback. This says nothing about whether the original external source contains the information. Corrupt hashes, invalid bindings, duplicate rows and stale input identities remain distinct errors, not missing-capture outcomes.

A timeout or connection error inside a model callback is classified as an interrupted callback, stops without retry and records that the callback effect is not established. Callback entry is not proof of network dispatch, and the controller does not infer an external ledger receipt. Other callback exceptions retain a technical-failure status plus the same effect-state note. The separate effect executor's durable journal was tested with a connection reset: its started attempt remained uncertain on restart and was not retried. Only an explicitly authorized 429 can take the bounded retry path. The redacted view distinguishes depth, generation-call and episode-call limits.

Offline tests exercise two genuinely different saved observations with scripted selection/inference and an explicitly unverified conflicting assessment. They check that both source references survive without automatic averaging; this does not establish that a live model recognizes a contradiction. Separate fixtures cover absent captures, no supplied evidence, tampered hashes and bindings, callback failures, local errors and stop labels. The scoped suite passed 127 tests and 38 subtests; of 18 historical checks using the fixture adapter, 17 passed and one was explicitly skipped because it asserts the predecessor timeout label. The successor behavior is checked separately. The 12-case saved-source audit again checked 30 responses and 94 passages. No model or source calls were made. Original-document coordinates and model accuracy remain unverified.

The source-loop and strict-controller versions are successors; the prior run contracts and evidence are not rewritten or resumable with this implementation. Tests use synthetic callbacks and the historical private inputs as disclosed in [the prior offline check](span-unknown-offline-check-20261101.md).

The historical adapter requires the repository root on the import path: `PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 python3 notes/offline-span-regressions-20261101.py`.

## Русский

Если в проверенном каталоге воспроизведения отсутствует необходимый сохранённый ответ, новая версия возвращает ограниченный `unknown` до вызова модели. Это не говорит о том, содержит ли исходный внешний источник нужную информацию. Повреждённые хеши, неправильные привязки, дубли и несовпадение версии входа остаются отдельными ошибками, а не классифицируются как отсутствие ответа.

Таймаут или ошибка соединения внутри callback классифицируется как прерванный callback, останавливает выполнение без повтора и получает пометку, что эффект callback не установлен. Сам вход в callback не доказывает сетевую отправку; контроллер не выдумывает квитанцию внешнего журнала. Другие исключения callback сохраняют технический статус и отдельную пометку о неустановленном эффекте. Отдельный журнал эффектов проверен на разрыве соединения: начатая попытка осталась неопределённой после перезапуска и не повторилась. Ограниченный повтор возможен только для явно разрешённого 429. Безопасный вид различает ограничения глубины, числа генераций и общего числа вызовов.

Офлайн-тест использует два действительно разных сохранённых наблюдения, тестовые ответы Selection/Inference и явно непроверенную оценку конфликта. Он проверяет сохранение обеих ссылок на источники без автоматического усреднения, но не доказывает, что реальная модель распознает противоречие. Отдельные фикстуры проверяют отсутствие ответов и свидетельств, подмену хеша и привязок, ошибки callback, локальные ошибки и отображение причин остановки. В ограниченном наборе прошли 127 тестов и 38 подтестов; из 18 исторических проверок с адаптером фикстур 17 прошли, а одна явно пропущена, поскольку ожидает прежнюю метку таймаута. Новое поведение проверено отдельно. Повторная проверка 12 случаев охватила 30 ответов и 94 фрагмента. Вызовов модели и источников не было. Координаты в оригиналах и точность модели не подтверждены.

Версии внешнего цикла и контроллера изменены как версия-преемник; прежние контракты и данные не переписываются и не могут быть возобновлены на новой реализации. Тесты используют синтетические callbacks и закрытые исторические входы, как описано в [предыдущей проверке](span-unknown-offline-check-20261101.md).

Для исторического адаптера нужен корень репозитория в пути импорта: `PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 python3 notes/offline-span-regressions-20261101.py`.
