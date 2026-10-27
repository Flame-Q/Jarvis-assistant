# Architecture Decision Records

Короткие записи о значимых архитектурных решениях. Формат: контекст →
варианты → решение → последствия. Все ADR приняты в версии 1.0.

| ADR | Решение | Ключевые требования |
|---|---|---|
| [0001](0001-stt-faster-whisper.md) | faster-whisper small int8 для STT | FR-2, NFR-2, NFR-7 |
| [0002](0002-tts-pyttsx3.md) | Windows SAPI5 как офлайн-TTS, pyttsx3 fallback, edge-tts опционально | FR-3, FR-9, NFR-7 |
| [0003](0003-wakeword-openwakeword.md) | openWakeWord `hey_jarvis`, окна 80 мс | FR-1, NFR-1, NFR-7 |
| [0004](0004-llm-ollama.md) | Ollama + qwen2.5:3b-instruct через OpenAI API | FR-7, FR-10, NFR-6 |
| [0005](0005-gui-pyside6.md) | PySide6 для трея и настроек, консольный fallback | FR-13, FR-14, NFR-4 |
| [0006](0006-storage-sqlite.md) | SQLite + репозитории | FR-12, FR-14 |
| [0007](0007-push-to-talk.md) | Push-to-talk кнопкой/`Ctrl+Alt+Space`, wake word отключаемый | FR-16, FR-1, NFR-5 |

## Что сознательно не выбрано

- **Picovoice Porcupine** — бесплатный тариф закрыт 30.06.2026, требуется ключ.
- **LangChain** — избыточная зависимость для двух вызовов LLM; запрещена
  условиями проекта.
- **Облачные LLM** — нарушают офлайн-режим и приватность обязательной части.
- **PyTorch/Silero** — тяжёлая зависимость без необходимости для TTS.
- **JSON вместо SQLite** — гонки и отсутствие запросов при истории/заметках.
