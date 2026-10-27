# Итоговый отчёт по проекту «Джарвис»

## 1. Аннотация

«Джарвис» — локальный голосовой ассистент для Windows 10/11 на Python 3.10.
Он активируется фразой «Хей, Джарвис» или `Ctrl+Alt+J`, распознаёт русскую
речь, выполняет команды ПК, озвучивает ответы и ведёт диалог с локальной
моделью `qwen2.5:3b-instruct` через Ollama. Обязательная часть работает
офлайн, без API-ключей и аккаунтов; сеть нужна только для погоды и веб-поиска.

Проект выполнен в рамках дисциплины «Технологии проектирования программного
обеспечения». Использованы слоистая архитектура, FSM, EventBus, SkillRegistry
и паттерны Facade, State, Command, Strategy, Adapter, Observer, Registry/Factory,
Repository.

## 2. Этапы

| Этап | Содержание | Артефакты | Проверка |
|---|---|---|---|
| P0 | Анализ, требования, выбор технологий | `docs/requirements.md`, ADR 0001–0004 | MoSCoW, FR/NFR, use cases |
| P1 | Каркас: конфиг, логирование, модели, EventBus, FSM, реестр, роутер, репозитории, CLI | `src/jarvis/core`, `storage`, `config.py`, `app.py` | unit-тесты ядра, mypy |
| P2 | Аудио: микрофон, VAD, wake word, STT, TTS, голосовой цикл | `audio/`, `providers/stt`, `providers/tts` | синтетические WAV, замеры |
| P3 | Локальная LLM, гибридная маршрутизация, tool calling, стриминг | `providers/llm`, `skills/chat.py`, `core/assistant.py` | ответ Ollama, тесты degraded |
| P4 | Навыки ПК, погода, таймеры, громкость, скриншоты, заметки, питание, shell | `skills/`, `os_win/` | 74 теста, ручной чек-лист |
| P5 | Трей, пульт push-to-talk, настройки, горячие клавиши, упаковка | `ui/`, `pyproject.toml`, `requirements.txt` | запуск трея, скриншот GUI |
| P6 | Тестовая документация, UML, ADR, руководства, финальный QA | `docs/`, `README.md` | ruff, mypy, pytest, 92 % core |

## 3. Архитектура

```
Presentation  ui/tray.py, ui/settings_window.py, ui/control_window.py, ui/hotkeys.py
Application   core/assistant.py (Facade), core/fsm.py, core/router.py,
              core/registry.py, skills/*
Domain        core/models.py, core/events.py, core/errors.py
Infrastructure audio/, providers/, os_win/, storage/, config.py
```

- `AssistantService` — фасад: маршрутизация, подтверждения, озвучка,
  деградация при недоступной LLM.
- `AssistantFSM` — состояния `IDLE`, `LISTENING`, `ROUTING`, `THINKING`,
  `SPEAKING`, `MUTED`, `ERROR`; переходы проверяются.
- `IntentRouter` — правила и RapidFuzz; при неуверенности — tool calling LLM,
  затем обычный чат.
- `SkillRegistry` — регистрация навыков и генерация JSON-схем инструментов.
- `EventBus` — слабая связанность UI, FSM и голосового цикла.
- `storage/repositories.py` — SQLite: история, команды, заметки, таймеры.

UML: `docs/uml/` (use case, компоненты, классы, 3 последовательности,
состояния, деятельность, развёртывание, ER). ADR: `docs/adr/`.

## 4. Что реализовано

- Wake word `hey_jarvis` (openWakeWord ONNX), `Ctrl+Alt+J` или push-to-talk
  кнопка «Говорить» / `Ctrl+Alt+Space`; wake word можно отключить в настройках.
- STT faster-whisper small int8, VAD 800 мс, авто-запись до 12 с,
  push-to-talk — до 60 с.
- TTS Windows SAPI5 (прямой `SAPI.SpVoice`), русский голос, очередь и остановка;
  `pyttsx3` оставлен резервным провайдером.
- LLM Ollama через OpenAI-совместимый API, стриминг по предложениям,
  tool calling, история 12 реплик, degraded-режим.
- Навыки: запуск программ (алиасы, меню Пуск, UWP, PATH, URI), погода
  Open-Meteo, таймеры/напоминания, громкость, скриншоты, время/дата, поиск,
  заметки, блокировка/выключение/перезагрузка, shell (выключен).
- Подтверждения опасных действий, команда «стоп», «заверши работу».
- Трей, окно «Пульт микрофона», окно настроек с сохранением `config/config.toml`,
  история.
- 10 UML-диаграмм, 7 ADR, требования, архитектура, тестирование, руководства.

## 5. Итоговые проверки

Окружение: Windows 10.0.26200, Python 3.10.0, 16 ГБ RAM, Ollama 0.40.11.

```text
ruff check .            All checks passed!
mypy src                Success: no issues found in 52 source files
pytest -q               74 passed
coverage jarvis.core    92 % (374 stmts, 29 miss)
pip check               No broken requirements found
```

Ключевые замеры:

- wake word: score 0.999, порог 0.4 пересечён на 0.72 с синтетического клипа;
  CPU ~2.4 % одного ядра;
- STT: холодный старт 3.42 с, тёплое распознавание 1.51 с для 3.7-с фразы;
- правила: 0.157 мс на команду;
- LLM: первый токен 2.52 с, полный короткий ответ 2.76 с;
- RSS после прогрева Whisper и wake word — 524 МБ; модель Ollama — 2163 МБ.

Подробности и ручной чек-лист: `docs/testing.md`.

## 6. Ограничения

- Barge-in не реализован: микрофон приостановлен во время речи, «стоп»
  работает, когда ассистент молчит.
- Whisper не потоковый: текст появляется после конца фразы.
- Wake word обучен на английском «hey jarvis»; русское произношение может
  не срабатывать, есть hotkey и настройка порога. Для шумной аудитории
  предусмотрен push-to-talk: кнопка «Говорить» или `Ctrl+Alt+Space`,
  а wake word отключается в настройках.
- Погода и веб-поиск требуют интернета; остальное работает офлайн.
- Сложные действия внутри приложений (каналы Discord, сообщения) не входят.
- Таймеры после перезапуска не догоняются (ограничение documented).
- UWP-приложения зависят от `explorer.exe shell:AppsFolder`; часть может
  не реагировать.
- Реальный микрофон и акустика проверяются пользователем по E2E-чек-листу;
  в автоматических тестах используются синтетические WAV и фейки.

## 7. Запуск и демонстрация

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
ollama pull qwen2.5:3b-instruct
.venv\Scripts\python.exe scripts\download_models.py
.venv\Scripts\python.exe -m jarvis --tray
```

Демо: «Хей, Джарвис» → «открой дискорд» → «открой хром» → «какая погода в
Москве» → «таймер на 5 минут» → «громкость 30» → «сделай скриншот» →
«объясни, что такое инкапсуляция» → «стоп».

## 8. Структура репозитория

```
src/jarvis/   core, audio, providers, skills, os_win, storage, ui
tests/        74 автотеста без микрофона и сети
docs/         требования, архитектура, UML, ADR, тестирование, руководства
scripts/      скачивание моделей, проверка wake word/TTS
config/       пример конфигурации
```

Лицензия MIT.
