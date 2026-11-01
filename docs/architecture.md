# Faithful Engine architecture / Архитектура Faithful Engine

## English

This diagram describes the local `faithful_v3` research controller and its saved-source replay, not a deployed FitCheck product. Each named model role is a separate callback request; an offline test can substitute scripted responses. Python validates the shape of inputs and outputs, routes calls, records provenance and bounds the work. It does not replace the model roles or establish semantic truth.

```mermaid
flowchart TD
    U["User target and prepared task"] --> R["Saved-source replay: available actions and observed responses"]
    R --> D["Model role: source decision"]
    D -->|"Choose allowed action"| R
    D -->|"STOP"| S
    R -->|"No actions left"| S
    D -->|"UNKNOWN / failure"| O
    S["Selection: question and available statements → source spans or derived IDs"] --> I["Inference: selected premise texts only"]
    I --> H["Halter: question and current inference"]
    H --> V["Value: score candidate branch"]
    H -. "unverified branch-local feedback, if continued" .-> S
    V -->|"Bounded beam; continue"| S
    V -->|"Select halted branch"| F["Formatter: final inference and allowed citation IDs"]
    F --> O["Proposed answer, unknown, or technical failure"]
    S -.-> T["Trace: role calls, branches, evidence IDs and provenance"]
    I -.-> T
    H -.-> T
    V -.-> T
    F -.-> T
    D -.-> E["Optional journaled callback: role request and operation receipt"]
    S -.-> E
    I -.-> E
    H -.-> E
    V -.-> E
    F -.-> E
    O --> J["Separate review / human judgment"]
    T --> J
```

The acquisition loop reads previously saved source responses; it is not live market or news retrieval. Source hashes identify saved inputs, not independent verification. Inference is given only selected premises plus its fixed instruction, but the model retains its learned knowledge. The v3 formatter receives the final inference and allowed citation IDs; an earlier prototype has a different formatter context.

Halter feedback is passed only to the next Selection on the same continuing branch as an unverified observation; it is not a source fact or an Inference input. Halter judges factual sufficiency and substantive constraints; Formatter supplies the final wording and citations. For structured saved responses, Selection proposes exact passage spans; the controller checks their bounds and payload-hash consistency, then supplies only the selected substring to Inference. For unstructured responses Selection may propose a verbatim quote, from which the controller derives Unicode offsets only if it matches uniquely. Historical numeric spans remain accepted. The view is raw text for nonblank string payloads and serialized JSON for objects, lists and blank strings. Whole-response selection remains an explicitly labelled fallback. Text-view offsets are not original-document offsets. Captured passage coordinates are source-reported; without the complete original document they cannot be independently verified. A matching substring does not establish semantic support.

When no final answer is produced, a structured explanation separates the recorded stop condition from an optional, unverified model assessment of the recorded inference and source references. The default v3/stop renderer uses per-view aliases for questions, sources, passages and branches, plus bounded call ordinals and offsets; it omits original IDs, hashes, model text, source text and user input. The explicit private view includes an alias key with sanitized display identifiers and SHA-256 fingerprints of the original IDs; these fingerprints can be linkable and the view may contain sensitive content. This is a limited projection, not a general guarantee that rendered material is safe to publish; bounded fields may be omitted or truncated, and the v1 renderer and opt-in views may include sensitive content.

An absent saved capture yields a scoped preflight `unknown` before any model callback; it is not a claim that the external source has no information. A callback timeout or connection failure is recorded as an interrupted callback with the effect not established; callback entry alone does not prove dispatch. Other callback failures retain a technical status and explicitly record that the effect is not established. The optional effect journal owns its own durable attempt states and only retries an explicitly authorized 429. The bounded view distinguishes call limits from depth limits.

The role outputs and trace are **unreviewed**, and a trace is not proof of entailment, causal faithfulness, factual correctness or alignment. An independent review and the human's own judgment remain separate. When a run stops for budget, invalid output or uncertainty, those outcomes must remain distinguishable. The offline demo uses scripted callbacks and is not evidence of model performance.

The optional `JournaledCallback` binds each v3 role request, including its fixed instruction, to a durable `EffectExecutor` operation. Use a unique, non-sensitive session ID per run; reuse it only to replay the identical ordered sequence. The adapter records a canonical role request, not the actual provider wire request. Its single-shot transport returns an `HttpResponse` whose body must be the role-output JSON object; the journal stores those returned bytes, which need not be the provider's original response. Disable retries in transport. The integration has only been tested with offline fixtures; it is not a Vertex adapter or proof of provider dispatch, billing, or response authenticity. A receipt is attached to its exact role call; default rendering hides operation IDs and hashes. Unknown outcomes are not automatically retried.

The separate `VertexJournal` bridges versioned role requests to Vertex request bodies and stores distinct count and generation effects and their raw responses before parsing. It needs caller-supplied single-shot transports, an explicit per-run budget and price configuration, and an optional, explicitly authorized 429 retry policy. Local reservations are estimates, not a provider-enforced account limit; the caller owns credential handling, endpoint binding, current rates, and cross-run accounting. It assumes one active worker. At commit `47fb684`, the public implementation completed one synthetic end-to-end Vertex run. This is a limited compatibility check, not a production reliability or semantic correctness guarantee.

