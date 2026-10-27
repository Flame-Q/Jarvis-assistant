"""Power actions with mandatory voice confirmation."""

from __future__ import annotations

import ctypes
import subprocess
from typing import Literal

from pydantic import BaseModel

from jarvis.core.models import SkillResult
from jarvis.skills.base import BaseSkill, normalize_text

CREATE_NO_WINDOW = 0x08000000


class SystemArgs(BaseModel):
    action: Literal["lock", "shutdown", "reboot", "cancel"] = "lock"


class SystemSkill(BaseSkill):
    name = "system"
    description = "Заблокировать, выключить или перезагрузить компьютер."
    examples = ["заблокируй компьютер", "выключи компьютер"]
    triggers = [
        "заблокируй",
        "блокировка",
        "выключи компьютер",
        "перезагрузи",
        "перезагрузка",
        "отмени выключение",
    ]
    args_model: type[BaseModel] = SystemArgs
    requires_confirmation = True

    def extract_args(self, text: str) -> SystemArgs:
        normalized = normalize_text(text)
        if "отмени" in normalized:
            return SystemArgs(action="cancel")
        if "перезагруз" in normalized:
            return SystemArgs(action="reboot")
        if "выключ" in normalized:
            return SystemArgs(action="shutdown")
        return SystemArgs(action="lock")

    def needs_confirmation(self, args: BaseModel) -> bool:
        assert isinstance(args, SystemArgs)
        return args.action in {"shutdown", "reboot"}

    def confirmation_prompt(self, args: BaseModel) -> str:
        assert isinstance(args, SystemArgs)
        if args.action == "reboot":
            return "Перезагрузить компьютер? Скажите да или нет."
        if args.action == "shutdown":
            return "Выключить компьютер? Скажите да или нет."
        return "Подтвердите действие."

    def execute(self, args: BaseModel) -> SkillResult:
        assert isinstance(args, SystemArgs)
        if args.action == "lock":
            try:
                ctypes.windll.user32.LockWorkStation()
            except Exception as exc:
                return SkillResult.failure(f"Не удалось заблокировать: {exc}")
            return SkillResult.success("Блокирую компьютер.")

        if args.action == "cancel":
            subprocess.run(
                ["shutdown", "/a"], capture_output=True, creationflags=CREATE_NO_WINDOW
            )
            return SkillResult.success("Выключение отменено.")

        flag = "/r" if args.action == "reboot" else "/s"
        subprocess.run(
            ["shutdown", flag, "/t", "60", "/c", "Jarvis: выключение через минуту"],
            capture_output=True,
            creationflags=CREATE_NO_WINDOW,
        )
        action = "перезагрузку" if args.action == "reboot" else "выключение"
        return SkillResult.success(f"Запускаю {action} через минуту. Скажите «отмени выключение», чтобы отменить.")
