"""Screenshot capture."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from pydantic import BaseModel

from jarvis.core.models import SkillResult
from jarvis.skills.base import BaseSkill


class ScreenshotArgs(BaseModel):
    pass


class ScreenshotSkill(BaseSkill):
    name = "screenshot"
    description = "Сделать снимок экрана и сохранить его в папку data/screenshots."
    examples = ["сделай скриншот", "снимок экрана"]
    triggers = ["скриншот", "снимок экрана", "скрин"]
    args_model: type[BaseModel] = ScreenshotArgs

    def __init__(self, data_dir: Path) -> None:
        self._dir = data_dir / "screenshots"

    def execute(self, args: BaseModel) -> SkillResult:
        self._dir.mkdir(parents=True, exist_ok=True)
        path = self._dir / f"screenshot_{datetime.now():%Y%m%d_%H%M%S}.png"
        try:
            from PIL import ImageGrab

            image = ImageGrab.grab(all_screens=True)
            image.save(path)
        except Exception:
            try:
                import pyautogui

                pyautogui.screenshot(str(path))
            except Exception as exc:
                return SkillResult.failure(f"Не удалось сделать скриншот: {exc}")
        return SkillResult.success(f"Скриншот сохранён: {path.name}.", path=str(path))
