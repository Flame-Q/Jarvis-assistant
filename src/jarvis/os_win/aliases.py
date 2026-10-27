"""Alias resolution for application and site names."""

from __future__ import annotations

from rapidfuzz import fuzz, process

from jarvis.skills.base import normalize_text


def resolve_alias(target: str, aliases: dict[str, str]) -> tuple[str, str] | None:
    """Return ``(alias, value)`` for an exact or fuzzy alias match."""

    key = normalize_text(target)
    if not key or not aliases:
        return None

    normalized = {normalize_text(alias): (alias, value) for alias, value in aliases.items()}
    if key in normalized:
        return normalized[key]

    best = process.extractOne(key, list(normalized), scorer=fuzz.WRatio, score_cutoff=80)
    if best is None:
        return None
    return normalized[best[0]]


def special_folder(name: str) -> str | None:
    from pathlib import Path

    key = normalize_text(name)
    home = Path.home()
    folders = {
        "загрузки": home / "Downloads",
        "downloads": home / "Downloads",
        "документы": home / "Documents",
        "музыка": home / "Music",
        "видео": home / "Videos",
        "картинки": home / "Pictures",
        "изображения": home / "Pictures",
        "рабочий стол": home / "Desktop",
    }
    path = folders.get(key)
    return str(path) if path is not None else None
