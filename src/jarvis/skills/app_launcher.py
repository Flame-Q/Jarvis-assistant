"""Open any installed application, folder, site or URI."""

from __future__ import annotations

import os
import re
import shutil
import webbrowser
from pathlib import Path

from loguru import logger
from pydantic import BaseModel

from jarvis.config import AppConfig
from jarvis.core.errors import SkillError
from jarvis.core.models import SkillResult
from jarvis.os_win.aliases import resolve_alias, special_folder
from jarvis.os_win.apps_index import AppsIndex
from jarvis.os_win.uwp import launch_discord, launch_entry, open_target
from jarvis.skills.base import BaseSkill, normalize_text

_DOMAIN_RE = re.compile(r"^[a-z0-9-]+(\.[a-z0-9-]+)+$")
_FILLERS = ("программу", "приложение", "мне", "пожалуйста", "быстро")


class AppLaunchArgs(BaseModel):
    target: str = ""


class RefreshAppsArgs(BaseModel):
    pass


class RefreshAppsSkill(BaseSkill):
    name = "refresh_apps"
    description = "Обновить кэш списка установленных программ."
    examples = ["обнови список программ"]
    triggers = ["обнови список программ", "обновить список программ", "обнови программы"]
    args_model: type[BaseModel] = RefreshAppsArgs

    def __init__(self, index: AppsIndex) -> None:
        self._index = index

    def execute(self, args: BaseModel) -> SkillResult:
        count = self._index.refresh()
        return SkillResult.success(f"Список программ обновлён, найдено {count} приложений.")


class AppLauncherSkill(BaseSkill):
    name = "app_launcher"
    description = "Открыть установленную программу, папку или сайт по названию."
    examples = ["открой дискорд", "запусти блокнот", "открой хром", "открой загрузки"]
    triggers = ["открой", "запусти", "открыть", "запустить"]
    args_model: type[BaseModel] = AppLaunchArgs

    def __init__(self, config: AppConfig, index: AppsIndex) -> None:
        self._config = config
        self._index = index

    def extract_args(self, text: str) -> AppLaunchArgs:
        value = normalize_text(text)
        for trigger in sorted(self.triggers, key=len, reverse=True):
            if value.startswith(trigger + " "):
                value = value[len(trigger) + 1 :]
                break
        words = [word for word in value.split() if word not in _FILLERS]
        return AppLaunchArgs(target=" ".join(words).strip())

    def execute(self, args: BaseModel) -> SkillResult:
        assert isinstance(args, AppLaunchArgs)
        target = args.target.strip()
        if not target:
            return SkillResult.failure("Что именно открыть?")

        folder = special_folder(target)
        if folder:
            open_target(folder)
            return SkillResult.success(f"Открываю папку {target}.")

        if target.startswith(("http://", "https://")):
            webbrowser.open(target)
            return SkillResult.success("Открываю сайт.")

        url = self._as_url(target)
        if url:
            webbrowser.open(url)
            return SkillResult.success(f"Открываю {target}.")

        alias = resolve_alias(target, self._config.skills.aliases)
        if alias is not None:
            alias_name, alias_value = alias
            logger.info("Alias resolved: {} -> {}", alias_name, alias_value)
            return self._launch_value(alias_value, original=target)

        return self._launch_value(target, original=target)

    def _launch_value(self, value: str, *, original: str) -> SkillResult:
        try:
            if value.startswith(("http://", "https://")) or "://" in value:
                open_target(value)
                return SkillResult.success(f"Открываю {original}.")

            executable = shutil.which(value)

            entry = self._index.find(value)
            if entry is not None:
                launch_entry(entry)
                logger.info("Launched {} -> {} ({})", original, entry.name, entry.kind)
                return SkillResult.success(f"Открываю {entry.name}.")

            if executable:
                os.startfile(executable)
                return SkillResult.success(f"Открываю {original}.")

            if normalize_text(value) in {"discord", "дискорд"} and launch_discord():
                return SkillResult.success("Открываю Discord.")

            path = Path(value).expanduser()
            if path.exists():
                os.startfile(str(path))
                return SkillResult.success(f"Открываю {original}.")

        except SkillError as exc:
            return SkillResult.failure(str(exc))
        except OSError as exc:
            logger.warning("Launch failed for {}: {}", value, exc)
            return SkillResult.failure(f"Не удалось открыть {original}: {exc}")

        suggestions = self._index.suggestions(original)
        hint = ""
        if suggestions:
            hint = " Возможно, вы имели в виду: " + ", ".join(suggestions) + "."
        return SkillResult.failure(f"Не нашёл программу {original}.{hint}")

    @staticmethod
    def _as_url(target: str) -> str | None:
        candidate = target.strip().lower()
        if _DOMAIN_RE.fullmatch(candidate) and not candidate.endswith(".exe"):
            return f"https://{candidate}"
        return None
