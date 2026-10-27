"""System volume control through pycaw."""

from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel

from jarvis.core.models import SkillResult
from jarvis.skills.base import BaseSkill, normalize_text

_PERCENT_RE = re.compile(r"(\d{1,3})")


class VolumeArgs(BaseModel):
    action: Literal["set", "up", "down", "mute", "unmute"] = "set"
    value: int = 0


def _endpoint_volume() -> Any:
    from comtypes import CLSCTX_ALL
    from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume

    speakers = AudioUtilities.GetSpeakers()
    endpoint = getattr(speakers, "EndpointVolume", None)
    if endpoint is not None:
        return endpoint
    interface = speakers.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
    return interface.QueryInterface(IAudioEndpointVolume)


class VolumeSkill(BaseSkill):
    name = "volume"
    description = "Изменить громкость, включить или выключить звук."
    examples = ["громкость 30", "сделай громче", "выключи звук"]
    triggers = ["громкость", "звук", "громче", "тише", "погромче", "потише"]
    args_model: type[BaseModel] = VolumeArgs

    def extract_args(self, text: str) -> VolumeArgs:
        normalized = normalize_text(text)
        if any(word in normalized for word in ("выключи звук", "без звука", "замолчи")):
            return VolumeArgs(action="mute")
        if any(word in normalized for word in ("включи звук", "верни звук")):
            return VolumeArgs(action="unmute")
        if "громче" in normalized:
            return VolumeArgs(action="up", value=10)
        if "тише" in normalized:
            return VolumeArgs(action="down", value=10)
        match = _PERCENT_RE.search(normalized)
        if match:
            return VolumeArgs(action="set", value=max(0, min(100, int(match.group(1)))))
        return VolumeArgs(action="set", value=50)

    def execute(self, args: BaseModel) -> SkillResult:
        assert isinstance(args, VolumeArgs)
        try:
            volume = _endpoint_volume()
            if args.action == "mute":
                volume.SetMute(1, None)
                return SkillResult.success("Звук выключен.")
            if args.action == "unmute":
                volume.SetMute(0, None)
                return SkillResult.success("Звук включён.")

            current = float(volume.GetMasterVolumeLevelScalar())
            if args.action == "up":
                target = min(1.0, current + args.value / 100)
            elif args.action == "down":
                target = max(0.0, current - args.value / 100)
            else:
                target = max(0.0, min(1.0, args.value / 100))

            volume.SetMasterVolumeLevelScalar(target, None)
            if target > 0:
                volume.SetMute(0, None)
            return SkillResult.success(f"Громкость {round(target * 100)} процентов.")
        except Exception as exc:
            return SkillResult.failure(f"Не удалось изменить громкость: {exc}")
