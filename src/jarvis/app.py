"""Application wiring and CLI entry point."""

from __future__ import annotations

import argparse
import os
import sys
import threading
from dataclasses import dataclass
from pathlib import Path

from loguru import logger

from jarvis.audio.loop import VoiceLoop
from jarvis.config import AppConfig, load_config
from jarvis.core.assistant import AssistantService
from jarvis.core.events import EventBus
from jarvis.core.fsm import AssistantFSM
from jarvis.core.registry import SkillRegistry
from jarvis.core.router import IntentRouter
from jarvis.logging_setup import setup_logging
from jarvis.os_win.apps_index import AppsIndex
from jarvis.providers.llm.base import LLMProvider
from jarvis.providers.llm.ollama import OllamaProvider
from jarvis.providers.stt.base import STTProvider
from jarvis.providers.stt.whisper import WhisperSTT
from jarvis.providers.tts.base import TTSProvider
from jarvis.providers.tts.pyttsx3_tts import Pyttsx3TTS
from jarvis.skills.app_launcher import AppLauncherSkill, RefreshAppsSkill
from jarvis.skills.chat import ChatSkill
from jarvis.skills.control import ControlSkill
from jarvis.skills.notes import NotesSkill
from jarvis.skills.screenshot import ScreenshotSkill
from jarvis.skills.search_web import SearchWebSkill
from jarvis.skills.shell import ShellSkill
from jarvis.skills.system import SystemSkill
from jarvis.skills.time_date import TimeDateSkill
from jarvis.skills.timer import TimerSkill
from jarvis.skills.volume import VolumeSkill
from jarvis.skills.weather import WeatherSkill
from jarvis.storage.db import Database
from jarvis.storage.repositories import (
    CommandRepository,
    HistoryRepository,
    NotesRepository,
    TimerRepository,
)

BANNER = """
+--------------------------------------------------------------+
|   J A R V I S   -   голосовой ассистент (локальный, офлайн)   |
+--------------------------------------------------------------+
"""


@dataclass
class Services:
    root: Path
    config: AppConfig
    db: Database
    bus: EventBus
    fsm: AssistantFSM
    registry: SkillRegistry
    router: IntentRouter
    assistant: AssistantService
    tts: TTSProvider
    stt: STTProvider
    llm: LLMProvider
    history: HistoryRepository
    commands: CommandRepository
    notes: NotesRepository
    timers: TimerRepository
    shutdown_event: threading.Event
    voice: VoiceLoop | None = None


def find_root(start: Path | None = None) -> Path:
    candidate = start or Path.cwd()
    if (candidate / "config").is_dir() or (candidate / "src" / "jarvis").is_dir():
        return candidate
    module_root = Path(__file__).resolve().parents[2]
    if (module_root / "config").is_dir():
        return module_root
    return candidate


def build_services(config: AppConfig, root: Path) -> Services:
    data_dir = config.data_path(root)
    db = Database(data_dir / "jarvis.db")
    history = HistoryRepository(db)
    commands = CommandRepository(db)
    notes = NotesRepository(db)
    timers = TimerRepository(db)

    bus = EventBus()
    fsm = AssistantFSM(bus)
    tts = _build_tts(config)
    stt = WhisperSTT(config.stt)
    llm = OllamaProvider(config.llm)
    chat = ChatSkill(config, llm, history)

    registry = SkillRegistry()
    index = AppsIndex(data_dir / "apps.json")
    shutdown_event = threading.Event()

    # Registration order matters only for equal scores: the launcher is first
    # so "открой ютуб" launches the app instead of a web search.
    registry.register(AppLauncherSkill(config, index))
    registry.register(RefreshAppsSkill(index))
    registry.register(TimerSkill(tts.speak, timers))
    registry.register(VolumeSkill())
    registry.register(TimeDateSkill())
    registry.register(ScreenshotSkill(data_dir))
    registry.register(WeatherSkill(config))
    registry.register(SearchWebSkill())
    registry.register(NotesSkill(notes))
    registry.register(SystemSkill())
    registry.register(ControlSkill(tts, shutdown_event.set))
    registry.register(ShellSkill(config))

    router = IntentRouter(registry)
    assistant = AssistantService(
        config=config,
        bus=bus,
        fsm=fsm,
        registry=registry,
        router=router,
        chat=chat,
        tts=tts,
        llm=llm,
        history=history,
        commands=commands,
    )

    return Services(
        root=root,
        config=config,
        db=db,
        bus=bus,
        fsm=fsm,
        registry=registry,
        router=router,
        assistant=assistant,
        tts=tts,
        stt=stt,
        llm=llm,
        history=history,
        commands=commands,
        notes=notes,
        timers=timers,
        shutdown_event=shutdown_event,
    )


def _build_tts(config: AppConfig) -> TTSProvider:
    provider = config.tts.provider.strip().lower()
    if provider == "edge":
        try:
            from jarvis.providers.tts.edge_tts_provider import EdgeTTS

            edge = EdgeTTS(config.tts)
            if edge.available:
                return edge
        except Exception as exc:
            logger.warning("edge-tts is not available: {}", exc)
        logger.warning("Falling back to offline Windows SAPI5")

    # ``pyttsx3`` remains accepted as a compatibility alias: older generated
    # configs should get the working SAPI5 implementation without manual edits.
    if provider in {"sapi5", "pyttsx3", "auto"}:
        try:
            from jarvis.providers.tts.sapi5_tts import Sapi5TTS

            sapi = Sapi5TTS(config.tts)
            if sapi.available:
                return sapi
            logger.warning("Windows SAPI5 TTS is unavailable")
        except Exception as exc:
            logger.warning("Windows SAPI5 TTS failed to start: {}", exc)

    logger.warning("Falling back to legacy pyttsx3 TTS")
    return Pyttsx3TTS(config.tts)


