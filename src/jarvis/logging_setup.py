"""Logging setup based on loguru."""

from __future__ import annotations

import sys
from pathlib import Path

from loguru import logger

from jarvis.config import LoggingSettings

LOG_FORMAT = (
    "<green>{time:HH:mm:ss.SSS}</green> | <level>{level: <8}</level> | "
    "<cyan>{name}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>"
)


def setup_logging(settings: LoggingSettings, data_dir: Path) -> None:
    """Configure console and rotating file sinks. Safe to call twice."""

    logger.remove()
    logger.add(sys.stderr, level=settings.level, format=LOG_FORMAT, colorize=True)

    log_path = Path(settings.file)
    if not log_path.is_absolute():
        log_path = data_dir / log_path.name
    log_path.parent.mkdir(parents=True, exist_ok=True)
    logger.add(
        log_path,
        level=settings.level,
        format=LOG_FORMAT,
        encoding="utf-8",
        rotation="5 MB",
        retention=3,
        enqueue=True,
    )