## Русский

Диаграмма показывает локальный исследовательский контроллер `faithful_v3` и воспроизведение ранее сохранённых источников; это не развёрнутый продукт FitCheck. Каждая модельная роль — отдельный вызов через callback; в офлайн-тестах ответы могут быть заранее заданными. Python проверяет структуру, направляет вызовы, сохраняет происхождение и ограничивает выполнение. Он не заменяет модельные роли и не устанавливает истинность выводов.

Внешний цикл читает сохранённые ответы источников, а не получает новые данные рынков или новости. Хеш идентифицирует сохранённые входы, но не подтверждает их независимую достоверность. Inference получает только выбранные посылки и фиксированную инструкцию, хотя сохраняет знания, усвоенные моделью. Formatter версии v3 получает финальный вывод и допустимые идентификаторы источников; контекст formatter в более раннем прототипе отличается.

Замечание Halter передаётся только следующему Selection в той же продолжающейся ветви как непроверенное наблюдение; оно не становится фактом источника или входом Inference. Halter оценивает содержательную достаточность с учётом существенных ограничений, а окончательную формулировку и ссылки добавляет Formatter. Для структурированного сохранённого ответа Selection предлагает точные границы фрагмента; контроллер проверяет их и хеш сохранённых данных, после чего передаёт Inference только выбранный текст. Для неструктурированного ответа Selection может предложить буквальную цитату: контроллер вычисляет Unicode-координаты только при единственном совпадении. Прежние числовые диапазоны также поддерживаются. Представление содержит сохранённый текст непустой строки или сериализованный JSON для объектов, списков и пустых строк. Явно помеченный выбор всего ответа остаётся доступным. Координаты текстового представления не являются координатами исходного документа; координаты сохранённого отрывка сообщены источником и без полного оригинала не подтверждаются независимо. Совпадение текста не доказывает содержательную поддержку вывода.

Если итоговый ответ не получен, структурированное объяснение отделяет причину остановки от необязательной непроверенной модельной оценки записанного вывода и ссылок на источники. Отображение v3 и остановок по умолчанию использует локальные обозначения вопросов, источников, отрывков и ветвей с ограниченными номерами вызовов и координатами; исходные идентификаторы, хеши и тексты скрыты. Подробный приватный режим включает ключ с очищенными идентификаторами и SHA-256 исходных ID; хеши могут связывать записи, а сам режим — содержать чувствительные данные. Это ограниченная проекция, а не общая гарантия безопасности публикации: часть полей может быть пропущена или усечена, а отображение v1 и приватный режим могут содержать чувствительные данные.

Отсутствие сохранённого ответа даёт ограниченный `unknown` до вызова модели; это не утверждение об отсутствии информации у внешнего источника. Таймаут или разрыв соединения внутри callback записывается как прерванный callback с неустановленным эффектом; вход в callback не доказывает отправку запроса. Другие ошибки callback сохраняют технический статус и отдельную пометку, что эффект не установлен. Необязательный журнал эффектов ведёт свои устойчивые состояния попыток и повторяет только явно разрешённый 429. Безопасный вид различает лимит вызовов и лимит глубины.

Результаты ролей и трасса **не проверены содержательно**. Трасса не доказывает логическую корректность, причинную верность рассуждения, истинность фактов или соответствие ценностям человека. Независимая оценка и собственное суждение человека остаются отдельными. Исчерпание бюджета, некорректный ответ и неопределённость необходимо различать. Офлайн-демо использует заранее заданные ответы и не является результатом испытания модели.

Необязательный `JournaledCallback` связывает каждый запрос роли v3, включая фиксированную инструкцию, с устойчивой операцией `EffectExecutor`. Для каждого запуска нужен уникальный нечувствительный идентификатор сессии; повторно его можно использовать только для воспроизведения той же последовательности. Записывается канонический запрос роли, а не обязательно HTTP-запрос провайдеру. Однократный transport возвращает `HttpResponse` с JSON-объектом ответа роли; журнал хранит эти байты, которые не обязательно являются исходным ответом провайдера. Повторы в transport должны быть отключены. Интеграция проверена только на офлайн-фикстурах; она не является адаптером Vertex и не подтверждает отправку, биллинг или подлинность ответа провайдера. Квитанция привязана к конкретному вызову роли; обычный вид скрывает идентификаторы операций и хеши. Неопределённые операции автоматически не повторяются.

Отдельный `VertexJournal` преобразует версионированные запросы ролей в запросы Vertex и до разбора сохраняет раздельные операции подсчёта и генерации с их сырыми ответами. Вызывающая сторона предоставляет однократные transport-функции, явно задаёт бюджет и цены и при необходимости отдельно разрешает повтор 429. Локальные резервы являются оценкой, а не ограничением счёта у провайдера; вызывающая сторона отвечает за учётные данные, адреса, актуальные тарифы и общий учёт между запусками. Компонент рассчитан на одного исполнителя. Публичная версия в коммите `47fb684` прошла один сквозной вызов Vertex на синтетическом примере. Это ограниченная проверка совместимости, а не гарантия промышленной надёжности или содержательной правильности.
