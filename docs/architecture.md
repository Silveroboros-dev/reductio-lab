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
    O --> J["Separate review / human judgment"]
    T --> J
```

The acquisition loop reads previously saved source responses; it is not live market or news retrieval. Source hashes identify saved inputs, not independent verification. Inference is given only selected premises plus its fixed instruction, but the model retains its learned knowledge. The v3 formatter receives the final inference and allowed citation IDs; an earlier prototype has a different formatter context.

Halter feedback is passed only to the next Selection on the same continuing branch as an unverified observation; it is not a source fact or an Inference input. For structured saved responses, Selection proposes exact passage spans; the controller checks their bounds and payload-hash consistency, then supplies only the selected substring to Inference. For unstructured responses, whole-response selection remains available and is labelled accordingly. Captured passage coordinates are source-reported; without the complete original document they cannot be independently verified. A matching substring does not establish semantic support.

When no final answer is produced, a structured explanation separates the recorded stop condition from an optional, unverified model assessment of the current inference and source references. The default v3/stop renderer omits model text, source text, and user input; callers may opt in to a detailed private view. This is a limited projection, not a general guarantee that rendered material is safe to publish: hashes can be linkable, and the v1 renderer and opt-in views may include sensitive content.

The role outputs and trace are **unreviewed**, and a trace is not proof of entailment, causal faithfulness, factual correctness or alignment. An independent review and the human's own judgment remain separate. When a run stops for budget, invalid output or uncertainty, those outcomes must remain distinguishable. The offline demo uses scripted callbacks and is not evidence of model performance.

## Русский

Диаграмма показывает локальный исследовательский контроллер `faithful_v3` и воспроизведение ранее сохранённых источников; это не развёрнутый продукт FitCheck. Каждая модельная роль — отдельный вызов через callback; в офлайн-тестах ответы могут быть заранее заданными. Python проверяет структуру, направляет вызовы, сохраняет происхождение и ограничивает выполнение. Он не заменяет модельные роли и не устанавливает истинность выводов.

Внешний цикл читает сохранённые ответы источников, а не получает новые данные рынков или новости. Хеш идентифицирует сохранённые входы, но не подтверждает их независимую достоверность. Inference получает только выбранные посылки и фиксированную инструкцию, хотя сохраняет знания, усвоенные моделью. Formatter версии v3 получает финальный вывод и допустимые идентификаторы источников; контекст formatter в более раннем прототипе отличается.

Замечание Halter передаётся только следующему Selection в той же продолжающейся ветви как непроверенное наблюдение; оно не становится фактом источника или входом Inference. Для структурированного сохранённого ответа Selection предлагает точные границы фрагмента; контроллер проверяет их и хеш сохранённых данных, после чего передаёт Inference только выбранный текст. Неструктурированный ответ можно выбрать целиком с соответствующей пометкой. Координаты фрагмента сообщены источником; без полного оригинала их нельзя независимо подтвердить. Совпадение текста не доказывает содержательную поддержку вывода.

Если итоговый ответ не получен, структурированное объяснение отделяет причину остановки от необязательной непроверенной модельной оценки текущего вывода и ссылок на источники. Отображение v3 и остановок по умолчанию исключает текст модели, источника и пользовательского запроса; подробный приватный режим включается явно. Это ограниченная проекция, а не общая гарантия безопасности публикации: хеши могут быть связываемыми идентификаторами, а отображение v1 и приватный режим могут содержать чувствительные данные.

Результаты ролей и трасса **не проверены содержательно**. Трасса не доказывает логическую корректность, причинную верность рассуждения, истинность фактов или соответствие ценностям человека. Независимая оценка и собственное суждение человека остаются отдельными. Исчерпание бюджета, некорректный ответ и неопределённость необходимо различать. Офлайн-демо использует заранее заданные ответы и не является результатом испытания модели.
