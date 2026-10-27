"""Optional sound playback helpers used outside TTS (beeps, alerts)."""

from __future__ import annotations

from pathlib import Path


def beep(frequency: int = 880, duration_ms: int = 120) -> None:
    try:
        import winsound

        winsound.Beep(frequency, duration_ms)
    except Exception:  # pragma: no cover - non-Windows / no device
        pass


def play_file(path: Path) -> bool:
    if not path.is_file():
        return False
    try:
        import winsound

        winsound.PlaySound(str(path), winsound.SND_FILENAME)
        return True
    except Exception:  # pragma: no cover
        return False
