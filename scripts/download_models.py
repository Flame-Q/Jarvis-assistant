"""Pre-download Whisper and wake word models for a fully offline demo."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from jarvis.config import load_config  # noqa: E402


def main() -> int:
    config = load_config(ROOT)
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-whisper", action="store_true")
    args = parser.parse_args()

    if not args.skip_whisper:
        print(f"Скачиваю Whisper '{config.stt.model}' (~480 МБ при первом запуске)...")
        from faster_whisper import WhisperModel

        WhisperModel(
            config.stt.model,
            device=config.stt.device,
            compute_type=config.stt.compute_type,
        )
        print("Whisper готов.")

    print("Скачиваю модель wake word hey_jarvis...")
    import openwakeword

    openwakeword.utils.download_models()
    print("Модель wake word готова.")

    print("\nВсё скачано. Проверка: python scripts/wakeword_check.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
