# Feedback and explained unknown: offline check / Офлайн-проверка

## English

This successor changes the strict controller and prompt versions. Negative Halter feedback reaches only the next Selection on the same branch as a model-authored, unverified observation. Inference still receives only selected premise texts and metadata. An `unknown` or technical stop is represented with a structured stop kind; recorded negative assessments are attributed to their branches and are not presented as verified facts.

The development check used 12 previously exposed C_v3 cases, including the original nominal GDP case. Historical model outputs were used **only as scripted fixtures**: the prompt version has changed, so these are not responses to the new prompt. The check reached the new branch-local feedback boundary in 8 cases and stopped before reusing a response to the altered Selection input. In 4 cases the scripted callback sequence completed without encountering that boundary. Separately, deterministic explanations reconstructed the recorded Halter assessments in all 7 historical `unknown` cases. The remaining 5 cases had historical proposals; no unknown explanation was asserted for them.

The harness checks the outcome-file hashes against the local run summary, but that summary is not an independent external seal. The underlying historical files remain private and are not included in the repository. These checks show data routing and attribution, not that the revised model would answer any case correctly or improve against a baseline. No model or source calls were made. The historical run and its frozen contract are unchanged; this code and prompt revision cannot resume that old run.

References in explanations identify whole saved responses. Exact passage selection and source-document offsets are not implemented; absence outside supplied material remains unknown. The scoped local replay harness is `notes/offline-feedback-replay-20261101.py` and takes the private run directory as its sole argument.

From the repository root, run `PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 python3 notes/offline-feedback-replay-20261101.py PRIVATE_RUN_DIR`.

## Русский

В этой версии изменены контроллер и версия промпта. Отрицательное замечание Halter передаётся только следующему Selection в той же ветви как непроверенное суждение модели. Inference по-прежнему получает только тексты выбранных посылок и их метаданные. Для `unknown` и технической остановки формируется структурированное описание типа остановки; сохранённые отрицательные оценки привязаны к ветвям и не выдаются за проверенные факты.

Для проверки использованы 12 ранее раскрытых случаев C_v3, включая nominal GDP. Старые ответы модели служили **только заранее записанными тестовыми ответами**: версия промпта изменилась, поэтому считать их ответами на новый промпт нельзя. В 8 случаях проверка дошла до границы с новым замечанием Halter и остановилась до использования ответа на изменённый вход Selection. В 4 случаях тестовая последовательность завершилась без такой границы. Отдельно детерминированное объяснение восстановило записанные замечания Halter во всех 7 прежних случаях `unknown`. Остальные 5 случаев ранее закончились предложенными ответами; объяснение `unknown` для них не заявлялось.

Проверка сверяет хеши файлов результатов с локальным summary серии, но этот summary не является независимым внешним закреплением. Исторические файлы остаются закрытыми и в репозиторий не включены. Проверка подтверждает маршрутизацию и атрибуцию, но не то, что новая модельная последовательность решила бы эти случаи или оказалась лучше baseline. Вызовов модели и источников не было. Историческая серия и её замороженный контракт не изменены; новая версия кода и промпта не может возобновлять прежний запуск.

Ссылки в объяснении указывают на сохранённые ответы целиком. Выбор точных фрагментов и проверка позиции в исходном документе не реализованы; отсутствие сведений за пределами переданного материала остаётся неизвестным. Локальный скрипт проверки `notes/offline-feedback-replay-20261101.py` принимает единственный аргумент — каталог закрытой серии.

Из корня репозитория команда запуска: `PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 python3 notes/offline-feedback-replay-20261101.py PRIVATE_RUN_DIR`.
