"""Voice control commands: stop speaking and shut the assistant down (FR-9)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Literal

from pydantic import BaseModel

from jarvis.core.models import SkillResult
from jarvis.providers.tts.base import TTSProvider
from jarvis.skills.base import BaseSkill, normalize_text


class ControlArgs(BaseModel):
    action: Literal["stop", "shutdown"] = "stop"


class ControlSkill(BaseSkill):
    name = "control"
    description = "Остановить речь или завершить работу ассистента."
    examples = ["стоп", "хватит", "заверши работу"]
    triggers = ["стоп", "хватит", "заверши работу", "выключись", "остановись"]
    args_model: type[BaseModel] = ControlArgs

    def __init__(self, tts: TTSProvider, on_shutdown: Callable[[], None]) -> None:
        self._tts = tts
        self._on_shutdown = on_shutdown

    def extract_args(self, text: str) -> ControlArgs:
        normalized = normalize_text(text)
        if any(word in normalized for word in ("заверши", "выключись", "выход")):
            return ControlArgs(action="shutdown")
        return ControlArgs(action="stop")

    def execute(self, args: BaseModel) -> SkillResult:
        assert isinstance(args, ControlArgs)
        self._tts.stop()
        if args.action == "shutdown":
            self._on_shutdown()
            return SkillResult(
                ok=True, text="Завершаю работу. До встречи.", speak=True
            )
        return SkillResult(ok=True, text="Остановил.", speak=False)
