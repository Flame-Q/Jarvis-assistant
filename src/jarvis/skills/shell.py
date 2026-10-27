"""Controlled PowerShell execution (disabled by default)."""

from __future__ import annotations

import subprocess

from pydantic import BaseModel

from jarvis.config import AppConfig
from jarvis.core.models import SkillResult
from jarvis.skills.base import BaseSkill, normalize_text, strip_triggers

CREATE_NO_WINDOW = 0x08000000
TIMEOUT_S = 20

WHITELIST = (
    "ipconfig",
    "systeminfo",
    "whoami",
    "dir",
    "echo",
    "ping",
    "get-process",
    "get-date",
    "get-service",
    "tasklist",
    "ver",
    "hostname",
)

BLACKLIST = (
    "format",
    "rd /s",
    "rmdir /s",
    "del /f",
    "diskpart",
    "remove-item -recurse",
    "shutdown",
    "restart-computer",
    "stop-computer",
    "invoke-expression",
    "iex",
    "reg delete",
)


class ShellArgs(BaseModel):
    command: str = ""


class ShellSkill(BaseSkill):
    name = "shell"
    description = "Выполнить безопасную команду PowerShell из белого списка."
    examples = ["выполни команду ipconfig", "покажи ipconfig"]
    triggers = ["выполни команду", "запусти в терминале", "команда"]
    args_model: type[BaseModel] = ShellArgs
    requires_confirmation = True

    def __init__(self, config: AppConfig) -> None:
        self._enabled = config.skills.shell_enabled

    def extract_args(self, text: str) -> ShellArgs:
        value = strip_triggers(text, self.triggers)
        return ShellArgs(command=normalize_text(value))

    def execute(self, args: BaseModel) -> SkillResult:
        assert isinstance(args, ShellArgs)
        if not self._enabled:
            return SkillResult.failure(
                "Навык shell отключён. Включите skills.shell_enabled в config.toml."
            )
        command = args.command.strip()
        if not command:
            return SkillResult.failure("Какую команду выполнить?")
        lowered = command.lower()
        if any(bad in lowered for bad in BLACKLIST):
            return SkillResult.failure("Эта команда запрещена.")
        if not any(lowered.startswith(prefix) for prefix in WHITELIST):
            return SkillResult.failure("Команда не входит в белый список.")
        try:
            completed = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", command],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=TIMEOUT_S,
                creationflags=CREATE_NO_WINDOW,
            )
        except subprocess.TimeoutExpired:
            return SkillResult.failure("Команда выполнялась слишком долго.")
        output = (completed.stdout or completed.stderr or "").strip()
        if len(output) > 400:
            output = output[:400] + "..."
        return SkillResult(
            ok=completed.returncode == 0,
            text=output or "Команда выполнена без вывода.",
        )
