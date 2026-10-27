"""Windows application index: Start Menu shortcuts + UWP/desktop AppIDs.

The index is built once and cached in ``data/apps.json`` so the assistant can
resolve "открой <любая программа>" without hardcoded executable paths.
"""

from __future__ import annotations

import json
import os
import subprocess
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from loguru import logger
from rapidfuzz import fuzz, process

from jarvis.skills.base import normalize_text

CREATE_NO_WINDOW = 0x08000000
CACHE_TTL_S = 24 * 60 * 60


@dataclass(slots=True)
class AppEntry:
    name: str
    target: str
    kind: str  # lnk | appid | path


def _start_menu_dirs() -> list[Path]:
    dirs = []
    appdata = os.environ.get("APPDATA")
    programdata = os.environ.get("PROGRAMDATA")
    if appdata:
        dirs.append(Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs")
    if programdata:
        dirs.append(Path(programdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs")
    return [path for path in dirs if path.is_dir()]


class AppsIndex:
    def __init__(self, cache_path: Path) -> None:
        self._cache_path = cache_path
        self._entries: dict[str, AppEntry] | None = None

    def entries(self, refresh: bool = False) -> dict[str, AppEntry]:
        if self._entries is not None and not refresh:
            return self._entries
        if not refresh:
            cached = self._load_cache()
            if cached is not None:
                self._entries = cached
                return cached
        self._entries = self._build()
        self._save_cache(self._entries)
        return self._entries

    def refresh(self) -> int:
        self.entries(refresh=True)
        return len(self._entries or {})

    def find(self, query: str) -> AppEntry | None:
        entries = self.entries()
        key = normalize_text(query)
        if not key:
            return None
        if key in entries:
            return entries[key]

        best = process.extractOne(
            key, list(entries.keys()), scorer=fuzz.WRatio, score_cutoff=80
        )
        if best is None:
            return None
        return entries[best[0]]

    def suggestions(self, query: str, limit: int = 3) -> list[str]:
        entries = self.entries()
        key = normalize_text(query)
        matches = process.extract(key, list(entries.keys()), scorer=fuzz.WRatio, limit=limit)
        return [entries[name].name for name, score, _ in matches if score >= 55]

    def _build(self) -> dict[str, AppEntry]:
        result: dict[str, AppEntry] = {}
        for directory in _start_menu_dirs():
            try:
                for shortcut in directory.rglob("*.lnk"):
                    name = shortcut.stem
                    result.setdefault(normalize_text(name), AppEntry(name, str(shortcut), "lnk"))
            except OSError:
                logger.warning("Cannot scan Start Menu directory {}", directory)

        for name, app_id in self._start_apps():
            result.setdefault(normalize_text(name), AppEntry(name, app_id, "appid"))

        logger.info("Application index built: {} entries", len(result))
        return result

    def _start_apps(self) -> list[tuple[str, str]]:
        if os.name != "nt":
            return []
        script = (
            "[Console]::OutputEncoding=[Text.Encoding]::UTF8; "
            "Get-StartApps | ConvertTo-Json -Compress"
        )
        try:
            completed = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=25,
                creationflags=CREATE_NO_WINDOW,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            logger.warning("Get-StartApps failed: {}", exc)
            return []

        raw = (completed.stdout or "").strip()
        if not raw:
            return []
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("Cannot parse Get-StartApps output")
            return []
        if isinstance(payload, dict):
            payload = [payload]

        apps: list[tuple[str, str]] = []
        for item in payload:
            name = str(item.get("Name", "")).strip()
            app_id = str(item.get("AppID", "")).strip()
            if name and app_id:
                apps.append((name, app_id))
        return apps

    def _load_cache(self) -> dict[str, AppEntry] | None:
        if not self._cache_path.is_file():
            return None
        try:
            payload = json.loads(self._cache_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if time.time() - float(payload.get("created_at", 0)) > CACHE_TTL_S:
            return None
        entries: dict[str, AppEntry] = {}
        for item in payload.get("entries", []):
            entry = AppEntry(
                name=str(item["name"]), target=str(item["target"]), kind=str(item["kind"])
            )
            entries[normalize_text(entry.name)] = entry
        return entries

    def _save_cache(self, entries: dict[str, AppEntry]) -> None:
        payload = {
            "created_at": time.time(),
            "entries": [asdict(entry) for entry in entries.values()],
        }
        try:
            self._cache_path.parent.mkdir(parents=True, exist_ok=True)
            self._cache_path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except OSError as exc:
            logger.warning("Cannot write apps cache: {}", exc)