def _check_llm(services: Services) -> None:
    config = services.config
    if not services.llm.health():
        logger.warning(
            "Ollama is not reachable at {}. Chat is disabled, commands still work.",
            config.llm.base_url,
        )
        return
    try:
        models_fn = getattr(services.llm, "models", None)
        models = models_fn() if callable(models_fn) else []
    except Exception:
        models = []
    if models and not any(config.llm.model in name for name in models):
        logger.warning(
            "Model '{}' is not installed. Run: ollama pull {}", config.llm.model, config.llm.model
        )
        return
    logger.info("LLM ready: {} via Ollama", config.llm.model)


def _warmup(services: Services) -> None:
    if services.llm.health():
        threading.Thread(target=services.llm.warmup, daemon=True).start()


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="jarvis", description="Jarvis voice assistant")
    parser.add_argument("--config", type=Path, default=None, help="path to config.toml")
    parser.add_argument("--once", type=str, default=None, help="process one command and exit")
    parser.add_argument("--text", action="store_true", help="text only, no microphone")
    parser.add_argument("--voice", action="store_true", help="force voice mode")
    parser.add_argument("--tray", action="store_true", help="run in system tray")
    parser.add_argument("--no-greeting", action="store_true", help="do not speak on startup")
    parser.add_argument("--log-level", type=str, default=None)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    root = find_root()
    config = load_config(root, args.config)
    if args.log_level:
        config.logging.level = args.log_level.upper()

    src = root / "src"
    if src.is_dir() and str(src) not in sys.path:
        sys.path.insert(0, str(src))

    setup_logging(config.logging, config.data_path(root))
    if sys.platform == "win32":
        try:
            for stream in (sys.stdout, sys.stderr):
                reconfigure = getattr(stream, "reconfigure", None)
                if callable(reconfigure):
                    reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, OSError):  # pragma: no cover - redirected streams
            pass
    print(BANNER)

    services = build_services(config, root)
    _check_llm(services)

    if args.once:
        result = services.assistant.handle_text(args.once)
        print(f"Джарвис: {result.text}")
        _wait_for_tts(services)
        _shutdown(services)
        return 0 if result.ok else 1

    use_voice = not args.text
    if use_voice:
        services.voice = VoiceLoop(
            config=config,
            assistant=services.assistant,
            stt=services.stt,
            tts=services.tts,
            bus=services.bus,
        )
        if not services.voice.start():
            services.voice = None

    status = "готов" if services.assistant.llm_available() else "без чата (Ollama недоступна)"
    print(f"Статус: {status}. Модель: {config.llm.model}")
    if services.voice is not None:
        manual = config.assistant.manual_hotkey
        button = "кнопку «Говорить»"
        if manual:
            button += f" ({manual})"
        if config.assistant.wake_word_enabled:
            print(
                "Голос: включён. Скажите «хей, Джарвис», нажмите "
                f"{config.assistant.hotkey} или {button}."
            )
        else:
            if manual:
                activation = f"Нажмите {manual} или кнопку «Говорить»."
            else:
                activation = "Откройте трей и нажмите кнопку «Говорить»."
            print(f"Голос: включён (wake word выключен). {activation}")
    else:
        print("Голос: выключен (текстовый режим).")
    print("Напишите команду и нажмите Enter. Для выхода: выход или Ctrl+C.\n")

    if not args.no_greeting and services.tts.available:
        services.tts.speak("Джарвис на связи.")

    _start_shutdown_watcher(services)

    if args.tray:
        try:
            from jarvis.ui.tray import run_tray

            _warmup(services)
            return run_tray(services, on_quit=lambda: _shutdown(services))
        except Exception as exc:
            logger.error("Tray is unavailable: {}", exc)
            print(f"Трей недоступен: {exc}. Запускаю консольный режим.")

    _warmup(services)
    try:
        while True:
            try:
                line = input("Вы: ").strip()
            except EOFError:
                break
            if not line:
                continue
            if line.lower() in {"выход", "quit", "exit"}:
                break
            result = services.assistant.handle_text(line)
            if result.text:
                print(f"Джарвис: {result.text}\n")
    except KeyboardInterrupt:
        print()
    finally:
        if not args.no_greeting and services.tts.available:
            services.tts.speak("До встречи.")
        _wait_for_tts(services)
        _shutdown(services)
    return 0


def _wait_for_tts(services: Services) -> None:
    """Wait for queued speech before leaving a one-shot/console session."""

    wait = getattr(services.tts, "wait", None)
    if services.tts.available and callable(wait):
        try:
            wait()
        except Exception:  # pragma: no cover - provider-specific shutdown
            logger.exception("Cannot wait for TTS")


def _start_shutdown_watcher(services: Services) -> None:
    """Allow the voice command «заверши работу» to stop the whole app."""

    def watch() -> None:
        services.shutdown_event.wait()
        logger.info("Shutdown requested by voice")
        try:
            _shutdown(services)
        finally:
            os._exit(0)

    threading.Thread(target=watch, name="shutdown-watcher", daemon=True).start()


def _shutdown(services: Services) -> None:
    if services.voice is not None:
        services.voice.stop()
    try:
        services.tts.close()
    except Exception:  # pragma: no cover
        pass
    try:
        services.llm.close()
    except Exception:  # pragma: no cover
        pass
    services.db.close()
    logger.info("Jarvis stopped")
