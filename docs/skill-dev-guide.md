# Разработка нового навыка

Навык — это изолированная команда (паттерн **Command**), которую ядро вызывает
через `SkillRegistry`. Новый навык не требует изменений в `AssistantService`,
FSM или роутере: достаточно добавить файл, зарегистрировать его и написать тесты.

## 1. Контракт `Skill`

```python
class Skill(Protocol):
    name: str
    description: str
    examples: list[str]
    args_model: type[BaseModel]
    requires_confirmation: bool

    def can_handle(self, text: str) -> float: ...
    def extract_args(self, text: str) -> BaseModel: ...
    def execute(self, args: BaseModel) -> SkillResult: ...
```

- `name` — уникальное имя, оно же имя tool для LLM.
- `description` и `examples` — подсказки роутеру и модели (по-русски).
- `args_model` — pydantic-модель; из неё автоматически строится JSON-схема
  инструмента и валидируются аргументы из LLM.
- `can_handle` — уверенность 0..1; проще всего наследовать `BaseSkill` и задать
  `triggers`.
- `extract_args` — преобразует текст в аргументы; не должен ходить в сеть/ОС.
- `execute` — выполняет действие и возвращает `SkillResult`; ловит свои ошибки.

## 2. Пример: свободное место на диске

Создайте `src/jarvis/skills/disk_space.py`:

```python
"""Disk space skill (example)."""

from __future__ import annotations

import re
import shutil

from pydantic import BaseModel

from jarvis.core.models import SkillResult
from jarvis.skills.base import BaseSkill, normalize_text


class DiskArgs(BaseModel):
    path: str = "C:\\"


class DiskSpaceSkill(BaseSkill):
    name = "disk_space"
    description = "Сообщить свободное место на диске."
    examples = ["сколько места на диске", "свободное место на C"]
    triggers = ["сколько места", "свободное место", "место на диске"]
    args_model: type[BaseModel] = DiskArgs

    def extract_args(self, text: str) -> DiskArgs:
        normalized = normalize_text(text)
        match = re.search(r"\b([a-z]):", normalized)
        path = f"{match.group(1).upper()}:\\" if match else "C:\\"
        return DiskArgs(path=path)

    def execute(self, args: BaseModel) -> SkillResult:
        assert isinstance(args, DiskArgs)
        try:
            usage = shutil.disk_usage(args.path)
        except OSError as exc:
            return SkillResult.failure(f"Не удалось проверить диск {args.path}: {exc}")
        free_gb = usage.free / 1024**3
        total_gb = usage.total / 1024**3
        return SkillResult.success(
            f"На диске {args.path} свободно {free_gb:.1f} из {total_gb:.0f} гигабайт."
        )
```

Код и docstring — на английском, пользовательские фразы — на русском.

## 3. Регистрация

В `src/jarvis/app.py` в `build_services()`:

```python
from jarvis.skills.disk_space import DiskSpaceSkill

registry.register(DiskSpaceSkill())
```

Порядок важен только при равных score: более специфичный навык регистрируется
раньше. Например, `AppLauncherSkill` стоит до `SearchWebSkill`, чтобы «открой
ютуб» запускало приложение, а не поиск. `ChatSkill` не регистрируется — это
fallback.

После регистрации навык автоматически:

- участвует в rule-based маршрутизации (триггеры + RapidFuzz);
- попадает в `registry.tool_schemas()` и доступен LLM через tool calling;
- логируется в `commands` (intent, args, status) при выполнении.

## 4. Тесты

Добавьте в `tests/test_skills_parsing.py`:

```python
def test_disk_space_args() -> None:
    skill = DiskSpaceSkill()
    assert skill.extract_args("сколько места на диске D").path == "D:\\"
    assert skill.extract_args("сколько места").path == "C:\\"


def test_disk_space_execute() -> None:
    result = DiskSpaceSkill().execute(DiskArgs(path="C:\\"))
    assert result.ok is True
    assert "свободно" in result.text
```

Если навык меняет состояние (пишет файл, шлёт запрос), используйте `tmp_path`
и фейки, как в `tests/conftest.py`. Не вызывайте реальные опасные действия.

Проверки:

```powershell
.venv\Scripts\python.exe -m ruff check .
.venv\Scripts\python.exe -m mypy src
.venv\Scripts\python.exe -m pytest -q
```

## 5. Опасные действия

Если навык может навредить, задайте:

```python
requires_confirmation = True
```

или динамически:

```python
def needs_confirmation(self, args: BaseModel) -> bool:
    assert isinstance(args, DiskArgs)
    return args.path.startswith("C:")
```

Ядро запомнит действие и спросит «да/нет». По умолчанию (молчание, «нет»,
«стоп») действие **не** выполняется. Пример — `SystemSkill` (выключение ПК) и
`ShellSkill`.

## 6. Соглашения и чек-лист

- [ ] Имя навыка уникально, в `snake_case`.
- [ ] Триггеры — короткие русские фразы; не пересекаются с существующими.
- [ ] `extract_args` не делает сетевых/дисковых вызовов и не бросает исключений
  на пустом тексте.
- [ ] `execute` ловит ожидаемые ошибки и возвращает `SkillResult.failure`.
- [ ] Нет `TODO`, `pass`-заглушек и хардкода путей с версиями.
- [ ] Нет секретов и глобальных синглтонов; зависимости — через конструктор.
- [ ] Windows-вызовы — только в `infrastructure/os_win`, если они специфичны.
- [ ] Есть тест на извлечение аргументов и на успешное выполнение.
- [ ] Обновлены README (команды), `requirements.md` (FR) и трассировка.
- [ ] `ruff`, `mypy`, `pytest` зелёные.

## 7. Tool calling: что видит LLM

Для примера выше `SkillRegistry` сгенерирует примерно такую схему:

```json
{
  "type": "function",
  "function": {
    "name": "disk_space",
    "description": "Сообщить свободное место на диске.",
    "parameters": {
      "type": "object",
      "properties": {"path": {"type": "string", "default": "C:\\"}},
      "required": []
    }
  }
}
```

Модель может вернуть `{"name": "disk_space", "arguments": {"path": "D:\\"}}`.
Ядро проверит аргументы через `DiskArgs.model_validate`; при ошибке — откат к
текстовому ответу без исключения. Стриминг для tool call не используется.

## 8. Чего избегать

- **Один мега-навык** на все команды: ломает тесты и tool-схемы.
- **Сеть в `extract_args`**: роутер должен быть быстрым и офлайн.
- **Исключения наружу**: ядро поймает, но пользователь получит неинформативный
  ответ; лучше вернуть `SkillResult.failure` с понятной фразой.
- **Хардкод `C:\Users\<имя>`**: используйте `Path.home()`, конфиг или `data_dir`.
- **Прямой `print`**: используйте `logger` и результат навыка.
