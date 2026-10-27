"""Launch helpers for Windows shortcuts, AppIDs and URIs."""

from __future__ import annotations

import os
import subprocess
import webbrowser
from pathlib import Path

from loguru import logger

from jarvis.core.errors import SkillError
from jarvis.os_win.apps_index import CREATE_NO_WINDOW, AppEntry


def launch_entry(entry: AppEntry) -> None:
    if entry.kind == "appid":
        subprocess.Popen(
            ["explorer.exe", f"shell:AppsFolder\\{entry.target}"],
            creationflags=CREATE_NO_WINDOW,
        )
        return
    if entry.kind in {"lnk", "path"}:
        os.startfile(entry.target)
        return
    subprocess.Popen([entry.target], creationflags=CREATE_NO_WINDOW)


def open_target(target: str) -> None:
    """Open a URI, URL or file with the shell."""

    if target.startswith(("http://", "https://")):
        webbrowser.open(target)
        return
    if "://" in target:
        os.startfile(target)
        return
    path = Path(target).expanduser()
    if path.exists():
        os.startfile(str(path))
        return
    raise SkillError(f"Цель не найдена: {target}")


def launch_discord() -> bool:
    """Fallback for Discord: its exe lives in a versioned folder."""

    local_appdata = os.environ.get("LOCALAPPDATA")
    if not local_appdata:
        return False
    update = Path(local_appdata) / "Discord" / "Update.exe"
    if not update.is_file():
        return False
    subprocess.Popen(
        [str(update), "--processStart", "Discord.exe"], creationflags=CREATE_NO_WINDOW
    )
    logger.info("Discord launched via Update.exe")
    return True
